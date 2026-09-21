"""Partner ecosystem service layer (Phase 8).

SECURITY CORE:
- Organization scoping is derived server-side from ACTIVE OrganizationMember
  rows — never from client-supplied organization_id values in bodies.
- Unknown organization for a non-member caller → 404 (existence hidden).
- Known organization but revoked/expired membership → 403 (explicit, audited).
- Non-APPROVED organizations cannot perform protected operations.

HONESTY CORE (inherited):
- Lifecycle/claim transitions are service-enforced state machines.
- Provider-declared prices stay UNVERIFIED until an admin verifies them.
- No amounts are ever computed for settlements; no claim auto-approval.
- API keys are stored only as SHA-256 hashes; raw keys are shown once.
"""

import hashlib
import json
import secrets
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.models.ops import AuditLog
from app.models.partner import (
    CLAIM_TRANSITIONS,
    DOCUMENT_TYPES,
    LAB_BOOKING_TRANSITIONS,
    MEMBER_ROLES_ALLOWED,
    OPERABLE_STATUSES,
    ORG_TRANSITIONS,
    ORGANIZATION_TYPES,
    PARTNER_ROLES,
    WEBHOOK_EVENT_TYPES,
    Organization,
    OrganizationMember,
    PartnerClaim,
    PartnerClaimEvent,
    PartnerDocument,
    PartnerIntegration,
    PartnerLabBooking,
    PartnerLabTest,
    PartnerLifecycleEvent,
    PartnerNotification,
    PartnerProfile,
    PartnerService,
    PartnerWebhookEvent,
)
from app.models.user import User


class PartnerError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _audit(
    db: Session,
    *,
    actor_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str = "SUCCESS",
    detail: str = "",
    actor_role: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            detail=detail[:2000],
        )
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------- membership


def active_membership(db: Session, organization_id: str, user: User) -> OrganizationMember:
    """Resolve the caller's ACTIVE membership or raise 404/403.

    - No membership at all → PartnerError(404): existence of the organization
      is hidden from strangers (no IDOR enumeration).
    - Membership rows exist but inactive → PartnerError(403): the user knows
      the organization; stale/revoked access is an explicit denial.
    """
    rows = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user.id,
        )
        .all()
    )
    if not rows:
        raise PartnerError("Organization not found", 404)
    for row in rows:
        if row.is_active:
            return row
    raise PartnerError("Your membership for this organization is not active", 403)


def require_super_admin(user: User) -> None:
    if "SUPER_ADMIN" not in user.role_ids:
        raise PartnerError("SUPER_ADMIN role required", 403)


def require_active_organization(db: Session, organization: Organization) -> None:
    """Protected operations require an APPROVED organization."""
    if organization.status not in OPERABLE_STATUSES:
        raise PartnerError(
            f"Organization is {organization.status}; this operation requires APPROVED",
            403,
        )


