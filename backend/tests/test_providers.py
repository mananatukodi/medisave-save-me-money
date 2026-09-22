"""Provider registration + verification tests (Phase 3, spec §1-§4, §14, §20)."""

DOCTOR_REG = {
    "full_name": "Dr. Test Ophthalmologist",
    "specialty_slug": "eye-care",
    "qualifications": "MBBS, MS (Ophthalmology)",
    "registration_number": "TMC-12345",
    "registration_council": "Test Medical Council",
    "years_experience": 8,
    "languages": "te,en",
    "consultation_modes": "IN_PERSON,VIDEO",
    "city": "Hyderabad",
}

HOSPITAL_REG = {
    "name": "Test Eye Hospital",
    "hospital_type": "EYE_CLINIC",
    "registration_number": "TES-777",
    "address_line": "1 Test Street",
    "city": "Hyderabad",
    "departments": "eye-care,dental-care",
    "emergency_available": True,
}


def test_doctor_register_requires_doctor_role(client, patient_headers):
    resp = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=patient_headers)
    assert resp.status_code == 403


def test_doctor_register_success(client, doctor_headers):
    resp = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["verification_status"] == "PENDING"  # never pre-verified (spec §1)
    assert body["specialty_slug"] == "eye-care"


def test_doctor_register_unknown_specialty_rejected(client, doctor_headers):
    payload = {**DOCTOR_REG, "specialty_slug": "not-a-specialty"}
    assert client.post("/api/v1/doctors/register", json=payload, headers=doctor_headers).status_code == 422


def test_public_doctor_view_hides_registration_data(client, doctor_headers, db_session):
    created = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers).json()
    detail = client.get(f"/api/v1/doctors/{created['id']}").json()
    assert "registration_number" not in detail
    assert "registration_council" not in detail


def test_doctor_verification_requires_super_admin(client, doctor_headers):
    created = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers).json()
    denied_by_doctor = client.post(
        f"/api/v1/admin/verifications/doctors/{created['id']}/decision",
        json={"new_status": "VERIFIED", "decision_note": "self-approval attempt"},
        headers=doctor_headers,
    )
    assert denied_by_doctor.status_code == 403


def test_doctor_verification_flow(client, admin_headers, doctor_headers):
    created = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers).json()
    doctor_id = created["id"]

    approved = client.post(
        f"/api/v1/admin/verifications/doctors/{doctor_id}/decision",
        json={"new_status": "VERIFIED", "decision_note": "credentials checked"},
        headers=admin_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["verification_status"] == "VERIFIED"

    # Idempotency guard: same decision again is a conflict.
    again = client.post(
        f"/api/v1/admin/verifications/doctors/{doctor_id}/decision",
        json={"new_status": "VERIFIED"},
        headers=admin_headers,
    )
    assert again.status_code == 409

    # Suspension works from VERIFIED.
    suspended = client.post(
        f"/api/v1/admin/verifications/doctors/{doctor_id}/decision",
        json={"new_status": "SUSPENDED", "decision_note": "complaint investigation"},
        headers=admin_headers,
    )
    assert suspended.status_code == 200
    assert suspended.json()["verification_status"] == "SUSPENDED"

    # History is immutable and complete.
    history = client.get(
        f"/api/v1/admin/verifications/doctors/{doctor_id}/history", headers=admin_headers
    ).json()
    statuses = [row["new_status"] for row in history]
    assert statuses == ["SUSPENDED", "VERIFIED"]


def test_rejected_doctor_not_shown_as_verified_in_search(client, admin_headers, doctor_headers):
    created = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers).json()
    client.post(
        f"/api/v1/admin/verifications/doctors/{created['id']}/decision",
        json={"new_status": "REJECTED", "decision_note": "invalid registration"},
        headers=admin_headers,
    )
    verified_only = client.get(
        "/api/v1/doctors", params={"verification_status": "VERIFIED"}
    ).json()
    assert all(d["id"] != created["id"] for d in verified_only)


def test_hospital_register_requires_hospital_admin_role(client, patient_headers):
    resp = client.post("/api/v1/hospitals/register", json=HOSPITAL_REG, headers=patient_headers)
    assert resp.status_code == 403


def test_hospital_register_and_verify(client, admin_headers, hospital_headers):
    created = client.post("/api/v1/hospitals/register", json=HOSPITAL_REG, headers=hospital_headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["verification_status"] == "PENDING"
    # Emergency may be flagged by the hospital but is NOT verified yet (spec §14).
    assert body["emergency_available"] is True
    assert body["emergency_verified"] is False

    approved = client.post(
        f"/api/v1/admin/verifications/hospitals/{body['id']}/decision",
        json={"new_status": "VERIFIED", "decision_note": "license verified; emergency bay confirmed"},
        headers=admin_headers,
    )
    assert approved.status_code == 200

    history = client.get(
        f"/api/v1/admin/verifications/hospitals/{body['id']}/history", headers=admin_headers
    ).json()
    assert history[0]["new_status"] == "VERIFIED"


def test_hospital_unknown_department_rejected(client, hospital_headers):
    payload = {**HOSPITAL_REG, "departments": "astrology"}
    resp = client.post("/api/v1/hospitals/register", json=payload, headers=hospital_headers)
    assert resp.status_code == 422


def test_provider_search_filters(client, admin_headers, doctor_headers):
    created = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers).json()
    client.post(
        f"/api/v1/admin/verifications/doctors/{created['id']}/decision",
        json={"new_status": "VERIFIED", "decision_note": "ok"},
        headers=admin_headers,
    )
    # Generic provider search (spec §11)
    result = client.get(
        "/api/v1/providers", params={"kind": "doctor", "specialty": "eye-care", "city": "Hyderabad"}
    ).json()
    assert result["kind"] == "doctor"
    assert any(d["id"] == created["id"] for d in result["items"])

    dental = client.get("/api/v1/providers", params={"kind": "doctor", "specialty": "dental-care"}).json()
    assert all(d["id"] != created["id"] for d in dental["items"])

    hospitals = client.get("/api/v1/hospitals", params={"specialty": "eye-care"}).json()
    assert isinstance(hospitals, list)


def test_verification_decision_audited(client, admin_headers, doctor_headers):
    created = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers).json()
    client.post(
        f"/api/v1/admin/verifications/doctors/{created['id']}/decision",
        json={"new_status": "UNDER_REVIEW", "decision_note": "queued"},
        headers=admin_headers,
    )
    logs = client.get("/api/v1/admin/audit-logs", headers=admin_headers).json()
    actions = {log["action"] for log in logs}
    assert "VERIFICATION_DECISION" in actions
    assert "PROVIDER_REGISTER" in actions
