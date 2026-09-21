"""Admin partner governance endpoints (Phase 8) — SUPER_ADMIN only.

Every decision writes an immutable lifecycle/document history row AND an audit
entry (same pattern as Phase 3/4 verification queues). Aggregates only — no
patient clinical content.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.partner import (
    Organization,
    PartnerClaim,
    PartnerDocument,
    PartnerLabTest,
)
from app.schemas.partner import (
    DocumentDecision,
    DocumentOut,
    LabTestOut,
    LifecycleEventOut,
    OrganizationAdminOut,
)
from app.security.deps import CurrentUser, require_roles
from app.services import partner_service
from app.services.partner_service import PartnerError

router = APIRouter(
    prefix="/admin/partners",
    tags=["admin-partners"],
    dependencies=[Depends(require_roles("SUPER_ADMIN"))],
)


def _partner_error(err: PartnerError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=str(err))


def _get_org(db: Session, organization_id: str) -> Organization:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get("", response_model=list[OrganizationAdminOut])
def list_organizations(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None, max_length=24),
    organization_type: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=100, ge=1, le=200),
):
    query = db.query(Organization).order_by(Organization.created_at.asc())
    if status:
        query = query.filter(Organization.status == status)
    if organization_type:
        query = query.filter(Organization.organization_type == organization_type)
    return query.limit(limit).all()


@router.get("/overview")
def overview(db: Annotated[Session, Depends(get_db)]) -> dict:
    """Aggregate governance metrics: type/status counts, pending documents,
    claims/appointments/orders aggregates. No patient clinical content."""
    data = partner_service.admin_overview(db)
    # Operational cross-links (counts only — never patient data)
    from sqlalchemy import func

    from app.models.appointment import Appointment

    data["appointments_total"] = int(db.query(func.count(Appointment.id)).scalar() or 0)
    from app.models.pharmacy import MedicineOrder

    data["orders_total"] = int(db.query(func.count(MedicineOrder.id)).scalar() or 0)
    data["claims_total"] = int(db.query(func.count(PartnerClaim.id)).scalar() or 0)
    return data


@router.get("/{organization_id}", response_model=OrganizationAdminOut)
def get_organization(organization_id: str, db: Annotated[Session, Depends(get_db)]):
    return _get_org(db, organization_id)


@router.get("/{organization_id}/history", response_model=list[LifecycleEventOut])
def lifecycle_history(organization_id: str, db: Annotated[Session, Depends(get_db)]):
    return partner_service.lifecycle_history(db, _get_org(db, organization_id))


@router.get("/{organization_id}/documents", response_model=list[DocumentOut])
def org_documents(organization_id: str, db: Annotated[Session, Depends(get_db)]):
    org = _get_org(db, organization_id)
    return (
        db.query(PartnerDocument)
        .filter(PartnerDocument.organization_id == org.id)
        .order_by(PartnerDocument.created_at.desc())
        .limit(100)
        .all()
    )


@router.post("/{organization_id}/documents/{document_id}/decision", response_model=DocumentOut)
def decide_document(
    organization_id: str,
    document_id: str,
    payload: DocumentDecision,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    org = _get_org(db, organization_id)
    doc = (
        db.query(PartnerDocument)
        .filter(
            PartnerDocument.id == document_id,
            PartnerDocument.organization_id == org.id,
        )
        .first()
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        updated = partner_service.decide_document(
            db, doc, decision=payload.decision, admin=admin, note=payload.note
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return updated


# ---------------------------------------------------- lifecycle decisions


@router.post("/{organization_id}/review", response_model=OrganizationAdminOut)
def start_review(organization_id: str, admin: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    org = _get_org(db, organization_id)
    try:
        partner_service.transition_organization(
            db, org, new_status="UNDER_REVIEW", actor=admin, note="admin review started"
        )
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return org


@router.post("/{organization_id}/approve", response_model=OrganizationAdminOut)
def approve(organization_id: str, admin: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    org = _get_org(db, organization_id)
    try:
        partner_service.transition_organization(db, org, new_status="APPROVED", actor=admin)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return org


@router.post("/{organization_id}/reject", response_model=OrganizationAdminOut)
def reject(organization_id: str, admin: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    org = _get_org(db, organization_id)
    try:
        partner_service.transition_organization(db, org, new_status="REJECTED", actor=admin)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return org


@router.post("/{organization_id}/suspend", response_model=OrganizationAdminOut)
def suspend(organization_id: str, admin: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    org = _get_org(db, organization_id)
    try:
        partner_service.transition_organization(db, org, new_status="SUSPENDED", actor=admin)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return org


@router.post("/{organization_id}/reactivate", response_model=OrganizationAdminOut)
def reactivate(organization_id: str, admin: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """SUSPENDED -> APPROVED (re-approval after suspension)."""
    org = _get_org(db, organization_id)
    try:
        partner_service.transition_organization(db, org, new_status="APPROVED", actor=admin)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return org


@router.post("/{organization_id}/deactivate", response_model=OrganizationAdminOut)
def deactivate(organization_id: str, admin: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    org = _get_org(db, organization_id)
    try:
        partner_service.transition_organization(db, org, new_status="DEACTIVATED", actor=admin)
        db.commit()
    except PartnerError as err:
        raise _partner_error(err) from None
    return org


# ------------------------------------------------- lab test verification


@router.get("/lab/tests/queue", response_model=list[LabTestOut])
def lab_test_queue(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None, max_length=20),
):
    query = db.query(PartnerLabTest).order_by(PartnerLabTest.created_at.asc())
    if status:
        query = query.filter(PartnerLabTest.verification_status == status)
    return query.limit(100).all()


@router.post("/lab/tests/{test_id}/decision", response_model=LabTestOut)
def decide_lab_test(
    test_id: str,
    payload: DocumentDecision,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Human verification of a partner-entered lab test (catalog + price).
    decision VERIFIED | REJECTED."""
    test = db.get(PartnerLabTest, test_id)
    if test is None:
        raise HTTPException(status_code=404, detail="Lab test not found")
    if payload.decision not in ("VERIFIED", "REJECTED"):
        raise HTTPException(status_code=422, detail="decision must be VERIFIED or REJECTED")
    test.verification_status = payload.decision
    from app.services.partner_service import _audit

    _audit(
        db,
        actor_user_id=admin.id,
        action="PARTNER_LAB_TEST_DECISION",
        resource_type="partner_lab_test",
        resource_id=test.id,
        detail=f"-> {payload.decision}: {payload.note[:200]}",
        actor_role="SUPER_ADMIN",
    )
    db.commit()
    return test