def organizations_for_user(db: Session, user: User) -> list[Organization]:
    rows = (
        db.query(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .filter(
            OrganizationMember.user_id == user.id,
            OrganizationMember.is_active.is_(True),
        )
        .order_by(Organization.created_at.desc())
        .all()
    )
    return rows


def is_super_admin(user: User) -> bool:
    return "SUPER_ADMIN" in user.role_ids


# ------------------------------------------------------------- onboarding


def register_organization(
    db: Session,
    *,
    payload,
    owner: User,
) -> tuple[Organization, PartnerProfile]:
    """Create a DRAFT organization + PARTNER_OWNER membership + profile."""
    if payload.organization_type not in ORGANIZATION_TYPES:
        raise PartnerError(
            f"organization_type must be one of: {', '.join(ORGANIZATION_TYPES)}", 422
        )
    org = Organization(
        organization_type=payload.organization_type,
        legal_name=payload.legal_name.strip(),
        display_name=(payload.display_name or payload.legal_name).strip(),
        registration_number=(payload.registration_number or "").strip(),
        tax_identifier=payload.tax_identifier,
        phone=payload.phone,
        email=payload.email,
        address_line=payload.address_line or "",
        city=payload.city,
        state=payload.state,
        pincode=payload.pincode,
        latitude=payload.latitude,
        longitude=payload.longitude,
        status="DRAFT",
        verification_status="UNVERIFIED",
        created_by_user_id=owner.id,
    )
    db.add(org)
    db.flush()
    member = OrganizationMember(
        organization_id=org.id,
        user_id=owner.id,
        partner_role="PARTNER_OWNER",
        is_active=True,
        granted_by_user_id=owner.id,
    )
    db.add(member)
    profile = PartnerProfile(organization_id=org.id, metadata_json="{}")
    db.add(profile)
    db.add(
        PartnerLifecycleEvent(
            organization_id=org.id,
            previous_status="",
            new_status="DRAFT",
            actor_user_id=owner.id,
            note="organization created",
        )
    )
    _audit(
        db,
        actor_user_id=owner.id,
        action="PARTNER_ORG_REGISTERED",
        resource_type="organization",
        resource_id=org.id,
        detail=f"type={org.organization_type} display={org.display_name}",
        actor_role=",".join(owner.role_ids) or None,
    )
    db.flush()
    return org, profile


def update_organization(db: Session, org: Organization, payload, actor: User) -> Organization:
    """Partner profile updates. Status/verification fields are NOT editable here
    (they change only through the lifecycle machine)."""
    data = payload.model_dump(exclude_unset=True)
    protected = {"status", "verification_status", "organization_type", "created_by_user_id"}
    for field in protected:
        data.pop(field, None)
    for field, value in data.items():
        setattr(org, field, value)
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_ORG_UPDATED",
        resource_type="organization",
        resource_id=org.id,
        detail=f"fields={sorted(data)}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return org


def transition_organization(
    db: Session,
    org: Organization,
    *,
    new_status: str,
    actor: User,
    note: str = "",
) -> Organization:
    """Apply a lifecycle transition (state-machine enforced + audited)."""
    if new_status not in ORG_TRANSITIONS:
        raise PartnerError(f"Unknown organization status: {new_status}", 422)
    allowed = ORG_TRANSITIONS.get(org.status, ())
    if new_status not in allowed:
        raise PartnerError(
            f"Invalid transition {org.status} -> {new_status}. Allowed: {list(allowed) or 'none'}",
            409,
        )
    previous = org.status
    org.status = new_status
    if new_status == "APPROVED":
        org.verification_status = "VERIFIED"
    elif new_status in ("SUSPENDED", "REJECTED", "DEACTIVATED"):
        org.verification_status = new_status
    db.add(
        PartnerLifecycleEvent(
            organization_id=org.id,
            previous_status=previous,
            new_status=new_status,
            actor_user_id=actor.id,
            note=(note or "")[:500],
        )
    )
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_ORG_STATUS",
        resource_type="organization",
        resource_id=org.id,
        detail=f"{previous} -> {new_status}: {note[:200]}",
        actor_role=",".join(actor.role_ids) or None,
    )
    notify_organization(
        db,
        organization_id=org.id,
        event_type="PARTNER_STATUS_CHANGED",
        title=f"Organization status: {new_status}",
        body=note[:500],
    )
    db.flush()
    return org


# --------------------------------------------------------------- members


def add_member(
    db: Session,
    org: Organization,
    *,
    user_id: str,
    partner_role: str,
    actor: User,
) -> OrganizationMember:
    if partner_role not in PARTNER_ROLES:
        raise PartnerError(f"partner_role must be one of: {', '.join(PARTNER_ROLES)}", 422)
    if partner_role == "PARTNER_OWNER":
        raise PartnerError("PARTNER_OWNER is fixed to the organization creator", 422)
    actor_member = active_membership(db, org.id, actor)
    if not is_super_admin(actor):
        if actor_member.partner_role not in MEMBER_ROLES_ALLOWED:
            raise PartnerError("Only PARTNER_OWNER/PARTNER_ADMIN can manage members", 403)
        if partner_role not in MEMBER_ROLES_ALLOWED[actor_member.partner_role]:
            raise PartnerError("This role cannot be granted by you", 403)
    target = db.get(User, user_id)
    if target is None or not target.is_active:
        raise PartnerError("User not found", 404)
    existing = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.is_active.is_(True),
        )
        .first()
    )
    if existing is not None:
        raise PartnerError("User is already an active member", 409)
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user_id,
        partner_role=partner_role,
        is_active=True,
        granted_by_user_id=actor.id,
    )
    db.add(member)
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_MEMBER_ADDED",
        resource_type="organization_member",
        resource_id=member.id,
        detail=f"org={org.id} user={user_id} role={partner_role}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return member


