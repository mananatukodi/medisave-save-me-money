"""Availability + appointment lifecycle tests (Phase 3, spec §8-§10, §19).

Setup: one VERIFIED eye-care doctor with weekly availability Mon-Fri 10:00-13:00,
30-minute slots. All provider data here is test-fixture data in an in-memory DB —
never seeded into any real environment.
"""

from datetime import date, timedelta

DOCTOR_REG = {
    "full_name": "Dr. Slot Tester",
    "specialty_slug": "eye-care",
    "qualifications": "MBBS, MS",
    "registration_number": "TMC-999",
    "years_experience": 5,
    "consultation_modes": "IN_PERSON",
    "city": "Hyderabad",
}

SERVICE = {
    "specialty_slug": "eye-care",
    "name_en": "Vision screening",
    "name_te": "కంటి పరీక్ష",
    "name_hi": "दृष्टि जांच",
    "duration_minutes": 30,
    "consultation_type": "IN_PERSON",
    "price_amount": 350.0,
}

WEEK_RULES = [
    {"weekday": weekday, "start_time": "10:00", "end_time": "13:00", "slot_minutes": 30}
    for weekday in range(5)  # Monday..Friday
]


def _next_weekday_date(weekday: int) -> str:
    """Next calendar date (from tomorrow) falling on the given weekday (0=Mon)."""
    day = date.today() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day.isoformat()


def _setup_verified_doctor(client, doctor_headers, admin_headers):
    doctor = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers).json()
    service = client.post("/api/v1/doctors/me/services", json=SERVICE, headers=doctor_headers)
    assert service.status_code == 201, service.text
    service = service.json()
    assert service["prices"][0]["verification_status"] == "UNVERIFIED"  # declared, not verified
    rules = client.post("/api/v1/doctors/me/availability", json=WEEK_RULES, headers=doctor_headers)
    assert rules.status_code == 201, rules.text
    approved = client.post(
        f"/api/v1/admin/verifications/doctors/{doctor['id']}/decision",
        json={"new_status": "VERIFIED", "decision_note": "fixture"},
        headers=admin_headers,
    )
    assert approved.status_code == 200
    return doctor, service


def test_service_price_declared_not_verified(client, doctor_headers):
    client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers)
    service = client.post("/api/v1/doctors/me/services", json=SERVICE, headers=doctor_headers)
    assert service.status_code == 201
    price = service.json()["prices"][0]
    assert price["verification_status"] == "UNVERIFIED"
    assert price["source"] == "provider_declared"
    assert price["currency"] == "INR"


def test_booking_unverified_doctor_rejected(client, patient_headers, doctor_headers):
    # Register but DO NOT verify:
    doctor = client.post("/api/v1/doctors/register", json=DOCTOR_REG, headers=doctor_headers).json()
    service = client.post("/api/v1/doctors/me/services", json=SERVICE, headers=doctor_headers).json()
    day = _next_weekday_date(1)
    resp = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:00",
        },
        headers=patient_headers,
    )
    assert resp.status_code == 409


def test_availability_slots_generated(client, admin_headers, doctor_headers):
    _setup_verified_doctor(client, doctor_headers, admin_headers)
    day = _next_weekday_date(2)  # a Wednesday
    slots = client.get(
        "/api/v1/doctors/me/availability", headers=doctor_headers
    )
    assert slots.status_code == 200
    assert len(slots.json()) == 5  # Mon-Fri rules stored

    doctor_id = client.get("/api/v1/providers", params={"kind": "doctor"}).json()["items"][0]["id"]
    availability = client.get(
        f"/api/v1/doctors/{doctor_id}/availability", params={"date": day}
    ).json()
    assert availability[0]["date"] == day
    times = [slot["time"] for slot in availability[0]["slots"]]
    assert "10:00" in times and "12:30" in times
    assert all(slot["available"] for slot in availability[0]["slots"])
    # 10:00-13:00 with 30-minute slots = exactly 6 slots
    assert len(times) == 6


