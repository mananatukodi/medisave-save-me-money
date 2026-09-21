"""Pharmacy search, profile, registration, and self-service (Phase 4).

Public search exposes only VERIFIED+ACTIVE pharmacies. Registration numbers
are never exposed to patients (spec §15, §16).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.pharmacy import Pharmacy, PharmacyInventory
from app.schemas.pharmacy import (
    InventoryOut,
    InventoryUpsert,
    PharmacyPublic,
    PharmacyRegistration,
    PharmacyUpdate,
    PriceSubmit,
)
from app.security.deps import CurrentUser, record_audit, require_roles
from app.services.pharmacy_service import (
    PharmacyError,
    public_pharmacies_query,
    register_pharmacy,
    submit_price,
    upsert_inventory,
)

router = APIRouter(prefix="/pharmacies", tags=["pharmacies"])


@router.get("", response_model=list[PharmacyPublic])
def search_pharmacies(
    db: Annotated[Session, Depends(get_db)],
    city: str | None = Query(default=None, max_length=120),
    state: str | None = Query(default=None, max_length=120),
    postal_code: str | None = Query(default=None, max_length=12),
    medicine_id: str | None = Query(default=None, max_length=36),
    delivery_supported: bool | None = None,
    pickup_supported: bool | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Public pharmacy search — VERIFIED+ACTIVE only. `medicine_id` filters to
    pharmacies stocking that medicine; an empty result is honest (spec §15)."""
    query = public_pharmacies_query(db)
    if city:
        query = query.filter(Pharmacy.city == city)
    if state:
        query = query.filter(Pharmacy.state == state)
    if postal_code:
        query = query.filter(Pharmacy.postal_code == postal_code)
    if delivery_supported is not None:
        query = query.filter(Pharmacy.delivery_supported.is_(delivery_supported))
    if pickup_supported is not None:
        query = query.filter(Pharmacy.pickup_supported.is_(pickup_supported))
    if medicine_id:
        query = query.join(
            PharmacyInventory,
            PharmacyInventory.pharmacy_id == Pharmacy.id,
        ).filter(
            PharmacyInventory.medicine_id == medicine_id,
            PharmacyInventory.stock_status.in_(("IN_STOCK", "LOW_STOCK")),
        )
    return query.offset(offset).limit(limit).all()


@router.post(
    "",
    response_model=PharmacyPublic,
    status_code=201,
    dependencies=[Depends(require_roles("PHARMACY_ADMIN"))],
)
def register(
    payload: PharmacyRegistration,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Pharmacy onboarding (spec §5). New pharmacies start PENDING — never
    displayed as verified until a real admin decision exists."""
    pharmacy = register_pharmacy(db, payload, admin_user_id=user.id)
    record_audit(
        db,
        action="PHARMACY_REGISTERED",
        actor_user_id=user.id,
        actor_role="PHARMACY_ADMIN",
        resource_type="pharmacy",
        resource_id=pharmacy.id,
        detail=f"{pharmacy.name} | city={pharmacy.city}",
    )
    db.commit()
    return pharmacy


@router.get("/me", response_model=PharmacyPublic)
def my_pharmacy(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    pharmacy = (
        db.query(Pharmacy).filter(Pharmacy.admin_user_id == user.id).first()
    )
    if pharmacy is None:
        raise HTTPException(status_code=404, detail="No pharmacy registered for this user")
    return pharmacy


@router.get("/{pharmacy_id}", response_model=PharmacyPublic)
def pharmacy_detail(pharmacy_id: str, db: Annotated[Session, Depends(get_db)]):
    pharmacy = db.get(Pharmacy, pharmacy_id)
    if (
        pharmacy is None
        or not pharmacy.is_active
        or pharmacy.verification_status != "VERIFIED"
    ):
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    return pharmacy


# --------------------------------------------------------- self-service

self_router = APIRouter(prefix="/pharmacies", tags=["pharmacy-admin"])


@self_router.patch("/me", response_model=PharmacyPublic)
def update_my_pharmacy(
    payload: PharmacyUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    pharmacy = (
        db.query(Pharmacy).filter(Pharmacy.admin_user_id == user.id).first()
    )
    if pharmacy is None:
        raise HTTPException(status_code=404, detail="No pharmacy registered for this user")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(pharmacy, field, value)
    record_audit(
        db,
        action="PHARMACY_PROFILE_UPDATED",
        actor_user_id=user.id,
        actor_role="PHARMACY_ADMIN",
        resource_type="pharmacy",
        resource_id=pharmacy.id,
        detail=f"fields={sorted(data)}",
    )
    db.commit()
    return pharmacy


@self_router.get("/me/inventory", response_model=list[InventoryOut])
def my_inventory(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    pharmacy = (
        db.query(Pharmacy).filter(Pharmacy.admin_user_id == user.id).first()
    )
    if pharmacy is None:
        raise HTTPException(status_code=404, detail="No pharmacy registered for this user")
    return (
        db.query(PharmacyInventory)
        .filter(PharmacyInventory.pharmacy_id == pharmacy.id)
        .all()
    )


@self_router.post("/me/inventory", response_model=InventoryOut, status_code=201)
def upsert_my_inventory(
    payload: InventoryUpsert,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Add/update stock (spec §7). UNKNOWN is stored as UNKNOWN — the API never
    upgrades it."""
    pharmacy = (
        db.query(Pharmacy).filter(Pharmacy.admin_user_id == user.id).first()
    )
    if pharmacy is None:
        raise HTTPException(status_code=404, detail="No pharmacy registered for this user")
    try:
        row = upsert_inventory(db, pharmacy, payload)
    except PharmacyError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db,
        action="INVENTORY_UPDATED",
        actor_user_id=user.id,
        actor_role="PHARMACY_ADMIN",
        resource_type="pharmacy_inventory",
        resource_id=row.id,
        detail=f"pharmacy={pharmacy.id} medicine={payload.medicine_id} status={payload.stock_status}",
    )
    db.commit()
    return row


@self_router.post("/me/prices", status_code=201)
def submit_my_price(
    payload: PriceSubmit,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Submit a price version (spec §8, §17, §27). Creates a NEW PENDING row —
    history is never silently overwritten; the price becomes patient-visible
    only after SUPER_ADMIN verification."""
    pharmacy = (
        db.query(Pharmacy).filter(Pharmacy.admin_user_id == user.id).first()
    )
    if pharmacy is None:
        raise HTTPException(status_code=404, detail="No pharmacy registered for this user")
    try:
        price = submit_price(db, pharmacy, payload)
    except PharmacyError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db,
        action="PRICE_SUBMITTED",
        actor_user_id=user.id,
        actor_role="PHARMACY_ADMIN",
        resource_type="medicine_price",
        resource_id=price.id,
        detail=f"medicine={payload.medicine_id} price={payload.price} {payload.currency}",
    )
    db.commit()
    return {
        "id": price.id,
        "medicine_id": price.medicine_id,
        "price": float(price.price),
        "currency": price.currency,
        "verification_status": price.verification_status,
        "valid_from": str(price.valid_from) if price.valid_from else None,
        "valid_until": str(price.valid_until) if price.valid_until else None,
    }