def update_member(
    db: Session,
    org: Organization,
    member: OrganizationMember,
    *,
    partner_role: str,
    actor: User,
) -> OrganizationMember:
    if member.partner_role == "PARTNER_OWNER":
        raise PartnerError("The PARTNER_OWNER role cannot be changed", 409)
    if partner_role not in PARTNER_ROLES or partner_role == "PARTNER_OWNER":
        raise PartnerError("Invalid partner_role", 422)
    actor_member = active_membership(db, org.id, actor)
    if not is_super_admin(actor):
        if actor_member.partner_role not in MEMBER_ROLES_ALLOWED:
            raise PartnerError("Only PARTNER_OWNER/PARTNER_ADMIN can manage members", 403)
        if partner_role not in MEMBER_ROLES_ALLOWED[actor_member.partner_role]:
            raise PartnerError("This role cannot be granted by you", 403)
    member.partner_role = partner_role
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_MEMBER_UPDATED",
        resource_type="organization_member",
        resource_id=member.id,
        detail=f"org={org.id} role->{partner_role}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return member


def remove_member(
    db: Session, org: Organization, member: OrganizationMember, *, actor: User
) -> OrganizationMember:
    if member.partner_role == "PARTNER_OWNER":
        raise PartnerError("The PARTNER_OWNER cannot be removed", 409)
    actor_member = active_membership(db, org.id, actor)
    if not is_super_admin(actor) and actor_member.partner_role not in MEMBER_ROLES_ALLOWED:
        raise PartnerError("Only PARTNER_OWNER/PARTNER_ADMIN can manage members", 403)
    member.is_active = False
    member.revoked_at = _utcnow()
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_MEMBER_REMOVED",
        resource_type="organization_member",
        resource_id=member.id,
        detail=f"org={org.id} user={member.user_id}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return member


# -------------------------------------------------------------- documents

ALLOWED_DOCUMENT_TYPES = DOCUMENT_TYPES


def create_document(
    db: Session,
    org: Organization,
    *,
    document_type: str,
    file_id: str | None,
    storage_reference: str,
    checksum: str,
    issued_at: date | None,
    expires_at: date | None,
    actor: User,
) -> PartnerDocument:
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise PartnerError(
            f"document_type must be one of: {', '.join(ALLOWED_DOCUMENT_TYPES)}", 422
        )
    if file_id is None and not storage_reference:
        raise PartnerError("Either a stored file or a storage reference is required", 422)
    active_membership(db, org.id, actor)
    doc = PartnerDocument(
        organization_id=org.id,
        document_type=document_type,
        file_id=file_id,
        storage_reference=(storage_reference or "")[:255],
        checksum=(checksum or "")[:64],
        issued_at=issued_at,
        expires_at=expires_at,
        verification_status="UPLOADED",
        uploaded_by_user_id=actor.id,
    )
    db.add(doc)
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_DOCUMENT_UPLOADED",
        resource_type="partner_document",
        resource_id=doc.id,
        detail=f"org={org.id} type={document_type} checksum={doc.checksum[:12]}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return doc


def decide_document(
    db: Session,
    doc: PartnerDocument,
    *,
    decision: str,
    admin: User,
    note: str = "",
) -> PartnerDocument:
    """SUPER_ADMIN verification decision. Human decision only — no automated
    government verification is claimed anywhere."""
    require_super_admin(admin)
    if decision not in ("UNDER_REVIEW", "VERIFIED", "REJECTED", "EXPIRED"):
        raise PartnerError("decision must be UNDER_REVIEW|VERIFIED|REJECTED|EXPIRED", 422)
    if doc.verification_status in ("VERIFIED", "REJECTED") and decision != "EXPIRED":
        raise PartnerError(f"Document already {doc.verification_status}", 409)
    doc.verification_status = decision
    doc.verified_by_user_id = admin.id
    doc.verified_at = _utcnow() if decision in ("VERIFIED", "REJECTED") else None
    doc.review_note = (note or "")[:1000]
    _audit(
        db,
        actor_user_id=admin.id,
        action="PARTNER_DOCUMENT_DECISION",
        resource_type="partner_document",
        resource_id=doc.id,
        detail=f"org={doc.organization_id} -> {decision}: {note[:200]}",
        actor_role="SUPER_ADMIN",
    )
    db.flush()
    return doc


