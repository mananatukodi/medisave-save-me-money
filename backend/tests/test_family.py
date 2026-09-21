"""Phase 6 tests: family accounts & caregiver access — invitation security,
relationship lifecycle, scoped consent, Health Vault integration, appointment
on-behalf-of, medicine-order view, IDOR, and regression of owner rights
(spec §3-§9, §13-§14, §19, §24).

All persons, records, and relationships here are synthetic test fixtures in an
in-memory database — never seeded into any real environment.
"""

from datetime import UTC, datetime, timedelta

from tests.test_vault import _headers, _record


def _pair(client, db_session):
    """Create (owner_headers, member_headers) with a linked account."""
    owner = _headers(client, db_session)
    member = _headers(client, db_session)
    member_id = _member_id(db_session, member["Authorization"])
    return owner, member, member_id


def _member_id(db_session, auth_header):

    email = _email_from_token(db_session, auth_header)
    return email and _user_id_by_email(db_session, email)


def _email_from_token(db_session, auth_header):
    # The tests create users with known emails; decode from DB by latest login
    # is fragile — instead use the JWT subject directly.
    import jwt

    from app.core.config import settings

    token = auth_header.split(" ", 1)[1]
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    return payload["sub"]


def _user_id_by_email(db_session, user_id):
    return user_id  # JWT subject IS the user id


