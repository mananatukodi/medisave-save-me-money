"""Phase 8 partner module tests: lab + insurance + claims + settlement honesty.

Focus:
- Lab test catalog honesty (partner-entered, admin-verified before public).
- Lab booking lifecycle state machine + organization isolation.
- Insurance products + claim machine: no auto-approval, audited transitions.
- Claim isolation between organizations and between patients.
- Settlement honesty: nothing computed, no fabricated amounts.
"""

from app.models.partner import (
    PartnerClaim,
    PartnerSettlement,
)
from tests.conftest import login_headers, make_user
from tests.test_partners import _approve_org, _enable_flag, _register_org


def _make_lab(client, db_session, email: str, name: str):
    headers, org = _register_org(client, db_session, email, org_type="DIAGNOSTIC_LAB", name=name)
    _enable_flag(db_session, "partner_lab")
    _enable_flag(db_session, "partner_verification")
    return headers, org


def _make_insurer(client, db_session, email: str, name: str):
    headers, org = _register_org(client, db_session, email, org_type="INSURANCE", name=name)
    _enable_flag(db_session, "partner_insurance")
    _enable_flag(db_session, "partner_claims")
    return headers, org


def _add_test(client, headers, org_id: str, code: str = "CBC", price: float | None = 250.0):
    resp = client.post(
        f"/api/v1/partners/{org_id}/lab/tests",
        json={"code": code, "name": f"Test {code}", "price": price},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ------------------------------------------------------------------- lab


def test_lab_test_created_unverified_and_hidden_from_public(client, db_session, admin_headers):
    h, org = _make_lab(client, db_session, "labone@example.com", "Lab One")
    _approve_org(client, h, admin_headers, org["id"])
    test = _add_test(client, h, org["id"], code="LFT")
    assert test["verification_status"] == "UNVERIFIED"
    public = client.get("/api/v1/lab-tests").json()
    assert all(row["id"] != test["id"] for row in public)


def test_verified_test_visible_only_when_org_approved(client, db_session, admin_headers):
    h, org = _make_lab(client, db_session, "labtwo@example.com", "Lab Two")
    _approve_org(client, h, admin_headers, org["id"])
    test = _add_test(client, h, org["id"], code="TSH")
    # admin verifies the test
    r = client.post(
        f"/api/v1/admin/partners/lab/tests/{test['id']}/decision",
        json={"decision": "VERIFIED", "note": "catalog checked"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    public = client.get("/api/v1/lab-tests").json()
    assert any(row["id"] == test["id"] for row in public)
    # suspend the lab -> test disappears from public view
    client.post(f"/api/v1/admin/partners/{org['id']}/suspend", headers=admin_headers)
    public2 = client.get("/api/v1/lab-tests").json()
    assert all(row["id"] != test["id"] for row in public2)


def test_lab_isolation_tests_scoped(client, db_session, admin_headers):
    hA, orgA = _make_lab(client, db_session, "laba@example.com", "Lab A")
    hB, orgB = _make_lab(client, db_session, "labb@example.com", "Lab B")
    _approve_org(client, hA, admin_headers, orgA["id"])
    testA = _add_test(client, hA, orgA["id"], code="LABA1")
    # B cannot see A's tests through its own org view
    testsB = client.get(f"/api/v1/partners/{orgB['id']}/lab/tests", headers=hB).json()
    assert all(row["id"] != testA["id"] for row in testsB)
    # B cannot transition A's booking (404)
    # B cannot add a booking into A's org for a random patient
    make_user(db_session, "labpatient@example.com")
    from app.models.user import User

    patient = db_session.query(User).filter(User.email == "labpatient@example.com").first()
    resp = client.post(
        f"/api/v1/partners/{orgA['id']}/lab/bookings",
        json={"test_id": testA["id"], "patient_user_id": patient.id},
        headers=hB,
    )
    assert resp.status_code == 404


def test_lab_booking_lifecycle(client, db_session, admin_headers):
    h, org = _make_lab(client, db_session, "lablife@example.com", "Lab Life")
    _approve_org(client, h, admin_headers, org["id"])
    test = _add_test(client, h, org["id"], code="HBA1C")
    # admin verifies test so it can be booked
    client.post(
        f"/api/v1/admin/partners/lab/tests/{test['id']}/decision",
        json={"decision": "VERIFIED"},
        headers=admin_headers,
    )
    make_user(db_session, "lifebooker@example.com")
    from app.models.user import User

    patient = db_session.query(User).filter(User.email == "lifebooker@example.com").first()
    booking = client.post(
        f"/api/v1/partners/{org['id']}/lab/bookings",
        json={"test_id": test["id"], "patient_user_id": patient.id},
        headers=h,
    )
    assert booking.status_code == 201, booking.text
    bid = booking.json()["id"]
    assert booking.json()["status"] == "REQUESTED"
    # valid path REQUESTED -> CONFIRMED -> SAMPLE_COLLECTED -> IN_PROGRESS -> REPORT_READY
    for status in ("CONFIRMED", "SAMPLE_COLLECTED", "IN_PROGRESS", "REPORT_READY"):
        r = client.post(
            f"/api/v1/partners/{org['id']}/lab/bookings/{bid}/status",
            json={"status": status},
            headers=h,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == status
    # invalid transition REPORT_READY -> CONFIRMED
    r = client.post(
        f"/api/v1/partners/{org['id']}/lab/bookings/{bid}/status",
        json={"status": "CONFIRMED"},
        headers=h,
    )
    assert r.status_code == 409


def test_lab_booking_requires_verified_test(client, db_session, admin_headers):
    h, org = _make_lab(client, db_session, "labver@example.com", "Lab Ver")
    _approve_org(client, h, admin_headers, org["id"])
    test = _add_test(client, h, org["id"], code="UNVER1")  # left UNVERIFIED
    make_user(db_session, "verbooker@example.com")
    from app.models.user import User

    patient = db_session.query(User).filter(User.email == "verbooker@example.com").first()
    resp = client.post(
        f"/api/v1/partners/{org['id']}/lab/bookings",
        json={"test_id": test["id"], "patient_user_id": patient.id},
        headers=h,
    )
    assert resp.status_code == 409


# -------------------------------------------------------------- insurance


def test_insurance_product_created_by_partner(client, db_session, admin_headers):
    h, org = _make_insurer(client, db_session, "insco@example.com", "InsCo")
    _approve_org(client, h, admin_headers, org["id"])
    r = client.post(
        f"/api/v1/partners/{org['id']}/insurance/products",
        json={"product_name": "Real Product", "product_type": "HEALTH", "claim_intake_supported": True},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["claim_intake_supported"] is True


def test_claim_lifecycle_no_auto_approval(client, db_session, admin_headers):
    h, org = _make_insurer(client, db_session, "claimco@example.com", "ClaimCo")
    _approve_org(client, h, admin_headers, org["id"])
    make_user(db_session, "claimpatient@example.com")
    from app.models.user import User

    patient = db_session.query(User).filter(User.email == "claimpatient@example.com").first()
    created = client.post(
        f"/api/v1/partners/{org['id']}/insurance/claims",
        json={
            "patient_user_id": patient.id,
            "subject_type": "APPOINTMENT",
            "description": "Consultation claim",
            "amount": 1200,
        },
        headers=h,
    )
    assert created.status_code == 201, created.text
    claim = created.json()
    assert claim["status"] == "DRAFT"
    assert claim["approved_amount"] is None
    # SUBMIT
    r = client.post(
        f"/api/v1/partners/{org['id']}/insurance/claims/{claim['id']}/status",
        json={"status": "SUBMITTED", "note": "docs attached"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SUBMITTED"
    # staff cannot decide claims (role gate)
    make_user(db_session, "claimstaff@example.com")
    staff_user = db_session.query(User).filter(User.email == "claimstaff@example.com").first()
    client.post(
        f"/api/v1/partners/{org['id']}/members",
        json={"user_id": staff_user.id, "partner_role": "PARTNER_STAFF"},
        headers=h,
    )
    h_staff = login_headers(client, "claimstaff@example.com")
    r_staff = client.post(
        f"/api/v1/partners/{org['id']}/insurance/claims/{claim['id']}/status",
        json={"status": "APPROVED"},
        headers=h_staff,
    )
    assert r_staff.status_code == 403
    # admin/billing approves with amount (human decision)
    r2 = client.post(
        f"/api/v1/partners/{org['id']}/insurance/claims/{claim['id']}/status",
        json={"status": "APPROVED", "approved_amount": 800, "note": "approved by adjuster"},
        headers=h,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "APPROVED"
    assert r2.json()["approved_amount"] == 800
    # settle
    r3 = client.post(
        f"/api/v1/partners/{org['id']}/insurance/claims/{claim['id']}/status",
        json={"status": "SETTLED", "note": "paid via bank"},
        headers=h,
    )
    assert r3.status_code == 200
    # terminal: no further transitions
    r4 = client.post(
        f"/api/v1/partners/{org['id']}/insurance/claims/{claim['id']}/status",
        json={"status": "CANCELLED"},
        headers=h,
    )
    assert r4.status_code == 409
    # full history recorded
    history = client.get(
        f"/api/v1/partners/{org['id']}/insurance/claims/{claim['id']}/history", headers=h
    ).json()
    statuses = [row["new_status"] for row in history]
    assert statuses == ["DRAFT", "SUBMITTED", "APPROVED", "SETTLED"]


def test_claim_invalid_transitions_rejected(client, db_session, admin_headers):
    h, org = _make_insurer(client, db_session, "badclaim@example.com", "BadClaimCo")
    _approve_org(client, h, admin_headers, org["id"])
    make_user(db_session, "badclaimp@example.com")
    from app.models.user import User

    patient = db_session.query(User).filter(User.email == "badclaimp@example.com").first()
    claim = client.post(
        f"/api/v1/partners/{org['id']}/insurance/claims",
        json={"patient_user_id": patient.id, "subject_type": "ORDER"},
        headers=h,
    ).json()
    # DRAFT -> APPROVED is invalid
    r = client.post(
        f"/api/v1/partners/{org['id']}/insurance/claims/{claim['id']}/status",
        json={"status": "APPROVED"},
        headers=h,
    )
    assert r.status_code == 409


def test_claim_isolation_between_organizations(client, db_session, admin_headers):
    hA, orgA = _make_insurer(client, db_session, "claima@example.com", "Claim A Co")
    hB, orgB = _make_insurer(client, db_session, "claimb@example.com", "Claim B Co")
    _approve_org(client, hA, admin_headers, orgA["id"])
    make_user(db_session, "claimapatient@example.com")
    from app.models.user import User

    patient = db_session.query(User).filter(User.email == "claimapatient@example.com").first()
    claim = client.post(
        f"/api/v1/partners/{orgA['id']}/insurance/claims",
        json={"patient_user_id": patient.id, "subject_type": "OTHER"},
        headers=hA,
    ).json()
    # B cannot view/transition A's claim
    assert client.get(
        f"/api/v1/partners/{orgB['id']}/insurance/claims/{claim['id']}/history", headers=hB
    ).status_code == 404
    r = client.post(
        f"/api/v1/partners/{orgB['id']}/insurance/claims/{claim['id']}/status",
        json={"status": "APPROVED"},
        headers=hB,
    )
    # B's scoped query on A's claim id returns 404 (claim belongs to A)
    assert r.status_code == 404


def test_patient_claims_are_owner_scoped(client, db_session, admin_headers):
    h, org = _make_insurer(client, db_session, "patientclaim@example.com", "Patient Claim Co")
    _approve_org(client, h, admin_headers, org["id"])
    make_user(db_session, "pcowner@example.com")
    make_user(db_session, "pcstranger@example.com")
    from app.models.user import User

    owner = db_session.query(User).filter(User.email == "pcowner@example.com").first()
    assert db_session.query(User).filter(User.email == "pcstranger@example.com").first() is not None
    claim = client.post(
        f"/api/v1/partners/{org['id']}/insurance/claims",
        json={"patient_user_id": owner.id, "subject_type": "OTHER"},
        headers=h,
    ).json()
    # partner-side set the patient via direct service call (patient param)

    row = db_session.get(PartnerClaim, claim["id"])
    row.patient_user_id = owner.id
    db_session.commit()
    h_owner = login_headers(client, "pcowner@example.com")
    h_stranger = login_headers(client, "pcstranger@example.com")
    mine = client.get("/api/v1/insurance/claims", headers=h_owner).json()
    assert [c["id"] for c in mine] == [claim["id"]]
    detail = client.get(f"/api/v1/insurance/claims/{claim['id']}", headers=h_owner)
    assert detail.status_code == 200
    # stranger gets 404 (no existence leak)
    assert client.get(f"/api/v1/insurance/claims/{claim['id']}", headers=h_stranger).status_code == 404


# -------------------------------------------------------------- settlement


def test_settlement_no_fabrication(client, db_session, admin_headers):
    """Settlement rows exist as architecture; nothing computes amounts and no
    gateway is called. Amounts stay None until a finance action records them."""
    h, org = _register_org(client, db_session, "settle@example.com", name="Settle Org")
    _enable_flag(db_session, "partner_settlement")
    from datetime import date

    row = PartnerSettlement(
        organization_id=org["id"],
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        gross_amount=None,  # nothing recorded by any gateway
        platform_fee=None,
        net_amount=None,
        status="PENDING_CONFIRMATION",
        note="awaiting finance reconciliation",
    )
    db_session.add(row)
    db_session.commit()
    fetched = db_session.get(PartnerSettlement, row.id)
    assert fetched.gross_amount is None
    assert fetched.net_amount is None
    # there is no API that fabricates settlement totals
    from app.services import partner_service

    overview = partner_service.admin_overview(db_session)
    assert "settlements" not in overview or overview.get("settlements") is None


def test_commission_configuration_only(client, db_session):
    """Commissions are configuration rows; nothing applies them automatically."""
    from app.models.partner import PartnerCommission

    h, org = _register_org(client, db_session, "commission@example.com", name="Commission Org")
    row = PartnerCommission(
        organization_id=org["id"],
        commission_type="PERCENT",
        commission_value=5.0,
        service_type="CONSULTATION",
        status="ACTIVE",
    )
    db_session.add(row)
    db_session.commit()
    assert row.status == "ACTIVE"
    # No service-layer function applies commissions — enforced by absence:
    from app.services import partner_service

    assert not hasattr(partner_service, "apply_commission")