def expire_stale_documents(db: Session) -> int:
    """Documents past expires_at move to EXPIRED (honesty: expired data must
    not continue to look verified)."""
    today = date.today()
    stale = (
        db.query(PartnerDocument)
        .filter(
            PartnerDocument.verification_status == "VERIFIED",
            PartnerDocument.expires_at.isnot(None),
            PartnerDocument.expires_at < today,
        )
        .all()
    )
    for doc in stale:
        doc.verification_status = "EXPIRED"
    if stale:
        db.flush()
    return len(stale)


# --------------------------------------------------------------- services


def create_service(db: Session, org: Organization, payload, actor: User) -> PartnerService:
    active_membership(db, org.id, actor)
    require_active_organization(db, org)
    service = PartnerService(
        organization_id=org.id,
        service_type=payload.service_type,
        name=payload.name.strip(),
        description=payload.description or "",
        status="ACTIVE",
        price=payload.price,
        currency=payload.currency or "INR",
        price_verification_status="UNVERIFIED",
        price_source="partner_declared",
    )
    db.add(service)
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_SERVICE_CREATED",
        resource_type="partner_service",
        resource_id=service.id,
        detail=(
            f"org={org.id} type={payload.service_type} "
            f"price={'declared' if payload.price is not None else 'none'}"
        ),
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return service


def update_service(db: Session, service: PartnerService, payload, actor: User) -> PartnerService:
    active_membership(db, service.organization_id, actor)
    data = payload.model_dump(exclude_unset=True)
    data.pop("price_verification_status", None)
    data.pop("price_source", None)
    if "price" in data and data["price"] != service.price:
        # A new declared price resets verification honesty.
        service.price_verification_status = "UNVERIFIED"
        service.price_source = "partner_declared"
    for field, value in data.items():
        setattr(service, field, value)
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_SERVICE_UPDATED",
        resource_type="partner_service",
        resource_id=service.id,
        detail=f"fields={sorted(data)}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return service


# ------------------------------------------------------------ lab module


def create_lab_test(db: Session, org: Organization, payload, actor: User) -> PartnerLabTest:
    active_membership(db, org.id, actor)
    require_active_organization(db, org)
    existing = (
        db.query(PartnerLabTest)
        .filter(
            PartnerLabTest.organization_id == org.id,
            PartnerLabTest.code == payload.code,
            PartnerLabTest.is_active.is_(True),
        )
        .first()
    )
    if existing is not None:
        raise PartnerError(f"Test code {payload.code} already exists for this lab", 409)
    test = PartnerLabTest(
        organization_id=org.id,
        code=payload.code.strip(),
        name=payload.name.strip(),
        description=payload.description or "",
        category=payload.category or "",
        sample_type=payload.sample_type or "",
        preparation_notes=payload.preparation_notes or "",
        price=payload.price,
        currency=payload.currency or "INR",
        verification_status="UNVERIFIED",
    )
    db.add(test)
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_LAB_TEST_CREATED",
        resource_type="partner_lab_test",
        resource_id=test.id,
        detail=f"org={org.id} code={test.code} price={'declared' if payload.price is not None else 'none'}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return test


def create_lab_booking(
    db: Session,
    *,
    test: PartnerLabTest,
    patient: User,
    collection_mode: str,
    scheduled_for: datetime | None,
    notes: str = "",
) -> PartnerLabBooking:
    """Patient-initiated booking against a VERIFIED test at an APPROVED lab."""
    if collection_mode not in ("CENTER_VISIT", "HOME_COLLECTION"):
        raise PartnerError("collection_mode must be CENTER_VISIT or HOME_COLLECTION", 422)
    org = db.get(Organization, test.organization_id)
    if org is None or not org.is_operable:
        raise PartnerError("This lab cannot accept bookings right now", 409)
    if test.verification_status != "VERIFIED" or not test.is_active:
        raise PartnerError("Only VERIFIED, active tests can be booked", 409)
    booking = PartnerLabBooking(
        organization_id=org.id,
        test_id=test.id,
        patient_user_id=patient.id,
        status="REQUESTED",
        collection_mode=collection_mode,
        scheduled_for=scheduled_for,
        notes=(notes or "")[:500],
    )
    db.add(booking)
    _audit(
        db,
        actor_user_id=patient.id,
        action="LAB_BOOKING_REQUESTED",
        resource_type="partner_lab_booking",
        resource_id=booking.id,
        detail=f"org={org.id} test={test.code}",
        actor_role="PATIENT",
    )
    db.flush()
    return booking


