"""Specialty care catalog models (spec §6, §21).

Provider data (doctors/hospitals/clinics) is NEVER seeded with fabricated entries;
those tables belong to Phase 3 and require a real verification workflow.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.user import new_uuid, utcnow

# Spec §6 mandatory specialty list.
SPECIALTY_SLUGS = (
    "eye-care",
    "dental-care",
    "cardiology",
    "pediatrics",
    "general-medicine",
    "neurology",
    "orthopedics",
    "gynecology",
    "dermatology",
    "ent",
    "pulmonology",
    "nephrology",
    "oncology",
    "mental-health",
    "physiotherapy",
    "diagnostics-lab",
    "other",
)


class Specialty(Base):
    __tablename__ = "specialties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_te: Mapped[str] = mapped_column(String(120))
    name_hi: Mapped[str] = mapped_column(String(120))
    icon: Mapped[str] = mapped_column(String(16), default="🩺")
    description_en: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    services: Mapped[list["SpecialtyService"]] = relationship(
        back_populates="specialty", cascade="all, delete-orphan"
    )
    provider_links: Mapped[list["ProviderSpecialty"]] = relationship(
        back_populates="specialty", cascade="all, delete-orphan"
    )


class SpecialtyService(Base):
    """A service within a specialty, e.g. 'Vision screening' under eye-care.

    Verified prices (Phase 3) attach to services via service_prices with
    source/lastUpdated/verificationStatus — never fabricated (spec §16).
    """

    __tablename__ = "specialty_services"
    __table_args__ = (UniqueConstraint("specialty_id", "code", name="uq_specialty_service_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    specialty_id: Mapped[str] = mapped_column(String(36), ForeignKey("specialties.id"), index=True)
    code: Mapped[str] = mapped_column(String(60))
    name_en: Mapped[str] = mapped_column(String(160))
    name_te: Mapped[str] = mapped_column(String(160))
    name_hi: Mapped[str] = mapped_column(String(160))
    description_en: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    specialty: Mapped[Specialty] = relationship(back_populates="services")


class ProviderSpecialty(Base):
    """Structural link table for Phase 3 provider registration (no fabricated rows)."""

    __tablename__ = "provider_specialties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    specialty_id: Mapped[str] = mapped_column(String(36), ForeignKey("specialties.id"), index=True)
    provider_kind: Mapped[str] = mapped_column(String(20))  # DOCTOR | HOSPITAL | CLINIC | LAB
    provider_id: Mapped[str] = mapped_column(String(36), index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    specialty: Mapped[Specialty] = relationship(back_populates="provider_links")
