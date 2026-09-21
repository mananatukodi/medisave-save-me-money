"""Partner ecosystem endpoints (Phase 8).

SECURITY CONTRACT:
- Organization scope always comes from the path/ACTIVE membership — a
  client-supplied organization_id in a body is never trusted for authorization.
- Stranger access to another organization's resources → 404 (existence hidden).
- Stale membership → 403 (explicit, audited).
- Non-APPROVED organizations cannot perform protected operations.
- Every sensitive action writes an audit row via the service layer.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ops import FeatureFlag
from app.models.partner import Organization
from app.models.user import User
from app.schemas.partner import (
    ApiKeyCreate,
    ApiKeyCreated,
    ClaimCreate,
    ClaimEventOut,
    ClaimOut,
    ClaimTransition,
    DocumentCreate,
    DocumentOut,
    InsuranceProductCreate,
    InsuranceProductOut,
    IntegrationOut,
    LabBookingCreate,
    LabBookingOut,
    LabBookingStatus,
    LabTestCreate,
    LabTestOut,
    MemberCreate,
    MemberOut,
    MemberUpdate,
    NotificationOut,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    PartnerDashboard,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
    WebhookCreate,
)
from app.security.deps import CurrentUser
from app.services import partner_service
from app.services.partner_service import PartnerError

router = APIRouter(prefix="/partners", tags=["partners"])
partner_router = APIRouter(prefix="/partner", tags=["partner-portal"])


def _flag_enabled(db: Session, key: str) -> bool:
    flag = db.get(FeatureFlag, key)
    return bool(flag and flag.is_enabled)


def _flag_guard(db: Session, key: str) -> None:
    if not _flag_enabled(db, key):
        raise HTTPException(
            status_code=503,
            detail=f"This feature requires the '{key}' flag to be enabled",
        )


def _partner_error(err: PartnerError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=str(err))


def _get_scoped_org(db: Session, organization_id: str, user: User) -> Organization:
    """Load an organization the user is an ACTIVE member of (or SUPER_ADMIN).
    Existence is hidden from strangers (404)."""
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        partner_service.active_membership(db, org.id, user)
    except PartnerError as err:
        if err.status_code == 404:
            raise HTTPException(status_code=404, detail="Organization not found") from None
        raise _partner_error(err) from None
    return org


def _admin_org(db: Session, organization_id: str, user: User) -> Organization:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


# ------------------------------------------------------------- onboarding


@router.post("", response_model=OrganizationOut, status_code=201)
def register(
    payload: OrganizationCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Partner onboarding: creates a DRAFT organization with the caller as
    PARTNER_OWNER. Data comes from the partner — nothing is invented."""
    _flag_guard(db, "partner_onboarding")
    try:
        org, profile = partner_service.register_organization(db, payload=payload, owner=user)
        if payload.profile_metadata:
            import json

            profile.metadata_json = json.dumps(payload.profile_metadata)[:8000]
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return org


