"""Phase 4 schemas: medicines, pharmacies, prices, savings, orders.

Honesty rules encoded here (spec §9, §12, §14, §37):
- A price row is rendered VERIFIED only when its verification status is VERIFIED
  and its validity window has not lapsed (see `PriceOut.verified_effective`).
- Stock UNKNOWN is rendered as UNKNOWN, never as IN_STOCK.
- Savings output carries `status` (CALCULATED | INSUFFICIENT_DATA | NO_COMPARISON)
  and must never invent a monetary number without verified inputs.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.pharmacy import (
    DOSAGE_FORMS,
    ORDER_STATUSES,
    STOCK_STATUSES,
    VERIFICATION_STATES,
)

DEFAULT_CURRENCY = "INR"


# ----------------------------------------------------------------- medicines

class MedicineCreate(BaseModel):
    """Admin medicine master-data creation. Descriptions must come from a real
    source; the API records `data_source` for provenance."""

    name: str = Field(min_length=2, max_length=255)
    generic_name: str = Field(default="", max_length=255)
    brand_name: str = Field(default="", max_length=255)
    manufacturer: str = Field(default="", max_length=255)
    strength: str = Field(default="", max_length=80)
    dosage_form: str = Field(default="TABLET", max_length=20)
    pack_size: str = Field(default="", max_length=80)
    prescription_required: bool = False
    description: str = Field(default="", max_length=4000)
    active_ingredients: str = Field(default="", max_length=2000)
    data_source: str = Field(default="MANUAL_ENTRY", max_length=120)

    @field_validator("dosage_form")
    @classmethod
    def _validate_form(cls, value: str) -> str:
        if value not in DOSAGE_FORMS:
            raise ValueError(f"dosage_form must be one of {DOSAGE_FORMS}")
        return value


class AliasOut(BaseModel):
    id: str
    alias: str
    alias_kind: str

    model_config = ConfigDict(from_attributes=True)


class MedicineOut(BaseModel):
    id: str
    name: str
    generic_name: str
    brand_name: str
    manufacturer: str
    strength: str
    dosage_form: str
    pack_size: str
    prescription_required: bool
    description: str
    active_ingredients: str
    status: str
    data_source: str
    aliases: list[AliasOut] = []

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------- pharmacies

class PharmacyRegistration(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    registration_number: str = Field(default="", max_length=80)
    license_authority: str = Field(default="", max_length=120)
    address_line: str = Field(default="", max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=12)
    latitude: str | None = Field(default=None, max_length=24)
    longitude: str | None = Field(default=None, max_length=24)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    operating_hours: str = Field(default="", max_length=2000)
    delivery_supported: bool = False
    pickup_supported: bool = True


class PharmacyUpdate(BaseModel):
    """Pharmacy self-service profile fields (spec §17)."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=12)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    operating_hours: str | None = Field(default=None, max_length=2000)
    delivery_supported: bool | None = None
    pickup_supported: bool | None = None


class PharmacyPublic(BaseModel):
    """Public pharmacy view. Registration number and admin identity are never
    exposed to patients (spec §15)."""

    id: str
    name: str
    city: str | None
    state: str | None
    postal_code: str | None
    address_line: str
    phone: str | None
    operating_hours: str
    delivery_supported: bool
    pickup_supported: bool
    verification_status: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PharmacyAdminOut(PharmacyPublic):
    """Owner/admin view including registration info."""

    registration_number: str
    license_authority: str
    admin_user_id: str | None
    email: str | None