def transition_lab_booking(
    db: Session, booking: PartnerLabBooking, *, new_status: str, actor: User
) -> PartnerLabBooking:
    active_membership(db, booking.organization_id, actor)
    allowed = LAB_BOOKING_TRANSITIONS.get(booking.status, ())
    if new_status not in allowed:
        raise PartnerError(
            f"Invalid transition {booking.status} -> {new_status}. Allowed: {list(allowed) or 'none'}",
            409,
        )
    booking.status = new_status
    _audit(
        db,
        actor_user_id=actor.id,
        action="LAB_BOOKING_STATUS",
        resource_type="partner_lab_booking",
        resource_id=booking.id,
        detail=f"-> {new_status}",
        actor_role=",".join(actor.role_ids) or None,
    )
    if new_status == "REPORT_READY":
        notify_organization(
            db,
            organization_id=booking.organization_id,
            event_type="LAB_REPORT_READY",
            title="Lab report ready",
            body=f"Booking {booking.id} has a report ready for delivery.",
            resource_type="partner_lab_booking",
            resource_id=booking.id,
        )
    db.flush()
    return booking


# ------------------------------------------------------ insurance module


def create_insurance_product(
    db: Session, org: Organization, payload, actor: User
):
    active_membership(db, org.id, actor)
    require_active_organization(db, org)
    from app.models.partner import PartnerInsuranceProduct

    product = PartnerInsuranceProduct(
        organization_id=org.id,
        product_name=payload.product_name.strip(),
        product_type=payload.product_type or "",
        description=payload.description or "",
        claim_intake_supported=bool(payload.claim_intake_supported),
    )
    db.add(product)
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_INSURANCE_PRODUCT_CREATED",
        resource_type="partner_insurance_product",
        resource_id=product.id,
        detail=f"org={org.id} product={product.product_name}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return product


def create_claim(
    db: Session,
    org: Organization,
    *,
    patient: User,
    payload,
    actor: User,
) -> PartnerClaim:
    """Create a claim. Claim amounts are partner/patient-declared values for a
    real subject; nothing is computed or approved automatically."""
    if payload.subject_type not in ("APPOINTMENT", "ORDER", "LAB_BOOKING", "OTHER"):
        raise PartnerError("subject_type must be APPOINTMENT|ORDER|LAB_BOOKING|OTHER", 422)
    claim = PartnerClaim(
        organization_id=org.id,
        patient_user_id=patient.id,
        claim_number=(payload.claim_number or "").strip(),
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        status="DRAFT",
        description=(payload.description or "")[:2000],
        amount=payload.amount,
        currency=payload.currency or "INR",
    )
    db.add(claim)
    db.flush()
    db.add(
        PartnerClaimEvent(
            claim_id=claim.id,
            previous_status="",
            new_status="DRAFT",
            actor_user_id=actor.id,
            note="claim created",
        )
    )
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_CLAIM_CREATED",
        resource_type="partner_claim",
        resource_id=claim.id,
        detail=f"org={org.id} patient={patient.id} subject={payload.subject_type}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return claim


def transition_claim(
    db: Session,
    claim: PartnerClaim,
    *,
    new_status: str,
    actor: User,
    note: str = "",
    approved_amount: float | None = None,
) -> PartnerClaim:
    """State-machine-enforced claim transition. APPROVED/PARTIALLY_APPROVED/
    SETTLED are human decisions recorded with the actor identity — never
    automatic."""
    actor_member = active_membership(db, claim.organization_id, actor)
    is_org_admin = actor_member.partner_role in (
        "PARTNER_OWNER", "PARTNER_ADMIN", "PARTNER_MANAGER", "PARTNER_BILLING",
    )
    privileged = new_status in ("APPROVED", "PARTIALLY_APPROVED", "REJECTED", "SETTLED")
    if privileged and not (is_org_admin or is_super_admin(actor)):
        raise PartnerError("Only partner admin/billing roles can decide claims", 403)
    if new_status == "SUBMITTED" and claim.status == "DRAFT":
        claim.submitted_by_user_id = actor.id
        claim.submitted_at = _utcnow()
    if privileged:
        claim.decided_by_user_id = actor.id
        claim.decided_at = _utcnow()
        if approved_amount is not None:
            claim.approved_amount = approved_amount
    allowed = CLAIM_TRANSITIONS.get(claim.status, ())
    if new_status not in allowed:
        raise PartnerError(
            f"Invalid transition {claim.status} -> {new_status}. Allowed: {list(allowed) or 'none'}",
            409,
        )
    previous = claim.status
    claim.status = new_status
    db.add(
        PartnerClaimEvent(
            claim_id=claim.id,
            previous_status=previous,
            new_status=new_status,
            actor_user_id=actor.id,
            note=(note or "")[:500],
        )
    )
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_CLAIM_STATUS",
        resource_type="partner_claim",
        resource_id=claim.id,
        detail=f"{previous} -> {new_status}: {note[:200]}",
        actor_role=",".join(actor.role_ids) or None,
    )
    notify_organization(
        db,
        organization_id=claim.organization_id,
        event_type="CLAIM_UPDATED",
        title=f"Claim {claim.claim_number or claim.id}: {new_status}",
        body=note[:500],
        resource_type="partner_claim",
        resource_id=claim.id,
    )
    db.flush()
    return claim