def test_no_availability_outside_rules(client, admin_headers, doctor_headers):
    _setup_verified_doctor(client, doctor_headers, admin_headers)
    doctor_id = client.get("/api/v1/providers", params={"kind": "doctor"}).json()["items"][0]["id"]
    sunday = _next_weekday_date(6)
    availability = client.get(
        f"/api/v1/doctors/{doctor_id}/availability", params={"date": sunday}
    ).json()
    assert availability[0]["slots"] == []


def test_book_appointment_happy_path(client, admin_headers, doctor_headers, patient_headers):
    doctor, service = _setup_verified_doctor(client, doctor_headers, admin_headers)
    day = _next_weekday_date(1)
    resp = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:00",
            "notes": "blurred vision",
        },
        headers=patient_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "REQUESTED"
    assert body["specialty_slug"] == "eye-care"
    assert body["consultation_type"] == "IN_PERSON"
    assert body["price_amount"] == 350.0
    assert body["price_verified"] is False  # unverified price never marked verified (spec §7)

    # The slot now shows BOOKED and unavailable.
    availability = client.get(
        f"/api/v1/doctors/{doctor['id']}/availability", params={"date": day}
    ).json()
    slot = next(s for s in availability[0]["slots"] if s["time"] == "10:00")
    assert slot["available"] is False
    assert slot["reason"] == "BOOKED"


def test_double_booking_prevented(
    client, admin_headers, doctor_headers, patient_headers, second_patient_headers
):
    doctor, service = _setup_verified_doctor(client, doctor_headers, admin_headers)
    day = _next_weekday_date(3)
    payload = {
        "doctor_id": doctor["id"],
        "service_id": service["id"],
        "appointment_date": day,
        "appointment_time": "11:00",
    }
    first = client.post("/api/v1/appointments", json=payload, headers=patient_headers)
    assert first.status_code == 201
    second = client.post("/api/v1/appointments", json=payload, headers=second_patient_headers)
    assert second.status_code == 409
    assert "not available" in second.json()["detail"]


def test_slot_block_prevents_booking(client, admin_headers, doctor_headers, patient_headers):
    doctor, service = _setup_verified_doctor(client, doctor_headers, admin_headers)
    day = _next_weekday_date(4)
    blocked = client.post(
        "/api/v1/doctors/me/blocks",
        json={"block_date": day, "start_time": "10:00", "end_time": "12:00", "reason": "conference"},
        headers=doctor_headers,
    )
    assert blocked.status_code == 201
    availability = client.get(
        f"/api/v1/doctors/{doctor['id']}/availability", params={"date": day}
    ).json()
    ten = next(s for s in availability[0]["slots"] if s["time"] == "10:00")
    twelve = next(s for s in availability[0]["slots"] if s["time"] == "12:00")
    assert ten["available"] is False and "conference" in ten["reason"]
    assert twelve["available"] is True  # block ends at 12:00

    resp = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:30",
        },
        headers=patient_headers,
    )
    assert resp.status_code == 409


def test_appointment_confirm_complete_flow_and_rbac(
    client, admin_headers, doctor_headers, patient_headers, second_patient_headers
):
    doctor, service = _setup_verified_doctor(client, doctor_headers, admin_headers)
    day = _next_weekday_date(0)
    appointment = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:00",
        },
        headers=patient_headers,
    ).json()
    appointment_id = appointment["id"]

    # Doctor confirms (provider-side PATCH).
    confirmed = client.patch(
        f"/api/v1/appointments/{appointment_id}",
        json={"status": "CONFIRMED"},
        headers=doctor_headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"

    # Patient may not set provider-side statuses.
    denied = client.patch(
        f"/api/v1/appointments/{appointment_id}",
        json={"status": "COMPLETED"},
        headers=patient_headers,
    )
    assert denied.status_code == 403

    # Unrelated patient cannot even see the appointment (ownership).
    foreign_get = client.get(
        f"/api/v1/appointments/{appointment_id}", headers=second_patient_headers
    )
    assert foreign_get.status_code == 404

    # Doctor completes it.
    completed = client.patch(
        f"/api/v1/appointments/{appointment_id}",
        json={"status": "COMPLETED"},
        headers=doctor_headers,
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"

    # Terminal state: no further transitions.
    zombie = client.patch(
        f"/api/v1/appointments/{appointment_id}",
        json={"status": "CANCELLED"},
        headers=doctor_headers,
    )
    assert zombie.status_code == 409


def test_invalid_state_transition_rejected(client, admin_headers, doctor_headers, patient_headers):
    doctor, service = _setup_verified_doctor(client, doctor_headers, admin_headers)
    day = _next_weekday_date(2)
    appointment = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:00",
        },
        headers=patient_headers,
    ).json()
    # REQUESTED -> COMPLETED is not a legal transition.
    resp = client.patch(
        f"/api/v1/appointments/{appointment['id']}",
        json={"status": "COMPLETED"},
        headers=doctor_headers,
    )
    assert resp.status_code == 409


