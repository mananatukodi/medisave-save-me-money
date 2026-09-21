"""Availability computation and appointment lifecycle (Phase 3, spec §8-§10).

Double-booking prevention is defense-in-depth:
1. In-process check against existing active appointments.
2. A partial unique index (uq_active_appointment_slot) in the database as the
   hard guarantee — enforced even under concurrent requests. An IntegrityError
   is surfaced as a 409 to the caller.
"""

import threading
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.providers import (
    APPOINTMENT_STATUSES,
    Doctor,
    ProviderBlock,
    ProviderService,
    ServiceAvailability,
)
from app.schemas.providers import (
    AppointmentOut,
    AvailabilityRule,
    BlockCreate,
    DayAvailabilityOut,
    SlotOut,
)

_active_lock = threading.Lock()

ACTIVE_STATUSES = ("REQUESTED", "CONFIRMED", "RESCHEDULED")

# Allowed lifecycle transitions (spec §9).
TRANSITIONS: dict[str, set[str]] = {
    "REQUESTED": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"RESCHEDULED", "CANCELLED", "COMPLETED", "NO_SHOW"},
    "RESCHEDULED": {"CONFIRMED", "CANCELLED", "COMPLETED", "NO_SHOW"},
    "CANCELLED": set(),
    "COMPLETED": set(),
    "NO_SHOW": set(),
}


