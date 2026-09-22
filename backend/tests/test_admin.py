"""Admin endpoint tests (spec §32, §37)."""

from tests.conftest import make_user


def test_admin_lists_audit_logs(client, admin_headers):
    logs = client.get("/api/v1/admin/audit-logs", headers=admin_headers).json()
    assert isinstance(logs, list)


def test_audit_log_records_login(client, db_session, admin_headers):
    make_user(db_session, "audited@example.com")
    client.post("/api/v1/auth/login", json={"email": "audited@example.com", "password": "Password123!"})
    logs = client.get("/api/v1/admin/audit-logs", headers=admin_headers).json()
    actions = {log["action"] for log in logs}
    assert "LOGIN" in actions


def test_admin_can_assign_role(client, admin_headers, db_session):
    make_user(db_session, "promo@example.com")
    user = db_session.query(__import__("app.models.user", fromlist=["User"]).User).filter(
        __import__("app.models.user", fromlist=["User"]).User.email == "promo@example.com"
    ).first()
    resp = client.post(
        f"/api/v1/admin/users/{user.id}/roles",
        json={"role_id": "SUPPORT_AGENT"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert "SUPPORT_AGENT" in resp.json()["roles"]


def test_audit_records_role_change(client, admin_headers, db_session):
    from app.models.user import User

    make_user(db_session, "audit-role@example.com")
    user = db_session.query(User).filter(User.email == "audit-role@example.com").first()
    client.post(
        f"/api/v1/admin/users/{user.id}/roles", json={"role_id": "FIELD_AGENT"}, headers=admin_headers
    )
    logs = client.get("/api/v1/admin/audit-logs", headers=admin_headers).json()
    assert any(log["action"] == "ROLE_CHANGE" for log in logs)
