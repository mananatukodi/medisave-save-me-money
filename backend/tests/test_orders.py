"""Phase 4 tests: medicine orders — state machine, price snapshots,
prescription workflow, ownership, RBAC (spec §14, §18-§20, §34)."""

import uuid

from tests.conftest import login_headers, make_user
from tests.test_pharmacy import (
    _admin_create_medicine,
    _submit_verified_price,
    _verified_pharmacy,
)


def _orderable_setup(client, db_session, admin_headers, *, prescription_required=False):
    """Verified pharmacy + verified price (+ inventory). Returns
    (patient_headers, pharmacy_headers, pharmacy_id, medicine_id)."""
    suffix = uuid.uuid4().hex[:6]
    make_user(db_session, f"ord{suffix}@example.com", roles=("PATIENT",))
    patient_headers = login_headers(client, f"ord{suffix}@example.com")
    medicine_id = _admin_create_medicine(
        client, admin_headers, prescription_required=prescription_required
    ).json()["id"]
    pharmacy_headers, pharmacy_id = _verified_pharmacy(
        client, db_session, admin_headers, f"O{suffix}"
    )
    _submit_verified_price(client, pharmacy_headers, pharmacy_id, medicine_id, 45)
    client.post(
        "/api/v1/pharmacies/me/inventory",
        json={"medicine_id": medicine_id, "stock_status": "IN_STOCK", "quantity": 100},
        headers=pharmacy_headers,
    )
    return patient_headers, pharmacy_headers, pharmacy_id, medicine_id


def _place_order(client, patient_headers, pharmacy_id, medicine_id, qty=2, pickup=True):
    return client.post(
        "/api/v1/orders",
        json={
            "pharmacy_id": pharmacy_id,
            "items": [{"medicine_id": medicine_id, "quantity": qty}],
            "pickup_option": pickup,
            "delivery_address": "" if pickup else "1 Test Road, Hyderabad",
        },
        headers=patient_headers,
    )


# ------------------------------------------------------------ creation

def test_order_happy_path(client, admin_headers, db_session):
    patient_headers, pharmacy_headers, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers
    )
    resp = _place_order(client, patient_headers, pharmacy_id, medicine_id, qty=3)
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "CONFIRMED" or order["status"] == "CREATED"
    assert order["subtotal"] == 45 * 3
    assert order["total"] == order["subtotal"]
    assert order["currency"] == "INR"
    item = order["items"][0]
    assert item["unit_price"] == 45.0
    assert item["price_snapshot_id"]  # snapshot recorded
    assert item["snapshot_verification_status"] == "VERIFIED"
    assert item["medicine_name"]  # name snapshot present


def test_order_requires_verified_pharmacy(client, admin_headers, db_session):
    """Orders at PENDING pharmacies are refused (spec §5, §18)."""
    suffix = uuid.uuid4().hex[:6]
    make_user(db_session, f"pend{suffix}@example.com", roles=("PHARMACY_ADMIN",))
    pend_headers = login_headers(client, f"pend{suffix}@example.com")
    pend_id = client.post(
        "/api/v1/pharmacies",
        json={"name": "Pending Pharma (NOT REAL)"},
        headers=pend_headers,
    ).json()["id"]
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]

    make_user(db_session, "cust@example.com", roles=("PATIENT",))
    patient = login_headers(client, "cust@example.com")
    resp = _place_order(client, patient, pend_id, medicine_id)
    assert resp.status_code == 409


def test_order_requires_verified_price(client, admin_headers, db_session):
    """No ordering without a verified price — never an invented price (spec §37)."""
    make_user(db_session, "cust2@example.com", roles=("PATIENT",))
    patient = login_headers(client, "cust2@example.com")
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    _, pharmacy_id = _verified_pharmacy(client, db_session, admin_headers, "NoPrice")
    resp = _place_order(client, patient, pharmacy_id, medicine_id)
    assert resp.status_code == 409


