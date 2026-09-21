"""Medicine orders: patient creation, ownership-scoped views, pharmacy/admin
state transitions, prescription workflow (Phase 4, spec §14, §18-§20)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.pharmacy import MedicineOrder
from app.schemas.pharmacy import (
    OrderCreate,
    OrderOut,
    OrderStatusUpdate,
    PrescriptionRequestOut,
)
from app.security.deps import CurrentUser, record_audit
from app.services.order_service import (
    OrderError,
    create_order,
    get_owned_order,
    review_prescription,
    submit_prescription,
    transition_order,
)

router = APIRouter(prefix="/orders", tags=["orders"])


class PrescriptionSubmit(BaseModel):
    document_ref: str = Field(min_length=2, max_length=255)


class PrescriptionReview(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=1000)


@router.post("", response_model=OrderOut, status_code=201)
def place_order(
    payload: OrderCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Create an order with price snapshots (spec §19). Prescription-required
    medicines pause the order at PRESCRIPTION_REQUIRED — never bypassed."""
    try:
        order = create_order(db, payload, patient_id=user.id)
    except OrderError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db,
        action="ORDER_CREATED",
        actor_user_id=user.id,
        actor_role="PATIENT",
        resource_type="medicine_order",
        resource_id=order.id,
        detail=f"pharmacy={order.pharmacy_id} total={order.total} {order.currency} items={len(order.items)}",
    )
    db.commit()
    return order


@router.get("", response_model=list[OrderOut])
def my_orders(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    for_patient: str | None = Query(default=None, max_length=36),
):
    """Patient medicine history: own orders only (spec §20).

    Phase 6: `for_patient` adds a consent-scoped view for family members —
    requires an ACTIVE relationship with that patient plus VIEW_MEDICINE_ORDERS
    consent. The family member sees limited order data, never prescription
    content (spec §10: no prescribing/override).
    """
    query = (
        db.query(MedicineOrder)
        .order_by(MedicineOrder.created_at.desc())
    )
    if for_patient is None:
        query = query.filter(MedicineOrder.patient_id == user.id)
    else:
        if for_patient == user.id:
            query = query.filter(MedicineOrder.patient_id == user.id)
        else:
            from app.services import family_service

            rel = family_service.relationship_for_member(
                db, member_user_id=user.id, owner_user_id=for_patient
            )
            if rel is None:
                raise HTTPException(status_code=403, detail="No active family relationship with this patient")
            consent = family_service.active_consent(db, rel.id)
            if consent is None or "VIEW_MEDICINE_ORDERS" not in consent.scope_list:
                raise HTTPException(status_code=403, detail="VIEW_MEDICINE_ORDERS consent is required")
            record_audit(
                db,
                action="FAMILY_MEDICINE_ORDERS_VIEWED",
                actor_user_id=user.id,
                actor_role="PATIENT",
                resource_type="family",
                resource_id=rel.id,
                detail=f"subject={for_patient} relationship={rel.id}",
            )
            db.commit()
            query = query.filter(MedicineOrder.patient_id == for_patient)
    if status:
        query = query.filter(MedicineOrder.status == status)
    return query.limit(100).all()


@router.get("/{order_id}", response_model=OrderOut)
def order_detail(
    order_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Ownership-scoped: patients see only their own orders; pharmacy admins
    see orders for their pharmacy; 404 (not 403) otherwise to avoid leaking
    existence (spec §32)."""
    try:
        return get_owned_order(db, order_id, user)
    except OrderError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None


@router.patch("/{order_id}", response_model=OrderOut)
def update_status(
    order_id: str,
    payload: OrderStatusUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """State-machine transitions (spec §18). Pharmacy admins progress their
    pharmacy's orders; patients may only cancel their own CREATED /
    PRESCRIPTION_REQUIRED orders."""
    order = get_owned_order(db, order_id, user)
    is_patient_owner = order.patient_id == user.id and "PHARMACY_ADMIN" not in user.role_ids
    if is_patient_owner:
        if payload.status != "CANCELLED":
            raise HTTPException(status_code=403, detail="Patients may only cancel orders")
        if order.status not in ("CREATED", "PRESCRIPTION_REQUIRED"):
            raise HTTPException(
                status_code=409,
                detail="Order can no longer be cancelled from its current state",
            )
    if "PHARMACY_ADMIN" in user.role_ids and not is_patient_owner:
        # Pharmacy staff must manage their own pharmacy's orders.
        try:
            from app.services.pharmacy_service import get_owned_pharmacy

            get_owned_pharmacy(db, order.pharmacy_id, user)
        except Exception:  # PharmacyError
            raise HTTPException(status_code=403, detail="You do not manage this pharmacy") from None
    try:
        order = transition_order(db, order, payload.status, user)
    except OrderError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db,
        action="ORDER_STATUS_CHANGED",
        actor_user_id=user.id,
        actor_role=",".join(user.role_ids) or None,
        resource_type="medicine_order",
        resource_id=order.id,
        detail=f"-> {payload.status}",
    )
    db.commit()
    return order


@router.post("/{order_id}/prescription", response_model=PrescriptionRequestOut, status_code=201)
def add_prescription(
    order_id: str,
    payload: PrescriptionSubmit,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Patient submits a prescription document reference for a paused order.
    Submission is recorded; it does NOT fabricate approval (spec §14)."""
    try:
        order = get_owned_order(db, order_id, user)
    except OrderError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    if order.patient_id != user.id:
        raise HTTPException(status_code=403, detail="Only the patient can submit a prescription")
    try:
        request = submit_prescription(db, order, payload.document_ref)
    except OrderError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db,
        action="PRESCRIPTION_SUBMITTED",
        actor_user_id=user.id,
        actor_role="PATIENT",
        resource_type="prescription_request",
        resource_id=request.id,
        detail=f"order={order.id}",
    )
    db.commit()
    return request


@router.post("/{order_id}/prescription-review", response_model=OrderOut)
def prescription_review(
    order_id: str,
    payload: PrescriptionReview,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Pharmacy/admin review of a submitted prescription (spec §14). This is
    the only path to CONFIRMED for prescription orders — a human decision,
    recorded and audited."""
    order = get_owned_order(db, order_id, user)
    if "PHARMACY_ADMIN" not in user.role_ids and "SUPER_ADMIN" not in user.role_ids:
        raise HTTPException(status_code=403, detail="Insufficient role for this operation")
    if "SUPER_ADMIN" not in user.role_ids:
        try:
            from app.services.pharmacy_service import get_owned_pharmacy

            get_owned_pharmacy(db, order.pharmacy_id, user)
        except Exception:
            raise HTTPException(status_code=403, detail="You do not manage this pharmacy") from None
    try:
        order = review_prescription(
            db, order, approved=payload.approved, reviewer_user_id=user.id, note=payload.note
        )
    except OrderError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db,
        action="PRESCRIPTION_REVIEWED",
        actor_user_id=user.id,
        actor_role=",".join(user.role_ids) or None,
        resource_type="medicine_order",
        resource_id=order.id,
        detail=f"approved={payload.approved}",
    )
    db.commit()
    return order
