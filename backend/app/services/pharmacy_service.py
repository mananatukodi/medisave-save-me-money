"""Pharmacy registration, verification, inventory, and price lifecycle (Phase 4).

Verification rule: a pharmacy's `verification_status` is only changed through
`decide_pharmacy_verification`, which writes an immutable history row. Price
submissions create NEW versioned rows — history is never silently overwritten
(spec §17, §27). Nothing here fabricates pharmacies, stock, or prices.
"""

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.models.pharmacy import (
    Medicine,
    MedicinePrice,
    MedicinePriceHistory,
    Pharmacy,
    PharmacyInventory,
    PharmacyVerification,
)

# Pharmacies under these statuses cannot serve patient-visible prices/stock.
NON_PUBLIC_STATUSES = ("REJECTED", "SUSPENDED")


class PharmacyError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ------------------------------------------------------------- registration

def register_pharmacy(
    db: Session, payload, admin_user_id: str | None = None
) -> Pharmacy:
    pharmacy = Pharmacy(
        admin_user_id=admin_user_id,
        name=payload.name.strip(),
        registration_number=payload.registration_number,
        license_authority=payload.license_authority,
        address_line=payload.address_line,
        city=payload.city,
        state=payload.state,
        postal_code=payload.postal_code,
        latitude=payload.latitude,
        longitude=payload.longitude,
        phone=payload.phone,
        email=payload.email,
        operating_hours=payload.operating_hours,
        delivery_supported=payload.delivery_supported,
        pickup_supported=payload.pickup_supported,
        verification_status="PENDING",
    )
    db.add(pharmacy)
    db.flush()
    return pharmacy


def decide_pharmacy_verification(
    db: Session, pharmacy: Pharmacy, decision, admin_user_id: str
) -> Pharmacy:
    """Apply a verification decision with an immutable history row."""
    if pharmacy.verification_status == decision.new_status:
        raise PharmacyError(f"Pharmacy is already {decision.new_status}", 409)
    db.add(
        PharmacyVerification(
            pharmacy_id=pharmacy.id,
            previous_status=pharmacy.verification_status,
            new_status=decision.new_status,
            decided_by_user_id=admin_user_id,
            decision_note=decision.decision_note,
            document_refs=",".join(decision.document_refs),
        )
    )
    pharmacy.verification_status = decision.new_status
    db.flush()
    return pharmacy


def get_owned_pharmacy(db: Session, pharmacy_id: str, user) -> Pharmacy:
    """PHARMACY_ADMIN ownership check: the pharmacy row must belong to this user."""
    pharmacy = db.get(Pharmacy, pharmacy_id)
    if pharmacy is None:
        raise PharmacyError("Pharmacy not found", 404)
    if "SUPER_ADMIN" not in user.role_ids and pharmacy.admin_user_id != user.id:
        raise PharmacyError("You do not manage this pharmacy", 403)
    return pharmacy


# ---------------------------------------------------------------- inventory

def upsert_inventory(db: Session, pharmacy: Pharmacy, payload) -> PharmacyInventory:
    if db.get(Medicine, payload.medicine_id) is None:
        raise PharmacyError(f"Unknown medicine: {payload.medicine_id}", 404)
    row = (
        db.query(PharmacyInventory)
        .filter(
            PharmacyInventory.pharmacy_id == pharmacy.id,
            PharmacyInventory.medicine_id == payload.medicine_id,
        )
        .first()
    )
    if row is None:
        row = PharmacyInventory(pharmacy_id=pharmacy.id, medicine_id=payload.medicine_id)
        db.add(row)
    row.stock_status = payload.stock_status
    if payload.quantity is not None:
        row.quantity = payload.quantity
    row.minimum_order_quantity = payload.minimum_order_quantity
    row.last_updated = datetime.now(UTC)
    db.flush()
    return row


# ------------------------------------------------------------------- prices

def submit_price(db: Session, pharmacy: Pharmacy, payload) -> MedicinePrice:
    """Create a NEW price version (PENDING). The previous current row for the
    same pharmacy+medicine is retired (is_current=False) — never overwritten."""
    if db.get(Medicine, payload.medicine_id) is None:
        raise PharmacyError(f"Unknown medicine: {payload.medicine_id}", 404)

    previous = (
        db.query(MedicinePrice)
        .filter(
            MedicinePrice.pharmacy_id == pharmacy.id,
            MedicinePrice.medicine_id == payload.medicine_id,
            MedicinePrice.is_current.is_(True),
        )
        .first()
    )
    if previous is not None:
        previous.is_current = False

    price = MedicinePrice(
        medicine_id=payload.medicine_id,
        pharmacy_id=pharmacy.id,
        price=payload.price,
        currency=payload.currency,
        source="PHARMACY_SUBMITTED",
        source_reference=payload.source_reference,
        verification_status="PENDING",
        valid_from=date.today(),
        valid_until=payload.valid_until,
        is_current=True,
    )
    db.add(price)
    db.flush()
    db.add(
        MedicinePriceHistory(
            price_id=price.id,
            event_type="SUBMITTED",
            previous_status=previous.verification_status if previous else "",
            new_status="PENDING",
            new_price=price.price,
            actor_user_id=pharmacy.admin_user_id,
            note="Submitted via pharmacy self-service",
        )
    )
    db.flush()
    return price


def decide_price(db: Session, price: MedicinePrice, decision, admin_user_id: str) -> MedicinePrice:
    """Admin price verification (spec §27): PENDING → VERIFIED | REJECTED."""
    if price.verification_status not in ("PENDING", "UNVERIFIED"):
        raise PharmacyError(
            f"Price is already {price.verification_status}; only PENDING prices can be decided", 409
        )
    from datetime import datetime as dt

    price.verification_status = decision.decision
    if decision.decision == "VERIFIED":
        price.verified_by_user_id = admin_user_id
        price.verified_at = dt.now(UTC)
    db.add(
        MedicinePriceHistory(
            price_id=price.id,
            event_type=decision.decision,
            previous_status="PENDING",
            new_status=decision.decision,
            new_price=price.price,
            actor_user_id=admin_user_id,
            note=decision.note,
        )
    )
    db.flush()
    return price


def expire_stale_prices(db: Session) -> int:
    """VERIFIED → EXPIRED once valid_until has lapsed (spec §27). Expired data
    must never continue to be presented as current."""
    today = date.today()
    stale = (
        db.query(MedicinePrice)
        .filter(
            MedicinePrice.verification_status == "VERIFIED",
            MedicinePrice.valid_until.isnot(None),
            MedicinePrice.valid_until < today,
        )
        .all()
    )
    for price in stale:
        price.verification_status = "EXPIRED"
        db.add(
            MedicinePriceHistory(
                price_id=price.id,
                event_type="EXPIRED",
                previous_status="VERIFIED",
                new_status="EXPIRED",
                new_price=price.price,
                note="valid_until lapse",
            )
        )
    if stale:
        db.flush()
    return len(stale)


# ------------------------------------------------------------------ queries

def verified_pharmacies_query(db: Session):
    """Base query for pharmacies eligible for public verified display."""
    return db.query(Pharmacy).filter(
        Pharmacy.verification_status == "VERIFIED",
        Pharmacy.is_active.is_(True),
    )


def public_pharmacies_query(db: Session):
    """Pharmacies visible in search: verified + active, or not yet decided
    (PENDING/UNDER_REVIEW are visible only to admins, never as verified)."""
    return verified_pharmacies_query(db)