def test_order_blocked_when_out_of_stock(client, admin_headers, db_session):
    patient_headers, pharmacy_headers, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers
    )
    client.post(
        "/api/v1/pharmacies/me/inventory",
        json={"medicine_id": medicine_id, "stock_status": "OUT_OF_STOCK"},
        headers=pharmacy_headers,
    )
    resp = _place_order(client, patient_headers, pharmacy_id, medicine_id)
    assert resp.status_code == 409
    assert "out of stock" in resp.json()["detail"].lower()


def test_order_respects_pharmacy_delivery_capability(client, admin_headers, db_session):
    suffix = uuid.uuid4().hex[:6]
    make_user(db_session, f"pu{suffix}@example.com", roles=("PATIENT",))
    patient = login_headers(client, f"pu{suffix}@example.com")
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    # Register a pickup-only pharmacy and verify it
    make_user(db_session, f"pp{suffix}@example.com", roles=("PHARMACY_ADMIN",))
    ph_headers = login_headers(client, f"pp{suffix}@example.com")
    resp = client.post(
        "/api/v1/pharmacies",
        json={
            "name": f"PickupOnly {suffix} (NOT REAL)",
            "pickup_supported": True,
            "delivery_supported": False,
        },
        headers=ph_headers,
    )
    assert resp.status_code == 201, resp.text
    pharmacy_id = resp.json()["id"]
    admin = login_headers(client, "admin@example.com")
    assert client.post(
        f"/api/v1/admin/pharmacies/{pharmacy_id}/verify",
        json={"new_status": "VERIFIED"},
        headers=admin,
    ).status_code == 200
    _submit_verified_price(client, ph_headers, pharmacy_id, medicine_id, 30)

    # Pickup-only pharmacy: delivery order must be refused
    resp = _place_order(client, patient, pharmacy_id, medicine_id, pickup=False)
    assert resp.status_code == 422


# ------------------------------------------------- prescription workflow

def test_prescription_required_order_pauses(client, admin_headers, db_session):
    """Rx-required medicine never bypasses the prescription gate (spec §14)."""
    patient_headers, pharmacy_headers, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers, prescription_required=True
    )
    resp = _place_order(client, patient_headers, pharmacy_id, medicine_id)
    assert resp.status_code == 201
    order = resp.json()
    assert order["status"] == "PRESCRIPTION_REQUIRED"


def test_prescription_workflow_to_confirmation(client, admin_headers, db_session):
    patient_headers, pharmacy_headers, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers, prescription_required=True
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id).json()["id"]

    # Cannot confirm directly while awaiting prescription
    resp = client.patch(
        f"/api/v1/orders/{order_id}", json={"status": "CONFIRMED"}, headers=pharmacy_headers
    )
    assert resp.status_code == 409

    # Patient submits prescription document reference
    sub = client.post(
        f"/api/v1/orders/{order_id}/prescription",
        json={"document_ref": "records/prescription-test.pdf"},
        headers=patient_headers,
    )
    assert sub.status_code == 201, sub.text

    # Pharmacy reviews and approves -> CONFIRMED (human decision, audited)
    resp = client.post(
        f"/api/v1/orders/{order_id}/prescription-review",
        json={"approved": True, "note": "verified by pharmacist"},
        headers=pharmacy_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CONFIRMED"


def test_prescription_rejection_cancels_order(client, admin_headers, db_session):
    patient_headers, pharmacy_headers, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers, prescription_required=True
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id).json()["id"]
    client.post(
        f"/api/v1/orders/{order_id}/prescription",
        json={"document_ref": "records/bad.pdf"},
        headers=patient_headers,
    )
    resp = client.post(
        f"/api/v1/orders/{order_id}/prescription-review",
        json={"approved": False, "note": "invalid prescription"},
        headers=pharmacy_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_prescription_submit_requires_owner(client, admin_headers, db_session):
    patient_headers, _, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers, prescription_required=True
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id).json()["id"]

    make_user(db_session, "other@example.com", roles=("PATIENT",))
    other = login_headers(client, "other@example.com")
    resp = client.post(
        f"/api/v1/orders/{order_id}/prescription",
        json={"document_ref": "records/x.pdf"},
        headers=other,
    )
    assert resp.status_code == 404  # existence hidden from non-owners


# ---------------------------------------------------------- state machine

