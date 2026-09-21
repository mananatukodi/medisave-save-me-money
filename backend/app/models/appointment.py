"""Appointment model (spec §9) with server-side double-booking prevention.

The partial unique index below is the hard guarantee: only one active
appointment can exist per (provider, date, time). Cancelled/NO_SHOW rows are
excluded via a partial index (SQLite supports partial indexes too).
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.user import new_uuid, utcnow


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index(
            "uq_active_appointment_slot",
            "doctor_id",
            "appointment_date",
            "appointment_time",
            unique=True,
            sqlite_where=text("status IN ('REQUESTED','CONFIRMED','RESCHEDULED')"),
            postgresql_where=text("status IN ('REQUESTED','CONFIRMED','RESCHEDULED')"),
        ),
        Index("ix_appointments_patient", "patient_user_id", "appointment_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    patient_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(String(36), ForeignKey("doctors.id"), index=True)
    specialty_slug: Mapped[str] = mapped_column(String(60), ForeignKey("specialties.slug"))
    service_id: Mapped[str] = mapped_column(String(36), ForeignKey("provider_services.id"))
    appointment_date: Mapped[str] = mapped_column(String(10))  # ISO "YYYY-MM-DD"
    appointment_time: Mapped[str] = mapped_column(String(5))  # "HH:MM"
    consultation_type: Mapped[str] = mapped_column(String(20), default="IN_PERSON")
    location: Mapped[str] = mapped_column(String(300), default="")
    price_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    price_currency: Mapped[str] = mapped_column(String(8), default="INR")
    price_verified: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="REQUESTED", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    # Phase 6: family member who requested the appointment on behalf of the
    # patient (actor). NULL for self-booked appointments.
    requested_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    doctor: Mapped["Doctor"] = relationship()
    service: Mapped["ProviderService"] = relationship()


# Imported late purely for type resolution of the relationships above.
from app.models.providers import Doctor, ProviderService  # noqa: E402
