"""Partner ecosystem models (Phase 8).

REAL DATA RULE (inherited from Phases 1–7): these models exist to receive data
through the partner onboarding + verification workflow. Nothing in this module
seeds fabricated organizations, services, prices, claims, settlements, or
emergency providers. Verification information is always explicitly sourced
(human SUPER_ADMIN decision, recorded with an immutable history row).

ISOLATION RULE: every partner-facing row carries organization_id and every
partner query is scoped through an ACTIVE OrganizationMember row — never
through generic roles alone.

CREDENTIAL RULE: API keys are stored ONLY as SHA-256 hashes plus a short
lookup prefix. Raw keys are returned exactly once at creation (same pattern
as Phase 6 invitation tokens).

HONESTY RULES (carried forward):
- Settlement amounts are nullable until a real finance action records them;
  nothing computes or fabricates money.
- Claims never auto-approve; every state change is an explicit, audited
  transition.
- Notification external channels without a configured provider are recorded
  FAILED with error_detail="provider_not_configured" (Phase 7 semantics).
- Provider-declared prices are never rendered as verified without a real
  verification decision.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.user import new_uuid, utcnow

# --------------------------------------------------------------------- enums

ORGANIZATION_TYPES = (
    "DOCTOR",
    "HOSPITAL",
    "PHARMACY",
    "DIAGNOSTIC_LAB",
    "INSURANCE",
    "AMBULANCE",
)

# Partner lifecycle (spec Phase 8). Transitions are service-enforced.
ORGANIZATION_STATUSES = (
    "DRAFT",
    "SUBMITTED",
    "UNDER_REVIEW",
    "VERIFICATION_REQUIRED",
    "APPROVED",
    "SUSPENDED",
    "REJECTED",
    "DEACTIVATED",
)

ORG_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "DRAFT": ("SUBMITTED", "DEACTIVATED"),
    "SUBMITTED": ("UNDER_REVIEW", "REJECTED", "DEACTIVATED"),
    "UNDER_REVIEW": ("APPROVED", "VERIFICATION_REQUIRED", "REJECTED", "DEACTIVATED"),
    "VERIFICATION_REQUIRED": ("UNDER_REVIEW", "DEACTIVATED"),
    "APPROVED": ("SUSPENDED", "DEACTIVATED"),
    "SUSPENDED": ("APPROVED", "DEACTIVATED"),
    "REJECTED": ("UNDER_REVIEW", "DEACTIVATED"),
    "DEACTIVATED": (),
}

# Statuses allowed to operate on patient-facing transactions.
OPERABLE_STATUSES = ("APPROVED",)

PARTNER_ROLES = (
    "PARTNER_OWNER",
    "PARTNER_ADMIN",
    "PARTNER_MANAGER",
    "PARTNER_STAFF",
    "PARTNER_BILLING",
    "PARTNER_SUPPORT",
)

MEMBER_ROLES_ALLOWED: dict[str, tuple[str, ...]] = {
    # Who may grant which partner roles (owner/admin only, owner role immutable).
    "PARTNER_OWNER": (
        "PARTNER_ADMIN", "PARTNER_MANAGER", "PARTNER_STAFF", "PARTNER_BILLING", "PARTNER_SUPPORT",
    ),
    "PARTNER_ADMIN": ("PARTNER_MANAGER", "PARTNER_STAFF", "PARTNER_BILLING", "PARTNER_SUPPORT"),
}

DOCUMENT_TYPES = (
    "BUSINESS_REGISTRATION",
    "PROFESSIONAL_LICENSE",
    "PHARMACY_LICENSE",
    "LAB_LICENSE",
    "INSURANCE_LICENSE",
    "HOSPITAL_REGISTRATION",
    "TAX_DOCUMENT",
    "IDENTITY_DOCUMENT",
    "ADDRESS_PROOF",
    "OTHER",
)

DOCUMENT_STATUSES = ("UPLOADED", "UNDER_REVIEW", "VERIFIED", "REJECTED", "EXPIRED")

SERVICE_STATUSES = ("ACTIVE", "INACTIVE")
PRICE_VERIFICATION_STATUSES = ("UNVERIFIED", "PENDING", "VERIFIED", "REJECTED")

CLAIM_STATUSES = (
    "DRAFT",
    "SUBMITTED",
    "UNDER_REVIEW",
    "ADDITIONAL_INFORMATION_REQUIRED",
    "APPROVED",
    "PARTIALLY_APPROVED",
    "REJECTED",
    "SETTLED",
    "CANCELLED",
)

CLAIM_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "DRAFT": ("SUBMITTED", "CANCELLED"),
    "SUBMITTED": (
        "UNDER_REVIEW", "ADDITIONAL_INFORMATION_REQUIRED",
        "APPROVED", "PARTIALLY_APPROVED", "REJECTED", "CANCELLED",
    ),
    "UNDER_REVIEW": (
        "ADDITIONAL_INFORMATION_REQUIRED",
        "APPROVED",
        "PARTIALLY_APPROVED",
        "REJECTED",
        "CANCELLED",
    ),
    "ADDITIONAL_INFORMATION_REQUIRED": ("UNDER_REVIEW", "CANCELLED"),
    "APPROVED": ("SETTLED", "CANCELLED"),
    "PARTIALLY_APPROVED": ("SETTLED", "CANCELLED"),
    "REJECTED": ("CANCELLED",),
    "SETTLED": (),
    "CANCELLED": (),
}

CLAIM_SUBJECT_TYPES = ("APPOINTMENT", "ORDER", "LAB_BOOKING", "OTHER")

LAB_TEST_STATUSES = ("ACTIVE", "INACTIVE")
LAB_BOOKING_STATUSES = (
    "REQUESTED",
    "CONFIRMED",
    "SAMPLE_COLLECTED",
    "IN_PROGRESS",
    "REPORT_READY",
    "COMPLETED",
    "CANCELLED",
)
LAB_BOOKING_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "REQUESTED": ("CONFIRMED", "CANCELLED"),
    "CONFIRMED": ("SAMPLE_COLLECTED", "CANCELLED"),
    "SAMPLE_COLLECTED": ("IN_PROGRESS", "CANCELLED"),
    "IN_PROGRESS": ("REPORT_READY", "CANCELLED"),
    "REPORT_READY": ("COMPLETED",),
    "COMPLETED": (),
    "CANCELLED": (),
}
HOME_COLLECTION_MODES = ("CENTER_VISIT", "HOME_COLLECTION", "BOTH")

INTEGRATION_KINDS = ("API_KEY", "WEBHOOK_ENDPOINT")
INTEGRATION_STATUSES = ("ACTIVE", "REVOKED")
WEBHOOK_EVENT_TYPES = (
    "APPOINTMENT_CREATED",
    "APPOINTMENT_UPDATED",
    "ORDER_CREATED",
    "ORDER_UPDATED",
    "CLAIM_UPDATED",
    "LAB_REPORT_READY",
    "EMERGENCY_HANDOFF_UPDATED",
    "PAYMENT_UPDATED",
    "PARTNER_STATUS_CHANGED",
)
DELIVERY_STATUSES = ("PENDING", "DELIVERED", "FAILED")

SETTLEMENT_STATUSES = ("RECORDED", "PENDING_CONFIRMATION", "DISPUTED", "REVERSED")
COMMISSION_TYPES = ("PERCENT", "FIXED")
COMMISSION_STATUSES = ("ACTIVE", "INACTIVE", "EXPIRED")

NOTIFICATION_CHANNELS = ("IN_APP", "PUSH", "SMS", "EMAIL")
NOTIFICATION_STATUSES = ("QUEUED", "SENT", "DELIVERED", "FAILED")

POLICY_STATUSES = ("PROPOSED", "ACTIVE", "LAPSED", "CANCELLED")


# ----------------------------------------------------------------- core org


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        # registration numbers are partner-supplied; uniqueness only applies
        # where a value actually exists (never invent one).
        Index(
            "uq_organization_registration",
            "organization_type",
            "registration_number",
            unique=True,
            sqlite_where=text("registration_number <> ''"),
            postgresql_where=text("registration_number <> ''"),
        ),
        Index("ix_organizations_type_status", "organization_type", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_type: Mapped[str] = mapped_column(String(30), index=True)
    legal_name: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    registration_number: Mapped[str] = mapped_column(String(80), default="")
    tax_identifier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    latitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    longitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    verification_status: Mapped[str] = mapped_column(String(24), default="UNVERIFIED")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    members: Mapped[list["OrganizationMember"]] = relationship(back_populates="organization")
    profile: Mapped["PartnerProfile | None"] = relationship(
        back_populates="organization", uselist=False
    )

    @property
    def is_operable(self) -> bool:
        return self.status in OPERABLE_STATUSES


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        # At most one ACTIVE membership per (org, user): stale memberships are
        # revoked (is_active=False), never silently re-created.
        Index(
            "uq_org_member_active",
            "organization_id",
            "user_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = true"),
        ),
        Index("ix_org_members_user", "user_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    partner_role: Mapped[str] = mapped_column(String(30), default="PARTNER_STAFF")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    organization: Mapped[Organization] = relationship(back_populates="members")


class PartnerProfile(Base):
    """Organization-specific metadata. Link columns attach EXISTING Phase 3/4
    provider rows (doctors/hospitals/pharmacies) to the organization — the
    provider systems themselves are never duplicated."""

    __tablename__ = "partner_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), unique=True, index=True
    )
    # Type-specific free-form metadata (hospital type, specialties CSV,
    # emergency capability, delivery capability, service area, diagnostics...).
    # Validated by the service layer per organization_type; never fabricated.
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    # Existing provider links (nullable; used when the org maps to a Phase 3/4 row)
    doctor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("doctors.id"), nullable=True, index=True
    )
    hospital_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("hospitals.id"), nullable=True, index=True
    )
    pharmacy_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pharmacies.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    organization: Mapped[Organization] = relationship(back_populates="profile")


class PartnerLifecycleEvent(Base):
    """Append-only partner status history (Phase 3 verification-history pattern)."""

    __tablename__ = "partner_lifecycle_events"
    __table_args__ = (Index("ix_partner_lifecycle_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    previous_status: Mapped[str] = mapped_column(String(24), default="")
    new_status: Mapped[str] = mapped_column(String(24))
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------------------------------------------------------------- documents


class PartnerDocument(Base):
    """Partner KYC/verification documents. Files live in the Phase 5 encrypted
    storage (`stored_files`) — never public, object keys never exposed."""

    __tablename__ = "partner_documents"
    __table_args__ = (
        Index("ix_partner_documents_org_status", "organization_id", "verification_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    document_type: Mapped[str] = mapped_column(String(40))
    file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stored_files.id"), nullable=True
    )
    storage_reference: Mapped[str] = mapped_column(String(255), default="")
    checksum: Mapped[str] = mapped_column(String(64), default="")
    issued_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="UPLOADED", index=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    uploaded_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ----------------------------------------------------------------- services


class PartnerService(Base):
    """A service a partner organization offers. Price is optional and, when
    declared, starts UNVERIFIED — never shown as verified without a real
    verification decision (Phase 3/4 pricing honesty)."""

    __tablename__ = "partner_services"
    __table_args__ = (
        Index("ix_partner_services_org_type", "organization_id", "service_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    service_type: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    price_verification_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    price_source: Mapped[str] = mapped_column(String(120), default="partner_declared")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ------------------------------------------------------------------- claims


class PartnerClaim(Base):
    """Reusable claim architecture (insurance first, extensible). States change
    ONLY through the service-layer machine; nothing auto-approves."""

    __tablename__ = "partner_claims"
    __table_args__ = (
        Index(
            "uq_partner_claim_number",
            "organization_id",
            "claim_number",
            unique=True,
            sqlite_where=text("claim_number <> ''"),
            postgresql_where=text("claim_number <> ''"),
        ),
        Index("ix_partner_claims_org_status", "organization_id", "status"),
        Index("ix_partner_claims_patient", "patient_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    patient_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    claim_number: Mapped[str] = mapped_column(String(60), default="")
    subject_type: Mapped[str] = mapped_column(String(24), default="OTHER")
    subject_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    approved_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    submitted_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PartnerClaimEvent(Base):
    """Append-only claim transition history — every change auditable."""

    __tablename__ = "partner_claim_events"
    __table_args__ = (Index("ix_partner_claim_events_claim", "claim_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("partner_claims.id"), index=True)
    previous_status: Mapped[str] = mapped_column(String(40), default="")
    new_status: Mapped[str] = mapped_column(String(40))
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# --------------------------------------------------------------- lab module


class PartnerLabTest(Base):
    """Lab test catalog (partner-entered). Admin verification is required
    before a test is publicly visible. Nothing is seeded — the catalog stays
    empty until a real lab partner enters real tests."""

    __tablename__ = "partner_lab_tests"
    __table_args__ = (
        Index(
            "uq_partner_lab_test_code",
            "organization_id",
            "code",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = true"),
        ),
        Index("ix_partner_lab_tests_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="")
    sample_type: Mapped[str] = mapped_column(String(80), default="")
    preparation_notes: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    verification_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PartnerLabBooking(Base):
    """Lab test booking/request lifecycle (patient-initiated or partner-entered
    reference). Report delivery integrates with the Health Vault via the
    existing Phase 5 authorization rules — never a bypass."""

    __tablename__ = "partner_lab_bookings"
    __table_args__ = (Index("ix_partner_lab_bookings_org_status", "organization_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    test_id: Mapped[str] = mapped_column(String(36), ForeignKey("partner_lab_tests.id"), index=True)
    patient_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="REQUESTED", index=True)
    collection_mode: Mapped[str] = mapped_column(String(20), default="CENTER_VISIT")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_reference: Mapped[str] = mapped_column(String(255), default="")
    # Set only when the report is actually attached to the patient's vault.
    health_record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("health_records.id"), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# --------------------------------------------------------- insurance module


class PartnerInsuranceProduct(Base):
    """Insurance product catalog. Coverage text is partner-declared and is
    NEVER treated as verified coverage truth — no fabricated coverage."""

    __tablename__ = "partner_insurance_products"
    __table_args__ = (Index("ix_partner_ins_products_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(200))
    product_type: Mapped[str] = mapped_column(String(60), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    claim_intake_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PartnerInsurancePolicy(Base):
    """Patient-held policy references recorded from real submissions only.
    The policy number belongs to the patient; partners see it only for their
    own organization's policies."""

    __tablename__ = "partner_insurance_policies"
    __table_args__ = (Index("ix_partner_ins_policies_patient", "patient_user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    product_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("partner_insurance_products.id"), nullable=True
    )
    patient_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    policy_number: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="PROPOSED")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PartnerInsuranceClaimDetail(Base):
    """Insurance-specific claim metadata linked to a generic PartnerClaim."""

    __tablename__ = "partner_insurance_claim_details"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    claim_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("partner_claims.id"), unique=True, index=True
    )
    policy_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("partner_insurance_policies.id"), nullable=True
    )
    documents_ref: Mapped[str] = mapped_column(Text, default="")
    insurer_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ------------------------------------------------------------- integrations


class PartnerIntegration(Base):
    """API keys + webhook endpoints. `key_hash` is SHA-256; `key_prefix` is a
    short lookup prefix (not a secret). Raw keys are never stored."""

    __tablename__ = "partner_integrations"
    __table_args__ = (
        Index("ix_partner_integrations_org_kind", "organization_id", "integration_kind"),
        Index("ix_partner_integrations_prefix", "key_prefix"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    integration_kind: Mapped[str] = mapped_column(String(24), default="API_KEY")
    name: Mapped[str] = mapped_column(String(120), default="")
    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    key_prefix: Mapped[str] = mapped_column(String(16), default="")
    key_hash: Mapped[str] = mapped_column(String(64), default="")
    scopes: Mapped[str] = mapped_column(String(300), default="read")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PartnerWebhookEvent(Base):
    """Append-only outbound event ledger with idempotent event ids. Delivery
    attempts are recorded honestly; without a delivery worker configured,
    events stay PENDING (never marked DELIVERED)."""

    __tablename__ = "partner_webhook_events"
    __table_args__ = (
        Index("uq_partner_webhook_event_id", "event_id", unique=True),
        Index("ix_partner_webhook_events_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[str] = mapped_column(String(64))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    delivery_status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------------------------------------------------- settlements/commission


class PartnerSettlement(Base):
    """Explicit settlement records. Amounts are nullable until a real finance
    action supplies them; the API never computes or fabricates amounts and no
    gateway is called (partner_settlement flag OFF until configured)."""

    __tablename__ = "partner_settlements"
    __table_args__ = (
        Index("ix_partner_settlements_org", "organization_id"),
        Index(
            "uq_partner_settlement_period",
            "organization_id",
            "period_start",
            "period_end",
            unique=True,
            sqlite_where=text("period_start IS NOT NULL AND period_end IS NOT NULL"),
            postgresql_where=text("period_start IS NOT NULL AND period_end IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    gross_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    platform_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="RECORDED")
    external_reference: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    recorded_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PartnerCommission(Base):
    """Commercial-rule configuration for future settlement engines. Rows are
    configuration only — nothing applies them automatically in this phase."""

    __tablename__ = "partner_commissions"
    __table_args__ = (Index("ix_partner_commissions_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    commission_type: Mapped[str] = mapped_column(String(20), default="PERCENT")
    commission_value: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    service_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ------------------------------------------------------------ notifications


class PartnerNotification(Base):
    """Partner notification ledger with Phase 7 honesty semantics: IN_APP is
    real (this table is the inbox); external channels without a configured
    provider are FAILED with error_detail="provider_not_configured"."""

    __tablename__ = "partner_notifications"
    __table_args__ = (Index("ix_partner_notifications_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    recipient_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(10), default="IN_APP")
    status: Mapped[str] = mapped_column(String(10), default="QUEUED", index=True)
    event_type: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    resource_type: Mapped[str] = mapped_column(String(40), default="")
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