def claim_events(db: Session, claim: PartnerClaim) -> list[PartnerClaimEvent]:
    return (
        db.query(PartnerClaimEvent)
        .filter(PartnerClaimEvent.claim_id == claim.id)
        .order_by(PartnerClaimEvent.created_at.asc())
        .all()
    )


# ----------------------------------------------------------- integrations


def create_api_key(
    db: Session, org: Organization, *, name: str, scopes: str, actor: User
) -> tuple[PartnerIntegration, str]:
    """Create an API key. The raw key is returned EXACTLY ONCE; only the
    SHA-256 hash and a lookup prefix are persisted."""
    active_membership(db, org.id, actor)
    member = active_membership(db, org.id, actor)
    if member.partner_role not in ("PARTNER_OWNER", "PARTNER_ADMIN"):
        raise PartnerError("Only PARTNER_OWNER/PARTNER_ADMIN can create API keys", 403)
    raw = f"msk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    integration = PartnerIntegration(
        organization_id=org.id,
        integration_kind="API_KEY",
        name=(name or "api-key")[:120],
        key_prefix=raw[:12],
        key_hash=key_hash,
        scopes=(scopes or "read")[:300],
        status="ACTIVE",
        created_by_user_id=actor.id,
    )
    db.add(integration)
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_API_KEY_CREATED",
        resource_type="partner_integration",
        resource_id=integration.id,
        detail=f"org={org.id} prefix={integration.key_prefix}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return integration, raw


def verify_api_key(db: Session, raw_key: str) -> PartnerIntegration | None:
    """Constant-time hash lookup by prefix, then full-hash compare."""
    if not raw_key or len(raw_key) < 12:
        return None
    prefix = raw_key[:12]
    candidates = (
        db.query(PartnerIntegration)
        .filter(
            PartnerIntegration.key_prefix == prefix,
            PartnerIntegration.integration_kind == "API_KEY",
            PartnerIntegration.status == "ACTIVE",
        )
        .all()
    )
    digest = hashlib.sha256(raw_key.encode()).hexdigest()
    for candidate in candidates:
        if secrets.compare_digest(candidate.key_hash, digest):
            candidate.last_used_at = _utcnow()
            db.flush()
            return candidate
    return None


def revoke_integration(db: Session, integration: PartnerIntegration, *, actor: User) -> PartnerIntegration:
    active_membership(db, integration.organization_id, actor)
    member = active_membership(db, integration.organization_id, actor)
    if member.partner_role not in ("PARTNER_OWNER", "PARTNER_ADMIN") and not is_super_admin(actor):
        raise PartnerError("Only PARTNER_OWNER/PARTNER_ADMIN can revoke integrations", 403)
    integration.status = "REVOKED"
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_INTEGRATION_REVOKED",
        resource_type="partner_integration",
        resource_id=integration.id,
        detail=f"org={integration.organization_id} kind={integration.integration_kind}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return integration