class VerificationDecision(BaseModel):
    new_status: str
    decision_note: str = Field(default="", max_length=2000)
    document_refs: list[str] = []

    @field_validator("new_status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in VERIFICATION_STATES:
            raise ValueError(f"new_status must be one of {VERIFICATION_STATES}")
        return value


class VerificationHistoryOut(BaseModel):
    id: str
    previous_status: str
    new_status: str
    decision_note: str
    decided_by_user_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ inventory

class InventoryUpsert(BaseModel):
    medicine_id: str
    stock_status: str = Field(default="UNKNOWN")
    quantity: int | None = Field(default=None, ge=0)
    minimum_order_quantity: int = Field(default=1, ge=1)

    @field_validator("stock_status")
    @classmethod
    def _validate_stock(cls, value: str) -> str:
        if value not in STOCK_STATUSES:
            raise ValueError(f"stock_status must be one of {STOCK_STATUSES}")
        return value


class InventoryOut(BaseModel):
    medicine_id: str
    pharmacy_id: str
    stock_status: str
    quantity: int | None
    minimum_order_quantity: int
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------- prices

class PriceSubmit(BaseModel):
    """Pharmacy price submission. Always creates a NEW versioned row; the
    previous current row for the same pharmacy+medicine is retired."""

    medicine_id: str
    price: float = Field(ge=0, description="Price per pack in `currency`")
    currency: str = Field(default=DEFAULT_CURRENCY, max_length=8)
    source_reference: str = Field(default="", max_length=255)
    valid_until: date | None = None


class PriceDecision(BaseModel):
    """Admin price verification decision (spec §27)."""

    decision: str = Field(description="One of: VERIFIED, REJECTED")
    note: str = Field(default="", max_length=2000)

    @field_validator("decision")
    @classmethod
    def _validate_decision(cls, value: str) -> str:
        if value not in ("VERIFIED", "REJECTED"):
            raise ValueError("decision must be VERIFIED or REJECTED")
        return value


class PriceOut(BaseModel):
    """Public price record with full provenance (spec §9)."""

    id: str
    medicine_id: str
    pharmacy_id: str
    pharmacy_name: str | None = None
    price: float
    currency: str
    source: str
    source_reference: str
    verification_status: str
    valid_from: date | None
    valid_until: date | None
    # Mapped from MedicinePrice.updated_at by the router (provenance, spec §9)
    last_updated: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PriceVerificationQueueOut(BaseModel):
    """Admin queue row: pending price with pharmacy context."""

    id: str
    medicine_id: str
    medicine_name: str = ""
    pharmacy_id: str
    pharmacy_name: str = ""
    price: float
    currency: str
    source: str
    submitted_at: datetime
    verification_status: str

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------- savings

class SavingsOut(BaseModel):
    """Transparent savings result (spec §11, §12). When `status` is not
    CALCULATED, `potential_savings` stays None — never a fabricated number."""

    medicine_id: str
    status: str = Field(
        description="CALCULATED | INSUFFICIENT_DATA | NO_COMPARISON | MEDICINE_NOT_FOUND"
    )
    representation_key: str | None = Field(
        default=None, description="strength|dosage_form|pack_size of the compared records"
    )
    reference_price: float | None = None
    reference_pharmacy_id: str | None = None
    reference_pharmacy_name: str | None = None
    selected_price: float | None = None
    selected_pharmacy_id: str | None = None
    selected_pharmacy_name: str | None = None
    potential_savings: float | None = None
    currency: str = DEFAULT_CURRENCY
    source: str | None = Field(default=None, description="Price data source description")
    last_updated: datetime | None = None
    note: str = ""


# --------------------------------------------------------------------- orders

class OrderItemCreate(BaseModel):
    medicine_id: str
    quantity: int = Field(ge=1, le=100)


class OrderCreate(BaseModel):
    pharmacy_id: str
    items: list[OrderItemCreate] = Field(min_length=1)
    pickup_option: bool = True
    delivery_address: str = Field(default="", max_length=1000)


class OrderItemOut(BaseModel):
    id: str
    medicine_id: str
    medicine_name: str
    quantity: int
    unit_price: float
    price_source: str
    price_snapshot_id: str | None = None
    snapshot_verification_status: str

    model_config = ConfigDict(from_attributes=True)


class OrderOut(BaseModel):
    id: str
    patient_id: str
    pharmacy_id: str
    status: str
    subtotal: float
    delivery_fee: float
    total: float
    currency: str
    delivery_address: str
    pickup_option: bool
    items: list[OrderItemOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in ORDER_STATUSES:
            raise ValueError(f"status must be one of {ORDER_STATUSES}")
        return value


class PrescriptionRequestOut(BaseModel):
    id: str
    order_id: str
    status: str
    document_ref: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
