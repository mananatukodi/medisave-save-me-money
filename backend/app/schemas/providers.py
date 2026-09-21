"""Provider, service, availability, and appointment schemas (Phase 3)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.providers import CONSULTATION_TYPES, VERIFICATION_STATES

WEEKDAY_HELP = "0=Monday .. 6=Sunday"


class DoctorRegistration(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    gender: str | None = Field(default=None, max_length=20)
    specialty_slug: str = Field(max_length=60)
    sub_specialty: str | None = Field(default=None, max_length=160)
    qualifications: str = Field(default="", max_length=300)
    registration_number: str = Field(default="", max_length=80)
    registration_council: str = Field(default="", max_length=120)
    years_experience: int = Field(default=0, ge=0, le=70)
    languages: str = Field(default="te,en", max_length=200)
    consultation_modes: str = Field(default="IN_PERSON", max_length=60)
    about: str = Field(default="", max_length=2000)
    phone_number: str | None = Field(default=None, max_length=20)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)
    hospital_id: str | None = None
    document_refs: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("consultation_modes")
    @classmethod
    def _validate_modes(cls, value: str) -> str:
        if not value:
            return "IN_PERSON"
        modes = [m.strip().upper() for m in value.split(",") if m.strip()]
        invalid = [m for m in modes if m not in CONSULTATION_TYPES]
        if invalid:
            raise ValueError(f"consultation modes must be from {CONSULTATION_TYPES}, got {invalid}")
        return ",".join(modes)


class DoctorPublic(BaseModel):
    """Public projection — no registration numbers, no admin notes (spec §11)."""

    id: str
    full_name: str
    gender: str | None
    photo_url: str | None
    specialty_slug: str
    sub_specialty: str | None
    qualifications: str
    years_experience: int
    languages: str
    consultation_modes: str
    about: str
    city: str | None
    hospital_id: str | None
    verification_status: str

    model_config = ConfigDict(from_attributes=True)


class DoctorVerificationDecision(BaseModel):
    new_status: str = Field(description=f"One of: {', '.join(VERIFICATION_STATES)}")
    decision_note: str = Field(default="", max_length=1000)
    document_refs: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("new_status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in VERIFICATION_STATES:
            raise ValueError(f"new_status must be one of {VERIFICATION_STATES}")
        return value


class HospitalVerificationDecision(BaseModel):
    new_status: str = Field(description=f"One of: {', '.join(VERIFICATION_STATES)}")
    decision_note: str = Field(default="", max_length=1000)
    document_refs: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("new_status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in VERIFICATION_STATES:
            raise ValueError(f"new_status must be one of {VERIFICATION_STATES}")
        return value


class HospitalRegistration(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    hospital_type: str = Field(default="HOSPITAL", max_length=40)
    registration_number: str = Field(default="", max_length=80)
    address_line: str = Field(default="", max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)
    phone_number: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    departments: str = Field(default="", max_length=2000)  # CSV of specialty slugs
    services_summary: str = Field(default="", max_length=2000)
    emergency_available: bool = False
    insurance_info: str = Field(default="", max_length=2000)
    document_refs: list[str] = Field(default_factory=list, max_length=20)


class HospitalPublic(BaseModel):
    id: str
    name: str
    hospital_type: str
    address_line: str
    city: str | None
    state: str | None
    pincode: str | None
    phone_number: str | None
    departments: str
    services_summary: str
    emergency_available: bool
    emergency_verified: bool
    insurance_info: str
    verification_status: str

    model_config = ConfigDict(from_attributes=True)


class ServiceCreate(BaseModel):
    specialty_slug: str = Field(max_length=60)
    name_en: str = Field(min_length=2, max_length=160)
    name_te: str = Field(default="", max_length=160)
    name_hi: str = Field(default="", max_length=160)
    description_en: str = Field(default="", max_length=2000)
    duration_minutes: int = Field(default=30, ge=5, le=240)
    consultation_type: str = Field(default="IN_PERSON")
    price_amount: float | None = Field(default=None, ge=0)
    price_currency: str = Field(default="INR", max_length=8)

    @field_validator("consultation_type")
    @classmethod
    def _validate_consultation(cls, value: str) -> str:
        if value not in CONSULTATION_TYPES:
            raise ValueError(f"consultation_type must be one of {CONSULTATION_TYPES}")
        return value


class PriceDeclare(BaseModel):
    amount: float = Field(ge=0)
    currency: str = Field(default="INR", max_length=8)


class ServicePriceOut(BaseModel):
    amount: float
    currency: str
    verification_status: str
    source: str
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceOut(BaseModel):
    id: str
    provider_kind: str
    provider_id: str
    specialty_slug: str
    name_en: str
    name_te: str
    name_hi: str
    description_en: str
    duration_minutes: int
    consultation_type: str
    is_active: bool
    prices: list[ServicePriceOut] = []

    model_config = ConfigDict(from_attributes=True)


class DoctorDetail(DoctorPublic):
    """Public detail view: profile + bookable services + verified specialty links."""

    specialty_slugs: list[str] = []
    services: list[ServiceOut] = []


class VerificationHistoryOut(BaseModel):
    previous_status: str
    new_status: str
    decided_by_user_id: str | None
    decision_note: str
    document_refs: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AvailabilityRule(BaseModel):
    weekday: int = Field(ge=0, le=6, description=WEEKDAY_HELP)
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    slot_minutes: int = Field(default=30, ge=5, le=120)


class AvailabilityRuleOut(AvailabilityRule):
    id: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class BlockCreate(BaseModel):
    block_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    reason: str = Field(default="", max_length=200)


class BlockOut(BlockCreate):
    id: str

    model_config = ConfigDict(from_attributes=True)


class SlotOut(BaseModel):
    time: str
    available: bool
    reason: str | None = None


class DayAvailabilityOut(BaseModel):
    date: str
    weekday: int
    slots: list[SlotOut]


class AppointmentCreate(BaseModel):
    doctor_id: str
    service_id: str
    appointment_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    appointment_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    notes: str = Field(default="", max_length=1000)
    # Phase 6: family/caregiver booking on behalf of the patient. Requires an
    # ACTIVE family relationship + REQUEST_APPOINTMENT consent, verified
    # server-side; the patient remains the appointment owner.
    on_behalf_of_patient_id: str | None = Field(default=None, max_length=36)


class AppointmentOut(BaseModel):
    id: str
    patient_user_id: str
    doctor_id: str
    specialty_slug: str
    service_id: str
    appointment_date: str
    appointment_time: str
    consultation_type: str
    location: str
    price_amount: float | None
    price_currency: str
    price_verified: bool
    status: str
    notes: str
    created_at: datetime
    updated_at: datetime
    # Phase 6: set when a family member requested the appointment on behalf
    # of the patient (actor ≠ patient). None for self-booked appointments.
    requested_by_user_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RescheduleRequest(BaseModel):
    appointment_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    appointment_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(CONFIRMED|COMPLETED|NO_SHOW|CANCELLED)$")
    note: str = Field(default="", max_length=500)