def test_order_state_machine_valid_path(client, admin_headers, db_session):
    patient_headers, pharmacy_headers, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id).json()["id"]

    for status in ("CONFIRMED", "PROCESSING", "READY_FOR_PICKUP", "DELIVERED"):
        resp = client.patch(
            f"/api/v1/orders/{order_id}", json={"status": status}, headers=pharmacy_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == status


def test_order_state_machine_rejects_invalid_transitions(client, admin_headers, db_session):
    patient_headers, pharmacy_headers, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id).json()["id"]

    # CREATED -> DELIVERED is invalid
    resp = client.patch(
        f"/api/v1/orders/{order_id}", json={"status": "DELIVERED"}, headers=pharmacy_headers
    )
    assert resp.status_code == 409
    # CREATED -> OUT_FOR_DELIVERY is invalid
    resp = client.patch(
        f"/api/v1/orders/{order_id}", json={"status": "OUT_FOR_DELIVERY"}, headers=pharmacy_headers
    )
    assert resp.status_code == 409


def test_terminal_state_is_frozen(client, admin_headers, db_session):
    patient_headers, pharmacy_headers, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id).json()["id"]
    for status in ("CONFIRMED", "PROCESSING", "READY_FOR_PICKUP", "DELIVERED"):
        resp = client.patch(
            f"/api/v1/orders/{order_id}", json={"status": status}, headers=pharmacy_headers
        )
        assert resp.status_code == 200, resp.text
    # Terminal: nothing further is allowed
    resp = client.patch(
        f"/api/v1/orders/{order_id}", json={"status": "CANCELLED"}, headers=pharmacy_headers
    )
    assert resp.status_code == 409


def test_patient_can_cancel_own_created_order(client, admin_headers, db_session):
    patient_headers, _, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id).json()["id"]
    resp = client.patch(f"/api/v1/orders/{order_id}", json={"status": "CANCELLED"}, headers=patient_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_patient_cannot_confirm_own_order(client, admin_headers, db_session):
    patient_headers, _, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id).json()["id"]
    resp = client.patch(f"/api/v1/orders/{order_id}", json={"status": "CONFIRMED"}, headers=patient_headers)
    assert resp.status_code == 403


# --------------------------------------------------- ownership & history

def test_patient_sees_only_own_orders(client, admin_headers, db_session):
    patient_headers, _, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id).json()["id"]

    make_user(db_session, "stranger@example.com", roles=("PATIENT",))
    stranger = login_headers(client, "stranger@example.com")

    mine = client.get("/api/v1/orders", headers=patient_headers).json()
    assert any(o["id"] == order_id for o in mine)
    theirs = client.get("/api/v1/orders", headers=stranger).json()
    assert all(o["id"] != order_id for o in theirs)
    # Detail endpoint hides existence (404, not 403)
    assert client.get(f"/api/v1/orders/{order_id}", headers=stranger).status_code == 404


def test_order_history_survives_price_change(client, admin_headers, db_session):
    """Historical order prices never change when catalog prices change (spec §19)."""
    patient_headers, pharmacy_headers, pharmacy_id, medicine_id = _orderable_setup(
        client, db_session, admin_headers
    )
    order_id = _place_order(client, patient_headers, pharmacy_id, medicine_id, qty=1).json()["id"]
    original = client.get(f"/api/v1/orders/{order_id}", headers=patient_headers).json()
    assert original["items"][0]["unit_price"] == 45.0

    # Submit + verify a NEW price version (50) — old order snapshot unchanged
    _submit_verified_price(client, pharmacy_headers, pharmacy_id, medicine_id, 50)
    after = client.get(f"/api/v1/orders/{order_id}", headers=patient_headers).json()
    assert after["items"][0]["unit_price"] == 45.0

    # And the public comparison now shows the new verified price
    prices = client.get(f"/api/v1/medicines/{medicine_id}/prices").json()
    assert {p["price"] for p in prices} == {50.0}


def test_orders_require_authentication(client):
    assert client.get("/api/v1/orders").status_code == 401
    assert client.post("/api/v1/orders", json={}).status_code == 401
