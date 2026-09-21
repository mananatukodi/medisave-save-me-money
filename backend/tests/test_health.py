"""Health check tests (spec §40)."""


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["demo_mode"] is True


def test_ready_checks_database(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["checks"]["database"] == "ok"


def test_version_branding(client):
    body = client.get("/version").json()
    assert body["name"] == "MediSave AI"
    assert body["tagline"] == "Smart Healthcare. Better Care. Lower Cost."