def register_webhook(
    db: Session, org: Organization, *, name: str, endpoint_url: str, actor: User
) -> PartnerIntegration:
    active_membership(db, org.id, actor)
    member = active_membership(db, org.id, actor)
    if member.partner_role not in ("PARTNER_OWNER", "PARTNER_ADMIN"):
        raise PartnerError("Only PARTNER_OWNER/PARTNER_ADMIN can register webhooks", 403)
    if not endpoint_url.startswith(("https://",)):
        raise PartnerError("Webhook endpoint_url must be https://", 422)
    integration = PartnerIntegration(
        organization_id=org.id,
        integration_kind="WEBHOOK_ENDPOINT",
        name=(name or "webhook")[:120],
        endpoint_url=endpoint_url[:500],
        status="ACTIVE",
        created_by_user_id=actor.id,
    )
    db.add(integration)
    _audit(
        db,
        actor_user_id=actor.id,
        action="PARTNER_WEBHOOK_REGISTERED",
        resource_type="partner_integration",
        resource_id=integration.id,
        detail=f"org={org.id} url={endpoint_url[:120]}",
        actor_role=",".join(actor.role_ids) or None,
    )
    db.flush()
    return integration


def record_webhook_event(
    db: Session,
    *,
    organization_id: str,
    event_type: str,
    payload: dict,
    webhook_flag_enabled: bool,
) -> PartnerWebhookEvent | None:
    """Append an outbound event to the ledger. Without a configured delivery
    worker the event stays PENDING — never DELIVERED (honesty)."""
    if not webhook_flag_enabled:
        return None
    if event_type not in WEBHOOK_EVENT_TYPES:
        return None
    import json as _json

    from app.models.user import new_uuid

    event = PartnerWebhookEvent(
        event_id=str(new_uuid()),
        organization_id=organization_id,
        event_type=event_type,
        payload=_json.dumps(payload, default=str)[:8000],
        delivery_status="PENDING",
    )
    db.add(event)
    db.flush()
    return event


# ---------------------------------------------------------- notifications


def notify_organization(
    db: Session,
    *,
    organization_id: str,
    event_type: str,
    title: str,
    body: str,
    resource_type: str = "",
    resource_id: str | None = None,
) -> list[PartnerNotification]:
    """Queue IN_APP notifications for all active members of the organization.
    External channels are NOT attempted here (no provider configured) — they
    are never marked SENT/DELIVERED without a real provider confirmation."""
    members = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.is_active.is_(True),
        )
        .all()
    )
    rows: list[PartnerNotification] = []
    for member in members:
        row = PartnerNotification(
            organization_id=organization_id,
            recipient_user_id=member.user_id,
            channel="IN_APP",
            status="SENT",
            event_type=event_type[:40],
            title=title[:200],
            body=body[:2000],
            resource_type=resource_type[:40],
            resource_id=resource_id,
            provider_name="in_app",
            sent_at=_utcnow(),
        )
        db.add(row)
        rows.append(row)
    if rows:
        db.flush()
    return rows


def notifications_for_user(db: Session, user: User, limit: int = 50) -> list[PartnerNotification]:
    """Inbox: notifications for organizations where the user has an ACTIVE
    membership — organization-scoped by construction."""
    return (
        db.query(PartnerNotification)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == PartnerNotification.organization_id,
        )
        .filter(
            OrganizationMember.user_id == user.id,
            OrganizationMember.is_active.is_(True),
        )
        .order_by(PartnerNotification.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )


# ----------------------------------------------------------------- dashboard


def dashboard_for_user(db: Session, user: User) -> dict:
    """Aggregated partner operations view across the caller's organizations.
    Counts only — minimum necessary, no patient clinical content."""
    orgs = organizations_for_user(db, user)
    out = []
    for org in orgs:
        member = next(m for m in org.members if m.user_id == user.id and m.is_active)
        services = (
            db.query(PartnerService)
            .filter(PartnerService.organization_id == org.id)
            .count()
        )
        docs_pending = (
            db.query(PartnerDocument)
            .filter(
                PartnerDocument.organization_id == org.id,
                PartnerDocument.verification_status.in_(("UPLOADED", "UNDER_REVIEW")),
            )
            .count()
        )
        claims_open = (
            db.query(PartnerClaim)
            .filter(
                PartnerClaim.organization_id == org.id,
                PartnerClaim.status.in_(
                    ("DRAFT", "SUBMITTED", "UNDER_REVIEW", "ADDITIONAL_INFORMATION_REQUIRED")
                ),
            )
            .count()
        )
        lab_tests = (
            db.query(PartnerLabTest)
            .filter(PartnerLabTest.organization_id == org.id, PartnerLabTest.is_active.is_(True))
            .count()
        )
        lab_bookings_open = (
            db.query(PartnerLabBooking)
            .filter(
                PartnerLabBooking.organization_id == org.id,
                PartnerLabBooking.status.in_(("REQUESTED", "CONFIRMED", "SAMPLE_COLLECTED", "IN_PROGRESS")),
            )
            .count()
        )
        out.append(
            {
                "organization_id": org.id,
                "organization_type": org.organization_type,
                "display_name": org.display_name,
                "status": org.status,
                "verification_status": org.verification_status,
                "my_role": member.partner_role,
                "services": services,
                "documents_pending": docs_pending,
                "claims_open": claims_open,
                "lab_tests": lab_tests,
                "lab_bookings_open": lab_bookings_open,
            }
        )
    return {"organizations": out}


