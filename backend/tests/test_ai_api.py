"""AI Health Assistant API tests (spec §10, §11)."""

AI_CONSENT = {
    "consent_type": "AI_ACCESS",
    "purpose": "Use the AI health navigation assistant",
    "data_scope": "ai_navigation",
}


def _grant_consent(client, headers):
    resp = client.post("/api/v1/consents", json=AI_CONSENT, headers=headers)
    assert resp.status_code == 201, resp.text


def test_ai_requires_auth(client):
    assert client.post("/api/v1/ai/chat", json={"message": "hello"}).status_code == 401


def test_ai_blocked_without_consent(client, patient_headers):
    resp = client.post(
        "/api/v1/ai/chat",
        json={"message": "I have eye pain", "language": "en"},
        headers=patient_headers,
    )
    assert resp.status_code == 403
    assert "consent" in resp.json()["detail"].lower()


def test_ai_chat_happy_path(client, patient_headers):
    _grant_consent(client, patient_headers)
    resp = client.post(
        "/api/v1/ai/chat",
        json={"message": "I need a vision screening for eye pain", "language": "en"},
        headers=patient_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_id"]
    assert body["intent"] in ("EYE_CARE", "SYMPTOM_INFORMATION")
    assert body["disclaimer"]
    assert body["urgency"] in ("ROUTINE", "URGENT")
    # Structured navigation actions for the patient (spec §11).
    assert isinstance(body["navigation"], list)


def test_ai_emergency_bypasses_consent_and_flags_review(client, patient_headers):
    resp = client.post(
        "/api/v1/ai/chat",
        json={"message": "severe chest pain, father collapsed", "language": "en"},
        headers=patient_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["urgency"] == "EMERGENCY"
    assert body["requires_human_review"] is True
    assert "108" in body["message"]


def test_ai_session_continuity(client, patient_headers):
    _grant_consent(client, patient_headers)
    first = client.post(
        "/api/v1/ai/chat", json={"message": "eye pain", "language": "en"}, headers=patient_headers
    ).json()
    second = client.post(
        "/api/v1/ai/chat",
        json={"message": "also blurred vision", "language": "en", "session_id": first["session_id"]},
        headers=patient_headers,
    )
    assert second.status_code == 200
    assert second.json()["session_id"] == first["session_id"]


def test_ai_cannot_use_someone_elses_session(client, db_session, patient_headers):
    from tests.conftest import login_headers, make_user

    make_user(db_session, "session-owner@example.com")
    owner_headers = login_headers(client, "session-owner@example.com")
    _grant_consent(client, owner_headers)
    owner_session = client.post(
        "/api/v1/ai/chat", json={"message": "hello", "language": "en"}, headers=owner_headers
    ).json()["session_id"]

    _grant_consent(client, patient_headers)
    resp = client.post(
        "/api/v1/ai/chat",
        json={"message": "hi", "language": "en", "session_id": owner_session},
        headers=patient_headers,
    )
    assert resp.status_code == 404


def test_ai_disabled_by_feature_flag(client, admin_headers, patient_headers):
    _grant_consent(client, patient_headers)
    client.patch("/api/v1/feature-flags/AI_ENABLED", json={"is_enabled": False}, headers=admin_headers)
    resp = client.post(
        "/api/v1/ai/chat", json={"message": "eye pain", "language": "en"}, headers=patient_headers
    )
    assert resp.status_code == 503
    # Restore for other tests (fixtures are function-scoped, but be tidy).
    client.patch("/api/v1/feature-flags/AI_ENABLED", json={"is_enabled": True}, headers=admin_headers)


def test_ai_chat_in_telugu(client, patient_headers):
    _grant_consent(client, patient_headers)
    resp = client.post(
        "/api/v1/ai/chat",
        json={"message": "కంటి సంరక్షణ కావాలి", "language": "te"},
        headers=patient_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "EYE_CARE"
    assert "రోగనిర్ధారణ కాదు" in body["disclaimer"]
