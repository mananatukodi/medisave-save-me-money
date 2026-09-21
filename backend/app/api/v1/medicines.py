"""Medicine catalog: search, detail, prices, availability, savings (Phase 4).

The catalog starts EMPTY. Medicines enter only through the SUPER_ADMIN
master-data workflow (POST /medicines) — no fabricated starter data (spec §28).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.pharmacy import Medicine, MedicineAlias, MedicinePrice, Pharmacy, PharmacyInventory
from app.schemas.pharmacy import (
    InventoryOut,
    MedicineCreate,
    MedicineOut,
    PriceOut,
    SavingsOut,
)
from app.security.deps import CurrentUser, record_audit, require_roles
from app.services.savings_service import compute_savings

router = APIRouter(prefix="/medicines", tags=["medicines"])


@router.get("", response_model=list[MedicineOut])
def search_medicines(
    db: Annotated[Session, Depends(get_db)],
    q: str | None = Query(default=None, max_length=255),
    dosage_form: str | None = Query(default=None, max_length=20),
    prescription_required: bool | None = None,
    status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Paginated search across name, generic, brand, manufacturer, and aliases
    (exact + partial match). Returns an honest empty list when the catalog is
    empty — never fake entries (spec §3, §28)."""
    query = db.query(Medicine)
    query = query.filter(Medicine.status == (status or "ACTIVE"))
    if dosage_form:
        query = query.filter(Medicine.dosage_form == dosage_form)
    if prescription_required is not None:
        query = query.filter(Medicine.prescription_required.is_(prescription_required))
    if q:
        needle = f"%{q.lower()}%"
        alias_ids = (
            db.query(MedicineAlias.medicine_id)
            .filter(MedicineAlias.alias.ilike(needle))
            .subquery()
        )
        query = query.filter(
            or_(
                Medicine.name.ilike(needle),
                Medicine.generic_name.ilike(needle),
                Medicine.brand_name.ilike(needle),
                Medicine.manufacturer.ilike(needle),
                Medicine.id.in_(alias_ids),
            )
        )
    return query.order_by(Medicine.name.asc()).offset(offset).limit(limit).all()


@router.get("/{medicine_id}", response_model=MedicineOut)
def medicine_detail(medicine_id: str, db: Annotated[Session, Depends(get_db)]):
    medicine = db.get(Medicine, medicine_id)
    if medicine is None or medicine.status != "ACTIVE":
        raise HTTPException(status_code=404, detail="Medicine not found")
    return medicine


@router.get("/{medicine_id}/prices", response_model=list[PriceOut])
def medicine_prices(
    medicine_id: str,
    db: Annotated[Session, Depends(get_db)],
    city: str | None = Query(default=None, max_length=120),
    include_all: bool = Query(
        default=False, description="SUPER_ADMIN review: include non-verified records"
    ),
):
    """Verified, current, comparable price records with provenance (spec §9,
    §10). Only the same strength/dosage-form/pack-size representation is
    returned. Unverified data is never presented as a verified current price."""
    medicine = db.get(Medicine, medicine_id)
    if medicine is None:
        raise HTTPException(status_code=404, detail="Medicine not found")

    query = (
        db.query(MedicinePrice)
        .options(joinedload(MedicinePrice.pharmacy))
        .join(Pharmacy, MedicinePrice.pharmacy_id == Pharmacy.id)
        .filter(
            MedicinePrice.medicine_id == medicine_id,
            Pharmacy.verification_status == "VERIFIED",
            Pharmacy.is_active.is_(True),
        )
    )
    if not include_all:
        query = query.filter(
            MedicinePrice.verification_status == "VERIFIED",
            MedicinePrice.is_current.is_(True),
            MedicinePrice.valid_until.is_(None) | (MedicinePrice.valid_until >= date.today()),
        )
    if city:
        query = query.filter(Pharmacy.city == city)

    rows = []
    for p in query.all():
        if p.medicine.representation_key != medicine.representation_key:
            continue  # never compare mismatched representations (spec §10)
        row = PriceOut.model_validate(p)
        row.pharmacy_name = p.pharmacy.name
        row.last_updated = p.updated_at
        rows.append(row)
    return rows


@router.get("/{medicine_id}/availability", response_model=list[InventoryOut])
def medicine_availability(medicine_id: str, db: Annotated[Session, Depends(get_db)]):
    """Verified pharmacies' stock for this medicine. UNKNOWN stays UNKNOWN
    (spec §7) — the API never upgrades stock status."""
    if db.get(Medicine, medicine_id) is None:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return (
        db.query(PharmacyInventory)
        .join(Pharmacy, PharmacyInventory.pharmacy_id == Pharmacy.id)
        .filter(
            PharmacyInventory.medicine_id == medicine_id,
            Pharmacy.verification_status == "VERIFIED",
            Pharmacy.is_active.is_(True),
        )
        .all()
    )


@router.get("/{medicine_id}/savings", response_model=SavingsOut)
def medicine_savings(medicine_id: str, db: Annotated[Session, Depends(get_db)]):
    """Savings engine result. When verified data is insufficient, the response
    says so — `potential_savings` stays null (spec §11, §12, §37)."""
    return compute_savings(db, medicine_id)


# ------------------------------------------------------- admin master data

@router.post(
    "",
    response_model=MedicineOut,
    status_code=201,
    dependencies=[Depends(require_roles("SUPER_ADMIN"))],
)
def create_medicine(
    payload: MedicineCreate,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """SUPER_ADMIN medicine master-data creation. `description` and
    `data_source` must reflect real source information; provenance is recorded
    and audited (spec §2, §20)."""
    medicine = Medicine(
        name=payload.name.strip(),
        generic_name=payload.generic_name,
        brand_name=payload.brand_name,
        manufacturer=payload.manufacturer,
        strength=payload.strength,
        dosage_form=payload.dosage_form,
        pack_size=payload.pack_size,
        prescription_required=payload.prescription_required,
        description=payload.description,
        active_ingredients=payload.active_ingredients,
        data_source=payload.data_source,
        status="ACTIVE",
    )
    db.add(medicine)
    db.flush()
    record_audit(
        db,
        action="MEDICINE_CREATED",
        actor_user_id=admin.id,
        actor_role="SUPER_ADMIN",
        resource_type="medicine",
        resource_id=medicine.id,
        detail=(
            f"{medicine.name} | {medicine.strength} | {medicine.dosage_form} "
            f"| source={medicine.data_source}"
        ),
    )
    db.commit()
    return medicine