# ------------------------------------------------------------ admin overview


def admin_overview(db: Session) -> dict:
    """SUPER_ADMIN governance aggregates. No patient clinical content."""
    from sqlalchemy import func

    from app.models.partner import (
        PartnerClaim,
        PartnerDocument,
        PartnerInsuranceProduct,
        PartnerIntegration,
        PartnerLabTest,
        PartnerWebhookEvent,
    )

    type_counts = dict(
        db.query(Organization.organization_type, func.count(Organization.id))
        .group_by(Organization.organization_type)
        .all()
    )
    status_counts = dict(
        db.query(Organization.status, func.count(Organization.id))
        .group_by(Organization.status)
        .all()
    )
    pending_docs = (
        db.query(func.count(PartnerDocument.id))
        .filter(PartnerDocument.verification_status.in_(("UPLOADED", "UNDER_REVIEW")))
        .scalar()
        or 0
    )
    claim_status = dict(
        db.query(PartnerClaim.status, func.count(PartnerClaim.id))
        .group_by(PartnerClaim.status)
        .all()
    )
    webhook_pending = (
        db.query(func.count(PartnerWebhookEvent.id))
        .filter(PartnerWebhookEvent.delivery_status == "PENDING")
        .scalar()
        or 0
    )
    integration_counts = dict(
        db.query(PartnerIntegration.integration_kind, func.count(PartnerIntegration.id))
        .group_by(PartnerIntegration.integration_kind)
        .all()
    )
    lab_tests = db.query(func.count(PartnerLabTest.id)).scalar() or 0
    insurance_products = db.query(func.count(PartnerInsuranceProduct.id)).scalar() or 0
    denied = (
        db.query(func.count(AuditLog.id))
        .filter(
            AuditLog.resource_type.in_(
                ("organization", "partner_document", "partner_claim", "partner_lab_booking")
            ),
            AuditLog.outcome == "DENIED",
        )
        .scalar()
        or 0
    )
    recent = (
        db.query(AuditLog)
        .filter(
            AuditLog.action.like("PARTNER_%")
            | AuditLog.action.like("LAB_%")
        )
        .order_by(AuditLog.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "total_organizations": sum(type_counts.values()),
        "organizations_by_type": {k: int(v) for k, v in type_counts.items()},
        "organizations_by_status": {k: int(v) for k, v in status_counts.items()},
        "pending_documents": int(pending_docs),
        "claims_by_status": {k: int(v) for k, v in claim_status.items()},
        "webhook_events_pending": int(webhook_pending),
        "integrations_by_kind": {k: int(v) for k, v in integration_counts.items()},
        "lab_tests": int(lab_tests),
        "insurance_products": int(insurance_products),
        "security_denied_events": int(denied),
        "recent_events": [
            {
                "id": ev.id,
                "action": ev.action,
                "outcome": ev.outcome,
                "resource_type": ev.resource_type,
                "created_at": ev.created_at.isoformat(),
            }
            for ev in recent
        ],
    }


def lifecycle_history(db: Session, org: Organization) -> list[PartnerLifecycleEvent]:
    return (
        db.query(PartnerLifecycleEvent)
        .filter(PartnerLifecycleEvent.organization_id == org.id)
        .order_by(PartnerLifecycleEvent.created_at.asc())
        .all()
    )


def profile_metadata(db: Session, org: Organization) -> dict:
    profile = db.query(PartnerProfile).filter(PartnerProfile.organization_id == org.id).first()
    if profile is None:
        return {}
    try:
        return json.loads(profile.metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
