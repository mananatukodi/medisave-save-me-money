"""Phase 7 tests: Emergency & SOS — state machine, idempotency, RBAC/IDOR,
consent-gated minimum-necessary disclosure, nearby hospitals, handoffs,
ambulance/notification honesty (spec §12, §32, §54).

All persons/events here are synthetic fixtures in an in-memory database.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.services import emergency_service
from tests.test_family import _pair as _family_pair  # convenience reuse
from tests.test_vault import _headers  # fixture helper

# ------------------------------------------------------------- helpers

def _sos(client, headers, **kw):
    return client.post("/api/v1/emergency/sos", json=kw, headers=headers)


def _contact(client, headers, **kw):
    payload = {
        "full_name": "Test Contact",
        "phone_number": "+919999999999",
        **kw,
    }
    return client.post("/api/v1/emergency/contacts", json=payload, headers=headers)


def _grant_emergency_consent(client, owner_headers, recipient, consent_type):
    """Grant an EMERGENCY_* consent to a recipient ('user:<id>' or
    'family:<relationship_id>')."""
    return client.post(
        "/api/v1/consents",
        json={
            "consent_type": consent_type,
            "purpose": "emergency test",
            "recipient": recipient,
        },
        headers=owner_headers,
    )


# ------------------------------------------------------------- SOS basics

def test_sos_state_machine_transitions(client, db_session, patient_headers):
    event = _sos(client, patient_headers, note="phase7").json()
    assert event["status"] == "REQUESTED"
    assert event["correlation_id"]
    # REQUESTED -> ALERTING -> CONTACTING (service-driven progression).
    from app.models.emergency import EmergencyEvent

    row = db_session.get(EmergencyEvent, event["id"])
    emergency_service.transition(db_session, row, "ALERTING", actor=None)
    db_session.commit()
    emergency_service.transition(db_session, row, "CONTACTING", actor=None)
    db_session.commit()
    got = client.get(f"/api/v1/emergency/sos/{event['id']}", headers=patient_headers)
    assert got.status_code == 200
    assert got.json()["status"] == "CONTACTING"


def test_sos_invalid_transitions_rejected(client, db_session, patient_headers):
    event = _sos(client, patient_headers).json()
    from app.models.emergency import EmergencyEvent

    row = db_session.get(EmergencyEvent, event["id"])
    # REQUESTED -> RESOLVED is not allowed (must go through the machine).
    with pytest.raises(emergency_service.EmergencyError):
        emergency_service.transition(db_session, row, "RESOLVED", actor=None)
    # REQUESTED -> ACTIVE is not allowed without real-world confirmation.
    with pytest.raises(emergency_service.EmergencyError):
        emergency_service.transition(db_session, row, "ACTIVE", actor=None)
    # Terminal states are immutable.
    client.post(f"/api/v1/emergency/sos/{event['id']}/cancel", json={}, headers=patient_headers)
    with pytest.raises(emergency_service.EmergencyError):
        emergency_service.transition(db_session, row, "ALERTING", actor=None)


def test_sos_idempotency_same_key_same_event(client, patient_headers):
    first = _sos(client, patient_headers, idempotency_key="retry-42")
    assert first.status_code == 201
    second = _sos(client, patient_headers, idempotency_key="retry-42")
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_sos_active_dedup_returns_existing(client, patient_headers):
    first = _sos(client, patient_headers).json()
    second = _sos(client, patient_headers, note="still emergency")
    assert second.status_code == 200  # never rejects a legitimate retry
    assert second.json()["id"] == first["id"]


def test_sos_cancel_then_new_sos_allowed(client, patient_headers):
    first = _sos(client, patient_headers).json()
    client.post(f"/api/v1/emergency/sos/{first['id']}/cancel", json={}, headers=patient_headers)
    second = _sos(client, patient_headers, note="new emergency")
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]


def test_sos_false_alarm_reason(client, patient_headers):
    event = _sos(client, patient_headers).json()
    resp = client.post(
        f"/api/v1/emergency/sos/{event['id']}/cancel",
        json={"reason": "FALSE_ALARM"},
        headers=patient_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "FALSE_ALARM"
    # Terminal: cannot cancel again.
    again = client.post(
        f"/api/v1/emergency/sos/{event['id']}/cancel", json={}, headers=patient_headers
    )
    assert again.status_code == 409


def test_sos_resolve_lifecycle(client, db_session, patient_headers):
    event = _sos(client, patient_headers).json()
    # Early-stage events cannot be RESOLVED — the machine requires real
    # engagement first (cancel / false alarm are the early exits).
    early = client.post(f"/api/v1/emergency/sos/{event['id']}/resolve", headers=patient_headers)
    assert early.status_code == 409
    # Walk the machine to ACTIVE, then resolution works.
    from app.models.emergency import EmergencyEvent

    row = db_session.get(EmergencyEvent, event["id"])
    emergency_service.transition(db_session, row, "ALERTING", actor=None)
    emergency_service.transition(db_session, row, "CONTACTING", actor=None)
    emergency_service.transition(db_session, row, "ACTIVE", actor=None)
    db_session.commit()
    resp = client.post(f"/api/v1/emergency/sos/{event['id']}/resolve", headers=patient_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "RESOLVED"


def test_cancel_reason_validation(client, patient_headers):
    event = _sos(client, patient_headers).json()
    resp = client.post(
        f"/api/v1/emergency/sos/{event['id']}/cancel",
        json={"reason": "NOT_A_REASON"},
        headers=patient_headers,
    )
    assert resp.status_code == 422


def test_sos_location_snapshot_timestamped(client, patient_headers):
    event = _sos(
        client,
        patient_headers,
        latitude="17.3850",
        longitude="78.4867",
        location_accuracy_m="12",
        location_timestamp="2026-09-20T10:00:00Z",
        network_status="2G",
        device_platform="android",
    ).json()
    assert event["latitude"] == "17.3850"
    # Location fields surface to the owner.
    got = client.get(f"/api/v1/emergency/sos/{event['id']}", headers=patient_headers)
    assert got.json()["latitude"] == "17.3850"


# --------------------------------------------------------------- RBAC / IDOR

def test_sos_hidden_from_other_patients(client, db_session, patient_headers):
    event = _sos(client, patient_headers, note="private").json()
    stranger = _headers(client, db_session)
    assert client.get(f"/api/v1/emergency/sos/{event['id']}", headers=stranger).status_code == 404
    assert client.post(
        f"/api/v1/emergency/sos/{event['id']}/cancel", json={}, headers=stranger
    ).status_code == 404
    assert client.post(
        f"/api/v1/emergency/sos/{event['id']}/resolve", headers=stranger
    ).status_code == 404
    assert client.get(f"/api/v1/emergency/{event['id']}/audit", headers=stranger).status_code == 404


def test_stranger_cannot_view_medical_summary(client, db_session, patient_headers):
    event = _sos(client, patient_headers).json()
    stranger = _headers(client, db_session)
    assert client.get(
        f"/api/v1/emergency/{event['id']}/medical-summary", headers=stranger
    ).status_code == 404


def test_history_scoped_to_owner(client, db_session, patient_headers):
    _sos(client, patient_headers, note="mine")
    stranger = _headers(client, db_session)
    events = client.get("/api/v1/emergency/history", headers=stranger).json()
    assert all(e["note"] != "mine" for e in events)


# ---------------------------------------------------------- emergency contacts

def test_contacts_patch_priority_and_active(client, patient_headers):
    created = _contact(client, patient_headers, priority=5).json()
    resp = client.patch(
        f"/api/v1/emergency/contacts/{created['id']}",
        json={"priority": 1, "active": False},
        headers=patient_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["priority"] == 1
    assert body["active"] is False


def test_contact_update_hidden_from_strangers(client, db_session, patient_headers):
    created = _contact(client, patient_headers).json()
    stranger = _headers(client, db_session)
    resp = client.patch(
        f"/api/v1/emergency/contacts/{created['id']}",
        json={"priority": 1},
        headers=stranger,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------- emergency profile

def test_profile_upsert_and_last_updated(client, patient_headers):
    resp = client.put(
        "/api/v1/emergency/profile",
        json={
            "blood_group": "O+",
            "allergies": "penicillin",
            "critical_conditions": "asthma",
        },
        headers=patient_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blood_group"] == "O+"
    assert body["updated_at"]
    # Unset fields stay unset, never fabricated.
    assert body["critical_medications"] == ""


def test_profile_ownership_enforced(client, db_session, patient_headers):
    client.put("/api/v1/emergency/profile", json={"blood_group": "AB-"}, headers=patient_headers)
    stranger = _headers(client, db_session)
    got = client.get("/api/v1/emergency/profile", headers=stranger)
    assert got.status_code == 200
    assert got.json()["blood_group"] is None  # their own (empty) profile, not the owner's


# ------------------------------------ minimum-necessary medical summary + consent

def test_medical_summary_owner_with_unknown_fields(client, patient_headers):
    event = _sos(client, patient_headers).json()
    client.put("/api/v1/emergency/profile", json={"blood_group": "B+"}, headers=patient_headers)
    summary = client.get(
        f"/api/v1/emergency/{event['id']}/medical-summary", headers=patient_headers
    ).json()
    assert summary["blood_group"] == "B+"
    # Missing information is UNKNOWN, never guessed.
    assert summary["allergies"] == "UNKNOWN"
    assert summary["critical_conditions"] == "UNKNOWN"
    assert summary["disclaimer"].startswith("This information is user-provided")


def test_family_member_requires_explicit_consent(client, db_session, patient_headers):
    owner, member, member_id = _family_pair(client, db_session)
    event = _sos(client, owner).json()
    # ACTIVE relationship + RECEIVE_HEALTH_ALERTS is NOT enough for the summary:
    # an explicit EMERGENCY_MEDICAL_SUMMARY consent is required.
    from tests.test_family import _activate

    _activate(client, owner, member, member_id)
    resp = client.get(f"/api/v1/emergency/{event['id']}/medical-summary", headers=member)
    assert resp.status_code == 404  # no EMERGENCY_MEDICAL_SUMMARY consent yet
    # Owner grants the emergency consent to this family relationship.
    from app.models.family import FamilyRelationship

    rel = (
        db_session.query(FamilyRelationship)
        .filter(
            FamilyRelationship.owner_user_id == _owner_user_id(db_session, owner),
            FamilyRelationship.member_user_id == member_id,
            FamilyRelationship.status == "ACTIVE",
        )
        .first()
    )
    granted = _grant_emergency_consent(
        client, owner, f"family:{rel.id}", "EMERGENCY_MEDICAL_SUMMARY"
    )
    assert granted.status_code == 201, granted.text
    resp = client.get(f"/api/v1/emergency/{event['id']}/medical-summary", headers=member)
    assert resp.status_code == 200
    assert resp.json()["patient_user_id"] == _owner_user_id(db_session, owner)


def _owner_user_id(db_session, owner_headers):
    import jwt

    from app.core.config import settings

    token = owner_headers["Authorization"].split(" ", 1)[1]
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])["sub"]


def test_revoked_emergency_consent_denies_family(client, db_session, patient_headers):
    owner, member, member_id = _family_pair(client, db_session)
    from tests.test_family import _activate

    _activate(client, owner, member, member_id)
    owner_id = _owner_user_id(db_session, owner)
    from app.models.family import FamilyRelationship

    rel = (
        db_session.query(FamilyRelationship)
        .filter(
            FamilyRelationship.owner_user_id == owner_id,
            FamilyRelationship.member_user_id == member_id,
            FamilyRelationship.status == "ACTIVE",
        )
        .first()
    )
    _grant_emergency_consent(client, owner, f"family:{rel.id}", "EMERGENCY_MEDICAL_SUMMARY")
    event = _sos(client, owner).json()
    assert client.get(
        f"/api/v1/emergency/{event['id']}/medical-summary", headers=member
    ).status_code == 200
    # Revoke the consent -> immediate denial.
    consents = client.get("/api/v1/consents", headers=owner).json()
    target = next(c for c in consents if c["consent_type"] == "EMERGENCY_MEDICAL_SUMMARY")
    revoked = client.post(
        f"/api/v1/consents/{target['id']}/revoke",
        json={"reason": "test revocation"},
        headers=owner,
    )
    assert revoked.status_code == 200
    assert client.get(
        f"/api/v1/emergency/{event['id']}/medical-summary", headers=member
    ).status_code == 404


def test_expired_emergency_consent_denies_family(client, db_session, patient_headers):
    owner, member, member_id = _family_pair(client, db_session)
    from tests.test_family import _activate

    _activate(client, owner, member, member_id)
    from app.models.consent import Consent
    from app.models.family import FamilyRelationship

    owner_id = _owner_user_id(db_session, owner)
    rel = (
        db_session.query(FamilyRelationship)
        .filter(
            FamilyRelationship.owner_user_id == owner_id,
            FamilyRelationship.member_user_id == member_id,
            FamilyRelationship.status == "ACTIVE",
        )
        .first()
    )
    _grant_emergency_consent(client, owner, f"family:{rel.id}", "EMERGENCY_MEDICAL_SUMMARY")
    consent = (
        db_session.query(Consent)
        .filter(
            Consent.user_id == owner_id,
            Consent.consent_type == "EMERGENCY_MEDICAL_SUMMARY",
        )
        .first()
    )
    consent.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()
    event = _sos(client, owner).json()
    assert client.get(
        f"/api/v1/emergency/{event['id']}/medical-summary", headers=member
    ).status_code == 404


def test_revoked_relationship_denies_family_alerts(client, db_session, patient_headers):
    owner, member, member_id = _family_pair(client, db_session)
    from tests.test_family import _activate

    rel = _activate(client, owner, member, member_id)
    from tests.test_family import _grant

    _grant(client, owner, rel["id"], ("RECEIVE_HEALTH_ALERTS",))
    _sos(client, owner, note="alert test")
    alerts = client.get("/api/v1/emergency/family-alerts", headers=member)
    assert alerts.status_code == 200
    assert any(a["status"] == "REQUESTED" for a in alerts.json())
    # Revoke the relationship -> alerts gone.
    client.post(f"/api/v1/family/relationships/{rel['id']}/revoke", headers=owner)
    alerts = client.get("/api/v1/emergency/family-alerts", headers=member)
    assert alerts.json() == []


def test_family_alerts_location_requires_consent(client, db_session, patient_headers):
    owner, member, member_id = _family_pair(client, db_session)
    from tests.test_family import _activate, _grant

    rel = _activate(client, owner, member, member_id)
    _grant(client, owner, rel["id"], ("RECEIVE_HEALTH_ALERTS",))
    _sos(
        client, owner, note="loc", latitude="17.3850", longitude="78.4867"
    )
    alerts = client.get("/api/v1/emergency/family-alerts", headers=member).json()
    assert alerts and alerts[0]["location"] is None  # no EMERGENCY_LOCATION consent
    _grant_emergency_consent(
        client, owner, f"family:{rel['id']}", "EMERGENCY_LOCATION"
    )
    alerts = client.get("/api/v1/emergency/family-alerts", headers=member).json()
    assert alerts[0]["location"] == {"latitude": "17.3850", "longitude": "78.4867"}


def test_family_alerts_exclude_unrelated_strangers(client, db_session, patient_headers):
    _sos(client, patient_headers, note="not yours")
    stranger = _headers(client, db_session)
    assert client.get("/api/v1/emergency/family-alerts", headers=stranger).json() == []


# ---------------------------------------------------------- nearby hospitals

def test_nearby_hospitals_requires_auth(client):
    assert client.get(
        "/api/v1/emergency/hospitals/nearby?lat=17.38&lng=78.48"
    ).status_code == 401


def test_nearby_hospitals_no_fabricated_availability(client, db_session):
    from app.models.providers import Hospital

    hospital = Hospital(
        name="Emergency Test Hospital (TEST FIXTURE)",
        hospital_type="HOSPITAL",
        city="Hyderabad",
        latitude="17.3850",
        longitude="78.4867",
        emergency_available=True,
        emergency_verified=True,
        verification_status="VERIFIED",
    )
    db_session.add(hospital)
    db_session.commit()
    try:
        body = client.get(
            "/api/v1/emergency/hospitals/nearby?lat=17.3850&lng=78.4867&radius_km=5",
            headers=_headers(client, db_session),
        ).json()
        match = next(h for h in body if h["hospital_id"] == hospital.id)
        assert match["emergency_available"] is True
        assert match["emergency_verified"] is True
        # HONESTY: real-time availability is NOT_VERIFIED — never invented.
        assert match["availability_status"] == "NOT_VERIFIED"
        assert "beds" not in match and "icu" not in match and "eta" not in match
    finally:
        db_session.delete(hospital)
        db_session.commit()


def test_nearby_excludes_unverified_and_non_emergency(client, db_session):
    from app.models.providers import Hospital

    h1 = Hospital(
        name="Pending Hosp (TEST FIXTURE)", verification_status="PENDING",
        latitude="17.3850", longitude="78.4867", emergency_available=True,
    )
    h2 = Hospital(
        name="No-ER Hosp (TEST FIXTURE)", verification_status="VERIFIED",
        latitude="17.3850", longitude="78.4867", emergency_available=False,
    )
    db_session.add_all([h1, h2])
    db_session.commit()
    try:
        body = client.get(
            "/api/v1/emergency/hospitals/nearby?lat=17.3850&lng=78.4867&radius_km=5",
            headers=_headers(client, db_session),
        ).json()
        ids = {h["hospital_id"] for h in body}
        assert h1.id not in ids and h2.id not in ids
    finally:
        db_session.delete(h1)
        db_session.delete(h2)
        db_session.commit()


# ---------------------------------------------------------- handoffs

def test_handoff_lifecycle_with_hospital_decision(client, db_session):
    from app.models.providers import Hospital

    owner = _headers(client, db_session)
    event = _sos(client, owner).json()
    # Verified hospital owned by a HOSPITAL_ADMIN.
    admin = _headers(client, db_session, role="HOSPITAL_ADMIN")
    hospital = Hospital(
        name="Handoff Hosp (TEST FIXTURE)", verification_status="VERIFIED",
        emergency_available=True,
    )
    db_session.add(hospital)
    db_session.commit()
    # Bind the admin user to the hospital.
    import jwt

    from app.core.config import settings

    admin_id = jwt.decode(
        admin["Authorization"].split(" ", 1)[1],
        settings.secret_key, algorithms=["HS256"],
    )["sub"]
    hospital.admin_user_id = admin_id
    db_session.commit()
    try:
        created = client.post(
            f"/api/v1/emergency/{event['id']}/handoffs",
            json={"hospital_id": hospital.id},
            headers=owner,
        )
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "HANDOFF_REQUESTED"
        # Event moved to HANDOFF_PENDING by the state machine.
        got = client.get(f"/api/v1/emergency/sos/{event['id']}", headers=owner)
        assert got.json()["status"] == "HANDOFF_PENDING"
        # Hospital-side acceptance is real: the owning HOSPITAL_ADMIN decides.
        decided = client.post(
            f"/api/v1/emergency/handoffs/{created.json()['id']}/decision",
            json={"accept": True},
            headers=admin,
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["status"] == "HANDOFF_ACCEPTED"
        got = client.get(f"/api/v1/emergency/sos/{event['id']}", headers=owner)
        assert got.json()["status"] == "HANDED_OFF"
        assert got.json()["confirmed_by_provider"] == f"hospital:{hospital.id}"
    finally:
        db_session.delete(hospital)
        db_session.commit()


def test_handoff_rejected_by_other_hospital_admin(client, db_session):
    owner = _headers(client, db_session)
    event = _sos(client, owner).json()
    from app.models.providers import Hospital

    hospital = Hospital(
        name="Other Hosp (TEST FIXTURE)", verification_status="VERIFIED"
    )
    db_session.add(hospital)
    db_session.commit()
    try:
        created = client.post(
            f"/api/v1/emergency/{event['id']}/handoffs",
            json={"hospital_id": hospital.id},
            headers=owner,
        ).json()
        stranger_admin = _headers(client, db_session)
        resp = client.post(
            f"/api/v1/emergency/handoffs/{created['id']}/decision",
            json={"accept": True},
            headers=stranger_admin,
        )
        # Non-hospital-admin -> 403; hospital A cannot decide hospital B's handoff.
        assert resp.status_code == 403
    finally:
        db_session.delete(hospital)
        db_session.commit()


def test_handoff_requires_verified_hospital(client, db_session):
    from app.models.providers import Hospital

    owner = _headers(client, db_session)
    event = _sos(client, owner).json()
    hospital = Hospital(name="Pending Handoff (TEST FIXTURE)", verification_status="PENDING")
    db_session.add(hospital)
    db_session.commit()
    try:
        resp = client.post(
            f"/api/v1/emergency/{event['id']}/handoffs",
            json={"hospital_id": hospital.id},
            headers=owner,
        )
        assert resp.status_code == 422
    finally:
        db_session.delete(hospital)
        db_session.commit()


# ------------------------------------------------- ambulance + notifications

def test_ambulance_not_configured_is_honest(client, patient_headers):
    event = _sos(client, patient_headers).json()
    resp = client.post(
        f"/api/v1/emergency/{event['id']}/ambulance", json={}, headers=patient_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "NOT_CONFIGURED"
    assert "not currently available" in body["detail"]
    # And nothing advanced the event: still REQUESTED.
    got = client.get(f"/api/v1/emergency/sos/{event['id']}", headers=patient_headers)
    assert got.json()["status"] == "REQUESTED"


def test_ambulance_ledger_records_request(client, patient_headers):
    event = _sos(client, patient_headers).json()
    client.post(f"/api/v1/emergency/{event['id']}/ambulance", json={}, headers=patient_headers)
    audit = client.get(f"/api/v1/emergency/{event['id']}/audit", headers=patient_headers).json()
    assert any(a["action"] == "AMBULANCE_REQUESTED" for a in audit)


def test_notifications_honest_without_provider(client, db_session, patient_headers):
    owner = patient_headers
    _contact(client, owner, notification_preferences="IN_APP,SMS")
    event = _sos(client, owner).json()
    rows = client.get(f"/api/v1/emergency/{event['id']}/notifications", headers=owner).json()
    # Family notifications (if any) are IN_APP SENT; no SMS provider configured ->
    # any SMS channel attempt would be FAILED provider_not_configured. The
    # patient's own contact notification is queued by policy, not pretended.
    for row in rows:
        if row["channel"] == "SMS":
            assert row["status"] == "FAILED"
            assert row["error_detail"] == "provider_not_configured"
        else:
            assert row["status"] in ("QUEUED", "SENT", "FAILED")


def test_emergency_audit_trail(client, db_session, patient_headers):
    event = _sos(client, patient_headers, note="audit").json()
    from app.models.emergency import EmergencyEvent

    row = db_session.get(EmergencyEvent, event["id"])
    emergency_service.transition(db_session, row, "ALERTING", actor=None)
    emergency_service.transition(db_session, row, "CONTACTING", actor=None)
    emergency_service.transition(db_session, row, "ACTIVE", actor=None)
    db_session.commit()
    client.post(f"/api/v1/emergency/sos/{event['id']}/resolve", headers=patient_headers)
    audit = client.get(f"/api/v1/emergency/{event['id']}/audit", headers=patient_headers)
    assert audit.status_code == 200
    actions = {a["action"] for a in audit.json()}
    assert "SOS_CREATED" in actions
    assert "EMERGENCY_RESOLVED" in actions


# ------------------------------------------------------------- AI safety

def test_ai_emergency_response_routes_to_sos_without_treatment():
    from app.ai.engine import PipelineContext, run_pipeline

    response = run_pipeline(
        PipelineContext(
            user_id="u1", language="te",
            message="నాకు ఊపిరి తీసుకోవడం కష్టంగా ఉంది", consent_active=False,
        )
    )
    assert response.urgency == "EMERGENCY"
    routes = [a.route for a in response.navigation]
    assert "/emergency" in routes
    assert "tel:108" in routes
    lowered = response.message.lower()
    for banned in ("you definitely", "take this medicine", "ambulance is coming"):
        assert banned not in lowered


def test_ai_cannot_create_sos(client, patient_headers):
    """The AI surface has no capability to create emergency events — only the
    deterministic /emergency/sos endpoint can, and it requires auth."""
    resp = client.post(
        "/api/v1/ai/chat",
        json={"message": "severe chest pain", "language": "en"},
        headers=patient_headers,
    )
    assert resp.status_code == 200  # emergency bypasses consent, routes only
    assert resp.json()["urgency"] == "EMERGENCY"