@router.get("/mine", response_model=list[OrganizationOut])
def my_organizations(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    _flag_guard(db, "partner_ecosystem")
    return partner_service.organizations_for_user(db, user)


@router.get("/{organization_id}", response_model=OrganizationOut)
def get_organization(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_ecosystem")
    org = _get_scoped_org(db, organization_id, user)
    return org


@router.patch("/{organization_id}", response_model=OrganizationOut)
def update_organization(
    organization_id: str,
    payload: OrganizationUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_ecosystem")
    org = _get_scoped_org(db, organization_id, user)
    try:
        member = partner_service.active_membership(db, org.id, user)
        if member.partner_role not in ("PARTNER_OWNER", "PARTNER_ADMIN", "PARTNER_MANAGER"):
            raise PartnerError("Only partner owner/admin/manager can update the organization", 403)
        partner_service.update_organization(db, org, payload, user)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return org


@router.post("/{organization_id}/submit", response_model=OrganizationOut)
def submit_for_review(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """DRAFT/SUBMITTED -> verification queue. Submission is the partner's
    declaration that details + required documents are complete; the admin
    decision happens later through the verification lifecycle."""
    _flag_guard(db, "partner_verification")
    org = _get_scoped_org(db, organization_id, user)
    try:
        member = partner_service.active_membership(db, org.id, user)
        if member.partner_role not in ("PARTNER_OWNER", "PARTNER_ADMIN"):
            raise PartnerError("Only partner owner/admin can submit for review", 403)
        if org.status == "DRAFT" and org.verification_status == "UNVERIFIED":
            # DRAFT -> SUBMITTED happens directly; a re-submission of a
            # REJECTED org routes through UNDER_REVIEW.
            partner_service.transition_organization(
                db, org, new_status="SUBMITTED", actor=user, note="submitted for review"
            )
        else:
            partner_service.transition_organization(
                db, org, new_status="UNDER_REVIEW", actor=user, note="submitted for review"
            )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return org


@router.get("/{organization_id}/history", response_model=list)
def lifecycle_history(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_ecosystem")
    org = _get_scoped_org(db, organization_id, user)
    return [
        {
            "id": ev.id,
            "previous_status": ev.previous_status,
            "new_status": ev.new_status,
            "actor_user_id": ev.actor_user_id,
            "note": ev.note,
            "created_at": ev.created_at.isoformat(),
        }
        for ev in partner_service.lifecycle_history(db, org)
    ]


# --------------------------------------------------------------- documents


@router.post("/{organization_id}/documents", response_model=DocumentOut, status_code=201)
def upload_document(
    organization_id: str,
    payload: DocumentCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_verification")
    org = _get_scoped_org(db, organization_id, user)
    try:
        doc = partner_service.create_document(
            db,
            org,
            document_type=payload.document_type,
            file_id=payload.file_id,
            storage_reference=payload.storage_reference,
            checksum=payload.checksum,
            issued_at=payload.issued_at,
            expires_at=payload.expires_at,
            actor=user,
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return doc


@router.get("/{organization_id}/documents", response_model=list[DocumentOut])
def list_documents(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_verification")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerDocument

    return (
        db.query(PartnerDocument)
        .filter(PartnerDocument.organization_id == org.id)
        .order_by(PartnerDocument.created_at.desc())
        .limit(100)
        .all()
    )


# ----------------------------------------------------------------- members


@router.post("/{organization_id}/members", response_model=MemberOut, status_code=201)
def add_member(
    organization_id: str,
    payload: MemberCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_ecosystem")
    org = _get_scoped_org(db, organization_id, user)
    try:
        member = partner_service.add_member(
            db, org, user_id=payload.user_id, partner_role=payload.partner_role, actor=user
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return member


@router.get("/{organization_id}/members", response_model=list[MemberOut])
def list_members(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_ecosystem")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import OrganizationMember

    return (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == org.id)
        .order_by(OrganizationMember.created_at.asc())
        .limit(200)
        .all()
    )


@router.patch("/{organization_id}/members/{member_id}", response_model=MemberOut)
def update_member(
    organization_id: str,
    member_id: str,
    payload: MemberUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_ecosystem")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import OrganizationMember

    member = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == org.id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    try:
        updated = partner_service.update_member(
            db, org, member, partner_role=payload.partner_role, actor=user
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return updated


@router.delete("/{organization_id}/members/{member_id}", response_model=MemberOut)
def remove_member(
    organization_id: str,
    member_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_ecosystem")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import OrganizationMember

    member = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == org.id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    try:
        updated = partner_service.remove_member(db, org, member, actor=user)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return updated


# ---------------------------------------------------------------- services


@router.get("/{organization_id}/services", response_model=list[ServiceOut])
def list_services(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_services")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerService

    return (
        db.query(PartnerService)
        .filter(PartnerService.organization_id == org.id)
        .order_by(PartnerService.created_at.desc())
        .limit(200)
        .all()
    )


@router.post("/{organization_id}/services", response_model=ServiceOut, status_code=201)
def create_service(
    organization_id: str,
    payload: ServiceCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_services")
    org = _get_scoped_org(db, organization_id, user)
    try:
        service = partner_service.create_service(db, org, payload, user)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return service


@router.patch("/{organization_id}/services/{service_id}", response_model=ServiceOut)
def update_service(
    organization_id: str,
    service_id: str,
    payload: ServiceUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_services")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerService

    service = (
        db.query(PartnerService)
        .filter(PartnerService.id == service_id, PartnerService.organization_id == org.id)
        .first()
    )
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    try:
        updated = partner_service.update_service(db, service, payload, user)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return updated


# ---------------------------------------------------------------- lab module


@router.post("/{organization_id}/lab/tests", response_model=LabTestOut, status_code=201)
def create_lab_test(
    organization_id: str,
    payload: LabTestCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_lab")
    org = _get_scoped_org(db, organization_id, user)
    try:
        test = partner_service.create_lab_test(db, org, payload, user)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return test


@router.get("/{organization_id}/lab/tests", response_model=list[LabTestOut])
def list_lab_tests(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_lab")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerLabTest

    return (
        db.query(PartnerLabTest)
        .filter(PartnerLabTest.organization_id == org.id)
        .order_by(PartnerLabTest.name.asc())
        .limit(200)
        .all()
    )


@router.post("/{organization_id}/lab/bookings", response_model=LabBookingOut, status_code=201)
def create_lab_booking(
    organization_id: str,
    payload: LabBookingCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Partner-entered booking reference for an existing patient (e.g. walk-in).
    Patient-initiated bookings go through the public lab-booking endpoint."""
    _flag_guard(db, "partner_lab")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerLabTest

    test = (
        db.query(PartnerLabTest)
        .filter(
            PartnerLabTest.id == payload.test_id,
            PartnerLabTest.organization_id == org.id,
        )
        .first()
    )
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found for this organization")
    patient = db.get(User, payload.patient_user_id) if payload.patient_user_id else None
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        booking = partner_service.create_lab_booking(
            db,
            test=test,
            patient=patient,
            collection_mode=payload.collection_mode,
            scheduled_for=payload.scheduled_for,
            notes=payload.notes,
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return booking


@router.post("/{organization_id}/lab/bookings/{booking_id}/status", response_model=LabBookingOut)
def lab_booking_status(
    organization_id: str,
    booking_id: str,
    payload: LabBookingStatus,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_lab")
    _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerLabBooking

    booking = (
        db.query(PartnerLabBooking)
        .filter(
            PartnerLabBooking.id == booking_id,
            PartnerLabBooking.organization_id == organization_id,
        )
        .first()
    )
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    try:
        updated = partner_service.transition_lab_booking(
            db, booking, new_status=payload.status, actor=user
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return updated


# --------------------------------------------------------- insurance module


@router.post("/{organization_id}/insurance/products", response_model=InsuranceProductOut, status_code=201)
def create_insurance_product(
    organization_id: str,
    payload: InsuranceProductCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_insurance")
    org = _get_scoped_org(db, organization_id, user)
    try:
        product = partner_service.create_insurance_product(db, org, payload, user)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return product


@router.get("/{organization_id}/insurance/products", response_model=list[InsuranceProductOut])
def list_insurance_products(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_insurance")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerInsuranceProduct

    return (
        db.query(PartnerInsuranceProduct)
        .filter(PartnerInsuranceProduct.organization_id == org.id)
        .order_by(PartnerInsuranceProduct.created_at.desc())
        .limit(100)
        .all()
    )


@router.post("/{organization_id}/insurance/claims", response_model=ClaimOut, status_code=201)
def create_claim(
    organization_id: str,
    payload: ClaimCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Partner-created claim for a real patient subject. Starts in DRAFT;
    nothing is approved automatically."""
    _flag_guard(db, "partner_claims")
    org = _get_scoped_org(db, organization_id, user)
    patient = db.get(User, payload.patient_user_id) if payload.patient_user_id else None
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        claim = partner_service.create_claim(db, org, patient=patient, payload=payload, actor=user)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return claim


@router.get("/{organization_id}/insurance/claims", response_model=list[ClaimOut])
def list_claims(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None, max_length=40),
):
    _flag_guard(db, "partner_claims")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerClaim

    query = db.query(PartnerClaim).filter(PartnerClaim.organization_id == org.id)
    if status:
        query = query.filter(PartnerClaim.status == status)
    return query.order_by(PartnerClaim.created_at.desc()).limit(100).all()


@router.post("/{organization_id}/insurance/claims/{claim_id}/status", response_model=ClaimOut)
def transition_claim(
    organization_id: str,
    claim_id: str,
    payload: ClaimTransition,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_claims")
    _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerClaim

    claim = (
        db.query(PartnerClaim)
        .filter(
            PartnerClaim.id == claim_id,
            PartnerClaim.organization_id == organization_id,
        )
        .first()
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    try:
        updated = partner_service.transition_claim(
            db,
            claim,
            new_status=payload.status,
            actor=user,
            note=payload.note,
            approved_amount=payload.approved_amount,
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return updated


@router.get("/{organization_id}/insurance/claims/{claim_id}/history", response_model=list[ClaimEventOut])
def claim_history(
    organization_id: str,
    claim_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_claims")
    _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerClaim

    claim = (
        db.query(PartnerClaim)
        .filter(
            PartnerClaim.id == claim_id,
            PartnerClaim.organization_id == organization_id,
        )
        .first()
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return partner_service.claim_events(db, claim)


# ------------------------------------------------------------- integrations


@router.post("/{organization_id}/integrations/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_api_key(
    organization_id: str,
    payload: ApiKeyCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_api")
    org = _get_scoped_org(db, organization_id, user)
    try:
        integration, raw_key = partner_service.create_api_key(
            db, org, name=payload.name, scopes=payload.scopes, actor=user
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    out = ApiKeyCreated.model_validate(integration, from_attributes=True)
    out = out.model_copy(update={"raw_key": raw_key})  # shown once; only the hash is stored
    return out


@router.post("/{organization_id}/integrations/webhooks", response_model=IntegrationOut, status_code=201)
def register_webhook(
    organization_id: str,
    payload: WebhookCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_webhooks")
    org = _get_scoped_org(db, organization_id, user)
    try:
        integration = partner_service.register_webhook(
            db, org, name=payload.name, endpoint_url=payload.endpoint_url, actor=user
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return integration


@router.get("/{organization_id}/integrations", response_model=list[IntegrationOut])
def list_integrations(
    organization_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_webhooks")
    org = _get_scoped_org(db, organization_id, user)
    from app.models.partner import PartnerIntegration

    return (
        db.query(PartnerIntegration)
        .filter(PartnerIntegration.organization_id == org.id)
        .order_by(PartnerIntegration.created_at.desc())
        .limit(100)
        .all()
    )


# ------------------------------------------------------- partner portal


@partner_router.get("/dashboard", response_model=PartnerDashboard)
def partner_dashboard(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Aggregated operations dashboard across the caller's organizations.
    Counts only — no patient clinical content."""
    _flag_guard(db, "partner_ecosystem")
    return PartnerDashboard.model_validate(partner_service.dashboard_for_user(db, user))


@partner_router.get("/notifications", response_model=list[NotificationOut])
def partner_notifications(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
):
    _flag_guard(db, "partner_ecosystem")
    return partner_service.notifications_for_user(db, user, limit=limit)


# ------------------------------------------------------- patient-facing


lab_public_router = APIRouter(prefix="/lab-tests", tags=["lab-tests"])
claims_public_router = APIRouter(prefix="/insurance/claims", tags=["insurance-claims"])


@lab_public_router.get("", response_model=list[LabTestOut])
def public_lab_tests(
    db: Annotated[Session, Depends(get_db)],
    organization_id: str | None = Query(default=None, max_length=36),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Public verified test catalog: only VERIFIED tests at APPROVED labs are
    shown. Prices appear exactly as verified — none are invented."""
    _flag_guard(db, "partner_lab")
    from app.models.partner import PartnerLabTest

    query = (
        db.query(PartnerLabTest)
        .join(Organization, Organization.id == PartnerLabTest.organization_id)
        .filter(
            PartnerLabTest.verification_status == "VERIFIED",
            PartnerLabTest.is_active.is_(True),
            Organization.status == "APPROVED",
        )
    )
    if organization_id:
        query = query.filter(PartnerLabTest.organization_id == organization_id)
    if q:
        query = query.filter(PartnerLabTest.name.ilike(f"%{q}%"))
    return query.order_by(PartnerLabTest.name.asc()).limit(limit).all()


@claims_public_router.get("", response_model=list[ClaimOut])
def my_claims(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Patient's own insurance claims (owner-scoped)."""
    _flag_guard(db, "partner_claims")
    from app.models.partner import PartnerClaim

    return (
        db.query(PartnerClaim)
        .filter(PartnerClaim.patient_user_id == user.id)
        .order_by(PartnerClaim.created_at.desc())
        .limit(100)
        .all()
    )


@claims_public_router.get("/{claim_id}", response_model=ClaimOut)
def my_claim(
    claim_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    _flag_guard(db, "partner_claims")
    from app.models.partner import PartnerClaim

    claim = (
        db.query(PartnerClaim)
        .filter(PartnerClaim.id == claim_id, PartnerClaim.patient_user_id == user.id)
        .first()
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim
