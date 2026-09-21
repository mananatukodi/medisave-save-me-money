"""Phase 8 partner schemas. Validation is strict; client-supplied status fields
are never accepted (status changes go through lifecycle endpoints only)."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.partner import DOCUMENT_TYPES, ORGANIZATION_TYPES, PARTNER_ROLES


class OrganizationCreate(BaseModel):
    organization_type: str = Field(description="One of: " + ", ".join(ORGANIZATION_TYPES))
    legal_name: str = Field(min_length=2, max_length=255)
    display_name: str = Field(default="", max_length=255)
    registration_number: str = Field(default="", max_length=80)
    tax_identifier: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    address_line: str = Field(default="", max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)
    latitude: str | None = Field(default=None, max_length=24)
    longitude: str | None = Field(default=None, max_length=24)
    profile_metadata: dict = Field(default_factory=dict)


class OrganizationUpdate(BaseModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    registration_number: str | None = Field(default=None, max_length=80)
    tax_identifier: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)
    latitude: str | None = Field(default=None, max_length=24)
    longitude: str | None = Field(default=None, max_length=24)


class MemberOut(BaseModel):
    id: str
    organization_id: str
    user_id: str
    partner_role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemberCreate(BaseModel):
    user_id: str = Field(min_length=6, max_length=36)
    partner_role: str = Field(description="One of: " + ", ".join(PARTNER_ROLES))


class MemberUpdate(BaseModel):
    partner_role: str


class DocumentOut(BaseModel):
    id: str
    organization_id: str
    document_type: str
    verification_status: str
    issued_at: date | None
    expires_at: date | None
    checksum: str
    review_note: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentCreate(BaseModel):
    document_type: str = Field(description="One of: " + ", ".join(DOCUMENT_TYPES))
    file_id: str | None = Field(default=None, max_length=36)
    storage_reference: str = Field(default="", max_length=255)
    checksum: str = Field(default="", max_length=64)
    issued_at: date | None = None
    expires_at: date | None = None


class DocumentDecision(BaseModel):
    decision: str = Field(description="UNDER_REVIEW | VERIFIED | REJECTED | EXPIRED")
    note: str = Field(default="", max_length=1000)


class ServiceOut(BaseModel):
    id: str
    organization_id: str
    service_type: str
    name: str
    description: str
    status: str
    price: float | None
    currency: str
    price_verification_status: str
    price_source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceCreate(BaseModel):
    service_type: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)
    price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", max_length=8)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)


class OrganizationOut(BaseModel):
    id: str
    organization_type: str
    legal_name: str
    display_name: str
    registration_number: str
    city: str | None
    state: str | None
    status: str
    verification_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationAdminOut(OrganizationOut):
    email: str | None
    phone: str | None
    tax_identifier: str | None


class LifecycleEventOut(BaseModel):
    id: str
    previous_status: str
    new_status: str
    actor_user_id: str | None
    note: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------- lab


class LabTestOut(BaseModel):
    id: str
    organization_id: str
    code: str
    name: str
    description: str
    category: str
    sample_type: str
    preparation_notes: str
    price: float | None
    currency: str
    verification_status: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class LabTestCreate(BaseModel):
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    category: str = Field(default="", max_length=80)
    sample_type: str = Field(default="", max_length=80)
    preparation_notes: str = Field(default="", max_length=1000)
    price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", max_length=8)


class LabBookingOut(BaseModel):
    id: str
    organization_id: str
    test_id: str
    patient_user_id: str
    status: str
    collection_mode: str
    scheduled_for: datetime | None
    report_reference: str
    health_record_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LabBookingCreate(BaseModel):
    test_id: str = Field(max_length=36)
    patient_user_id: str = Field(min_length=6, max_length=36)
    collection_mode: str = Field(default="CENTER_VISIT", pattern="^(CENTER_VISIT|HOME_COLLECTION)$")
    scheduled_for: datetime | None = None
    notes: str = Field(default="", max_length=500)


class LabBookingStatus(BaseModel):
    status: str


# -------------------------------------------------------------- insurance


class InsuranceProductOut(BaseModel):
    id: str
    organization_id: str
    product_name: str
    product_type: str
    description: str
    status: str
    claim_intake_supported: bool

    model_config = ConfigDict(from_attributes=True)


class InsuranceProductCreate(BaseModel):
    product_name: str = Field(min_length=2, max_length=200)
    product_type: str = Field(default="", max_length=60)
    description: str = Field(default="", max_length=4000)
    claim_intake_supported: bool = False


class ClaimOut(BaseModel):
    id: str
    organization_id: str
    patient_user_id: str
    claim_number: str
    subject_type: str
    subject_id: str | None
    status: str
    description: str
    amount: float | None
    approved_amount: float | None
    currency: str
    submitted_at: datetime | None
    decided_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClaimCreate(BaseModel):
    patient_user_id: str | None = Field(default=None, max_length=36)
    claim_number: str = Field(default="", max_length=60)
    subject_type: str = Field(default="OTHER", pattern="^(APPOINTMENT|ORDER|LAB_BOOKING|OTHER)$")
    subject_id: str | None = Field(default=None, max_length=36)
    description: str = Field(default="", max_length=2000)
    amount: float | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", max_length=8)


class ClaimTransition(BaseModel):
    status: str
    note: str = Field(default="", max_length=1000)
    approved_amount: float | None = Field(default=None, ge=0)


class ClaimEventOut(BaseModel):
    id: str
    previous_status: str
    new_status: str
    actor_user_id: str | None
    note: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------ integrations


class IntegrationOut(BaseModel):
    id: str
    organization_id: str
    integration_kind: str
    name: str
    endpoint_url: str | None
    key_prefix: str
    scopes: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreate(BaseModel):
    name: str = Field(default="api-key", max_length=120)
    scopes: str = Field(default="read", max_length=300)


class ApiKeyCreated(IntegrationOut):
    raw_key: str = Field(default="", description="Shown exactly once; never stored or logged")


class WebhookCreate(BaseModel):
    name: str = Field(default="webhook", max_length=120)
    endpoint_url: str = Field(min_length=8, max_length=500)


class NotificationOut(BaseModel):
    id: str
    organization_id: str
    channel: str
    status: str
    event_type: str
    title: str
    body: str
    resource_type: str
    resource_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PartnerDashboardOrg(BaseModel):
    organization_id: str
    organization_type: str
    display_name: str
    status: str
    verification_status: str
    my_role: str
    services: int
    documents_pending: int
    claims_open: int
    lab_tests: int
    lab_bookings_open: int


class PartnerDashboard(BaseModel):
    organizations: list[PartnerDashboardOrg]
