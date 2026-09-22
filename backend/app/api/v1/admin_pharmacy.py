"""Admin pharmacy verification + price verification workflows (Phase 4,
spec §6, §21, §26, §27) — SUPER_ADMIN only. Every decision is audited and
writes an immutable history row."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.pharmacy import MedicinePrice, Pharmacy, PharmacyVerification
from app.schemas.pharmacy import (
    PharmacyPublic,
    PriceDecision,
    PriceVerificationQueueOut,
    VerificationDecision,
    VerificationHistoryOut,
)
from app.security.deps import CurrentUser, record_audit, require_roles
from app.services.pharmacy_service import (
    PharmacyError,
    decide_pharmacy_verification,
    decide_price,
    expire_stale_prices,
)

router = APIRouter(
    prefix="/admin",
    tags=["admin-pharmacy"],
    dependencies=[Depends(require_roles("SUPER_ADMIN"))],
)


def _load_pharmacy(db: Session, pharmacy_id: str) -> Pharmacy:
    pharmacy = db.get(Pharmacy, pharmacy_id)
    if pharmacy is None:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    return pharmacy


def _apply_pharmacy_decision(
    pharmacy_id: str,
    new_status: str,
    note: str,
    admin: CurrentUser,
    db: Session,
) -> Pharmacy:
    pharmacy = _load_pharmacy(db, pharmacy_id)
    decision = VerificationDecision(new_status=new_status, decision_note=note)
    try:
        pharmacy = decide_pharmacy_verification(db, pharmacy, decision, admin_user_id=admin.id)
    except PharmacyError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db,
        action=f"PHARMACY_{new_status}",
        actor_user_id=admin.id,
        actor_role="SUPER_ADMIN",
        resource_type="pharmacy",
        resource_id=pharmacy.id,
        detail=f"-> {new_status}: {note[:200]}",
    )
    db.commit()
    return pharmacy


@router.get("/pharmacies/verification", response_model=list[PharmacyPublic])
def pharmacy_queue(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None),
):
    query = db.query(Pharmacy).order_by(Pharmacy.created_at.asc())
    if status:
        query = query.filter(Pharmacy.verification_status == status)
    return query.limit(100).all()


@router.post("/pharmacies/{pharmacy_id}/verify", response_model=PharmacyPublic)
def verify_pharmacy(
    pharmacy_id: str, admin: CurrentUser, db: Annotated[Session, Depends(get_db)]
):
    return _apply_pharmacy_decision(pharmacy_id, "VERIFIED", "Verified by admin", admin, db)


@router.post("/pharmacies/{pharmacy_id}/reject", response_model=PharmacyPublic)
def reject_pharmacy(
    pharmacy_id: str,
    payload: VerificationDecision,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if payload.new_status not in ("REJECTED", "SUSPENDED", "PENDING", "UNDER_REVIEW"):
        raise HTTPException(status_code=422, detail="Use /verify for approval")
    return _apply_pharmacy_decision(
        pharmacy_id, payload.new_status, payload.decision_note, admin, db
    )


@router.post("/pharmacies/{pharmacy_id}/suspend", response_model=PharmacyPublic)
def suspend_pharmacy(
    pharmacy_id: str,
    payload: VerificationDecision,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if payload.new_status != "SUSPENDED":
        raise HTTPException(status_code=422, detail="suspend requires new_status=SUSPENDED")
    return _apply_pharmacy_decision(
        pharmacy_id, "SUSPENDED", payload.decision_note, admin, db
    )


@router.post("/pharmacies/{pharmacy_id}/review", response_model=PharmacyPublic)
def review_pharmacy(
    pharmacy_id: str,
    payload: VerificationDecision,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if payload.new_status != "UNDER_REVIEW":
        raise HTTPException(status_code=422, detail="review requires new_status=UNDER_REVIEW")
    return _apply_pharmacy_decision(
        pharmacy_id, "UNDER_REVIEW", payload.decision_note, admin, db
    )


@router.get("/pharmacies/{pharmacy_id}/history", response_model=list[VerificationHistoryOut])
def pharmacy_history(pharmacy_id: str, db: Annotated[Session, Depends(get_db)]):
    _load_pharmacy(db, pharmacy_id)
    return (
        db.query(PharmacyVerification)
        .filter(PharmacyVerification.pharmacy_id == pharmacy_id)
        .order_by(PharmacyVerification.created_at.desc())
        .all()
    )


# ------------------------------------------------------- price verification

@router.get("/prices/verification", response_model=list[PriceVerificationQueueOut])
def price_queue(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
):
    """Price records by verification status (PENDING by default). Admin can
    identify VERIFIED / UNVERIFIED / EXPIRED / REJECTED records (spec §26)."""
    query = (
        db.query(MedicinePrice)
        .options(joinedload(MedicinePrice.pharmacy), joinedload(MedicinePrice.medicine))
        .join(Pharmacy, MedicinePrice.pharmacy_id == Pharmacy.id)
        .order_by(MedicinePrice.created_at.asc())
    )
    query = query.filter(MedicinePrice.verification_status == (status or "PENDING"))
    rows = []
    for p in query.limit(limit).all():
        rows.append(
            PriceVerificationQueueOut(
                id=p.id,
                medicine_id=p.medicine_id,
                medicine_name=p.medicine.name if p.medicine else "",
                pharmacy_id=p.pharmacy_id,
                pharmacy_name=p.pharmacy.name,
                price=float(p.price),
                currency=p.currency,
                source=p.source,
                submitted_at=p.created_at,
                verification_status=p.verification_status,
            )
        )
    return rows


@router.post("/prices/{price_id}/decision")
def price_decision(
    price_id: str,
    payload: PriceDecision,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    price = db.get(MedicinePrice, price_id)
    if price is None:
        raise HTTPException(status_code=404, detail="Price record not found")
    try:
        price = decide_price(db, price, payload, admin_user_id=admin.id)
    except PharmacyError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db,
        action=f"PRICE_{payload.decision}",
        actor_user_id=admin.id,
        actor_role="SUPER_ADMIN",
        resource_type="medicine_price",
        resource_id=price.id,
        detail=f"price={price.price} {price.currency}: {payload.note[:180]}",
    )
    db.commit()
    return {
        "id": price.id,
        "verification_status": price.verification_status,
        "verified_at": str(price.verified_at) if price.verified_at else None,
    }


@router.post("/prices/expire-stale")
def run_price_expiration(admin: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """VERIFIED -> EXPIRED sweep (spec §27). In production this runs as a
    scheduled worker; it is exposed here for operational control and tests."""
    count = expire_stale_prices(db)
    if count:
        record_audit(
            db,
            action="PRICES_EXPIRED",
            actor_user_id=admin.id,
            actor_role="SUPER_ADMIN",
            resource_type="medicine_price",
            resource_id=None,
            detail=f"expired={count}",
        )
    db.commit()
    return {"expired": count}