class BookingError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _parse_hhmm(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _format_hhmm(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def set_availability(
    db: Session,
    *,
    provider_kind: str,
    provider_id: str,
    rules: list[AvailabilityRule],
) -> list[ServiceAvailability]:
    """Replace the provider's weekly template with the given rules."""
    if provider_kind != "DOCTOR":
        raise BookingError("Only doctor availability is supported in Phase 3", 422)
    for rule in rules:
        if _parse_hhmm(rule.start_time) >= _parse_hhmm(rule.end_time):
            raise BookingError(f"start_time must be before end_time for weekday {rule.weekday}", 422)
    db.query(ServiceAvailability).filter(
        ServiceAvailability.provider_kind == provider_kind,
        ServiceAvailability.provider_id == provider_id,
    ).delete()
    created = [
        ServiceAvailability(
            provider_kind=provider_kind,
            provider_id=provider_id,
            weekday=rule.weekday,
            start_time=rule.start_time,
            end_time=rule.end_time,
            slot_minutes=rule.slot_minutes,
        )
        for rule in rules
    ]
    for row in created:
        db.add(row)
    db.flush()
    return created


def add_block(db: Session, *, provider_kind: str, provider_id: str, block: BlockCreate):
    if block.start_time and block.end_time and _parse_hhmm(block.start_time) >= _parse_hhmm(block.end_time):
        raise BookingError("block start_time must be before end_time", 422)
    row = ProviderBlock(
        provider_kind=provider_kind,
        provider_id=provider_id,
        block_date=block.block_date,
        start_time=block.start_time,
        end_time=block.end_time,
        reason=block.reason,
    )
    db.add(row)
    db.flush()
    return row


def list_availability(db: Session, *, provider_kind: str, provider_id: str) -> list[ServiceAvailability]:
    return (
        db.query(ServiceAvailability)
        .filter(
            ServiceAvailability.provider_kind == provider_kind,
            ServiceAvailability.provider_id == provider_id,
        )
        .order_by(ServiceAvailability.weekday.asc(), ServiceAvailability.start_time.asc())
        .all()
    )


def _weekday_rules(db: Session, provider_id: str, weekday: int) -> list[ServiceAvailability]:
    return (
        db.query(ServiceAvailability)
        .filter(
            ServiceAvailability.provider_kind == "DOCTOR",
            ServiceAvailability.provider_id == provider_id,
            ServiceAvailability.weekday == weekday,
            ServiceAvailability.is_active.is_(True),
        )
        .all()
    )


def _blocks_for_date(db: Session, provider_id: str, day: str) -> list[ProviderBlock]:
    return (
        db.query(ProviderBlock)
        .filter(
            ProviderBlock.provider_kind == "DOCTOR",
            ProviderBlock.provider_id == provider_id,
            ProviderBlock.block_date == day,
        )
        .all()
    )


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def get_day_availability(db: Session, *, doctor_id: str, day: str) -> DayAvailabilityOut:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise BookingError("Doctor not found", 404)

    parsed = date.fromisoformat(day)
    weekday = parsed.weekday()
    rules = _weekday_rules(db, doctor_id, weekday)
    if not rules:
        return DayAvailabilityOut(date=day, weekday=weekday, slots=[])

    blocks = _blocks_for_date(db, doctor_id, day)
    booked = {
        a.appointment_time
        for a in db.query(Appointment)
        .filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == day,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
        .all()
    }

    slots: list[SlotOut] = []
    seen: set[int] = set()
    for rule in rules:
        cursor = _parse_hhmm(rule.start_time)
        end = _parse_hhmm(rule.end_time)
        step = rule.slot_minutes
        while cursor + step <= end:
            key = cursor
            if key not in seen:
                seen.add(key)
                slot_start = _format_hhmm(cursor)
                reason: str | None = None
                if slot_start in booked:
                    reason = "BOOKED"
                else:
                    for block in blocks:
                        b_start = _parse_hhmm(block.start_time) if block.start_time else 0
                        b_end = _parse_hhmm(block.end_time) if block.end_time else 24 * 60
                        if _overlaps(cursor, cursor + step, b_start, b_end):
                            reason = f"BLOCKED: {block.reason or 'unavailable'}"
                            break
                slots.append(SlotOut(time=slot_start, available=reason is None, reason=reason))
            cursor += step
    slots.sort(key=lambda s: s.time)
    return DayAvailabilityOut(date=day, weekday=weekday, slots=slots)


def get_range_availability(
    db: Session, *, doctor_id: str, start_date: str, days: int
) -> list[DayAvailabilityOut]:
    start = date.fromisoformat(start_date)
    return [
        get_day_availability(db, doctor_id=doctor_id, day=(start + timedelta(offset)).isoformat())
        for offset in range(max(1, min(days, 30)))
    ]


def create_appointment(
    db: Session,
    *,
    patient_user_id: str,
    doctor_id: str,
    service_id: str,
    appointment_date: str,
    appointment_time: str,
    notes: str = "",
    requested_by_user_id: str | None = None,
) -> Appointment:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or not doctor.is_active:
        raise BookingError("Doctor not found", 404)
    if doctor.verification_status != "VERIFIED":
        raise BookingError("Appointments can only be booked with VERIFIED doctors", 409)

    service = db.get(ProviderService, service_id)
    if service is None or service.provider_id != doctor_id or not service.is_active:
        raise BookingError("Service not found for this doctor", 404)

    day_availability = get_day_availability(db, doctor_id=doctor_id, day=appointment_date)
    slot = next((s for s in day_availability.slots if s.time == appointment_time), None)
    if slot is None or not slot.available:
        raise BookingError("Requested slot is not available", 409)

    verified_price = next(
        (p for p in service.prices if p.verification_status == "VERIFIED"), None
    )
    declared = service.prices[0] if service.prices else None
    price = verified_price or declared

    with _active_lock:
        appointment = Appointment(
            patient_user_id=patient_user_id,
            requested_by_user_id=requested_by_user_id,
            doctor_id=doctor_id,
            specialty_slug=service.specialty_slug,
            service_id=service_id,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            consultation_type=service.consultation_type,
            location=doctor.address_line or (doctor.city or ""),
            price_amount=price.amount if price else None,
            price_currency=price.currency if price else "INR",
            price_verified=verified_price is not None,
            status="REQUESTED",
            notes=notes,
        )
        db.add(appointment)
        try:
            db.flush()
        except IntegrityError as err:
            db.rollback()
            raise BookingError("Slot was just booked by someone else", 409) from err
    return appointment


def transition_appointment(
    db: Session,
    *,
    appointment: Appointment,
    new_status: str,
    actor_is_patient: bool,
) -> Appointment:
    if new_status not in APPOINTMENT_STATUSES:
        raise BookingError(f"Unknown status {new_status}", 422)
    allowed = TRANSITIONS.get(appointment.status, set())
    if new_status not in allowed:
        raise BookingError(
            f"Cannot move appointment from {appointment.status} to {new_status}", 409
        )
    if actor_is_patient and new_status not in ("CANCELLED",):
        raise BookingError("Patients may only cancel appointments", 403)

    if new_status in ("RESCHEDULED",):
        # Reschedule sets a marker; the new slot must still be validated by the caller
        # via _validate_slot_for_reschedule before CONFIRMED.
        pass
    appointment.status = new_status
    db.flush()
    return appointment


def validate_reschedule_slot(
    db: Session, *, appointment: Appointment, new_date: str, new_time: str
) -> None:
    """Ensure the new slot is within availability and free (excluding this appointment)."""
    doctor_id = appointment.doctor_id
    day_availability = get_day_availability(db, doctor_id=doctor_id, day=new_date)
    slot = next((s for s in day_availability.slots if s.time == new_time), None)
    if slot is None or not slot.available:
        raise BookingError("Requested slot is not available", 409)
    # The slot shows "available" because the current appointment on the OLD date/time
    # doesn't collide, but guard the pathological same-slot case explicitly:
    if appointment.appointment_date == new_date and appointment.appointment_time == new_time:
        return  # keeping the same slot is a no-op reschedule
    clash = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == new_date,
            Appointment.appointment_time == new_time,
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.id != appointment.id,
        )
        .scalar()
    )
    if clash:
        raise BookingError("Slot was just booked by someone else", 409)


def to_out(appointment: Appointment) -> AppointmentOut:
    return AppointmentOut.model_validate(appointment)
