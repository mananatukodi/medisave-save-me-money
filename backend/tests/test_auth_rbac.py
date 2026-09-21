"""Auth + server-side RBAC tests (spec §4, §36)."""

from tests.conftest import make_user


def test_register_returns_tokens(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Asha Reddy",
            "email": "asha@example.com",
            "password": "Password123!",
            "primary_language": "te",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]


def test_register_duplicate_email_conflict(client):
    payload = {
        "full_name": "Asha Reddy",
        "email": "dupe@example.com",
        "password": "Password123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_login_success_and_failure(client, db_session):
    make_user(db_session, "login@example.com", "CorrectHorse1!")
    ok = client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": "CorrectHorse1!"}
    )
    assert ok.status_code == 200
    bad = client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401


def test_refresh_token_flow(client, db_session):
    make_user(db_session, "refresh@example.com", "Password123!")
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "refresh@example.com", "password": "Password123!"}
    ).json()
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    # Access tokens must NOT be accepted as refresh tokens.
    bad = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert bad.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_profile_and_role(client, patient_headers):
    body = client.get("/api/v1/auth/me", headers=patient_headers).json()
    assert body["email"] == "patient@example.com"
    assert body["roles"] == ["PATIENT"]
    assert body["primary_language"] == "te"


def test_new_users_cannot_self_assign_elevated_roles(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Sneaky Sam",
            "email": "sneaky@example.com",
            "password": "Password123!",
            # requested elevated role must be ignored — server assigns PATIENT only
        },
    )
    assert resp.status_code == 201
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {resp.json()['access_token']}"},
    ).json()
    assert me["roles"] == ["PATIENT"]


def test_admin_endpoint_denies_patient(client, patient_headers):
    assert client.get("/api/v1/admin/users", headers=patient_headers).status_code == 403


def test_admin_endpoint_denies_doctor(client, doctor_headers):
    assert client.get("/api/v1/admin/users", headers=doctor_headers).status_code == 403


def test_admin_endpoint_allows_super_admin(client, admin_headers):
    assert client.get("/api/v1/admin/users", headers=admin_headers).status_code == 200


def test_feature_flag_update_requires_super_admin(client, admin_headers, patient_headers):
    resp = client.patch(
        "/api/v1/feature-flags/AI_ENABLED",
        json={"is_enabled": False},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False

    denied = client.patch(
        "/api/v1/feature-flags/AI_ENABLED",
        json={"is_enabled": True},
        headers=patient_headers,
    )
    assert denied.status_code == 403
