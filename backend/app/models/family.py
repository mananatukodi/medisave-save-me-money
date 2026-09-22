"""Family accounts & caregiver access models (Phase 6).

PRIVACY / SAFETY RULES:
- A family relationship grants ZERO access by itself. Every clinical access
  requires an explicit, scoped, time-bounded, revocable consent row
  (family_access_consents) validated server-side on every request.
- Invitation tokens are stored ONLY as SHA-256 hashes; the raw token exists
  in the invite response exactly once and is never logged.
- Relationship labels are user-declared and never verified (no legal claim).
- Status transitions are explicit: INVITED -> ACTIVE (accept) /
  DECLINED (decline) / REVOKED (either side) / EXPIRED (token TTL).
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base, new_uuid, utcnow

RELATIONSHIP_TYPES = (
    "SPOUSE",
    "PARENT",
    "CHILD",
    "SIBLING",
    "GRANDPARENT",
    "GRANDCHILD",
    "CAREGIVER",
    "OTHER",
)

RELATIONSHIP_STATUSES = (
    "INVITED",
    "ACTIVE",
    "DECLINED",
    "REVOKED",
    "EXPIRED",
)

FAMILY_SCOPES = (
    "VIEW_HEALTH_RECORDS",
    "VIEW_APPOINTMENTS",
    "VIEW_MEDICINE_ORDERS",
    "REQUEST_APPOINTMENT",
    "REQUEST_REFILL",
    "RECEIVE_HEALTH_ALERTS",
)

INVITATION_TTL_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FamilyRelationship(Base):
    __tablename__ = "family_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    member_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(120))
    relationship_type: Mapped[str] = mapped_column(String(40))  # user-declared
    invited_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="INVITED", index=True)
    invitation_token_hash: Mapped[str] = mapped_column(String(64), index=True)
    invitation_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        Index(
            "uq_family_active_relationship",
            "owner_user_id",
            "member_user_id",
            unique=True,
            sqlite_where=text("status = 'ACTIVE'"),
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_family_token_hash", "invitation_token_hash"),
    )

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE"

    @property
    def invitation_pending(self) -> bool:
        expires = self.invitation_expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=_utcnow().tzinfo)
        return self.status == "INVITED" and expires is not None and expires > _utcnow()


class FamilyAccessConsent(Base):
    __tablename__ = "family_access_consents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    relationship_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("family_relationships.id"), index=True
    )
    # Comma-separated subset of FAMILY_SCOPES — validated server-side, never trusted.
    scopes: Mapped[str] = mapped_column(String(300), default="")
    # Comma-separated record categories (HealthRecord.category values), optional.
    category_filter: Mapped[str] = mapped_column(String(300), default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    granted_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= _utcnow():
            return False
        return bool(self.scopes.strip())

    @property
    def scope_list(self) -> list[str]:
        return [s.strip() for s in self.scopes.split(",") if s.strip()]

    @property
    def categories(self) -> list[str]:
        return [c.strip() for c in self.category_filter.split(",") if c.strip()]
