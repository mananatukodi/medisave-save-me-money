"""Consent management tests (spec §30)."""

from tests.conftest import login_headers, make_user


def test_list_consents_empty(client, patient_headers):
    assert client.get("/api/v1/consents", headers=patient_headers).json() == []


def test_grant_ai_consent(client, patient_headers):
    resp = client.post(
        "/api/v1/consents",
        json={
            "consent_type": "AI_ACCESS",
            "purpose": "Use the AI health navigation assistant",
            "data_scope": "ai_navigation",
        },
        headers=patient_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["consent_type"] == "AI_ACCESS"
    assert body["is_active"] is True


def test_grant_invalid_consent_type_rejected(client, patient_headers):
    resp = client.post(
        "/api/v1/consents",
        json={"consent_type": "NOT_A_TYPE", "purpose": "invalid test"},
        headers=patient_headers,
    )
    assert resp.status_code == 422


def test_revoke_consent(client, patient_headers):
    granted = client.post(
        "/api/v1/consents",
        json={"consent_type": "DOCUMENT_SHARE", "purpose": "Share report with doctor"},
        headers=patient_headers,
    ).json()
    revoked = client.post(
        f"/api/v1/consents/{granted['id']}/revoke",
        json={"reason": "No longer needed"},
        headers=patient_headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["is_active"] is False

    # Double revoke is a conflict.
    again = client.post(
        f"/api/v1/consents/{granted['id']}/revoke",
        json={"reason": ""},
        headers=patient_headers,
    )
    assert again.status_code == 409


def test_cannot_revoke_someone_elses_consent(client, db_session, patient_headers):
    make_user(db_session, "other-user@example.com")
    other_headers = login_headers(client, "other-user@example.com")
    granted = client.post(
        "/api/v1/consents",
        json={"consent_type": "AI_ACCESS", "purpose": "other user consent"},
        headers=other_headers,
    ).json()
    resp = client.post(
        f"/api/v1/consents/{granted['id']}/revoke",
        json={"reason": "attacker attempt"},
        headers=patient_headers,
    )
    assert resp.status_code == 404