def test_cancel_and_reschedule(client, admin_headers, doctor_headers, patient_headers):
    doctor, service = _setup_verified_doctor(client, doctor_headers, admin_headers)
    day1 = _next_weekday_date(1)
    day2 = _next_weekday_date(2)
    appointment = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day1,
            "appointment_time": "11:00",
        },
        headers=patient_headers,
    ).json()

    # Patient reschedules to another free slot.
    moved = client.post(
        f"/api/v1/appointments/{appointment['id']}/reschedule",
        json={"appointment_date": day2, "appointment_time": "11:30"},
        headers=patient_headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["appointment_date"] == day2
    assert moved.json()["appointment_time"] == "11:30"

    # Old slot is free again; new slot is taken.
    availability = client.get(
        f"/api/v1/doctors/{doctor['id']}/availability", params={"date": day1}
    ).json()
    assert next(s for s in availability[0]["slots"] if s["time"] == "11:00")["available"] is True

    # Cancel frees the new slot.
    cancelled = client.post(f"/api/v1/appointments/{appointment['id']}/cancel", headers=patient_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    availability2 = client.get(
        f"/api/v1/doctors/{doctor['id']}/availability", params={"date": day2}
    ).json()
    assert next(s for s in availability2[0]["slots"] if s["time"] == "11:30")["available"] is True

    # Cannot reschedule a cancelled appointment.
    late = client.post(
        f"/api/v1/appointments/{appointment['id']}/reschedule",
        json={"appointment_date": day2, "appointment_time": "12:00"},
        headers=patient_headers,
    )
    assert late.status_code == 409


def test_appointment_listing_scoped_by_role(
    client, admin_headers, doctor_headers, patient_headers, second_patient_headers
):
    doctor, service = _setup_verified_doctor(client, doctor_headers, admin_headers)
    day = _next_weekday_date(3)
    client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:00",
        },
        headers=patient_headers,
    )
    mine = client.get("/api/v1/appointments", headers=patient_headers).json()
    assert len(mine) == 1
    other = client.get("/api/v1/appointments", headers=second_patient_headers).json()
    assert other == []
    doctor_view = client.get("/api/v1/appointments", params={"role": "doctor"}, headers=doctor_headers).json()
    assert len(doctor_view) == 1


def test_booking_audited(client, admin_headers, doctor_headers, patient_headers):
    doctor, service = _setup_verified_doctor(client, doctor_headers, admin_headers)
    day = _next_weekday_date(4)
    appointment = client.post(
        "/api/v1/appointments",
        json={
            "doctor_id": doctor["id"],
            "service_id": service["id"],
            "appointment_date": day,
            "appointment_time": "10:00",
        },
        headers=patient_headers,
    ).json()
    client.post(f"/api/v1/appointments/{appointment['id']}/cancel", headers=patient_headers)
    logs = client.get("/api/v1/admin/audit-logs", headers=admin_headers).json()
    actions = {log["action"] for log in logs}
    assert {"APPOINTMENT_BOOKED", "APPOINTMENT_CANCELLED", "AVAILABILITY_CHANGE"} <= actions
