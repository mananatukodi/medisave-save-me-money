"""Emergency & SOS endpoints (spec §12; Phase 7).

SAFETY CONTRACTS (never violated):
- SOS creation is deterministic CRUD — it never depends on AI.
- Status changes go through the service state machine only; clients cannot
  set status directly.
- The API never claims: ambulance dispatched, call connected, notification
  delivered, or hospital availability. Unavailable truth is reported as
  UNKNOWN / NOT_VERIFIED / UNAVAILABLE / NOT_CONFIGURED.
- Emergency records are never deleted.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.emergency import (
    EmergencyContact,
    EmergencyEvent,
    EmergencyHandoff,
    EmergencyNotification,
)
from app.models.ops import AuditLog, FeatureFlag
from app.security.deps import CurrentUser, record_audit
from app.services import emergency_service
from app.services.emergency_service import EmergencyError

router = APIRouter(prefix="/emergency", tags=["emergency"])


def _error(err: EmergencyError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=str(err))


def _flag_on(db: Session, key: str) -> bool:
    flag = db.get(FeatureFlag, key)
    return flag is not None and flag.is_enabled


def _require_sos_flag(db: Session) -> None:
    if not _flag_on(db, "SOS_ENABLED"):
        raise HTTPException(status_code=503, detail="SOS is disabled by feature flag")


# --------------------------------------------------------------- schemas

class SOSRequest(BaseModel):
    note: str = Field(default="", max_length=500)
    emergency_type: str = Field(default="MEDICAL", max_length=20)
    latitude: str | None = Field(default=None, max_length=24)
    longitude: str | None = Field(default=None, max_length=24)
    location_accuracy_m: str | None = Field(default=None, max_length=16)
    location_timestamp: datetime | None = None
    network_status: str | None = Field(default=None, max_length=20)
    device_platform: str | None = Field(default=None, max_length=40)
    idempotency_key: str | None = Field(default=None, max_length=64)


class SOSEventOut(BaseModel):
    id: str
    status: str
    note: str
    emergency_type: str = "MEDICAL"
    latitude: str | None
    longitude: str | None
    confirmed_by_provider: str | None
    created_at: datetime
    correlation_id: str | None = None

    model_config = {"from_attributes": True}


class CancelRequest(BaseModel):
    reason: str = Field(default="USER_CANCELLED", max_length=20)


class EmergencyContactCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone_number: str = Field(min_length=6, max_length=20)
    relationship_type: str = Field(default="OTHER", max_length=40)
    is_primary: bool = False
    priority: int = Field(default=100, ge=1, le=999)
    notification_preferences: str = Field(default="IN_APP", max_length=120)


class EmergencyContactUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone_number: str | None = Field(default=None, min_length=6, max_length=20)
    relationship_type: str | None = Field(default=None, max_length=40)
    is_primary: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=999)
    active: bool | None = None
    notification_preferences: str | None = Field(default=None, max_length=120)


class EmergencyContactOut(BaseModel):
    id: str
    full_name: str
    phone_number: str
    relationship_type: str
    is_primary: bool
    priority: int
    active: bool
    notification_preferences: str

    model_config = {"from_attributes": True}


class EmergencyProfileIn(BaseModel):
    blood_group: str | None = Field(default=None, max_length=8)
    allergies: str | None = Field(default=None, max_length=2000)
    critical_conditions: str | None = Field(default=None, max_length=2000)
    critical_medications: str | None = Field(default=None, max_length=2000)
    emergency_notes: str | None = Field(default=None, max_length=2000)
    preferred_hospital_id: str | None = Field(default=None, max_length=36)
    organ_donor_status: str | None = Field(default=None, max_length=20)
    accessibility_needs: str | None = Field(default=None, max_length=2000)


class EmergencyProfileOut(BaseModel):
    blood_group: str | None
    allergies: str
    critical_conditions: str
    critical_medications: str
    emergency_notes: str
    preferred_hospital_id: str | None
    organ_donor_status: str | None
    accessibility_needs: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class HandoffCreate(BaseModel):
    hospital_id: str = Field(max_length=36)
    notes: str = Field(default="", max_length=500)


class HandoffOut(BaseModel):
    id: str
    emergency_event_id: str
    hospital_id: str
    status: str
    notes: str
    requested_at: datetime
    responded_at: datetime | None

    model_config = {"from_attributes": True}


class HandoffDecision(BaseModel):
    accept: bool
    notes: str = Field(default="", max_length=500)


class AmbulanceRequest(BaseModel):
    note: str = Field(default="", max_length=500)


# -------------------------------------------------- static paths FIRST

@router.post("/sos", response_model=SOSEventOut, status_code=201)
def raise_sos(
    payload: SOSRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> Any:
    """One-tap SOS. Deterministic, AI-free, race-safe.

    201 = new event created. 200 = an existing event was returned
    (same idempotency key, or the patient already has a non-terminal SOS).
    Legitimate emergency retries are never rejected.
    """
    _require_sos_flag(db)
    try:
        event, created = emergency_service.create_sos(
            db,
            patient=current_user,
            note=payload.note,
            emergency_type=payload.emergency_type,
            latitude=payload.latitude,
            longitude=payload.longitude,
            location_accuracy_m=payload.location_accuracy_m,
            location_timestamp=payload.location_timestamp,
            network_status=payload.network_status,
            device_platform=payload.device_platform,
            idempotency_key=payload.idempotency_key,
        )
    except EmergencyError as err:
        raise _error(err) from None
    if created:
        emergency_service.notify_family(db, event=event, patient=current_user)
        emergency_service.notify_contacts(db, event=event, patient=current_user)
    if not created:
        response.status_code = 200
    return event


@router.get("/history", response_model=list[SOSEventOut])
def sos_history(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[EmergencyEvent]:
    query = (
        db.query(EmergencyEvent)
        .filter(EmergencyEvent.user_id == current_user.id)
        .order_by(EmergencyEvent.created_at.desc())
    )
    if status:
        query = query.filter(EmergencyEvent.status == status)
    return query.limit(limit).all()


@router.get("/contacts", response_model=list[EmergencyContactOut])
def list_contacts(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[EmergencyContact]:
    return (
        db.query(EmergencyContact)
        .filter(EmergencyContact.user_id == current_user.id)
        .order_by(EmergencyContact.priority.asc(), EmergencyContact.created_at.asc())
        .all()
    )


@router.post("/contacts", response_model=EmergencyContactOut, status_code=201)
def add_contact(
    payload: EmergencyContactCreate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyContact:
    contact = EmergencyContact(user_id=current_user.id, **payload.model_dump())
    db.add(contact)
    db.commit()
    record_audit(
        db, action="EMERGENCY_CONTACT_ADDED", actor_user_id=current_user.id,
        resource_type="emergency_contact", resource_id=contact.id,
    )
    db.commit()
    return contact


@router.patch("/contacts/{contact_id}", response_model=EmergencyContactOut)
def update_contact(
    contact_id: str,
    payload: EmergencyContactUpdate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyContact:
    contact = db.get(EmergencyContact, contact_id)
    if contact is None or contact.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)
    db.commit()
    record_audit(
        db, action="EMERGENCY_CONTACT_UPDATED", actor_user_id=current_user.id,
        resource_type="emergency_contact", resource_id=contact.id,
    )
    db.commit()
    return contact


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(
    contact_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    contact = db.get(EmergencyContact, contact_id)
    if contact is None or contact.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()


@router.get("/profile", response_model=EmergencyProfileOut)
def get_profile(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    return emergency_service.get_profile(db, current_user)


@router.put("/profile", response_model=EmergencyProfileOut)
def put_profile(
    payload: EmergencyProfileIn,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    profile = emergency_service.update_profile(
        db, current_user, payload.model_dump(exclude_unset=True)
    )
    return profile


@router.get("/hospitals/nearby")
def nearby_hospitals(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=25.0, gt=0, le=200),
) -> list[dict]:
    """Verified emergency-capable hospitals, nearest first.

    Real-time availability is NOT tracked here and is reported as
    NOT_VERIFIED — beds/ICU/doctors/ETA are never fabricated.
    """
    if not _flag_on(db, "EMERGENCY_HOSPITAL_SEARCH"):
        raise HTTPException(status_code=503, detail="Hospital search is disabled by feature flag")
    results = emergency_service.nearby_emergency_hospitals(
        db, lat=lat, lng=lng, radius_km=radius_km
    )
    record_audit(
        db, action="HOSPITAL_SEARCHED", actor_user_id=current_user.id,
        resource_type="emergency", resource_id="nearby_hospitals",
        detail=f"results={len(results)} radius_km={radius_km}",
    )
    db.commit()
    return results


@router.get("/family-alerts")
def family_alerts(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """Minimum-necessary emergency alerts for a family/caregiver member.
    Requires an ACTIVE Phase 6 relationship + RECEIVE_HEALTH_ALERTS consent;
    location only with an explicit EMERGENCY_LOCATION consent."""
    return emergency_service.family_alerts_for(db, current_user)


@router.post("/handoffs/{handoff_id}/decision", response_model=HandoffOut)
def decide_handoff(
    handoff_id: str,
    payload: HandoffDecision,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyHandoff:
    """Real hospital-side decision (HOSPITAL_ADMIN owning the target hospital).
    Acceptance is never simulated."""
    if "HOSPITAL_ADMIN" not in current_user.role_ids:
        raise HTTPException(status_code=403, detail="HOSPITAL_ADMIN role required")
    handoff = db.get(EmergencyHandoff, handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="Handoff not found")
    try:
        return emergency_service.hospital_decide_handoff(
            db, handoff=handoff, hospital_admin=current_user,
            accept=payload.accept, notes=payload.notes,
        )
    except EmergencyError as err:
        raise _error(err) from None


# ------------------------------------------------------- event-scoped paths

@router.get("/sos/{event_id}", response_model=SOSEventOut)
def get_sos(
    event_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyEvent:
    event = emergency_service.get_owned_event(db, event_id, current_user)
    if event is None:
        # Existence hidden from unrelated users (no IDOR).
        raise HTTPException(status_code=404, detail="Emergency event not found")
    return event


@router.post("/sos/{event_id}/cancel", response_model=SOSEventOut)
def cancel_sos_v2(
    event_id: str,
    payload: CancelRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyEvent:
    event = emergency_service.get_owned_event(db, event_id, current_user)
    if event is None:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    try:
        return emergency_service.cancel_sos(
            db, event=event, actor=current_user, reason=payload.reason
        )
    except EmergencyError as err:
        raise _error(err) from None


@router.post("/sos/{event_id}/resolve", response_model=SOSEventOut)
def resolve_sos(
    event_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyEvent:
    event = emergency_service.get_owned_event(db, event_id, current_user)
    if event is None:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    try:
        return emergency_service.resolve_sos(db, event=event, actor=current_user)
    except EmergencyError as err:
        raise _error(err) from None


@router.get("/{event_id}/medical-summary")
def medical_summary(
    event_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Minimum-necessary emergency medical summary.

    Owner: always. Family member: ACTIVE relationship + explicit
    EMERGENCY_MEDICAL_SUMMARY consent from the patient (re-checked per
    request). Everyone else: 404 (existence hidden). Every access is audited.
    """
    event = db.get(EmergencyEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    allowed = event.user_id == current_user.id
    if not allowed:
        allowed = emergency_service.family_summary_allowed(
            db, patient_id=event.user_id, member=current_user
        )
        if allowed:
            record_audit(
                db, action="EMERGENCY_PROFILE_ACCESSED", actor_user_id=current_user.id,
                resource_type="emergency", resource_id=event.id,
                detail="disclosure=medical_summary consent=EMERGENCY_MEDICAL_SUMMARY",
            )
            db.commit()
    if not allowed:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    if event.user_id == current_user.id:
        record_audit(
            db, action="EMERGENCY_PROFILE_ACCESSED", actor_user_id=current_user.id,
            resource_type="emergency", resource_id=event.id,
            detail="disclosure=medical_summary recipient=self",
        )
        db.commit()
    return emergency_service.medical_summary(db, event=event)


@router.post("/{event_id}/ambulance")
def request_ambulance(
    event_id: str,
    payload: AmbulanceRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Request ambulance dispatch via the provider abstraction.

    Every attempt is recorded in the provider ledger + audit, including
    NOT_CONFIGURED attempts. With no provider configured (default) the
    response honestly reports: 'Ambulance integration is not currently
    available.' — nothing is dispatched and no dispatch state is invented.
    """
    _require_sos_flag(db)
    event = emergency_service.get_owned_event(db, event_id, current_user)
    if event is None:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    try:
        return emergency_service.request_ambulance(
            db, event=event, actor=current_user, note=payload.note
        )
    except EmergencyError as err:
        raise _error(err) from None


@router.get("/{event_id}/handoffs", response_model=list[HandoffOut])
def list_handoffs(
    event_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[EmergencyHandoff]:
    event = emergency_service.get_owned_event(db, event_id, current_user)
    if event is None:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    return (
        db.query(EmergencyHandoff)
        .filter(EmergencyHandoff.emergency_event_id == event.id)
        .order_by(EmergencyHandoff.requested_at.desc())
        .all()
    )


@router.post("/{event_id}/handoffs", response_model=HandoffOut, status_code=201)
def create_handoff(
    event_id: str,
    payload: HandoffCreate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyHandoff:
    _require_sos_flag(db)
    if not _flag_on(db, "HOSPITAL_HANDOFF"):
        raise HTTPException(status_code=503, detail="Handoff is disabled by feature flag")
    event = emergency_service.get_owned_event(db, event_id, current_user)
    if event is None:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    try:
        return emergency_service.create_handoff(
            db, event=event, hospital_id=payload.hospital_id,
            actor=current_user, notes=payload.notes,
        )
    except EmergencyError as err:
        raise _error(err) from None


@router.get("/{event_id}/notifications")
def event_notifications(
    event_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """Delivery-status ledger for the patient. Honest: FAILED rows carry the
    real error (e.g. provider_not_configured)."""
    event = emergency_service.get_owned_event(db, event_id, current_user)
    if event is None:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    rows = (
        db.query(EmergencyNotification)
        .filter(EmergencyNotification.emergency_event_id == event.id)
        .order_by(EmergencyNotification.created_at.desc())
        .all()
    )
    return [
        {
            "id": n.id,
            "channel": n.channel,
            "status": n.status,
            "provider_name": n.provider_name,
            "error_detail": n.error_detail,
            "created_at": n.created_at.isoformat(),
        }
        for n in rows
    ]


@router.get("/{event_id}/audit")
def event_audit(
    event_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """Emergency audit trail. Owner sees their own event's rows; SUPER_ADMIN
    sees any (governance, audited). No payloads, no credentials."""
    event = db.get(EmergencyEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    if event.user_id != current_user.id and "SUPER_ADMIN" not in current_user.role_ids:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.resource_type == "emergency",
            AuditLog.resource_id == event.id,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "action": r.action,
            "outcome": r.outcome,
            "detail": r.detail,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# --------------------------------------------- legacy Phase 1 routes (kept)

@router.get("/events", response_model=list[SOSEventOut])
def list_events(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[EmergencyEvent]:
    return (
        db.query(EmergencyEvent)
        .filter(EmergencyEvent.user_id == current_user.id)
        .order_by(EmergencyEvent.created_at.desc())
        .all()
    )


@router.post("/events/{event_id}/cancel", response_model=SOSEventOut)
def cancel_event(
    event_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    payload: CancelRequest | None = None,
) -> EmergencyEvent:
    event = emergency_service.get_owned_event(db, event_id, current_user)
    if event is None:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    reason = payload.reason if payload is not None else "USER_CANCELLED"
    try:
        return emergency_service.cancel_sos(
            db, event=event, actor=current_user, reason=reason
        )
    except EmergencyError as err:
        raise _error(err) from None
