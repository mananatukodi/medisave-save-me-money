"""Emergency & SOS models (spec §12; Phase 7 expanded).

HONESTY RULES (carried from Phase 1, still binding):
- Dispatch/availability/acceptance is NEVER fabricated: an event stays in a
  non-terminal state until a real emergency provider or hospital confirms.
- Provider integrations that are not configured are reported as
  NOT_CONFIGURED; notification delivery without a provider is recorded as
  FAILED with error_detail="provider_not_configured".
- Emergency records are never deleted; terminal states are immutable.

STATE MACHINE (service-enforced; see app/services/emergency_service.py):
REQUESTED -> ALERTING -> CONTACTING -> ACTIVE -> HANDOFF_PENDING ->
HANDED_OFF -> RESOLVED, with CANCELLED / FALSE_ALARM / FAILED terminals.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base, new_uuid, utcnow

# Phase 7 state machine. REQUESTED is the initial state (= spec "CREATED");
# the Phase 1 names are kept so Phase 1-6 contracts keep passing.
EMERGENCY_STATUSES = (
    "REQUESTED",
    "ALERTING",
    "CONTACTING",
    "ACTIVE",
    "HANDOFF_PENDING",
    "HANDED_OFF",
    "CANCELLED",
    "FALSE_ALARM",
    "RESOLVED",
    "FAILED",
)

# Non-terminal states: a patient may hold at most ONE event in these.
ACTIVE_SOS_STATUSES = ("REQUESTED", "ALERTING", "CONTACTING", "ACTIVE", "HANDOFF_PENDING")

# Cancellation reasons (optional on cancel).
CANCEL_REASONS = ("USER_CANCELLED", "FALSE_ALARM", "DUPLICATE", "OTHER")

EMERGENCY_TYPES = ("MEDICAL", "ACCIDENT", "FIRE", "SAFETY", "OTHER")

HANDOFF_STATUSES = (
    "HANDOFF_REQUESTED",
    "HANDOFF_ACCEPTED",
    "HANDOFF_REJECTED",
    "HANDOFF_EXPIRED",
    "HANDOFF_COMPLETED",
)

NOTIFICATION_CHANNELS = ("IN_APP", "PUSH", "SMS", "EMAIL")
NOTIFICATION_STATUSES = ("QUEUED", "SENT", "DELIVERED", "FAILED")

PROVIDER_ACTIONS = ("DISPATCH_REQUESTED", "DISPATCH_STATUS", "DISPATCH_CANCELLED")


class EmergencyEvent(Base):
    __tablename__ = "emergency_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # The patient the SOS is for. For self-initiated SOS this equals initiated_by.
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    # The authenticated actor who raised the SOS (family booking extension point).
    initiated_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="REQUESTED", index=True)
    emergency_type: Mapped[str] = mapped_column(String(20), default="MEDICAL")
    note: Mapped[str] = mapped_column(Text, default="")
    latitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    longitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    location_accuracy_m: Mapped[str | None] = mapped_column(String(16), nullable=True)
    location_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    network_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    device_platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Client-supplied idempotency key (hashed nothing — opaque, unique per user).
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(36), default=new_uuid)
    confirmed_by_provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        # At most ONE non-terminal SOS per patient (race-safe duplicate guard).
        Index(
            "uq_patient_active_sos",
            "user_id",
            unique=True,
            sqlite_where=text(
                "status IN ('REQUESTED','ALERTING','CONTACTING','ACTIVE','HANDOFF_PENDING')"
            ),
            postgresql_where=text(
                "status IN ('REQUESTED','ALERTING','CONTACTING','ACTIVE','HANDOFF_PENDING')"
            ),
        ),
        # Same user + same idempotency key -> same event (race-safe).
        Index(
            "uq_sos_idempotency",
            "user_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_emergency_events_created_at", "created_at"),
    )


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str] = mapped_column(String(20))
    # Python attr avoids shadowing sqlalchemy.orm.relationship; DB column stays "relationship".
    relationship_type: Mapped[str] = mapped_column("relationship", String(40), default="OTHER")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Comma-separated channel preferences, e.g. "IN_APP,SMS". Server-validated subset.
    notification_preferences: Mapped[str] = mapped_column(String(120), default="IN_APP")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class EmergencyProfile(Base):
    """Patient-managed emergency profile. EVERY field is optional; missing
    information is reported as UNKNOWN — never guessed, never fabricated."""

    __tablename__ = "emergency_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, index=True
    )
    blood_group: Mapped[str | None] = mapped_column(String(8), nullable=True)
    allergies: Mapped[str] = mapped_column(Text, default="")
    critical_conditions: Mapped[str] = mapped_column(Text, default="")
    critical_medications: Mapped[str] = mapped_column(Text, default="")
    emergency_notes: Mapped[str] = mapped_column(Text, default="")
    preferred_hospital_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("hospitals.id"), nullable=True
    )
    # Only stored when explicitly provided; empty means "not stated".
    organ_donor_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    accessibility_needs: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class EmergencyHandoff(Base):
    """Emergency handoff to a hospital. Acceptance requires REAL hospital-side
    confirmation (HOSPITAL_ADMIN action or future integration) — never automatic."""

    __tablename__ = "emergency_handoffs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    emergency_event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("emergency_events.id"), index=True
    )
    hospital_id: Mapped[str] = mapped_column(String(36), ForeignKey("hospitals.id"), index=True)
    requested_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="HANDOFF_REQUESTED", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class EmergencyNotification(Base):
    """Notification ledger. Delivery is only ever marked what actually
    happened: IN_APP rows are real (this table is the inbox); external
    channels without a configured provider are recorded FAILED with
    error_detail="provider_not_configured" — never SENT/DELIVERED."""

    __tablename__ = "emergency_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    emergency_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("emergency_events.id"), nullable=True, index=True
    )
    contact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("emergency_contacts.id"), nullable=True
    )
    recipient_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    recipient_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    channel: Mapped[str] = mapped_column(String(10), default="IN_APP")
    status: Mapped[str] = mapped_column(String(10), default="QUEUED", index=True)
    provider_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmergencyProviderEvent(Base):
    """Append-only ledger of ambulance-provider interactions. What the provider
    actually returned is stored verbatim in `status`/`detail` — nothing invented."""

    __tablename__ = "emergency_provider_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    emergency_event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("emergency_events.id"), index=True
    )
    provider_name: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
