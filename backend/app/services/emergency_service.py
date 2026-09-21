"""Emergency & SOS service (Phase 7).

SAFETY RULES:
- SOS never depends on AI and never blocks on integrations.
- The state machine below is the ONLY way event status changes; clients can
  never set status directly.
- Ambulance dispatch, hospital acceptance, notification delivery, and call
  connection are reported truthfully: NOT_CONFIGURED / NOT_VERIFIED / FAILED
  instead of invented success.
- Emergency medical data is minimum-necessary: only fields the patient
  explicitly provided; missing values are UNKNOWN.
"""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.emergency import (
    ACTIVE_SOS_STATUSES,
    CANCEL_REASONS,
    EMERGENCY_TYPES,
    HANDOFF_STATUSES,
    NOTIFICATION_CHANNELS,
    EmergencyContact,
    EmergencyEvent,
    EmergencyHandoff,
    EmergencyNotification,
    EmergencyProfile,
    EmergencyProviderEvent,
)
from app.models.family import FamilyRelationship
from app.models.ops import AuditLog
from app.models.user import User, new_uuid


class EmergencyError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- state machine

ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "REQUESTED": ("ALERTING", "HANDOFF_PENDING", "CANCELLED", "FALSE_ALARM", "FAILED"),
    "ALERTING": ("CONTACTING", "HANDOFF_PENDING", "CANCELLED", "FALSE_ALARM", "FAILED"),
    "CONTACTING": ("ACTIVE", "HANDOFF_PENDING", "CANCELLED", "FALSE_ALARM", "FAILED"),
    "ACTIVE": ("HANDOFF_PENDING", "RESOLVED", "CANCELLED"),
    "HANDOFF_PENDING": ("HANDED_OFF", "FAILED"),
    "HANDED_OFF": ("RESOLVED",),
    # Terminals
    "CANCELLED": (),
    "FALSE_ALARM": (),
    "RESOLVED": (),
    "FAILED": (),
}

CANCELABLE_STATUSES = ("REQUESTED", "ALERTING", "CONTACTING", "ACTIVE")


def transition(db: Session, event: EmergencyEvent, new_status: str, *, actor) -> EmergencyEvent:
    """Apply a state-machine transition or raise 409. Audited by callers."""
    allowed = ALLOWED_TRANSITIONS.get(event.status, ())
    if new_status not in allowed:
        raise EmergencyError(
            f"Invalid transition {event.status} -> {new_status}", 409
        )
    event.status = new_status
    if new_status == "CANCELLED":
        event.cancelled_at = datetime.now(UTC)
    if new_status == "RESOLVED":
        event.resolved_at = datetime.now(UTC)
        event.resolved_by_user_id = actor.id if actor is not None else None
    return event


def is_terminal(status: str) -> bool:
    return not ALLOWED_TRANSITIONS.get(status)


def _audit(
    db: Session,
    *,
    actor_user_id: str | None,
    action: str,
    resource_id: str,
    detail: str = "",
    outcome: str = "SUCCESS",
    correlation_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_role=None,
            action=action,
            resource_type="emergency",
            resource_id=resource_id,
            outcome=outcome,
            detail=(f"correlation={correlation_id} " if correlation_id else "") + detail[:500],
        )
    )


# ----------------------------------------------------------------- SOS create

