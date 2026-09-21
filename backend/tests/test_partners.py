"""Phase 8 partner ecosystem tests: onboarding, lifecycle, membership, RBAC,
ORGANIZATION ISOLATION (BOLA/IDOR), documents, services, dashboard, API keys,
webhook ledger, notifications, audit.

ORGANIZATION ISOLATION is the most important contract: a partner user can never
access another organization's data by changing ids in the request.
"""


from app.models.partner import (
    Organization,
    OrganizationMember,
)
from app.models.user import User
from tests.conftest import login_headers, make_user


def _enable_flag(db_session, key: str) -> None:
    from app.models.ops import FeatureFlag

    flag = db_session.get(FeatureFlag, key)
    if flag is None:
        db_session.add(FeatureFlag(key=key, description=key, is_enabled=True))
    else:
        flag.is_enabled = True
    db_session.commit()


def _register_org(
    client, db_session, email_owner: str, org_type: str = "HOSPITAL", name: str = "Test Partner"
):
    make_user(db_session, email_owner)
    _enable_flag(db_session, "partner_ecosystem")
    _enable_flag(db_session, "partner_onboarding")
    _enable_flag(db_session, "partner_verification")
    headers = login_headers(client, email_owner)
    resp = client.post(
        "/api/v1/partners",
        json={
            "organization_type": org_type,
            "legal_name": name,
            "display_name": name,
            "city": "Hyderabad",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return headers, resp.json()


def _approve_org(client, owner_headers, admin_headers, org_id: str):
    """submit (partner) -> review -> approve (admin) through the real endpoints."""
    r = client.post(f"/api/v1/partners/{org_id}/submit", headers=owner_headers)
    if r.status_code == 409:
        pass  # already submitted
    r = client.post(f"/api/v1/admin/partners/{org_id}/review", headers=admin_headers)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/admin/partners/{org_id}/approve", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"


# ---------------------------------------------------------------- onboarding


def test_partner_registration_requires_flag(client, db_session):
    make_user(db_session, "flagowner@example.com")
    headers = login_headers(client, "flagowner@example.com")
    resp = client.post(
        "/api/v1/partners",
        json={"organization_type": "HOSPITAL", "legal_name": "Flag Off Hospital"},
        headers=headers,
    )
    assert resp.status_code == 503


def test_partner_registration_creates_draft_with_owner(client, db_session):
    headers, org = _register_org(client, db_session, "owner1@example.com", name="Owner One Hospitals")
    assert org["status"] == "DRAFT"
    assert org["organization_type"] == "HOSPITAL"
    members = client.get(f"/api/v1/partners/{org['id']}/members", headers=headers).json()
    assert len(members) == 1
    assert members[0]["partner_role"] == "PARTNER_OWNER"
    assert members[0]["user_id"] is not None


def test_partner_registration_rejects_unknown_type(client, db_session):
    make_user(db_session, "badtype@example.com")
    _enable_flag(db_session, "partner_ecosystem")
    _enable_flag(db_session, "partner_onboarding")
    headers = login_headers(client, "badtype@example.com")
    resp = client.post(
        "/api/v1/partners",
        json={"organization_type": "TIME_TRAVEL_CLINIC", "legal_name": "Nope"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_mine_lists_only_my_organizations(client, db_session):
    h1, org1 = _register_org(client, db_session, "mine1@example.com", name="Mine One")
    h2, org2 = _register_org(client, db_session, "mine2@example.com", name="Mine Two")
    rows = client.get("/api/v1/partners/mine", headers=h1).json()
    assert [o["id"] for o in rows] == [org1["id"]]


def test_partner_dashboard_aggregates(client, db_session):
    headers, org = _register_org(client, db_session, "dash@example.com", name="Dash Org")
    resp = client.get("/api/v1/partner/dashboard", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["organizations"]) == 1
    entry = data["organizations"][0]
    assert entry["organization_id"] == org["id"]
    assert entry["my_role"] == "PARTNER_OWNER"
    assert entry["status"] == "DRAFT"


# ----------------------------------------------------------------- lifecycle


def test_lifecycle_submit_review_approve(client, db_session, admin_headers):
    headers, org = _register_org(
        client, db_session, "lifecycle@example.com", org_type="DIAGNOSTIC_LAB", name="Lifecycle Labs"
    )
    r = client.post(f"/api/v1/partners/{org['id']}/submit", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "SUBMITTED"
    r = client.post(f"/api/v1/admin/partners/{org['id']}/review", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "UNDER_REVIEW"
    r = client.post(f"/api/v1/admin/partners/{org['id']}/approve", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"
    history = client.get(f"/api/v1/partners/{org['id']}/history", headers=headers).json()
    statuses = [h["new_status"] for h in history]
    assert statuses == ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED"]


def test_lifecycle_invalid_transitions_rejected(client, db_session, admin_headers):
    headers, org = _register_org(client, db_session, "invalid@example.com", name="Invalid Org")
    # DRAFT -> APPROVED is not allowed (409)
    r = client.post(f"/api/v1/admin/partners/{org['id']}/approve", headers=admin_headers)
    assert r.status_code == 409
    # DRAFT -> SUSPENDED not allowed
    r = client.post(f"/api/v1/admin/partners/{org['id']}/suspend", headers=admin_headers)
    assert r.status_code == 409


def test_suspended_partner_cannot_operate(client, db_session, admin_headers):
    headers, org = _register_org(
        client, db_session, "suspend@example.com", org_type="PHARMACY", name="Suspensible Org"
    )
    _enable_flag(db_session, "partner_services")
    _approve_org(client, headers, admin_headers, org["id"])
    svc = client.post(
        f"/api/v1/partners/{org['id']}/services",
        json={"service_type": "MEDICINE_FULFILLMENT", "name": "Home delivery"},
        headers=headers,
    )
    assert svc.status_code == 201
    # suspend
    r = client.post(f"/api/v1/admin/partners/{org['id']}/suspend", headers=admin_headers)
    assert r.status_code == 200
    svc2 = client.post(
        f"/api/v1/partners/{org['id']}/services",
        json={"service_type": "MEDICINE_FULFILLMENT", "name": "Second service"},
        headers=headers,
    )
    assert svc2.status_code == 403


def test_deactivated_is_terminal(client, db_session, admin_headers):
    headers, org = _register_org(client, db_session, "deactivate@example.com", name="Deactivatable Org")
    _approve_org(client, headers, admin_headers, org["id"])
    r = client.post(f"/api/v1/admin/partners/{org['id']}/deactivate", headers=admin_headers)
    assert r.status_code == 200
    r2 = client.post(f"/api/v1/admin/partners/{org['id']}/reactivate", headers=admin_headers)
    assert r2.status_code == 409  # terminal


# -------------------------------------------------------------- isolation


def test_org_isolation_partner_a_cannot_access_partner_b(client, db_session):
    hA, orgA = _register_org(client, db_session, "isolatea@example.com", name="Isolate A")
    hB, orgB = _register_org(client, db_session, "isolateb@example.com", name="Isolate B")
    _enable_flag(db_session, "partner_services")
    # A cannot read B's organization (404 existence-hidden)
    assert client.get(f"/api/v1/partners/{orgB['id']}", headers=hA).status_code == 404
    # A cannot list B's members/documents/services
    assert (
        client.get(f"/api/v1/partners/{orgB['id']}/members", headers=hA).status_code == 404
    )
    assert (
        client.get(f"/api/v1/partners/{orgB['id']}/documents", headers=hA).status_code == 404
    )
    assert (
        client.get(f"/api/v1/partners/{orgB['id']}/services", headers=hA).status_code == 404
    )
    # A cannot submit B's organization
    assert (
        client.post(f"/api/v1/partners/{orgB['id']}/submit", headers=hA).status_code == 404
    )
    # A cannot add a member to B
    from app.models.user import User

    userA = db_session.query(User).filter(User.email == "isolatea@example.com").first()
    resp = client.post(
        f"/api/v1/partners/{orgB['id']}/members",
        json={"user_id": userA.id, "partner_role": "PARTNER_STAFF"},
        headers=hA,
    )
    assert resp.status_code == 404


def test_stale_membership_is_denied_explicitly(client, db_session):
    from app.models.user import User

    hA, orgA = _register_org(client, db_session, "stale@example.com", name="Stale Org")
    userA = db_session.query(User).filter(User.email == "stale@example.com").first()
    member = (
        db_session.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == orgA["id"], OrganizationMember.user_id == userA.id)
        .first()
    )
    member.is_active = False
    db_session.commit()
    # Organization "exists" for this user but access must be denied (403, not 404)
    resp = client.get(f"/api/v1/partners/{orgA['id']}", headers=hA)
    assert resp.status_code == 403


def test_body_organization_id_is_never_trusted(client, db_session, admin_headers):
    """A partner cannot create a service in another organization by supplying
    a different organization id in the request body/path."""
    hA, orgA = _register_org(client, db_session, "bodyida@example.com", name="Body A")
    hB, orgB = _register_org(client, db_session, "bodyidb@example.com", name="Body B")
    _enable_flag(db_session, "partner_services")
    _enable_flag(db_session, "partner_verification")
    # B tries to create a service in A by hitting A's org id with B's token
    resp = client.post(
        f"/api/v1/partners/{orgA['id']}/services",
        json={"service_type": "CONSULTATION", "name": "Injected service"},
        headers=hB,
    )
    assert resp.status_code == 404
    # B (approved) creates a service in its OWN organization
    _approve_org(client, hB, admin_headers, orgB["id"])
    svc = client.post(
        f"/api/v1/partners/{orgB['id']}/services",
        json={"service_type": "CONSULTATION", "name": "B service"},
        headers=hB,
    )
    assert svc.status_code == 201, svc.text
    # and B cannot patch A's service even knowing its id
    resp2 = client.patch(
        f"/api/v1/partners/{orgA['id']}/services/{svc.json()['id']}",
        json={"name": "Hijacked"},
        headers=hB,
    )
    assert resp2.status_code == 404


# ----------------------------------------------------------------- members


def test_staff_cannot_manage_members(client, db_session, admin_headers):
    from app.models.user import User

    h_owner, org = _register_org(client, db_session, "mgmowner@example.com", name="Member Mgmt Org")
    make_user(db_session, "staffer@example.com")
    staff_user = db_session.query(User).filter(User.email == "staffer@example.com").first()
    r = client.post(
        f"/api/v1/partners/{org['id']}/members",
        json={"user_id": staff_user.id, "partner_role": "PARTNER_STAFF"},
        headers=h_owner,
    )
    assert r.status_code == 201
    h_staff = login_headers(client, "staffer@example.com")
    # staff tries to grant another member -> 403
    make_user(db_session, "newbie@example.com")
    newbie = db_session.query(User).filter(User.email == "newbie@example.com").first()
    r2 = client.post(
        f"/api/v1/partners/{org['id']}/members",
        json={"user_id": newbie.id, "partner_role": "PARTNER_STAFF"},
        headers=h_staff,
    )
    assert r2.status_code == 403
    # staff cannot remove the owner
    owner_member = (
        db_session.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == org["id"],
            OrganizationMember.partner_role == "PARTNER_OWNER",
        )
        .first()
    )
    r3 = client.delete(f"/api/v1/partners/{org['id']}/members/{owner_member.id}", headers=h_staff)
    assert r3.status_code in (403, 409)  # role gate or owner-protection


def test_owner_role_is_immutable_and_irremovable(client, db_session):

    h_owner, org = _register_org(client, db_session, "ownerguard@example.com", name="Owner Guard Org")
    owner_member = (
        db_session.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == org["id"],
            OrganizationMember.partner_role == "PARTNER_OWNER",
        )
        .first()
    )
    r = client.patch(
        f"/api/v1/partners/{org['id']}/members/{owner_member.id}",
        json={"partner_role": "PARTNER_STAFF"},
        headers=h_owner,
    )
    assert r.status_code == 409
    r2 = client.delete(f"/api/v1/partners/{org['id']}/members/{owner_member.id}", headers=h_owner)
    assert r2.status_code == 409


def test_duplicate_active_membership_rejected(client, db_session):
    from app.models.user import User

    h_owner, org = _register_org(client, db_session, "dupmember@example.com", name="Dup Member Org")
    make_user(db_session, "duptarget@example.com")
    target = db_session.query(User).filter(User.email == "duptarget@example.com").first()
    r1 = client.post(
        f"/api/v1/partners/{org['id']}/members",
        json={"user_id": target.id, "partner_role": "PARTNER_STAFF"},
        headers=h_owner,
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/api/v1/partners/{org['id']}/members",
        json={"user_id": target.id, "partner_role": "PARTNER_SUPPORT"},
        headers=h_owner,
    )
    assert r2.status_code == 409


# --------------------------------------------------------------- documents


def test_document_upload_and_verification(client, db_session, admin_headers):
    h, org = _register_org(client, db_session, "docs@example.com", name="Doc Org")
    _enable_flag(db_session, "partner_verification")
    r = client.post(
        f"/api/v1/partners/{org['id']}/documents",
        json={
            "document_type": "HOSPITAL_REGISTRATION",
            "storage_reference": "partner-docs/registration-001",
            "checksum": "a" * 64,
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["verification_status"] == "UPLOADED"
    # admin verifies
    r2 = client.post(
        f"/api/v1/admin/partners/{org['id']}/documents/{doc['id']}/decision",
        json={"decision": "VERIFIED", "note": "registration checked"},
        headers=admin_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["verification_status"] == "VERIFIED"
    # re-decision blocked
    r3 = client.post(
        f"/api/v1/admin/partners/{org['id']}/documents/{doc['id']}/decision",
        json={"decision": "REJECTED"},
        headers=admin_headers,
    )
    assert r3.status_code == 409


def test_document_invalid_type_rejected(client, db_session):
    h, org = _register_org(client, db_session, "baddoc@example.com", name="Bad Doc Org")
    _enable_flag(db_session, "partner_verification")
    r = client.post(
        f"/api/v1/partners/{org['id']}/documents",
        json={"document_type": "NOT_A_TYPE", "storage_reference": "x"},
        headers=h,
    )
    assert r.status_code == 422


def test_partner_cannot_decide_documents(client, db_session):

    h, org = _register_org(client, db_session, "selfdecide@example.com", name="Self Decide Org")
    _enable_flag(db_session, "partner_verification")
    doc = client.post(
        f"/api/v1/partners/{org['id']}/documents",
        json={"document_type": "ADDRESS_PROOF", "storage_reference": "addr"},
        headers=h,
    ).json()
    r = client.post(
        f"/api/v1/admin/partners/{org['id']}/documents/{doc['id']}/decision",
        json={"decision": "VERIFIED"},
        headers=h,
    )
    assert r.status_code == 403  # not SUPER_ADMIN


# --------------------------------------------------------------- services


def test_service_price_declared_is_never_verified(client, db_session, admin_headers):
    h, org = _register_org(client, db_session, "svcprice@example.com", name="Service Price Org")
    _enable_flag(db_session, "partner_services")
    _approve_org(client, h, admin_headers, org["id"])
    svc = client.post(
        f"/api/v1/partners/{org['id']}/services",
        json={"service_type": "CONSULTATION", "name": "General consultation", "price": 500},
        headers=h,
    )
    assert svc.status_code == 201
    body = svc.json()
    assert body["price"] == 500
    assert body["price_verification_status"] == "UNVERIFIED"
    assert body["price_source"] == "partner_declared"


def test_service_requires_approved_org(client, db_session):
    h, org = _register_org(client, db_session, "svcpend@example.com", name="Pending Svc Org")
    _enable_flag(db_session, "partner_services")
    r = client.post(
        f"/api/v1/partners/{org['id']}/services",
        json={"service_type": "CONSULTATION", "name": "Not approved yet"},
        headers=h,
    )
    assert r.status_code == 403


def test_service_update_resets_price_verification(client, db_session, admin_headers):
    h, org = _register_org(client, db_session, "svcreset@example.com", name="Svc Reset Org")
    _enable_flag(db_session, "partner_services")
    _approve_org(client, h, admin_headers, org["id"])
    svc = client.post(
        f"/api/v1/partners/{org['id']}/services",
        json={"service_type": "CONSULTATION", "name": "Consult", "price": 100},
        headers=h,
    ).json()
    r = client.patch(
        f"/api/v1/partners/{org['id']}/services/{svc['id']}",
        json={"price": 150},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["price_verification_status"] == "UNVERIFIED"


# ------------------------------------------------------ webhooks + api keys


def test_api_key_created_raw_shown_once_and_hashed(client, db_session, admin_headers):

    h, org = _register_org(client, db_session, "keyowner@example.com", name="Key Org")
    _enable_flag(db_session, "partner_api")
    r = client.post(
        f"/api/v1/partners/{org['id']}/integrations/api-keys",
        json={"name": "primary", "scopes": "read,write"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    raw = body["raw_key"]
    assert raw.startswith("msk_")
    # list view never exposes the raw key
    listing = client.get(f"/api/v1/partners/{org['id']}/integrations", headers=h).json()
    assert all("raw_key" not in row for row in listing)
    # stored value is a hash, not the raw key
    from app.models.partner import PartnerIntegration

    row = db_session.get(PartnerIntegration, body["id"])
    assert row.key_hash != raw
    assert len(row.key_hash) == 64
    assert row.key_prefix == raw[:12]
    # verification works
    match = client.get(f"/api/v1/partners/{org['id']}", headers=h)  # sanity auth
    assert match.status_code == 200


def test_verify_api_key_roundtrip(client, db_session):
    from app.services import partner_service

    h, org = _register_org(client, db_session, "keyround@example.com", name="Key Round Org")
    owner = (
        db_session.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == org["id"],
            OrganizationMember.partner_role == "PARTNER_OWNER",
        )
        .first()
    )
    from app.models.user import User

    owner_user = db_session.get(User, owner.user_id)
    integration, raw = partner_service.create_api_key(
        db_session, db_session.get(Organization, org["id"]), name="t", scopes="read", actor=owner_user
    )
    db_session.commit()
    assert partner_service.verify_api_key(db_session, raw) is not None
    assert partner_service.verify_api_key(db_session, raw + "tamper") is None
    assert partner_service.verify_api_key(db_session, "msk_bogusbogusbog") is None


def test_webhook_must_be_https(client, db_session):
    h, org = _register_org(client, db_session, "webhookhttp@example.com", name="Webhook Org")
    _enable_flag(db_session, "partner_webhooks")
    r = client.post(
        f"/api/v1/partners/{org['id']}/integrations/webhooks",
        json={"endpoint_url": "http://insecure.example.com/hook"},
        headers=h,
    )
    assert r.status_code == 422


def test_webhook_events_stay_pending_without_delivery_worker(client, db_session):
    """Honesty: without a delivery worker, events are PENDING — never DELIVERED."""
    from app.services import partner_service

    h, org = _register_org(client, db_session, "webhookledger@example.com", name="Ledger Org")
    _enable_flag(db_session, "partner_webhooks")
    event = partner_service.record_webhook_event(
        db_session,
        organization_id=org["id"],
        event_type="APPOINTMENT_CREATED",
        payload={"appointment_id": "abc"},
        webhook_flag_enabled=True,
    )
    db_session.commit()
    assert event is not None
    assert event.delivery_status == "PENDING"
    assert event.attempts == 0
    # flag off -> no event recorded
    event2 = partner_service.record_webhook_event(
        db_session,
        organization_id=org["id"],
        event_type="ORDER_CREATED",
        payload={},
        webhook_flag_enabled=False,
    )
    assert event2 is None
    # unknown event type -> ignored
    event3 = partner_service.record_webhook_event(
        db_session,
        organization_id=org["id"],
        event_type="NOT_A_REAL_EVENT",
        payload={},
        webhook_flag_enabled=True,
    )
    assert event3 is None


# ------------------------------------------------------------ notifications


def test_partner_notifications_in_app_real_and_scoped(client, db_session, admin_headers):
    hA, orgA = _register_org(client, db_session, "notifya@example.com", name="Notify A")
    hB, orgB = _register_org(client, db_session, "notifyb@example.com", name="Notify B")
    _approve_org(client, hA, admin_headers, orgA["id"])
    rows = (
        db_session.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == orgA["id"])
        .all()
    )
    assert rows, "members exist"
    # status transitions generated IN_APP notifications for A's members
    inbox = client.get("/api/v1/partner/notifications", headers=hA).json()
    assert any(n["organization_id"] == orgA["id"] for n in inbox)
    assert all(n["channel"] == "IN_APP" and n["status"] == "SENT" for n in inbox)
    # B's inbox has no A notifications
    inboxB = client.get("/api/v1/partner/notifications", headers=hB).json()
    assert all(n["organization_id"] != orgA["id"] for n in inboxB)


# -------------------------------------------------------------------- audit


def test_partner_actions_audited(client, db_session, admin_headers):
    from app.models.ops import AuditLog

    h, org = _register_org(client, db_session, "audited@example.com", name="Audited Org")
    _approve_org(client, h, admin_headers, org["id"])
    actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.resource_type == "organization", AuditLog.resource_id == org["id"])
        .all()
    }
    assert "PARTNER_ORG_REGISTERED" in actions
    assert "PARTNER_ORG_STATUS" in actions


def test_admin_overview_aggregates(client, db_session, admin_headers):
    _register_org(client, db_session, "adminov1@example.com", name="Admin Ov One", org_type="PHARMACY")
    resp = client.get("/api/v1/admin/partners/overview", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_organizations"] >= 1
    assert "organizations_by_type" in data
    assert "organizations_by_status" in data
    assert "pending_documents" in data


def test_admin_routes_require_super_admin(client, db_session):
    h, org = _register_org(client, db_session, "nonadmin@example.com", name="Non Admin Org")
    assert client.get("/api/v1/admin/partners", headers=h).status_code == 403
    assert client.post(f"/api/v1/admin/partners/{org['id']}/approve", headers=h).status_code == 403


# ------------------------------------------------- integration with Phase 3


def test_doctor_profile_link_on_organization(client, db_session):
    """A DOCTOR organization can link an existing Phase 3 doctor row."""
    from app.schemas.providers import DoctorRegistration
    from app.services.provider_service import register_doctor

    make_user(db_session, "docpartner@example.com", roles=("DOCTOR",))
    h = login_headers(client, "docpartner@example.com")
    _enable_flag(db_session, "partner_ecosystem")
    _enable_flag(db_session, "partner_onboarding")
    doctor_user = db_session.query(User).filter(User.email == "docpartner@example.com").first()
    doctor = register_doctor(
        db_session,
        DoctorRegistration(
            full_name="Linked Doctor",
            specialty_slug="cardiology",
            qualifications="MBBS",
        ),
        user_id=doctor_user.id,
    )
    db_session.commit()
    resp = client.post(
        "/api/v1/partners",
        json={
            "organization_type": "DOCTOR",
            "legal_name": "Linked Doctor Practice",
            "profile_metadata": {"doctor_id": doctor.id},
        },
        headers=h,
    )
    assert resp.status_code == 201
    org = resp.json()
    from app.models.partner import PartnerProfile

    profile = db_session.query(PartnerProfile).filter(PartnerProfile.organization_id == org["id"]).first()
    assert profile is not None
    assert profile.metadata_json != "{}"


# late import used in helper
