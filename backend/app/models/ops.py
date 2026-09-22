"""Operational models: audit logs (§37), feature flags (§41), system settings (§42)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.user import new_uuid, utcnow


class AuditLog(Base):
    """Append-only audit trail for sensitive operations. Never logs secrets."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)  # LOGIN, CONSENT_CHANGE, ...
    resource_type: Mapped[str] = mapped_column(String(60), default="")
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), default="SUCCESS")  # SUCCESS | DENIED | ERROR
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class FeatureFlag(Base):
    """Business/experimental feature toggles (spec §41)."""

    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)  # AI_ENABLED, SOS_ENABLED, ...
    description: Mapped[str] = mapped_column(String(200), default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemSetting(Base):
    """Admin-configurable commercial/business rules (spec §42: no hardcoded commissions)."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
