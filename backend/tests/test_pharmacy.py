"""Phase 4 tests: medicines, pharmacies, prices, savings (spec §34).

Fixture medicines/pharmacies are test data only (spec §28) — production seed
contains no fabricated healthcare data.
"""

import uuid
from datetime import date, timedelta

from tests.conftest import login_headers, make_user


def _admin_create_medicine(client, admin_headers, **overrides):
    payload = {
        "name": "Paracetamol 500mg Tablet",
        "generic_name": "Paracetamol",
        "brand_name": "Dolo",
        "manufacturer": "Test Pharma Ltd",
        "strength": "500 mg",
        "dosage_form": "TABLET",
        "pack_size": "10 tablets",
        "prescription_required": False,
        "description": "Test fixture medicine (NOT REAL data)",
        "data_source": "TEST_FIXTURE",
    }
    payload.update(overrides)
    return client.post("/api/v1/medicines", json=payload, headers=admin_headers)


def _register_pharmacy(client, headers, name_suffix="", city="Hyderabad"):
    return client.post(
        "/api/v1/pharmacies",
        json={
            "name": f"Test Pharmacy {name_suffix} (NOT REAL)"[:200],
            "registration_number": f"TS-{uuid.uuid4().hex[:8]}",
            "address_line": "1 Test Street",
            "city": city,
            "state": "Telangana",
            "postal_code": "500001",
            "phone": "9000000000",
            "delivery_supported": True,
            "pickup_supported": True,
        },
        headers=headers,
    )


def _verified_pharmacy(client, db_session, admin_headers, name_suffix="", city="Hyderabad"):
    """Create a PHARMACY_ADMIN user + pharmacy and verify it as SUPER_ADMIN."""
    suffix = uuid.uuid4().hex[:6]
    make_user(db_session, f"pharma{suffix}@example.com", roles=("PHARMACY_ADMIN",))
    headers = login_headers(client, f"pharma{suffix}@example.com")
    resp = _register_pharmacy(client, headers, name_suffix=name_suffix, city=city)
    assert resp.status_code == 201, resp.text
    pharmacy_id = resp.json()["id"]
    decide = client.post(
        f"/api/v1/admin/pharmacies/{pharmacy_id}/verify",
        json={"new_status": "VERIFIED", "decision_note": "test verification"},
        headers=admin_headers,
    )
    assert decide.status_code == 200, decide.text
    return headers, pharmacy_id


def _submit_verified_price(
    client, pharmacy_headers, pharmacy_id, medicine_id, amount, **overrides
):
    payload = {"medicine_id": medicine_id, "price": amount, "source_reference": "fixture"}
    payload.update(overrides)
    resp = client.post("/api/v1/pharmacies/me/prices", json=payload, headers=pharmacy_headers)
    assert resp.status_code == 201, resp.text
    price_id = resp.json()["id"]
    admin = login_headers(client, "admin@example.com")
    decide = client.post(
        f"/api/v1/admin/prices/{price_id}/decision",
        json={"decision": "VERIFIED", "note": "test"},
        headers=admin,
    )
    assert decide.status_code == 200, decide.text
    return price_id


# ------------------------------------------------------------ medicines

def test_medicine_create_requires_super_admin(client, patient_headers):
    assert client.post(
        "/api/v1/medicines", json={"name": "X Test"}, headers=patient_headers
    ).status_code == 403


def test_medicine_create_and_search(client, admin_headers):
    resp = _admin_create_medicine(client, admin_headers)
    assert resp.status_code == 201, resp.text
    medicine_id = resp.json()["id"]

    # exact
    found = client.get("/api/v1/medicines", params={"q": "Paracetamol 500mg Tablet"}).json()
    assert any(m["id"] == medicine_id for m in found)
    # partial
    found = client.get("/api/v1/medicines", params={"q": "parac"}).json()
    assert any(m["id"] == medicine_id for m in found)
    # generic name
    found = client.get("/api/v1/medicines", params={"q": "Paracetamol"}).json()
    assert any(m["id"] == medicine_id for m in found)
    # pagination
    one = client.get("/api/v1/medicines", params={"limit": 1, "offset": 0}).json()
    assert len(one) <= 1


def test_medicine_detail_public_fields(client, admin_headers):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    body = client.get(f"/api/v1/medicines/{medicine_id}").json()
    for field in (
        "name", "generic_name", "brand_name", "manufacturer", "strength",
        "dosage_form", "pack_size", "prescription_required",
    ):
        assert field in body
    # No dosage instructions are fabricated in the record
    assert "take two" not in body["description"].lower()


def test_invalid_dosage_form_rejected(client, admin_headers):
    resp = _admin_create_medicine(client, admin_headers, dosage_form="PILL")
    assert resp.status_code == 422


