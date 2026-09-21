"""MediSave Savings Engine (Phase 4, spec §11-§12).

Central product principle: "Save Me Money" — but every claimed saving must be
supported by actual verified data.

Rules enforced here:
- Only VERIFIED, unexpired prices from VERIFIED+ACTIVE pharmacies participate.
- Prices are only compared across the SAME representation
  (strength + dosage_form + pack_size) of the same medicine.
- `potential_savings = reference_price - selected_price` only when a valid
  reference (highest verified price) and a cheaper verified alternative exist.
- With fewer than two comparable verified prices, status is INSUFFICIENT_DATA
  (or NO_COMPARISON) and `potential_savings` stays None — never a fabricated
  number.
"""

from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.models.pharmacy import Medicine, MedicinePrice, Pharmacy
from app.schemas.pharmacy import SavingsOut


def _comparable_prices(db: Session, medicine_id: str) -> list[MedicinePrice]:
    """Verified, unexpired, current prices from verified pharmacies, with
    pharmacy joined once (no N+1, spec §38)."""
    today = date.today()
    return (
        db.query(MedicinePrice)
        .options(joinedload(MedicinePrice.pharmacy))
        .join(Pharmacy, MedicinePrice.pharmacy_id == Pharmacy.id)
        .filter(
            MedicinePrice.medicine_id == medicine_id,
            MedicinePrice.verification_status == "VERIFIED",
            MedicinePrice.is_current.is_(True),
            MedicinePrice.valid_until.is_(None) | (MedicinePrice.valid_until >= today),
            Pharmacy.verification_status == "VERIFIED",
            Pharmacy.is_active.is_(True),
        )
        .all()
    )


def compute_savings(db: Session, medicine_id: str) -> SavingsOut:
    medicine = db.get(Medicine, medicine_id)
    if medicine is None:
        return SavingsOut(medicine_id=medicine_id, status="MEDICINE_NOT_FOUND")

    prices = _comparable_prices(db, medicine_id)
    if not prices:
        return SavingsOut(
            medicine_id=medicine_id,
            status="INSUFFICIENT_DATA",
            note="Verified price data is currently unavailable.",
        )

    # Compatibility guard: split by representation; compare only within the
    # dominant group so different strength/form/pack are never mixed (spec §10).
    by_repr: dict[str, list[MedicinePrice]] = {}
    for p in prices:
        by_repr.setdefault(p.medicine.representation_key, []).append(p)
    dominant_key, group = max(by_repr.items(), key=lambda kv: len(kv[1]))

    if len(group) < 2:
        return SavingsOut(
            medicine_id=medicine_id,
            status="INSUFFICIENT_DATA",
            representation_key=dominant_key,
            note=(
                "Verified price data is insufficient to calculate savings. "
                "Price comparison available."
            ),
        )

    ordered = sorted(group, key=lambda p: (p.price, p.created_at))
    cheapest = ordered[0]
    reference = ordered[-1]
    savings = round(float(reference.price) - float(cheapest.price), 2)

    if savings <= 0:
        return SavingsOut(
            medicine_id=medicine_id,
            status="NO_COMPARISON",
            representation_key=dominant_key,
            reference_price=float(reference.price),
            reference_pharmacy_id=reference.pharmacy_id,
            reference_pharmacy_name=reference.pharmacy.name,
            selected_price=float(cheapest.price),
            selected_pharmacy_id=cheapest.pharmacy_id,
            selected_pharmacy_name=cheapest.pharmacy.name,
            note="All verified pharmacies currently list the same price.",
        )

    return SavingsOut(
        medicine_id=medicine_id,
        status="CALCULATED",
        representation_key=dominant_key,
        reference_price=float(reference.price),
        reference_pharmacy_id=reference.pharmacy_id,
        reference_pharmacy_name=reference.pharmacy.name,
        selected_price=float(cheapest.price),
        selected_pharmacy_id=cheapest.pharmacy_id,
        selected_pharmacy_name=cheapest.pharmacy.name,
        potential_savings=savings,
        currency=cheapest.currency,
        source="Verified pharmacy price data",
        last_updated=cheapest.updated_at,
        note=(
            "Reference is the highest current verified price; the selected price "
            "is the lowest current verified price for the same pack, strength, "
            "and dosage form."
        ),
    )
