"""Digital Health Vault models (Phase 5).

PRIVACY RULES (spec §5, §9, §15):
- The database stores opaque object keys, never public URLs or filesystem paths.
- Every record belongs to exactly one patient (owner). Access by anyone else
  requires an ACTIVE share (scope + expiry + revocation) — checked in the
  service layer, never inferred from roles. SUPPORT_AGENT and HOSPITAL_ADMIN
  have no default access; SUPER_ADMIN has no automatic clinical access
  (break-glass is deliberately NOT implemented in this phase).
- Audit events reference record IDs only — never document contents.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.user import new_uuid, utcnow

RECORD_CATEGORIES = (
    "PRESCRIPTION",
    "LAB_REPORT",
    "DIAGNOSTIC_REPORT",
    "IMAGING_REPORT",
    "DISCHARGE_SUMMARY",
    "DOCTOR_NOTE",
    "MEDICAL_CERTIFICATE",
    "VACCINATION_RECORD",
    "SURGERY_RECORD",
    "HOSPITAL_RECORD",
    "INSURANCE_DOCUMENT",
    "MEDICATION_RECORD",
    "OTHER",
)

SHARE_SCOPES = ("VIEW_RECORD", "VIEW_CATEGORY", "DOWNLOAD_RECORD")

UPLOAD_STATUSES = ("PENDING", "COMPLETED", "FAILED")
# Malware scanning REQUIRES PRODUCTION INTEGRATION (e.g. ClamAV); locally the
# record is marked PENDING and this is surfaced honestly in the UI/docs.
SCAN_STATUSES = ("PENDING", "CLEAN", "INFECTED", "SKIPPED")


class StoredFile(Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        Index("ix_stored_files_owner", "owner_id"),
        UniqueConstraint("storage_provider", "object_key", name="uq_stored_file_object"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(200))  # opaque key, not a path/URL
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="")
    storage_provider: Mapped[str] = mapped_column(String(40), default="LOCAL_ENCRYPTED")
    # JSON string: {"alg": "FERNET", "wrapped_dek": "...", "iv": "..."} — never
    # contains the raw key (spec §15 encryption-ready architecture).
    encryption_metadata: Mapped[str] = mapped_column(Text, default="")
    upload_status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    scan_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HealthRecord(Base):
    __tablename__ = "health_records"
    __table_args__ = (
        Index("ix_health_records_patient_cat", "patient_id", "category"),
        Index("ix_health_records_dates", "record_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    record_date: Mapped[str] = mapped_column(String(10), default="")  # ISO date, provider-asserted
    provider_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("doctors.id"), nullable=True, index=True
    )
    hospital_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("hospitals.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(40), default="PATIENT_UPLOAD")
    file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stored_files.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    # Soft delete: rows survive for audit; storage purge is explicit and separate
    # (spec §16: no cascading deletes that remove unrelated data).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    file: Mapped[StoredFile | None] = relationship(foreign_keys=[file_id])
    shares: Mapped[list["HealthRecordShare"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class HealthRecordShare(Base):
    """Record-scoped consent grant (spec §6, §7). Extends the consent system:
    each share links to a DOCUMENT_SHARE consent row so all grants live in one
    auditable consent ledger. WRITE access is never granted."""

    __tablename__ = "health_record_shares"
    __table_args__ = (
        Index("ix_shares_record", "record_id"),
        Index("ix_shares_grantee_active", "grantee_user_id", "revoked_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("health_records.id"), index=True
    )
    consent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("consents.id"), nullable=True
    )
    granted_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    grantee_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    # DOCTOR | FAMILY_MEMBER | HOSPITAL_ADMIN | USER
    grantee_type: Mapped[str] = mapped_column(String(40), default="DOCTOR")
    scope: Mapped[str] = mapped_column(String(30), default="VIEW_RECORD")
    # CSV of categories for VIEW_CATEGORY scope
    category_filter: Mapped[str] = mapped_column(String(400), default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    record: Mapped[HealthRecord] = relationship(back_populates="shares")

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            # SQLite returns naive datetimes; normalize before comparing.
            expires = self.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires <= datetime.now(UTC):
                return False
        return True


class HealthRecordAccessEvent(Base):
    """Per-record access ledger (spec §9). Contents of documents are never
    written here — only actor, record reference, action, and result."""

    __tablename__ = "health_record_access_events"
    __table_args__ = (
        Index("ix_vault_events_record", "record_id"),
        Index("ix_vault_events_actor", "actor_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    record_id: Mapped[str] = mapped_column(String(36), index=True)
    patient_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # VIEW | DOWNLOAD_URL | DENIED | SHARE_CREATED | SHARE_REVOKED | DELETE
    action: Mapped[str] = mapped_column(String(40))
    result: Mapped[str] = mapped_column(String(20), default="SUCCESS")  # SUCCESS | DENIED
    # e.g. "share_revoked" — reasons only, never document content
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