def create_sos(
    db: Session,
    *,
    patient,
    note: str = "",
    emergency_type: str = "MEDICAL",
    latitude: str | None = None,
    longitude: str | None = None,
    location_accuracy_m: str | None = None,
    location_timestamp: datetime | None = None,
    network_status: str | None = None,
    device_platform: str | None = None,
    idempotency_key: str | None = None,
    initiated_by=None,
) -> tuple[EmergencyEvent, bool]:
    """Create an SOS event. Returns (event, created).

    Honesty + safety behaviour:
    - Same user + same idempotency key -> the SAME event is returned (200),
      protected by a partial unique index (race-safe on concurrent requests).
    - Without a key, a patient with an existing non-terminal SOS gets that
      event back — legitimate retries are never rejected.
    - Location is stored only when provided; the timestamp records what the
      device actually supplied.
    """
    if emergency_type not in EMERGENCY_TYPES:
        raise EmergencyError(f"emergency_type must be one of: {', '.join(EMERGENCY_TYPES)}", 422)

    actor = initiated_by or patient
    now = datetime.now(UTC)

    if idempotency_key:
        existing = (
            db.query(EmergencyEvent)
            .filter(
                EmergencyEvent.user_id == patient.id,
                EmergencyEvent.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing is not None:
            return existing, False

    active = (
        db.query(EmergencyEvent)
        .filter(
            EmergencyEvent.user_id == patient.id,
            EmergencyEvent.status.in_(ACTIVE_SOS_STATUSES),
        )
        .first()
    )
    if active is not None:
        return active, False

    event = EmergencyEvent(
        user_id=patient.id,
        initiated_by_user_id=actor.id,
        status="REQUESTED",
        emergency_type=emergency_type,
        note=(note or "")[:500],
        latitude=latitude,
        longitude=longitude,
        location_accuracy_m=location_accuracy_m,
        location_timestamp=location_timestamp if (latitude or longitude) else None,
        network_status=(network_status or None),
        device_platform=(device_platform or None)[:40] if device_platform else None,
        idempotency_key=idempotency_key,
        correlation_id=new_uuid(),
        initiated_at=now,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        # Concurrent duplicate (same idempotency key or an active SOS won the
        # race): return the winner instead of failing a legitimate emergency.
        db.rollback()
        if idempotency_key:
            existing = (
                db.query(EmergencyEvent)
                .filter(
                    EmergencyEvent.user_id == patient.id,
                    EmergencyEvent.idempotency_key == idempotency_key,
                )
                .first()
            )
            if existing is not None:
                return existing, False
        active = (
            db.query(EmergencyEvent)
            .filter(
                EmergencyEvent.user_id == patient.id,
                EmergencyEvent.status.in_(ACTIVE_SOS_STATUSES),
            )
            .first()
        )
        if active is not None:
            return active, False
        raise EmergencyError("Could not create SOS event", 500) from None

    _audit(
        db,
        actor_user_id=actor.id,
        action="SOS_CREATED",
        resource_id=event.id,
        detail=(
            f"patient={event.user_id} type={event.emergency_type} "
            f"location={'provided' if (latitude or longitude) else 'not_provided'} "
            f"network={event.network_status or 'unknown'}"
        ),
        correlation_id=event.correlation_id,
    )
    if latitude or longitude:
        _audit(
            db,
            actor_user_id=actor.id,
            action="LOCATION_CAPTURED",
            resource_id=event.id,
            detail="accuracy_aware=true source=client_snapshot",
            correlation_id=event.correlation_id,
        )
    db.commit()
    return event, True


def cancel_sos(
    db: Session,
    *,
    event: EmergencyEvent,
    actor,
    reason: str = "USER_CANCELLED",
) -> EmergencyEvent:
    if reason not in CANCEL_REASONS:
        raise EmergencyError(
            f"reason must be one of: {', '.join(CANCEL_REASONS)}", 422
        )
    if event.status not in CANCELABLE_STATUSES:
        raise EmergencyError(f"Cannot cancel event in status {event.status}", 409)
    target = "FALSE_ALARM" if reason == "FALSE_ALARM" else "CANCELLED"
    transition(db, event, target, actor=actor)
    event.cancel_reason = reason
    _audit(
        db,
        actor_user_id=actor.id,
        action="SOS_FALSE_ALARM" if target == "FALSE_ALARM" else "SOS_CANCELLED",
        resource_id=event.id,
        detail=f"reason={reason}",
        correlation_id=event.correlation_id,
    )
    db.commit()
    return event


def resolve_sos(db: Session, *, event: EmergencyEvent, actor) -> EmergencyEvent:
    # RESOLVED is reachable only from ACTIVE / HANDED_OFF (real engagement);
    # early-stage exits are CANCELLED / FALSE_ALARM per the state machine.
    if event.status not in ("ACTIVE", "HANDED_OFF"):
        raise EmergencyError(
            f"Cannot resolve event in status {event.status} — "
            "cancel or mark false alarm instead",
            409,
        )
    transition(db, event, "RESOLVED", actor=actor)
    _audit(
        db,
        actor_user_id=actor.id,
        action="EMERGENCY_RESOLVED",
        resource_id=event.id,
        correlation_id=event.correlation_id,
    )
    db.commit()
    return event


def get_owned_event(db: Session, event_id: str, user) -> EmergencyEvent | None:
    event = db.get(EmergencyEvent, event_id)
    if event is None or event.user_id != user.id:
        return None
    return event


# ------------------------------------------------------- family/caregiver view

def _active_family_consent(db: Session, owner_id: str, member_id: str, consent_type: str) -> bool:
    """ACTIVE Phase 6 relationship + an active EMERGENCY_* consent granted by
    the owner to that relationship. Re-checked on every access."""
    rel = (
        db.query(FamilyRelationship)
        .filter(
            FamilyRelationship.owner_user_id == owner_id,
            FamilyRelationship.member_user_id == member_id,
            FamilyRelationship.status == "ACTIVE",
        )
        .first()
    )
    if rel is None:
        return False
    from app.models.consent import Consent

    consent = (
        db.query(Consent)
        .filter(
            Consent.user_id == owner_id,
            Consent.consent_type == consent_type,
            Consent.recipient == f"family:{rel.id}",
            Consent.revoked_at.is_(None),
        )
        .first()
    )
    return consent is not None and consent.is_active


def family_alert_allowed(db: Session, *, patient_id: str, member) -> bool:
    """Phase 6 RECEIVE_HEALTH_ALERTS family consent scope."""
    rel = (
        db.query(FamilyRelationship)
        .filter(
            FamilyRelationship.owner_user_id == patient_id,
            FamilyRelationship.member_user_id == member.id,
            FamilyRelationship.status == "ACTIVE",
        )
        .first()
    )
    if rel is None:
        return False
    from app.services import family_service

    consent = family_service.active_consent(db, rel.id)
    return consent is not None and "RECEIVE_HEALTH_ALERTS" in consent.scope_list


def family_summary_allowed(db: Session, *, patient_id: str, member) -> bool:
    return _active_family_consent(
        db, patient_id, member.id, "EMERGENCY_MEDICAL_SUMMARY"
    )


def family_location_allowed(db: Session, *, patient_id: str, member) -> bool:
    return _active_family_consent(db, patient_id, member.id, "EMERGENCY_LOCATION")


def notify_family(db: Session, *, event: EmergencyEvent, patient) -> int:
    """Queue minimum-necessary in-app alerts for family members with the
    RECEIVE_HEALTH_ALERTS scope. Location is included ONLY with an explicit
    EMERGENCY_LOCATION consent. Returns the number notified."""
    rels = (
        db.query(FamilyRelationship)
        .filter(
            FamilyRelationship.owner_user_id == event.user_id,
            FamilyRelationship.status == "ACTIVE",
        )
        .all()
    )
    notified = 0
    for rel in rels:
        member_id = rel.member_user_id
        if member_id is None:
            continue
        member = db.get(User, member_id)
        if member is None:
            continue
        from app.services import family_service

        consent = family_service.active_consent(db, rel.id)
        if consent is None or "RECEIVE_HEALTH_ALERTS" not in consent.scope_list:
            continue
        include_location = family_location_allowed(db, patient_id=event.user_id, member=member)
        db.add(
            EmergencyNotification(
                emergency_event_id=event.id,
                recipient_user_id=member_id,
                channel="IN_APP",
                status="SENT",
                provider_name="in_app",
                sent_at=datetime.now(UTC),
            )
        )
        _audit(
            db,
            actor_user_id=event.user_id,
            action="EMERGENCY_CONTACT_NOTIFIED",
            resource_id=event.id,
            detail=f"channel=IN_APP recipient=family:{member_id} "
            f"location_shared={str(include_location).lower()}",
            correlation_id=event.correlation_id,
        )
        notified += 1
    if notified:
        db.commit()
    return notified


def notify_contacts(db: Session, *, event: EmergencyEvent, patient) -> int:
    """Record notification attempts for the patient's active emergency
    contacts according to their channel preferences — truthfully:
    IN_APP is SENT (this ledger is the inbox); SMS/push/email without a
    configured provider are FAILED provider_not_configured."""
    contacts = (
        db.query(EmergencyContact)
        .filter(
            EmergencyContact.user_id == event.user_id,
            EmergencyContact.active.is_(True),
        )
        .order_by(EmergencyContact.priority.asc())
        .limit(5)
        .all()
    )
    count = 0
    for contact in contacts:
        prefs = [
            c.strip().upper()
            for c in contact.notification_preferences.split(",")
            if c.strip()
        ][:3]
        for channel in prefs:
            if channel not in NOTIFICATION_CHANNELS:
                continue
            provider_available = channel == "IN_APP"  # external providers: not configured yet
            row = EmergencyNotification(
                emergency_event_id=event.id,
                contact_id=contact.id,
                recipient_user_id=None,
                recipient_phone=contact.phone_number,
                channel=channel,
                status="SENT" if provider_available else "FAILED",
                provider_name="in_app" if provider_available else None,
                error_detail=None if provider_available else "provider_not_configured",
                sent_at=datetime.now(UTC) if provider_available else None,
            )
            db.add(row)
            count += 1
        _audit(
            db,
            actor_user_id=event.user_id,
            action="EMERGENCY_CONTACT_NOTIFIED",
            resource_id=event.id,
            detail=f"contact={contact.id} channels={contact.notification_preferences}",
            correlation_id=event.correlation_id,
        )
    if count:
        db.commit()
    return count


def family_alerts_for(db: Session, member) -> list[dict]:
    """Minimum-necessary alert view for a family member. Never includes vault
    content; location only with explicit EMERGENCY_LOCATION consent."""
    rels = (
        db.query(FamilyRelationship)
        .filter(
            FamilyRelationship.member_user_id == member.id,
            FamilyRelationship.status == "ACTIVE",
        )
        .all()
    )
    out: list[dict] = []
    for rel in rels:
        from app.services import family_service

        consent = family_service.active_consent(db, rel.id)
        if consent is None or "RECEIVE_HEALTH_ALERTS" not in consent.scope_list:
            continue
        events = (
            db.query(EmergencyEvent)
            .filter(
                EmergencyEvent.user_id == rel.owner_user_id,
                EmergencyEvent.created_at >= datetime.now(UTC) - timedelta(days=7),
            )
            .order_by(EmergencyEvent.created_at.desc())
            .limit(10)
            .all()
        )
        for event in events:
            patient = db.get(User, event.user_id)
            include_location = family_location_allowed(
                db, patient_id=event.user_id, member=member
            )
            out.append(
                {
                    "event_id": event.id,
                    "patient_name": patient.full_name if patient else "UNKNOWN",
                    "status": event.status,
                    "emergency_type": event.emergency_type,
                    "created_at": event.created_at.isoformat(),
                    "location": (
                        {"latitude": event.latitude, "longitude": event.longitude}
                        if include_location and (event.latitude or event.longitude)
                        else None
                    ),
                    "location_shared": include_location,
                }
            )
    return out


# ---------------------------------------------------------- emergency profile

def get_profile(db: Session, user):
    profile = db.query(EmergencyProfile).filter(EmergencyProfile.user_id == user.id).first()
    if profile is None:
        profile = EmergencyProfile(user_id=user.id)
        db.add(profile)
        db.flush()
    return profile


def update_profile(db: Session, user, payload: dict) -> EmergencyProfile:
    profile = get_profile(db, user)
    allowed = (
        "blood_group",
        "allergies",
        "critical_conditions",
        "critical_medications",
        "emergency_notes",
        "preferred_hospital_id",
        "organ_donor_status",
        "accessibility_needs",
    )
    for key in allowed:
        if key in payload:
            value = payload[key]
            if key == "blood_group" and value is not None:
                value = str(value).strip().upper()[:8] or None
            setattr(profile, key, value)
    db.commit()
    _audit(
        db,
        actor_user_id=user.id,
        action="EMERGENCY_PROFILE_UPDATED",
        resource_id=profile.id,
        detail=f"fields={','.join(sorted(set(payload) & set(allowed))) or 'none'}",
    )
    db.commit()
    return profile


def medical_summary(db: Session, *, event: EmergencyEvent) -> dict:
    """Minimum-necessary emergency summary. Only explicitly provided fields
    appear; anything unknown is literally UNKNOWN — never guessed."""
    profile = (
        db.query(EmergencyProfile)
        .filter(EmergencyProfile.user_id == event.user_id)
        .first()
    )
    def val(field: str | None) -> str:
        return (field or "").strip() or "UNKNOWN"

    allergies = val(profile.allergies if profile else None)
    conditions = val(profile.critical_conditions if profile else None)
    medications = val(profile.critical_medications if profile else None)
    blood_group = val(profile.blood_group if profile else None)
    notes = val(profile.emergency_notes if profile else None)
    return {
        "patient_user_id": event.user_id,
        "blood_group": blood_group,
        "allergies": allergies,
        "critical_conditions": conditions,
        "critical_medications": medications,
        "emergency_notes": notes,
        "location": (
            {"latitude": event.latitude, "longitude": event.longitude}
            if (event.latitude or event.longitude)
            else None
        ),
        "as_of": (profile.updated_at.isoformat() if profile else None),
        "disclaimer": "This information is user-provided and may not be complete.",
    }


# ---------------------------------------------------------- nearby hospitals

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby_emergency_hospitals(
    db: Session, *, lat: float, lng: float, radius_km: float = 25.0, limit: int = 20
) -> list[dict]:
    """Verified hospitals with emergency capability, nearest first.

    HONESTY: only fields that actually exist in the verified hospital record
    are returned. Real-time availability (beds/ICU/doctors on duty/ETA) is
    NOT tracked by this system and is therefore reported as NOT_VERIFIED —
    never invented.
    """
    from app.models.providers import Hospital

    rows = (
        db.query(Hospital)
        .filter(
            Hospital.verification_status == "VERIFIED",
            Hospital.emergency_available.is_(True),
            Hospital.latitude.isnot(None),
            Hospital.longitude.isnot(None),
        )
        .all()
    )
    scored = []
    for h in rows:
        try:
            d = _haversine_km(lat, lng, float(h.latitude), float(h.longitude))
        except (TypeError, ValueError):
            continue
        if d <= radius_km:
            scored.append((d, h))
    scored.sort(key=lambda pair: pair[0])
    return [
        {
            "hospital_id": h.id,
            "name": h.name,
            "city": h.city,
            "distance_km": round(d, 2),
            "emergency_available": True,
            "emergency_verified": bool(h.emergency_verified),
            "availability_status": "NOT_VERIFIED",
            "availability_note": (
                "Real-time availability (beds/ICU/doctors) is not verified — "
                "contact the hospital directly."
            ),
        }
        for d, h in scored[:limit]
    ]


# ----------------------------------------------------------- ambulance provider

class AmbulanceProvider:
    """Integration boundary for ambulance dispatch (e.g. 108 services).
    Production providers must be configured + feature-flagged; the default
    reports NOT_CONFIGURED and never invents dispatch state."""

    name = "none"

    def request_dispatch(self, event: EmergencyEvent, *, note: str = "") -> dict:
        return {
            "provider": self.name,
            "status": "NOT_CONFIGURED",
            "detail": "Ambulance integration is not currently available.",
        }

    def get_dispatch_status(self, event: EmergencyEvent) -> dict:
        return {
            "provider": self.name,
            "status": "NOT_CONFIGURED",
            "detail": "Ambulance integration is not currently available.",
        }

    def cancel_dispatch(self, event: EmergencyEvent) -> dict:
        return {
            "provider": self.name,
            "status": "NOT_CONFIGURED",
            "detail": "Ambulance integration is not currently available.",
        }


class MockAmbulanceProvider(AmbulanceProvider):
    """TEST-ONLY provider for automated tests. Never enabled by feature flag
    in real environments; selected explicitly via settings in test suites."""

    name = "mock_ambulance"

    def __init__(self):
        self._dispatch: dict[str, str] = {}

    def request_dispatch(self, event: EmergencyEvent, *, note: str = "") -> dict:
        self._dispatch[event.id] = "DISPATCH_REQUESTED"
        return {"provider": self.name, "status": "DISPATCH_REQUESTED", "detail": note}

    def get_dispatch_status(self, event: EmergencyEvent) -> dict:
        status = self._dispatch.get(event.id, "UNKNOWN")
        return {"provider": self.name, "status": status, "detail": ""}

    def cancel_dispatch(self, event: EmergencyEvent) -> dict:
        self._dispatch.pop(event.id, None)
        return {"provider": self.name, "status": "CANCELLED", "detail": ""}


_provider: AmbulanceProvider | None = None


def get_ambulance_provider() -> AmbulanceProvider:
    """Returns the configured provider or the honest NOT_CONFIGURED default.
    A production provider would be constructed here from settings — until
    then, no fake dispatch state is ever produced."""
    return _provider if _provider is not None else AmbulanceProvider()


def set_ambulance_provider(provider: AmbulanceProvider | None) -> None:
    """Test/ops hook: install a provider (None resets to not-configured)."""
    global _provider
    _provider = provider


def request_ambulance(db: Session, *, event: EmergencyEvent, actor, note: str = "") -> dict:
    """Record a dispatch request against the configured provider. The ledger
    stores exactly what the provider returned; the event status does NOT
    advance to ACTIVE on a request alone."""
    if not is_terminal(event.status) and event.status not in (
        "REQUESTED", "ALERTING", "CONTACTING", "ACTIVE", "HANDOFF_PENDING",
    ):
        raise EmergencyError(f"Cannot request ambulance in status {event.status}", 409)
    provider = get_ambulance_provider()
    result = provider.request_dispatch(event, note=note)
    db.add(
        EmergencyProviderEvent(
            emergency_event_id=event.id,
            provider_name=result["provider"],
            action="DISPATCH_REQUESTED",
            status=result["status"],
            detail=result.get("detail", "")[:500],
        )
    )
    _audit(
        db,
        actor_user_id=actor.id,
        action="AMBULANCE_REQUESTED",
        resource_id=event.id,
        detail=f"provider={result['provider']} status={result['status']}",
        outcome="SUCCESS" if result["status"] not in ("NOT_CONFIGURED", "FAILED") else "DENIED",
        correlation_id=event.correlation_id,
    )
    db.commit()
    return result


# ------------------------------------------------------------------ handoffs

def create_handoff(
    db: Session, *, event: EmergencyEvent, hospital_id: str, actor, notes: str = ""
) -> EmergencyHandoff:
    from app.models.providers import Hospital

    hospital = db.get(Hospital, hospital_id)
    if hospital is None or hospital.verification_status != "VERIFIED":
        raise EmergencyError("Handoff target must be a VERIFIED hospital", 422)
    if event.status not in CANCELABLE_STATUSES + ("HANDOFF_PENDING", "HANDED_OFF"):
        raise EmergencyError(f"Cannot create handoff in status {event.status}", 409)
    open_handoff = (
        db.query(EmergencyHandoff)
        .filter(
            EmergencyHandoff.emergency_event_id == event.id,
            EmergencyHandoff.status == "HANDOFF_REQUESTED",
        )
        .first()
    )
    if open_handoff is not None:
        raise EmergencyError("A handoff is already pending for this event", 409)
    handoff = EmergencyHandoff(
        emergency_event_id=event.id,
        hospital_id=hospital_id,
        requested_by_user_id=actor.id,
        status="HANDOFF_REQUESTED",
        notes=(notes or "")[:500],
    )
    db.add(handoff)
    if event.status in ("REQUESTED", "ALERTING", "CONTACTING", "ACTIVE"):
        transition(db, event, "HANDOFF_PENDING", actor=actor)
    _audit(
        db,
        actor_user_id=actor.id,
        action="HOSPITAL_HANDOFF_REQUESTED",
        resource_id=event.id,
        detail=f"handoff={handoff.id} hospital={hospital_id}",
        correlation_id=event.correlation_id,
    )
    db.commit()
    return handoff


def hospital_decide_handoff(
    db: Session, *, handoff: EmergencyHandoff, hospital_admin, accept: bool, notes: str = ""
) -> EmergencyHandoff:
    """Real hospital-side decision. Never simulated: only the HOSPITAL_ADMIN
    who owns the handoff's hospital may decide it."""
    from app.models.providers import Hospital

    owned = (
        db.query(Hospital.id)
        .filter(Hospital.admin_user_id == hospital_admin.id)
        .first()
    )
    if owned is None or handoff.hospital_id != owned[0]:
        raise EmergencyError("This handoff belongs to a different hospital", 403)
    if handoff.status != "HANDOFF_REQUESTED":
        raise EmergencyError(f"Handoff is not decidable in status {handoff.status}", 409)
    handoff.status = "HANDOFF_ACCEPTED" if accept else "HANDOFF_REJECTED"
    handoff.responded_at = datetime.now(UTC)
    handoff.notes = (notes or handoff.notes)[:500]
    event = db.get(EmergencyEvent, handoff.emergency_event_id)
    if accept and event is not None and event.status == "HANDOFF_PENDING":
        transition(db, event, "HANDED_OFF", actor=hospital_admin)
        event.confirmed_by_provider = f"hospital:{handoff.hospital_id}"
    _audit(
        db,
        actor_user_id=hospital_admin.id,
        action="HOSPITAL_HANDOFF_ACCEPTED" if accept else "HOSPITAL_HANDOFF_REJECTED",
        resource_id=handoff.emergency_event_id,
        detail=f"handoff={handoff.id} hospital={handoff.hospital_id}",
        correlation_id=event.correlation_id if event else None,
    )
    db.commit()
    return handoff


def handoff_status_values() -> tuple[str, ...]:
    return HANDOFF_STATUSES


# -------------------------------------------------------------- notifications

def send_notification(
    db: Session,
    *,
    event: EmergencyEvent | None,
    contact: EmergencyContact | None,
    recipient_user_id: str | None,
    channel: str,
    provider_available: bool,
) -> EmergencyNotification:
    """Record one notification attempt truthfully.

    IN_APP delivery is real (this ledger is the inbox). External channels
    (SMS/push/email) require a configured provider; without one the row is
    FAILED with error_detail="provider_not_configured" — never SENT.
    """
    if channel not in NOTIFICATION_CHANNELS:
        raise EmergencyError(f"Unknown notification channel: {channel}", 422)
    if channel == "IN_APP" or provider_available:
        row = EmergencyNotification(
            emergency_event_id=event.id if event else None,
            contact_id=contact.id if contact else None,
            recipient_user_id=recipient_user_id,
            recipient_phone=contact.phone_number if contact else None,
            channel=channel,
            status="SENT",
            provider_name="in_app" if channel == "IN_APP" else "configured_provider",
            sent_at=datetime.now(UTC),
        )
    else:
        row = EmergencyNotification(
            emergency_event_id=event.id if event else None,
            contact_id=contact.id if contact else None,
            recipient_user_id=recipient_user_id,
            recipient_phone=contact.phone_number if contact else None,
            channel=channel,
            status="FAILED",
            provider_name=None,
            error_detail="provider_not_configured",
        )
    db.add(row)
    db.commit()
    return row