def _invite(client, owner_headers, *, member_user_id=None, email=None, rtype="SPOUSE"):
    payload = {
        "display_name": "Test Relative",
        "relationship_type": rtype,
    }
    if member_user_id:
        payload["member_user_id"] = member_user_id
    if email:
        payload["invited_email"] = email
    resp = client.post("/api/v1/family/invitations", json=payload, headers=owner_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _activate(client, owner_headers, member_headers, member_id):
    rel = _invite(client, owner_headers, member_user_id=member_id)
    resp = client.post(
        f"/api/v1/family/invitations/{rel['id']}/accept", headers=member_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ACTIVE"
    return resp.json()


def _grant(client, owner_headers, rel_id, scopes=("VIEW_HEALTH_RECORDS",), **kw):
    resp = client.put(
        f"/api/v1/family/relationships/{rel_id}/consent",
        json={"scopes": list(scopes), "purpose": "test", **kw},
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ------------------------------------------------------------- relationship

def test_invite_accept_active(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _invite(client, owner, member_user_id=member_id)
    assert rel["status"] == "INVITED"
    assert rel["invitation_token"]  # shown once at creation
    got = client.get("/api/v1/family/invitations", headers=owner)
    assert got.status_code == 200
    assert all("invitation_token" not in item for item in got.json())  # never re-exposed
    accepted = _activate(client, owner, member, member_id)
    assert accepted["status"] == "ACTIVE"


def test_decline(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _invite(client, owner, member_user_id=member_id)
    resp = client.post(f"/api/v1/family/invitations/{rel['id']}/decline", headers=member)
    assert resp.status_code == 200
    assert resp.json()["status"] == "DECLINED"


def test_invite_self_rejected(client, db_session):
    owner = _headers(client, db_session)
    owner_id = _member_id(db_session, owner["Authorization"])
    resp = client.post(
        "/api/v1/family/invitations",
        json={"display_name": "Me", "relationship_type": "OTHER", "member_user_id": owner_id},
        headers=owner,
    )
    assert resp.status_code == 422


def test_duplicate_active_relationship_rejected(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    _activate(client, owner, member, member_id)
    resp = client.post(
        "/api/v1/family/invitations",
        json={"display_name": "Dup", "relationship_type": "SPOUSE", "member_user_id": member_id},
        headers=owner,
    )
    assert resp.status_code == 409


def test_only_invitee_can_accept(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _invite(client, owner, member_user_id=member_id)
    stranger = _headers(client, db_session)
    resp = client.post(f"/api/v1/family/invitations/{rel['id']}/accept", headers=stranger)
    assert resp.status_code == 403


def test_invitation_expiry(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _invite(client, owner, member_user_id=member_id)
    from app.db.session import Base  # noqa: F401  (engine bound in fixtures)
    from app.models.family import FamilyRelationship

    row = db_session.get(FamilyRelationship, rel["id"])
    row.invitation_expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()
    resp = client.post(f"/api/v1/family/invitations/{rel['id']}/accept", headers=member)
    assert resp.status_code == 410


def test_member_self_remove(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    resp = client.post(f"/api/v1/family/relationships/{rel['id']}/revoke", headers=member)
    assert resp.status_code == 200
    assert resp.json()["status"] == "REVOKED"


def test_relationship_hidden_from_strangers(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    stranger = _headers(client, db_session)
    resp = client.get(f"/api/v1/family/relationships/{rel['id']}", headers=stranger)
    assert resp.status_code == 404


# ----------------------------------------------------------------- consent

def test_consent_requires_active_relationship(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _invite(client, owner, member_user_id=member_id)  # still INVITED
    resp = client.put(
        f"/api/v1/family/relationships/{rel['id']}/consent",
        json={"scopes": ["VIEW_HEALTH_RECORDS"]},
        headers=owner,
    )
    assert resp.status_code == 409


def test_unknown_scope_rejected(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    resp = client.put(
        f"/api/v1/family/relationships/{rel['id']}/consent",
        json={"scopes": ["BECOME_DOCTOR"]},
        headers=owner,
    )
    assert resp.status_code == 422


def test_member_cannot_grant_own_consent(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    resp = client.put(
        f"/api/v1/family/relationships/{rel['id']}/consent",
        json={"scopes": ["VIEW_HEALTH_RECORDS"]},
        headers=member,
    )
    assert resp.status_code == 404  # grant is owner-only


def test_consent_update_replaces_and_revocation(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    first = _grant(client, owner, rel["id"], ("VIEW_HEALTH_RECORDS", "VIEW_APPOINTMENTS"))
    second = _grant(client, owner, rel["id"], ("VIEW_APPOINTMENTS",))
    assert second["scopes"] == "VIEW_APPOINTMENTS"
    assert first["id"] != second["id"]
    resp = client.delete(f"/api/v1/family/relationships/{rel['id']}/consent", headers=owner)
    assert resp.status_code == 200
    assert resp.json()["revoked_at"] is not None


# --------------------------------------------------- Health Vault integration

def test_family_record_access_with_consent(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    rec = _record(client, owner, category="PRESCRIPTION")
    _grant(client, owner, rel["id"], ("VIEW_HEALTH_RECORDS",))
    resp = client.get(f"/api/v1/health-records/{rec['id']}", headers=member)
    assert resp.status_code == 200, resp.text


def test_no_default_access_without_consent(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    _activate(client, owner, member, member_id)
    rec = _record(client, owner)
    resp = client.get(f"/api/v1/health-records/{rec['id']}", headers=member)
    assert resp.status_code == 403  # related but unauthorized


def test_category_filter_enforced(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    rx = _record(client, owner, category="PRESCRIPTION")
    lab = _record(client, owner, category="LAB_REPORT")
    _grant(
        client, owner, rel["id"], ("VIEW_HEALTH_RECORDS",), category_filter=["PRESCRIPTION"]
    )
    assert client.get(f"/api/v1/health-records/{rx['id']}", headers=member).status_code == 200
    assert client.get(f"/api/v1/health-records/{lab['id']}", headers=member).status_code == 403


def test_revoked_relationship_denies_access(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    rec = _record(client, owner)
    _grant(client, owner, rel["id"], ("VIEW_HEALTH_RECORDS",))
    client.post(f"/api/v1/family/relationships/{rel['id']}/revoke", headers=owner)
    assert client.get(f"/api/v1/health-records/{rec['id']}", headers=member).status_code == 403


def test_expired_consent_denies_access(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    rec = _record(client, owner)
    consent = _grant(
        client, owner, rel["id"], ("VIEW_HEALTH_RECORDS",), expires_in_days=1
    )
    from app.models.family import FamilyAccessConsent

    row = db_session.get(FamilyAccessConsent, consent["id"])
    row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()
    assert client.get(f"/api/v1/health-records/{rec['id']}", headers=member).status_code == 403


def test_family_consent_cannot_download(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    rec = _record(client, owner)
    _grant(client, owner, rel["id"], ("VIEW_HEALTH_RECORDS",))
    resp = client.get(f"/api/v1/health-records/{rec['id']}/download-url", headers=member)
    assert resp.status_code == 403  # downloads stay owner/direct-share


def test_unrelated_user_gets_404_no_idor(client, db_session):
    owner = _headers(client, db_session)
    rec = _record(client, owner)
    stranger = _headers(client, db_session)
    assert client.get(f"/api/v1/health-records/{rec['id']}", headers=stranger).status_code == 404


def test_owner_retains_access_regardless(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    rec = _record(client, owner)
    _grant(client, owner, rel["id"], ("VIEW_HEALTH_RECORDS",))
    client.delete(f"/api/v1/family/relationships/{rel['id']}/consent", headers=owner)
    assert client.get(f"/api/v1/health-records/{rec['id']}", headers=owner).status_code == 200


def test_member_view_shared_with_me(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    _activate(client, owner, member, member_id)
    resp = client.get("/api/v1/family/access-granted-to-me", headers=member)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------- appointments

def _doctor_fixture(client, db_session):
    from tests.test_booking import DOCTOR_REG, SERVICE, WEEK_RULES, _next_weekday_date

    doctor_headers = _headers(client, db_session, role="DOCTOR")
    admin_headers = _headers(client, db_session, role="SUPER_ADMIN")
    doctor = client.post(
        "/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers
    ).json()
    service = client.post(
        "/api/v1/doctors/me/services", json=SERVICE, headers=doctor_headers
    ).json()
    client.post(
        "/api/v1/doctors/me/availability", json=WEEK_RULES, headers=doctor_headers
    )
    client.post(
        f"/api/v1/admin/verifications/doctors/{doctor['id']}/decision",
        json={"new_status": "VERIFIED", "decision_note": "fixture"},
        headers=admin_headers,
    )
    # Monday is always a valid availability day in the fixture rules.
    return doctor, service, _next_weekday_date(0)


def test_family_booking_on_behalf(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    doctor, service, day = _doctor_fixture(client, db_session)
    _grant(client, owner, rel["id"], ("REQUEST_APPOINTMENT",))
    resp = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:30",
            "on_behalf_of_patient_id": _member_id(db_session, owner["Authorization"]),
        },
        headers=member,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["patient_user_id"] == _member_id(db_session, owner["Authorization"])
    assert body["requested_by_user_id"] == member_id


def test_family_booking_without_consent_denied(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    _activate(client, owner, member, member_id)
    doctor, service, day = _doctor_fixture(client, db_session)
    resp = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:30",
            "on_behalf_of_patient_id": _member_id(db_session, owner["Authorization"]),
        },
        headers=member,
    )
    assert resp.status_code == 403


def test_stranger_cannot_book_on_behalf(client, db_session):
    owner = _headers(client, db_session)
    stranger = _headers(client, db_session)
    doctor, service, day = _doctor_fixture(client, db_session)
    resp = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:30",
            "on_behalf_of_patient_id": _member_id(db_session, owner["Authorization"]),
        },
        headers=stranger,
    )
    assert resp.status_code == 403


# --------------------------------------------------------------- medicines

def test_family_medicine_orders_view(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    _grant(client, owner, rel["id"], ("VIEW_MEDICINE_ORDERS",))
    resp = client.get(
        f"/api/v1/orders?for_patient={_member_id(db_session, owner['Authorization'])}",
        headers=member,
    )
    assert resp.status_code == 200
    assert resp.json() == []  # owner has no orders — empty, not fabricated


def test_family_medicine_orders_without_consent_denied(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    _activate(client, owner, member, member_id)
    resp = client.get(
        f"/api/v1/orders?for_patient={_member_id(db_session, owner['Authorization'])}",
        headers=member,
    )
    assert resp.status_code == 403


# ------------------------------------------------------------------ audit

def test_family_access_history(client, db_session):
    owner, member, member_id = _pair(client, db_session)
    rel = _activate(client, owner, member, member_id)
    rec = _record(client, owner)
    _grant(client, owner, rel["id"], ("VIEW_HEALTH_RECORDS",))
    client.get(f"/api/v1/health-records/{rec['id']}", headers=member)
    history = client.get("/api/v1/family/access-history", headers=member)
    assert history.status_code == 200
    actions = {row["action"] for row in history.json()}
    assert "FAMILY_RECORD_ACCESS" in actions
    owner_history = client.get("/api/v1/family/access-history", headers=owner)
    assert "FAMILY_CONSENT_GRANTED" in {row["action"] for row in owner_history.json()}
