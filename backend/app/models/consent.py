"""Consent management model (spec §30 — consent-first platform)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base, new_uuid, utcnow

CONSENT_TYPES = (
    "AI_ACCESS",
    "DOCTOR_ACCESS",
    "HOSPITAL_ACCESS",
    "FAMILY_ACCESS",
    "INSURANCE_ACCESS",
    "DOCUMENT_SHARE",
    # Phase 7: emergency minimum-necessary disclosure scopes. Granted by the
    # patient; recipients are "family:<relationship_id>" or "user:<user_id>".
    "EMERGENCY_PROFILE",
    "EMERGENCY_LOCATION",
    "EMERGENCY_CONTACTS",
    "EMERGENCY_MEDICAL_SUMMARY",
)


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(40), index=True)
    purpose: Mapped[str] = mapped_column(Text)
    data_scope: Mapped[str] = mapped_column(String(200), default="")  # e.g. "basic_profile"
    recipient: Mapped[str] = mapped_column(String(120), default="MEDISAVE_AI")
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            return self.expires_at > utcnow()
        return True