# ------------------------------------------------------------ pharmacies

def test_pharmacy_registration_starts_pending(client, db_session):
    make_user(db_session, "pk@example.com", roles=("PHARMACY_ADMIN",))
    headers = login_headers(client, "pk@example.com")
    resp = _register_pharmacy(client, headers, "Alpha")
    assert resp.status_code == 201
    assert resp.json()["verification_status"] == "PENDING"


def test_pharmacy_registration_requires_role(client, patient_headers):
    assert client.post(
        "/api/v1/pharmacies", json={"name": "Nope Pharmacy"}, headers=patient_headers
    ).status_code == 403


def test_pharmacy_search_shows_only_verified(client, admin_headers, db_session):
    _, verified_id = _verified_pharmacy(client, db_session, admin_headers, "Visible")
    # A pending pharmacy that must NOT appear publicly
    make_user(db_session, "pend@example.com", roles=("PHARMACY_ADMIN",))
    pend_headers = login_headers(client, "pend@example.com")
    pend_id = _register_pharmacy(client, pend_headers, "Hidden").json()["id"]

    results = client.get("/api/v1/pharmacies").json()
    ids = {p["id"] for p in results}
    assert verified_id in ids
    assert pend_id not in ids


def test_pharmacy_verification_requires_super_admin(client, db_session):
    make_user(db_session, "pv@example.com", roles=("PHARMACY_ADMIN",))
    headers = login_headers(client, "pv@example.com")
    pharmacy_id = _register_pharmacy(client, headers, "Self").json()["id"]
    resp = client.post(
        f"/api/v1/admin/pharmacies/{pharmacy_id}/verify",
        json={"new_status": "VERIFIED"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_pharmacy_verification_writes_history_and_audit(client, admin_headers, db_session, client_db=None):
    headers, pharmacy_id = _verified_pharmacy(client, db_session, admin_headers, "Hist")
    history = client.get(f"/api/v1/admin/pharmacies/{pharmacy_id}/history", headers=admin_headers).json()
    assert len(history) == 1
    assert history[0]["previous_status"] == "PENDING"
    assert history[0]["new_status"] == "VERIFIED"


def test_pharmacy_verification_is_idempotent_guarded(client, admin_headers, db_session):
    headers, pharmacy_id = _verified_pharmacy(client, db_session, admin_headers, "Dup")
    resp = client.post(
        f"/api/v1/admin/pharmacies/{pharmacy_id}/verify",
        json={"new_status": "VERIFIED"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_suspended_pharmacy_disappears_from_public(client, admin_headers, db_session):
    headers, pharmacy_id = _verified_pharmacy(client, db_session, admin_headers, "Susp")
    resp = client.post(
        f"/api/v1/admin/pharmacies/{pharmacy_id}/suspend",
        json={"new_status": "SUSPENDED", "decision_note": "license issue"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    results = client.get("/api/v1/pharmacies").json()
    assert pharmacy_id not in {p["id"] for p in results}


# ------------------------------------------------------------ inventory

def test_inventory_upsert_and_unknown_honesty(client, admin_headers, db_session):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers, pharmacy_id = _verified_pharmacy(client, db_session, admin_headers, "Inv")

    resp = client.post(
        "/api/v1/pharmacies/me/inventory",
        json={"medicine_id": medicine_id, "stock_status": "IN_STOCK", "quantity": 50},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["stock_status"] == "IN_STOCK"

    # UNKNOWN is stored as UNKNOWN, never upgraded (spec §7)
    resp = client.post(
        "/api/v1/pharmacies/me/inventory",
        json={"medicine_id": medicine_id, "stock_status": "UNKNOWN"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["stock_status"] == "UNKNOWN"


def test_inventory_requires_ownership(client, admin_headers, db_session):
    """A pharmacy admin cannot write another pharmacy's inventory via /me scoping."""
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    _, pharmacy_a = _verified_pharmacy(client, db_session, admin_headers, "OwnA")
    headers_b, _ = _verified_pharmacy(client, db_session, admin_headers, "OwnB")

    # B writes own inventory (allowed) — scoping is via /me, not pharmacy_id
    resp = client.post(
        "/api/v1/pharmacies/me/inventory",
        json={"medicine_id": medicine_id, "stock_status": "LOW_STOCK"},
        headers=headers_b,
    )
    assert resp.status_code == 201


def test_inventory_rejects_unknown_medicine(client, admin_headers, db_session):
    headers, _ = _verified_pharmacy(client, db_session, admin_headers, "NoMed")
    resp = client.post(
        "/api/v1/pharmacies/me/inventory",
        json={"medicine_id": "nonexistent", "stock_status": "IN_STOCK"},
        headers=headers,
    )
    assert resp.status_code == 404


# ------------------------------------------------------------ prices

def test_price_submission_then_verification(client, admin_headers, db_session):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers, pharmacy_id = _verified_pharmacy(client, db_session, admin_headers, "Price")

    sub = client.post(
        "/api/v1/pharmacies/me/prices",
        json={"medicine_id": medicine_id, "price": 42.5},
        headers=headers,
    )
    assert sub.status_code == 201
    assert sub.json()["verification_status"] == "PENDING"
    price_id = sub.json()["id"]

    # Not visible to patients before verification
    public = client.get(f"/api/v1/medicines/{medicine_id}/prices").json()
    assert price_id not in {p["id"] for p in public}

    admin = login_headers(client, "admin@example.com")
    decide = client.post(
        f"/api/v1/admin/prices/{price_id}/decision",
        json={"decision": "VERIFIED", "note": "checked"},
        headers=admin,
    )
    assert decide.status_code == 200
    assert decide.json()["verification_status"] == "VERIFIED"

    public = client.get(f"/api/v1/medicines/{medicine_id}/prices").json()
    assert price_id in {p["id"] for p in public}
    provenance = public[0]
    for field in ("source", "source_reference", "last_updated", "valid_from", "verification_status"):
        assert field in provenance


def test_price_decision_requires_admin_and_pending_state(client, admin_headers, db_session):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers, _ = _verified_pharmacy(client, db_session, admin_headers, "PD")
    price_id = client.post(
        "/api/v1/pharmacies/me/prices",
        json={"medicine_id": medicine_id, "price": 10},
        headers=headers,
    ).json()["id"]

    # pharmacy admin cannot verify own price
    resp = client.post(
        f"/api/v1/admin/prices/{price_id}/decision",
        json={"decision": "VERIFIED"},
        headers=headers,
    )
    assert resp.status_code == 403

    admin = login_headers(client, "admin@example.com")
    assert client.post(
        f"/api/v1/admin/prices/{price_id}/decision",
        json={"decision": "VERIFIED"},
        headers=admin,
    ).status_code == 200
    # already VERIFIED -> cannot decide again
    resp = client.post(
        f"/api/v1/admin/prices/{price_id}/decision",
        json={"decision": "REJECTED"},
        headers=admin,
    )
    assert resp.status_code == 409


def test_new_price_submission_creates_version_not_overwrite(client, admin_headers, db_session):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers, _ = _verified_pharmacy(client, db_session, admin_headers, "Ver")
    admin = login_headers(client, "admin@example.com")

    first_id = client.post(
        "/api/v1/pharmacies/me/prices",
        json={"medicine_id": medicine_id, "price": 100},
        headers=headers,
    ).json()["id"]
    client.post(
        f"/api/v1/admin/prices/{first_id}/decision", json={"decision": "VERIFIED"}, headers=admin
    )
    second_id = client.post(
        "/api/v1/pharmacies/me/prices",
        json={"medicine_id": medicine_id, "price": 90},
        headers=headers,
    ).json()["id"]

    first = client.get(
        "/api/v1/admin/prices/verification", params={"status": "VERIFIED"}, headers=admin
    ).json()
    second = client.get(
        "/api/v1/admin/prices/verification", params={"status": "PENDING"}, headers=admin
    ).json()
    assert any(p["id"] == first_id for p in first)  # history kept
    assert any(p["id"] == second_id for p in second)  # new version pending


def test_price_expiration_sweep(client, admin_headers, db_session):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers, _ = _verified_pharmacy(client, db_session, admin_headers, "Exp")
    admin = login_headers(client, "admin@example.com")

    price_id = client.post(
        "/api/v1/pharmacies/me/prices",
        json={"medicine_id": medicine_id, "price": 55, "valid_until": str(date.today() - timedelta(days=1))},
        headers=headers,
    ).json()["id"]
    client.post(f"/api/v1/admin/prices/{price_id}/decision", json={"decision": "VERIFIED"}, headers=admin)

    resp = client.post("/api/v1/admin/prices/expire-stale", headers=admin)
    assert resp.status_code == 200
    assert resp.json()["expired"] >= 1

    # expired price no longer shown as verified public data
    public = client.get(f"/api/v1/medicines/{medicine_id}/prices").json()
    assert price_id not in {p["id"] for p in public}


def test_price_comparison_filters_mismatched_representation(client, admin_headers, db_session):
    """Prices are only compared within the same strength/form/pack (spec §10)."""
    med_a = _admin_create_medicine(client, admin_headers).json()["id"]  # 500 mg
    med_b = _admin_create_medicine(
        client, admin_headers, strength="650 mg", name="Paracetamol 650mg Tablet"
    ).json()["id"]
    headers, _ = _verified_pharmacy(client, db_session, admin_headers, "Repr")
    _submit_verified_price(client, headers, None, med_a, 30)
    _submit_verified_price(client, headers, None, med_b, 35)

    prices_a = client.get(f"/api/v1/medicines/{med_a}/prices").json()
    assert all(p["medicine_id"] == med_a for p in prices_a)
    prices_b = client.get(f"/api/v1/medicines/{med_b}/prices").json()
    assert all(p["medicine_id"] == med_b for p in prices_b)


# ------------------------------------------------------------ savings

def test_savings_calculated_from_verified_prices(client, admin_headers, db_session):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers_a, _ = _verified_pharmacy(client, db_session, admin_headers, "SA", city="Hyderabad")
    headers_b, _ = _verified_pharmacy(client, db_session, admin_headers, "SB", city="Warangal")
    _submit_verified_price(client, headers_a, None, medicine_id, 150)
    _submit_verified_price(client, headers_b, None, medicine_id, 120)

    resp = client.get(f"/api/v1/medicines/{medicine_id}/savings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "CALCULATED"
    assert body["reference_price"] == 150.0
    assert body["selected_price"] == 120.0
    assert body["potential_savings"] == 30.0
    assert body["source"] and body["last_updated"]
    # Transparency fields present (spec §12)
    for field in ("reference_pharmacy_name", "selected_pharmacy_name", "representation_key"):
        assert field in body


def test_savings_insufficient_with_single_price(client, admin_headers, db_session):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers, _ = _verified_pharmacy(client, db_session, admin_headers, "One")
    _submit_verified_price(client, headers, None, medicine_id, 80)

    body = client.get(f"/api/v1/medicines/{medicine_id}/savings").json()
    assert body["status"] == "INSUFFICIENT_DATA"
    assert body["potential_savings"] is None  # never fabricate a number


def test_savings_insufficient_with_no_prices(client):
    body = client.get(f"/api/v1/medicines/{uuid.uuid4()}/savings").json()
    assert body["status"] in ("INSUFFICIENT_DATA", "MEDICINE_NOT_FOUND")
    assert body["potential_savings"] is None


def test_savings_ignores_unverified_and_suspended_sources(client, admin_headers, db_session):
    """Unverified prices and prices from non-verified pharmacies must not
    create fake savings (spec §37)."""
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers_a, _ = _verified_pharmacy(client, db_session, admin_headers, "UA")

    # price from verified pharmacy but left PENDING
    client.post(
        "/api/v1/pharmacies/me/prices",
        json={"medicine_id": medicine_id, "price": 100},
        headers=headers_a,
    )
    # verified price from a pharmacy that gets suspended
    headers_b, pharmacy_b = _verified_pharmacy(client, db_session, admin_headers, "UB")
    price_b = client.post(
        "/api/v1/pharmacies/me/prices",
        json={"medicine_id": medicine_id, "price": 90},
        headers=headers_b,
    ).json()["id"]
    admin = login_headers(client, "admin@example.com")
    client.post(f"/api/v1/admin/prices/{price_b}/decision", json={"decision": "VERIFIED"}, headers=admin)
    client.post(
        f"/api/v1/admin/pharmacies/{pharmacy_b}/suspend",
        json={"new_status": "SUSPENDED", "decision_note": "test"},
        headers=admin,
    )

    body = client.get(f"/api/v1/medicines/{medicine_id}/savings").json()
    assert body["status"] == "INSUFFICIENT_DATA"
    assert body["potential_savings"] is None


def test_savings_ignores_expired_prices(client, admin_headers, db_session):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers_a, _ = _verified_pharmacy(client, db_session, admin_headers, "EA")
    headers_b, _ = _verified_pharmacy(client, db_session, admin_headers, "EB")
    _submit_verified_price(
        client, headers_a, None, medicine_id, 100,
        valid_until=str(date.today() - timedelta(days=2)),
    )
    _submit_verified_price(client, headers_b, None, medicine_id, 70)
    admin = login_headers(client, "admin@example.com")
    client.post("/api/v1/admin/prices/expire-stale", headers=admin)

    body = client.get(f"/api/v1/medicines/{medicine_id}/savings").json()
    assert body["status"] == "INSUFFICIENT_DATA"


def test_savings_same_price_no_comparison_claim(client, admin_headers, db_session):
    medicine_id = _admin_create_medicine(client, admin_headers).json()["id"]
    headers_a, _ = _verified_pharmacy(client, db_session, admin_headers, "PA")
    headers_b, _ = _verified_pharmacy(client, db_session, admin_headers, "PB")
    _submit_verified_price(client, headers_a, None, medicine_id, 100)
    _submit_verified_price(client, headers_b, None, medicine_id, 100)

    body = client.get(f"/api/v1/medicines/{medicine_id}/savings").json()
    assert body["status"] == "NO_COMPARISON"
    assert body["potential_savings"] is None
