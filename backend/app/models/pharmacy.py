"""Pharmacy, medicine, pricing, and order models (Phase 4).

REAL DATA RULE (spec §28, §37): these models exist to receive data through the
registration + verification workflow and pharmacy self-service. Nothing in this
module seeds fabricated medicines, pharmacies, prices, or availability. A
pharmacy is only shown as VERIFIED when a verification-history row with a real
decision exists. A price is only shown as VERIFIED when a price-verification
row exists and the record has not expired. Savings are only claimed from real,
compatible, verified price records (app/services/savings_service.py).
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.user import new_uuid, utcnow

VERIFICATION_STATES = ("PENDING", "UNDER_REVIEW", "VERIFIED", "REJECTED", "SUSPENDED")
DOSAGE_FORMS = (
    "TABLET", "CAPSULE", "SYRUP", "INJECTION", "CREAM", "OINTMENT",
    "DROPS", "INHALER", "POWDER", "SOLUTION", "OTHER",
)
STOCK_STATUSES = ("IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK", "UNKNOWN")
PRICE_VERIFICATION_STATUSES = ("UNVERIFIED", "PENDING", "VERIFIED", "EXPIRED", "REJECTED")
ORDER_STATUSES = (
    "CREATED",
    "PRESCRIPTION_REQUIRED",
    "PRESCRIPTION_SUBMITTED",
    "UNDER_REVIEW",
    "CONFIRMED",
    "PROCESSING",
    "READY_FOR_PICKUP",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "CANCELLED",
    "FAILED",
)
# Allowed forward transitions of the order state machine (spec §18). Anything
# not listed is an invalid transition and is rejected server-side.
ORDER_TRANSITIONS: dict[str, tuple[str, ...]] = {
    # Prescription flow: CREATED -> PRESCRIPTION_REQUIRED -> SUBMITTED
    # -> UNDER_REVIEW -> CONFIRMED (human review required, spec §14).
    "CREATED": ("PRESCRIPTION_REQUIRED", "CONFIRMED", "CANCELLED", "FAILED"),
    "PRESCRIPTION_REQUIRED": ("PRESCRIPTION_SUBMITTED", "CANCELLED"),
    "PRESCRIPTION_SUBMITTED": ("UNDER_REVIEW", "CANCELLED"),
    "UNDER_REVIEW": ("CONFIRMED", "CANCELLED"),
    "CONFIRMED": ("PROCESSING", "CANCELLED", "FAILED"),
    "PROCESSING": ("READY_FOR_PICKUP", "OUT_FOR_DELIVERY", "CANCELLED", "FAILED"),
    "READY_FOR_PICKUP": ("DELIVERED", "CANCELLED"),
    "OUT_FOR_DELIVERY": ("DELIVERED", "FAILED"),
    "DELIVERED": (),
    "CANCELLED": (),
    "FAILED": (),
}


class Medicine(Base):
    """Canonical medicine entity (spec §2). Created via admin workflow only —
    no fabricated starter data; the table stays empty until real records arrive."""

    __tablename__ = "medicines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), index=True)
    generic_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    brand_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    manufacturer: Mapped[str] = mapped_column(String(255), default="", index=True)
    strength: Mapped[str] = mapped_column(String(80), default="")  # e.g. "500 mg"
    dosage_form: Mapped[str] = mapped_column(String(20), default="TABLET")
    pack_size: Mapped[str] = mapped_column(String(80), default="")  # e.g. "10 tablets"
    prescription_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    active_ingredients: Mapped[str] = mapped_column(Text, default="")  # CSV; from source data only
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)  # ACTIVE | DISCONTINUED
    # Data provenance for the medicine record itself (spec §2 "do not invent")
    data_source: Mapped[str] = mapped_column(String(120), default="MANUAL_ENTRY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    aliases: Mapped[list["MedicineAlias"]] = relationship(
        back_populates="medicine", cascade="all, delete-orphan"
    )
    prices: Mapped[list["MedicinePrice"]] = relationship(
        back_populates="medicine", cascade="all, delete-orphan"
    )
    inventory: Mapped[list["PharmacyInventory"]] = relationship(
        back_populates="medicine", cascade="all, delete-orphan"
    )

    @property
    def representation_key(self) -> str:
        """Compatible-representation identity used by comparison/savings (spec §10):
        strength + dosage form + pack size. Prices are only compared across
        records sharing this key."""
        return f"{self.strength}|{self.dosage_form}|{self.pack_size}".strip().lower()


class MedicineAlias(Base):
    """Alternate names for search (brand spellings, regional names)."""

    __tablename__ = "medicine_aliases"
    __table_args__ = (
        Index("ix_aliases_alias", "alias"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    medicine_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicines.id"), index=True)
    alias: Mapped[str] = mapped_column(String(255))
    alias_kind: Mapped[str] = mapped_column(String(40), default="OTHER")  # BRAND | REGIONAL | OTHER

    medicine: Mapped[Medicine] = relationship(back_populates="aliases")


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    admin_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    registration_number: Mapped[str] = mapped_column(String(80), default="")
    license_authority: Mapped[str] = mapped_column(String(120), default="")
    address_line: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    latitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    longitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operating_hours: Mapped[str] = mapped_column(Text, default="")  # free text / JSON from pharmacy
    delivery_supported: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    pickup_supported: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Aggregate verification status (mirrors latest verification row)
    verification_status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    verifications: Mapped[list["PharmacyVerification"]] = relationship(
        back_populates="pharmacy", cascade="all, delete-orphan"
    )
    inventory: Mapped[list["PharmacyInventory"]] = relationship(
        back_populates="pharmacy", cascade="all, delete-orphan"
    )
    prices: Mapped[list["MedicinePrice"]] = relationship(
        back_populates="pharmacy", cascade="all, delete-orphan"
    )


class PharmacyVerification(Base):
    """Immutable verification history (spec §6, §33)."""

    __tablename__ = "pharmacy_verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    pharmacy_id: Mapped[str] = mapped_column(String(36), ForeignKey("pharmacies.id"), index=True)
    previous_status: Mapped[str] = mapped_column(String(20), default="")
    new_status: Mapped[str] = mapped_column(String(20))
    decided_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    document_refs: Mapped[str] = mapped_column(Text, default="")  # references, not document blobs
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    pharmacy: Mapped[Pharmacy] = relationship(back_populates="verifications")


class PharmacyInventory(Base):
    """Per-pharmacy stock for a medicine (spec §7). UNKNOWN is never rendered
    as IN_STOCK by the API layer; honesty is enforced in schemas/services."""

    __tablename__ = "pharmacy_inventory"
    __table_args__ = (
        UniqueConstraint("pharmacy_id", "medicine_id", name="uq_inventory_pharmacy_medicine"),
        Index("ix_inventory_medicine_stock", "medicine_id", "stock_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    pharmacy_id: Mapped[str] = mapped_column(String(36), ForeignKey("pharmacies.id"), index=True)
    medicine_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicines.id"), index=True)
    stock_status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = not tracked
    minimum_order_quantity: Mapped[int] = mapped_column(Integer, default=1)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    pharmacy: Mapped[Pharmacy] = relationship(back_populates="inventory")
    medicine: Mapped[Medicine] = relationship(back_populates="inventory")


class MedicinePrice(Base):
    """Price record with full provenance (spec §8, §9). New submissions create
    NEW rows (versioning); historical rows are never silently overwritten."""

    __tablename__ = "medicine_prices"
    __table_args__ = (
        Index("ix_prices_medicine_status", "medicine_id", "verification_status"),
        Index("ix_prices_pharmacy", "pharmacy_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    medicine_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicines.id"), index=True)
    pharmacy_id: Mapped[str] = mapped_column(String(36), ForeignKey("pharmacies.id"), index=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    source: Mapped[str] = mapped_column(String(120), default="PHARMACY_SUBMITTED")
    source_reference: Mapped[str] = mapped_column(String(255), default="")
    verification_status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    medicine: Mapped[Medicine] = relationship(back_populates="prices")
    pharmacy: Mapped[Pharmacy] = relationship(back_populates="prices")
    history: Mapped[list["MedicinePriceHistory"]] = relationship(
        back_populates="price_record", cascade="all, delete-orphan"
    )

    @property
    def is_effectively_verified(self) -> bool:
        """True only when verification exists AND the validity window is current."""
        if self.verification_status != "VERIFIED":
            return False
        if self.valid_until is not None:
            return self.valid_until >= date.today()
        return True


class MedicinePriceHistory(Base):
    """Append-only audit trail of every price change/decision (spec §17, §33)."""

    __tablename__ = "medicine_price_history"
    __table_args__ = (
        Index("ix_price_history_price", "price_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    price_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicine_prices.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))  # SUBMITTED | VERIFIED | REJECTED | EXPIRED | UPDATED
    previous_status: Mapped[str] = mapped_column(String(20), default="")
    new_status: Mapped[str] = mapped_column(String(20), default="")
    new_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    price_record: Mapped[MedicinePrice] = relationship(back_populates="history")


class MedicineOrder(Base):
    __tablename__ = "medicine_orders"
    __table_args__ = (
        Index("ix_orders_patient_status", "patient_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    pharmacy_id: Mapped[str] = mapped_column(String(36), ForeignKey("pharmacies.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="CREATED", index=True)
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    delivery_fee: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    delivery_address: Mapped[str] = mapped_column(Text, default="")
    pickup_option: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    items: Mapped[list["MedicineOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class MedicineOrderItem(Base):
    """Order line with an immutable price snapshot (spec §19): historical order
    prices never change when pharmacy catalog prices change."""

    __tablename__ = "medicine_order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicine_orders.id"), index=True)
    medicine_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicines.id"), index=True)
    medicine_name: Mapped[str] = mapped_column(String(255), default="")  # snapshot
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2))
    price_source: Mapped[str] = mapped_column(String(120), default="")
    price_snapshot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("medicine_prices.id"), nullable=True
    )
    snapshot_verification_status: Mapped[str] = mapped_column(String(20), default="")

    order: Mapped[MedicineOrder] = relationship(back_populates="items")


class PrescriptionRequest(Base):
    """Prescription workflow placeholder (spec §14). The document upload and
    pharmacist verification pipeline REQUIRES INTEGRATION; this table records
    the request state honestly without fabricating approval."""

    __tablename__ = "prescription_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicine_orders.id"), index=True)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    # PENDING | SUBMITTED | VERIFIED | REJECTED
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    document_ref: Mapped[str] = mapped_column(String(255), default="")
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
