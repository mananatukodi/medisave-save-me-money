"""Appointment endpoints (Phase 3, spec §9, §10) with ownership + RBAC + audit."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.providers import Doctor
from app.models.user import User
from app.schemas.providers import (
    AppointmentCreate,
    AppointmentOut,
    RescheduleRequest,
    StatusUpdate,
)
from app.security.deps import CurrentUser, record_audit
from app.services import family_service
from app.services.booking_service import (
    BookingError,
    create_appointment,
    transition_appointment,
    validate_reschedule_slot,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _get_owned_or_provider_appointment(
    db: Session, appointment_id: str, user: User
) -> tuple[Appointment, bool]:
    """Returns (appointment, actor_is_patient). 404 when the user has no relation."""
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.patient_user_id == user.id:
        return appointment, True
    doctor = db.get(Doctor, appointment.doctor_id)
    if doctor is not None and doctor.user_id == user.id:
        return appointment, False
    raise HTTPException(status_code=404, detail="Appointment not found")


def _booking_error(err: BookingError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=str(err))


@router.post("", response_model=AppointmentOut, status_code=201)
def book(
    payload: AppointmentCreate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Appointment:
    requested_by: str | None = None
    patient_user_id = current_user.id
    if payload.on_behalf_of_patient_id is not None:
        # Phase 6: family/caregiver booking. The server resolves the
        # relationship + consent; the client-supplied patient id is verified,
        # never trusted. Patient ownership does NOT transfer.
        if payload.on_behalf_of_patient_id == current_user.id:
            raise HTTPException(status_code=422, detail="Use self-booking without on_behalf_of_patient_id")
        rel = family_service.relationship_for_member(
            db, member_user_id=current_user.id, owner_user_id=payload.on_behalf_of_patient_id
        )
        if rel is None:
            raise HTTPException(status_code=403, detail="No active family relationship with this patient")
        consent = family_service.active_consent(db, rel.id)
        if consent is None or "REQUEST_APPOINTMENT" not in consent.scope_list:
            raise HTTPException(status_code=403, detail="REQUEST_APPOINTMENT consent is required")
        patient_user_id = payload.on_behalf_of_patient_id
        requested_by = current_user.id
    try:
        appointment = create_appointment(
            db,
            patient_user_id=patient_user_id,
            doctor_id=payload.doctor_id,
            service_id=payload.service_id,
            appointment_date=payload.appointment_date,
            appointment_time=payload.appointment_time,
            notes=payload.notes,
            requested_by_user_id=requested_by,
        )
    except BookingError as err:
        raise _booking_error(err) from None
    record_audit(
        db, action="APPOINTMENT_BOOKED", actor_user_id=current_user.id,
        actor_role="PATIENT", resource_type="appointment", resource_id=appointment.id,
        detail=f"doctor={appointment.doctor_id} {appointment.appointment_date} "
        f"{appointment.appointment_time}"
        + (f" on_behalf_of={patient_user_id} relationship={rel.id}" if requested_by else ""),
    )
    db.commit()
    return appointment


@router.get("", response_model=list[AppointmentOut])
def list_own(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    role: str = Query(default="patient", pattern="^(patient|doctor)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Appointment]:
    query = db.query(Appointment)
    if role == "doctor":
        doctor = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
        if doctor is None:
            return []
        query = query.filter(Appointment.doctor_id == doctor.id)
    else:
        query = query.filter(Appointment.patient_user_id == current_user.id)
    return (
        query.order_by(Appointment.appointment_date.desc(), Appointment.appointment_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_one(
    appointment_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Appointment:
    appointment, _ = _get_owned_or_provider_appointment(db, appointment_id, current_user)
    return appointment


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update_status(
    appointment_id: str,
    payload: StatusUpdate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Appointment:
    appointment, actor_is_patient = _get_owned_or_provider_appointment(db, appointment_id, current_user)
    try:
        transition_appointment(
            db,
            appointment=appointment,
            new_status=payload.status,
            actor_is_patient=actor_is_patient,
        )
    except BookingError as err:
        raise _booking_error(err) from None
    record_audit(
        db, action="APPOINTMENT_STATUS", actor_user_id=current_user.id,
        resource_type="appointment", resource_id=appointment.id,
        detail=f"{appointment.status} -> {payload.status} ({'patient' if actor_is_patient else 'provider'})",
    )
    db.commit()
    return appointment


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(
    appointment_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Appointment:
    appointment, actor_is_patient = _get_owned_or_provider_appointment(db, appointment_id, current_user)
    try:
        transition_appointment(
            db, appointment=appointment, new_status="CANCELLED", actor_is_patient=actor_is_patient
        )
    except BookingError as err:
        raise _booking_error(err) from None
    record_audit(
        db, action="APPOINTMENT_CANCELLED", actor_user_id=current_user.id,
        resource_type="appointment", resource_id=appointment.id,
    )
    db.commit()
    return appointment


@router.post("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule(
    appointment_id: str,
    payload: RescheduleRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Appointment:
    appointment, actor_is_patient = _get_owned_or_provider_appointment(db, appointment_id, current_user)
    if appointment.status not in ("REQUESTED", "CONFIRMED", "RESCHEDULED"):
        raise HTTPException(status_code=409, detail=f"Cannot reschedule a {appointment.status} appointment")
    try:
        validate_reschedule_slot(
            db,
            appointment=appointment,
            new_date=payload.appointment_date,
            new_time=payload.appointment_time,
        )
    except BookingError as err:
        raise _booking_error(err) from None

    previous = f"{appointment.appointment_date} {appointment.appointment_time}"
    appointment.appointment_date = payload.appointment_date
    appointment.appointment_time = payload.appointment_time
    if appointment.status == "CONFIRMED":
        appointment.status = "RESCHEDULED"
    try:
        db.flush()
    except Exception as err:  # IntegrityError from the unique slot index
        db.rollback()
        raise HTTPException(status_code=409, detail="Slot was just booked by someone else") from err

    record_audit(
        db, action="APPOINTMENT_RESCHEDULED", actor_user_id=current_user.id,
        resource_type="appointment", resource_id=appointment.id,
        detail=f"{previous} -> {payload.appointment_date} {payload.appointment_time}",
    )
    db.commit()
    return appointment
