"""Provider models: doctors, hospitals, verifications, services, availability (Phase 3).

REAL DATA RULE (spec §2, §54): these models exist to receive data through the
registration + verification workflow. Nothing in this module seeds fabricated
doctors, hospitals, or prices. A provider is only ever shown as VERIFIED when a
verification row with a real decision exists (checked in the service layer).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.user import new_uuid, utcnow

VERIFICATION_STATES = ("PENDING", "UNDER_REVIEW", "VERIFIED", "REJECTED", "SUSPENDED")
CONSULTATION_TYPES = ("IN_PERSON", "VIDEO", "AUDIO")
APPOINTMENT_STATUSES = ("REQUESTED", "CONFIRMED", "RESCHEDULED", "CANCELLED", "COMPLETED", "NO_SHOW")


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    specialty_slug: Mapped[str] = mapped_column(String(60), ForeignKey("specialties.slug"), index=True)
    sub_specialty: Mapped[str | None] = mapped_column(String(160), nullable=True)
    qualifications: Mapped[str] = mapped_column(String(300), default="")  # e.g. MBBS, MS (Ophth)
    registration_number: Mapped[str] = mapped_column(String(80), default="")
    registration_council: Mapped[str] = mapped_column(String(120), default="")
    years_experience: Mapped[int] = mapped_column(Integer, default=0)
    languages: Mapped[str] = mapped_column(String(200), default="te,en")  # CSV of language codes
    consultation_modes: Mapped[str] = mapped_column(String(60), default="IN_PERSON")  # CSV
    about: Mapped[str] = mapped_column(Text, default="")
    # Contact / location
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    latitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    longitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    hospital_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("hospitals.id"), nullable=True)
    # Aggregate verification status (mirrors the latest verification row; never set arbitrarily)
    verification_status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    verifications: Mapped[list["DoctorVerification"]] = relationship(
        back_populates="doctor", cascade="all, delete-orphan"
    )
    services: Mapped[list["ProviderService"]] = relationship(
        back_populates="doctor", cascade="all, delete-orphan"
    )
    specialties: Mapped[list["ProviderSpecialtyLink"]] = relationship(
        primaryjoin="and_(ProviderSpecialtyLink.provider_kind=='DOCTOR',"
        "foreign(ProviderSpecialtyLink.provider_id)==Doctor.id)",
        viewonly=True,
    )


class DoctorVerification(Base):
    """Audit trail of every verification decision (spec §2, §37)."""

    __tablename__ = "doctor_verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    doctor_id: Mapped[str] = mapped_column(String(36), ForeignKey("doctors.id"), index=True)
    previous_status: Mapped[str] = mapped_column(String(20), default="")
    new_status: Mapped[str] = mapped_column(String(20))
    decided_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    document_refs: Mapped[str] = mapped_column(Text, default="")  # references, not document blobs
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    doctor: Mapped[Doctor] = relationship(back_populates="verifications")


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    admin_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    # HOSPITAL | CLINIC | EYE_CLINIC | DENTAL_CLINIC
    hospital_type: Mapped[str] = mapped_column(String(40), default="HOSPITAL")
    registration_number: Mapped[str] = mapped_column(String(80), default="")
    address_line: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    latitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    longitude: Mapped[str | None] = mapped_column(String(24), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    departments: Mapped[str] = mapped_column(Text, default="")  # CSV of specialty slugs
    services_summary: Mapped[str] = mapped_column(Text, default="")
    emergency_available: Mapped[bool] = mapped_column(Boolean, default=False)
    # Emergency availability may only be advertised when verified (spec §14.14).
    emergency_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    insurance_info: Mapped[str] = mapped_column(Text, default="")  # free text; no fabricated coverage claims
    verification_status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    verifications: Mapped[list["HospitalVerification"]] = relationship(
        back_populates="hospital", cascade="all, delete-orphan"
    )


class HospitalVerification(Base):
    __tablename__ = "hospital_verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    hospital_id: Mapped[str] = mapped_column(String(36), ForeignKey("hospitals.id"), index=True)
    previous_status: Mapped[str] = mapped_column(String(20), default="")
    new_status: Mapped[str] = mapped_column(String(20))
    decided_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    document_refs: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    hospital: Mapped[Hospital] = relationship(back_populates="verifications")


class ProviderSpecialtyLink(Base):
    """Multi-specialty links for any provider kind (spec §4: a provider may have several)."""

    __tablename__ = "provider_specialty_links"
    __table_args__ = (
        UniqueConstraint("provider_kind", "provider_id", "specialty_slug", name="uq_provider_specialty"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_kind: Mapped[str] = mapped_column(String(20))  # DOCTOR | HOSPITAL
    provider_id: Mapped[str] = mapped_column(String(36), index=True)
    specialty_slug: Mapped[str] = mapped_column(String(60), ForeignKey("specialties.slug"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderService(Base):
    """A bookable service offered by a doctor (and later hospital services)."""

    __tablename__ = "provider_services"
    __table_args__ = (Index("ix_provider_services_provider", "provider_kind", "provider_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_kind: Mapped[str] = mapped_column(String(20), default="DOCTOR")
    provider_id: Mapped[str] = mapped_column(String(36), index=True)
    doctor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("doctors.id"), nullable=True)
    specialty_slug: Mapped[str] = mapped_column(String(60), ForeignKey("specialties.slug"), index=True)
    name_en: Mapped[str] = mapped_column(String(160))
    name_te: Mapped[str] = mapped_column(String(160), default="")
    name_hi: Mapped[str] = mapped_column(String(160), default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    # IN_PERSON | VIDEO | AUDIO
    consultation_type: Mapped[str] = mapped_column(String(20), default="IN_PERSON")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    doctor: Mapped[Doctor | None] = relationship(back_populates="services", foreign_keys=[doctor_id])
    prices: Mapped[list["ServicePrice"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )


class ServicePrice(Base):
    """Price entries with provenance. Unverified prices are NEVER shown as verified (spec §7, §16)."""

    __tablename__ = "service_prices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    service_id: Mapped[str] = mapped_column(String(36), ForeignKey("provider_services.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    # UNVERIFIED | VERIFIED
    verification_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    source: Mapped[str] = mapped_column(String(200), default="provider_declared")
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    service: Mapped[ProviderService] = relationship(back_populates="prices")


class ServiceAvailability(Base):
    """Weekly recurring availability template for a provider (spec §8)."""

    __tablename__ = "service_availability"
    __table_args__ = (
        UniqueConstraint(
            "provider_kind", "provider_id", "weekday", "start_time", name="uq_availability_rule"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_kind: Mapped[str] = mapped_column(String(20), default="DOCTOR")
    provider_id: Mapped[str] = mapped_column(String(36), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0=Monday .. 6=Sunday
    start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM" 24h
    end_time: Mapped[str] = mapped_column(String(5))
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderBlock(Base):
    """Holidays, breaks and blocked slots (spec §8). One-off date blocks."""

    __tablename__ = "provider_blocks"
    __table_args__ = (
        Index("ix_provider_blocks_provider", "provider_kind", "provider_id", "block_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_kind: Mapped[str] = mapped_column(String(20), default="DOCTOR")
    provider_id: Mapped[str] = mapped_column(String(36))
    block_date: Mapped[str] = mapped_column(String(10))  # ISO date "YYYY-MM-DD"
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # null = all day
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
