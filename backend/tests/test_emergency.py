"""Emergency SOS tests (spec §12) — including the no-fabricated-dispatch rule."""


def test_sos_requires_auth(client):
    assert client.post("/api/v1/emergency/sos", json={}).status_code == 401


def test_sos_creates_event_in_requested_status(client, patient_headers):
    resp = client.post(
        "/api/v1/emergency/sos",
        json={"note": "help", "latitude": "17.3850", "longitude": "78.4867"},
        headers=patient_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # MUST start at REQUESTED — never CONFIRMED (spec §54: never fabricate dispatch).
    assert body["status"] == "REQUESTED"
    assert body["confirmed_by_provider"] is None


def test_sos_events_listed_for_owner(client, patient_headers):
    client.post("/api/v1/emergency/sos", json={"note": "first"}, headers=patient_headers)
    events = client.get("/api/v1/emergency/events", headers=patient_headers).json()
    assert len(events) == 1
    assert events[0]["status"] == "REQUESTED"


def test_sos_cancel_own_event(client, patient_headers):
    event = client.post("/api/v1/emergency/sos", json={}, headers=patient_headers).json()
    resp = client.post(f"/api/v1/emergency/events/{event['id']}/cancel", json={}, headers=patient_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_sos_cannot_cancel_twice(client, patient_headers):
    event = client.post("/api/v1/emergency/sos", json={}, headers=patient_headers).json()
    client.post(f"/api/v1/emergency/events/{event['id']}/cancel", json={}, headers=patient_headers)
    again = client.post(f"/api/v1/emergency/events/{event['id']}/cancel", json={}, headers=patient_headers)
    assert again.status_code == 409


def test_emergency_contacts_crud(client, patient_headers):
    created = client.post(
        "/api/v1/emergency/contacts",
        json={
            "full_name": "Amma",
            "phone_number": "+919999999999",
            "relationship_type": "PARENT",
            "is_primary": True,
        },
        headers=patient_headers,
    )
    assert created.status_code == 201
    contacts = client.get("/api/v1/emergency/contacts", headers=patient_headers).json()
    assert len(contacts) == 1
    deleted = client.delete(f"/api/v1/emergency/contacts/{contacts[0]['id']}", headers=patient_headers)
    assert deleted.status_code == 204
    assert client.get("/api/v1/emergency/contacts", headers=patient_headers).json() == []
