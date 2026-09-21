"""Phase 5 tests: Digital Health Vault (spec §18).

Covers: ownership/IDOR, RBAC defaults (no support/hospital/admin access),
consent scope/expiry/revocation, share lifecycle, upload validation, signed
URLs, audit events. All documents are synthetic test bytes.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.models.vault import HealthRecordShare
from tests.conftest import login_headers, make_user

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _headers(client, db_session, role="PATIENT"):
    suffix = uuid.uuid4().hex[:8]
    email = f"{role.lower()}-{suffix}@example.com"
    make_user(db_session, email, roles=(role,) if role else ())
    return login_headers(client, email)


def _last_user_id(db_session, role_prefix: str) -> str:
    """ID of the most recently created user with the given email prefix.
    Tests must look this up AFTER creating the intended user."""
    from app.models.user import User

    user = (
        db_session.query(User)
        .filter(User.email.like(f"{role_prefix}-%"))
        .order_by(User.created_at.desc())
        .first()
    )
    assert user is not None, f"no user with prefix {role_prefix}"
    return user.id


def _record(client, headers, **overrides):
    payload = {
        "category": "LAB_REPORT",
        "title": "Test Lab Report (SYNTHETIC)",
        "record_date": "2026-09-01",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/health-records", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload(client, headers, record_id, data=_PNG, filename="test.png", mime="image/png"):
    return client.post(
        f"/api/v1/health-records/{record_id}/upload",
        files={"file": (filename, data, mime)},
        headers=headers,
    )


# ------------------------------------------------------------- creation

def test_create_and_get_own_record(client, db_session):
    headers = _headers(client, db_session)
    record = _record(client, headers)
    got = client.get(f"/api/v1/health-records/{record['id']}", headers=headers)
    assert got.status_code == 200
    assert got.json()["title"] == "Test Lab Report (SYNTHETIC)"
    assert got.json()["source"] == "PATIENT_UPLOAD"


def test_create_requires_patient_role(client, db_session):
    support = _headers(client, db_session, role="SUPPORT_AGENT")
    resp = client.post(
        "/api/v1/health-records",
        json={"category": "OTHER", "title": "Nope"},
        headers=support,
    )
    assert resp.status_code == 403


def test_list_returns_only_own_records(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    other = _headers(client, db_session)
    mine = client.get("/api/v1/health-records", headers=other).json()
    assert all(r["id"] != record["id"] for r in mine)
    # Cross-patient detail is 404 (existence hidden — no IDOR)
    assert client.get(f"/api/v1/health-records/{record['id']}", headers=other).status_code == 404


def test_record_search_filters(client, db_session):
    owner = _headers(client, db_session)
    _record(client, owner, category="LAB_REPORT", title="Blood Panel Sep", record_date="2026-09-02")
    _record(client, owner, category="PRESCRIPTION", title="Rx Sep", record_date="2026-09-10")
    by_cat = client.get("/api/v1/health-records", params={"category": "PRESCRIPTION"}, headers=owner).json()
    assert len(by_cat) == 1 and by_cat[0]["category"] == "PRESCRIPTION"
    by_title = client.get("/api/v1/health-records", params={"title": "blood"}, headers=owner).json()
    assert len(by_title) == 1
    by_date = client.get(
        "/api/v1/health-records", params={"date_from": "2026-09-05"}, headers=owner
    ).json()
    assert len(by_date) == 1 and by_date[0]["record_date"] == "2026-09-10"


# --------------------------------------------------------------- files

def test_upload_and_download_roundtrip(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    resp = _upload(client, owner, record["id"])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["file"]["upload_status"] == "COMPLETED"
    assert len(body["file"]["checksum_sha256"]) == 64
    assert body["file"]["scan_status"] == "PENDING"  # honest: scanner not integrated

    url_resp = client.get(f"/api/v1/health-records/{record['id']}/download-url", headers=owner)
    assert url_resp.status_code == 200
    assert url_resp.json()["ttl_seconds"] == 900
    dl = client.get(url_resp.json()["url"])
    assert dl.status_code == 200
    assert dl.content == _PNG
    assert dl.headers["content-type"].startswith("image/png")


def test_upload_rejects_disallowed_type(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    resp = _upload(
        client, owner, record["id"],
        data=b"#!/bin/sh\nrm -rf /\n", filename="evil.sh", mime="text/x-sh",
    )
    assert resp.status_code == 422


def test_upload_rejects_client_mime_mismatch(client, db_session):
    """A PDF byte stream declared as PNG must be caught by magic-byte sniffing."""
    owner = _headers(client, db_session)
    record = _record(client, owner)
    resp = _upload(
        client, owner, record["id"],
        data=b"%PDF-1.7 fake pdf", filename="faked.png", mime="image/png",
    )
    assert resp.status_code == 422


def test_upload_rejects_oversized(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    big = _PNG + b"\x00" * (10 * 1024 * 1024 + 1)
    resp = _upload(client, owner, record["id"], data=big, filename="big.png")
    assert resp.status_code == 422


def test_upload_requires_ownership(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    other = _headers(client, db_session)
    resp = _upload(client, other, record["id"])
    assert resp.status_code == 403


# -------------------------------------------------------------- shares

def test_share_and_provider_view(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    doctor = _headers(client, db_session, role="DOCTOR")

    share = client.post(
        "/api/v1/health-records/shares",
        json={
            "record_id": record["id"],
            "grantee_user_id": _user_id(db_session, "doctor"),
            "grantee_type": "DOCTOR",
            "scope": "VIEW_RECORD",
            "purpose": "consultation",
            "expires_in_days": 7,
        },
        headers=owner,
    )
    assert share.status_code == 201, share.text

    viewed = client.get(f"/api/v1/health-records/{record['id']}", headers=doctor)
    assert viewed.status_code == 200
    # Download NOT covered by VIEW scope
    denied = client.get(f"/api/v1/health-records/{record['id']}/download-url", headers=doctor)
    assert denied.status_code == 403


def _user_id(db_session, role_prefix):
    from app.models.user import User

    user = (
        db_session.query(User)
        .filter(User.email.like(f"{role_prefix}-%"))
        .order_by(User.created_at.desc())
        .first()
    )
    return user.id


def test_share_view_category_scope(client, db_session):
    owner = _headers(client, db_session)
    lab = _record(client, owner, category="LAB_REPORT")
    rx = _record(client, owner, category="PRESCRIPTION")
    doctor = _headers(client, db_session, role="DOCTOR")
    doctor_id = _user_id(db_session, "doctor")

    client.post(
        "/api/v1/health-records/shares",
        json={
            "record_id": lab["id"],
            "grantee_user_id": doctor_id,
            "scope": "VIEW_CATEGORY",
            "category_filter": "LAB_REPORT,DIAGNOSTIC_REPORT",
        },
        headers=owner,
    )
    assert client.get(f"/api/v1/health-records/{lab['id']}", headers=doctor).status_code == 200
    # Same share does NOT cover a different category record (no share for it →
    # existence hidden with 404, per no-IDOR rule)
    assert client.get(f"/api/v1/health-records/{rx['id']}", headers=doctor).status_code == 404


def test_share_expiry_and_revocation(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    doctor = _headers(client, db_session, role="DOCTOR")
    doctor_id = _user_id(db_session, "doctor")

    share = client.post(
        "/api/v1/health-records/shares",
        json={
            "record_id": record["id"],
            "grantee_user_id": doctor_id,
            "scope": "VIEW_RECORD",
            "expires_in_days": 1,
        },
        headers=owner,
    ).json()
    assert client.get(f"/api/v1/health-records/{record['id']}", headers=doctor).status_code == 200

    # Revocation: future access denied immediately (spec §8). The grantee had a
    # share row, so the denial is explicit 403 (not existence-hiding 404).
    rev = client.delete(f"/api/v1/health-records/shares/{share['id']}", headers=owner)
    assert rev.status_code == 200
    assert rev.json()["revoked_at"] is not None
    assert client.get(f"/api/v1/health-records/{record['id']}", headers=doctor).status_code == 403
    # Signed URL generation also denied post-revocation
    dl = client.post(
        "/api/v1/health-records/shares",
        json={
            "record_id": record["id"],
            "grantee_user_id": doctor_id,
            "scope": "DOWNLOAD_RECORD",
        },
        headers=owner,
    )
    assert dl.status_code == 201  # new share
    client.delete(f"/api/v1/health-records/shares/{dl.json()['id']}", headers=owner)
    denied_url = client.get(
        f"/api/v1/health-records/{record['id']}/download-url", headers=doctor
    )
    assert denied_url.status_code == 403


def test_expired_share_denied(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    owner_user_id = _user_id(db_session, "patient")
    doctor = _headers(client, db_session, role="DOCTOR")
    doctor_id = _user_id(db_session, "doctor")

    # Backdate an already-expired share directly (fixture manipulation)
    share = HealthRecordShare(
        record_id=record["id"],
        granted_by=owner_user_id,
        grantee_user_id=doctor_id,
        scope="VIEW_RECORD",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(share)
    db_session.commit()
    assert client.get(f"/api/v1/health-records/{record['id']}", headers=doctor).status_code == 403


def test_no_default_access_for_other_roles(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    for role in ("SUPPORT_AGENT", "HOSPITAL_ADMIN", "SUPER_ADMIN"):
        insider = _headers(client, db_session, role=role)
        assert client.get(f"/api/v1/health-records/{record['id']}", headers=insider).status_code == 404, role
        assert client.get("/api/v1/health-records", headers=insider).json() == []


# ---------------------------------------------------------- signed URLs

def test_download_url_requires_authorization(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    _upload(client, owner, record["id"])
    stranger = _headers(client, db_session)
    resp = client.get(f"/api/v1/health-records/{record['id']}/download-url", headers=stranger)
    assert resp.status_code == 404
    # Tampered token rejected by signature check
    forged = client.get("/api/v1/health-records/files/abc.9999999999.deadbeef")
    assert forged.status_code == 403


def test_download_url_scope_requirement(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    _upload(client, owner, record["id"])
    doctor = _headers(client, db_session, role="DOCTOR")
    doctor_id = _user_id(db_session, "doctor")
    client.post(
        "/api/v1/health-records/shares",
        json={"record_id": record["id"], "grantee_user_id": doctor_id, "scope": "VIEW_RECORD"},
        headers=owner,
    )
    # VIEW scope cannot mint download URLs
    denied_url = client.get(
        f"/api/v1/health-records/{record['id']}/download-url", headers=doctor
    )
    assert denied_url.status_code == 403


def test_download_url_expires(client, db_session):
    from app.services import vault_service

    owner = _headers(client, db_session)
    record = _record(client, owner)
    _upload(client, owner, record["id"])
    url = client.get(f"/api/v1/health-records/{record['id']}/download-url", headers=owner).json()
    token = url["url"].rsplit("/", 1)[-1]
    assert vault_service.resolve_download_token(db_session, token) is not None

    # Force-expired token must be rejected (tamper with expiry inside valid signature impossible;
    # so construct an expired token via the signing internals)
    import time as _time

    file_id, exp, sig = token.split(".", 2)
    expired_payload = f"{file_id}.{int(_time.time()) - 10}"
    from app.services.vault_service import _sign

    expired_token = f"{expired_payload}.{_sign(expired_payload)}"
    try:
        vault_service.resolve_download_token(db_session, expired_token)
        raise AssertionError("expired token accepted")
    except vault_service.VaultError as err:
        assert "expired" in str(err).lower()


# ----------------------------------------------------------------- audit

def test_audit_events_written(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    _upload(client, owner, record["id"])
    client.get(f"/api/v1/health-records/{record['id']}", headers=owner)  # owner VIEW event
    doctor = _headers(client, db_session, role="DOCTOR")
    doctor_id = _user_id(db_session, "doctor")

    # Denied access (no share) creates a DENIED event
    client.get(f"/api/v1/health-records/{record['id']}", headers=doctor)
    events = client.get(f"/api/v1/health-records/{record['id']}/audit", headers=owner).json()
    actions = [e["action"] for e in events]
    assert "VIEW" in actions and "DENIED" in actions

    # Successful share + view creates SHARE_CREATED / VIEW events
    client.post(
        "/api/v1/health-records/shares",
        json={"record_id": record["id"], "grantee_user_id": doctor_id, "scope": "VIEW_RECORD"},
        headers=owner,
    )
    client.get(f"/api/v1/health-records/{record['id']}", headers=doctor)
    events = client.get(f"/api/v1/health-records/{record['id']}/audit", headers=owner).json()
    actions = [e["action"] for e in events]
    assert "SHARE_CREATED" in actions


def test_shared_with_me_listing(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    doctor = _headers(client, db_session, role="DOCTOR")
    client.post(
        "/api/v1/health-records/shares",
        json={
            "record_id": record["id"],
            "grantee_user_id": _user_id(db_session, "doctor"),
            "scope": "VIEW_RECORD",
        },
        headers=owner,
    )
    shared = client.get("/api/v1/health-records/shared-with-me", headers=doctor).json()
    assert any(r["id"] == record["id"] for r in shared)


# ------------------------------------------------------------- deletion

def test_soft_delete_purges_document(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    _upload(client, owner, record["id"])
    resp = client.delete(f"/api/v1/health-records/{record['id']}", headers=owner)
    assert resp.status_code == 200
    assert resp.json()["status"] == "DELETED"
    # Record is gone from listing and detail
    assert client.get(f"/api/v1/health-records/{record['id']}", headers=owner).status_code == 404
    listings = client.get("/api/v1/health-records", headers=owner).json()
    assert all(r["id"] != record["id"] for r in listings)


def test_patient_update_own_metadata_only(client, db_session):
    owner = _headers(client, db_session)
    record = _record(client, owner)
    other = _headers(client, db_session)
    ok = client.patch(
        f"/api/v1/health-records/{record['id']}",
        json={"title": "Renamed (SYNTHETIC)"},
        headers=owner,
    )
    assert ok.status_code == 200 and ok.json()["title"] == "Renamed (SYNTHETIC)"
    assert client.patch(
        f"/api/v1/health-records/{record['id']}", json={"title": "Hijack"}, headers=other
    ).status_code in (403, 404)
