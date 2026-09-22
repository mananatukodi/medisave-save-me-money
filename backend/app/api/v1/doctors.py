"""Doctor discovery + doctor self-service endpoints (Phase 3, spec §1, §11, §14)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.providers import Doctor, ProviderService, ServicePrice
from app.models.user import User
from app.schemas.providers import (
    AvailabilityRule,
    AvailabilityRuleOut,
    BlockCreate,
    BlockOut,
    DayAvailabilityOut,
    DoctorDetail,
    DoctorPublic,
    DoctorRegistration,
    PriceDeclare,
    ServiceCreate,
    ServiceOut,
    ServicePriceOut,
)
from app.security.deps import CurrentUser, record_audit, require_roles
from app.services import booking_service, provider_service
from app.services.booking_service import BookingError
from app.services.provider_service import ProviderError

router = APIRouter(prefix="/doctors", tags=["doctors"])


def _get_own_doctor(db: Session, user: User) -> Doctor:
    doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
    if doctor is None:
        raise HTTPException(status_code=404, detail="No doctor profile for this user")
    return doctor


def _provider_error(err: ProviderError | BookingError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=str(err))


# ---------------------------------------------------------------- discovery

@router.get("", response_model=list[DoctorPublic])
def search_doctors(
    db: Annotated[Session, Depends(get_db)],
    specialty: str | None = None,
    city: str | None = None,
    consultation_type: str | None = None,
    verification_status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Doctor]:
    try:
        return provider_service.search_doctors(
            db, specialty=specialty, city=city, consultation_type=consultation_type,
            verification_status=verification_status, limit=limit, offset=offset,
        )
    except ProviderError as err:
        raise _provider_error(err) from None


@router.get("/{doctor_id}", response_model=DoctorDetail)
def get_doctor(doctor_id: str, db: Annotated[Session, Depends(get_db)]) -> DoctorDetail:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or not doctor.is_active:
        raise HTTPException(status_code=404, detail="Doctor not found")
    detail = DoctorDetail.model_validate(doctor, from_attributes=True)
    detail.specialty_slugs = provider_service.provider_specialty_slugs(
        db, provider_kind="DOCTOR", provider_id=doctor.id
    )
    return detail


# ---------------------------------------------------------------- self-service

@router.post("/register", response_model=DoctorPublic, status_code=201)
def register(
    payload: DoctorRegistration,
    current_user: Annotated[User, Depends(require_roles("DOCTOR"))],
    db: Annotated[Session, Depends(get_db)],
) -> Doctor:
    try:
        doctor = provider_service.register_doctor(db, payload, user_id=current_user.id)
    except ProviderError as err:
        raise _provider_error(err) from None
    record_audit(
        db, action="PROVIDER_REGISTER", actor_user_id=current_user.id, actor_role="DOCTOR",
        resource_type="doctor", resource_id=doctor.id, detail=f"specialty={doctor.specialty_slug}",
    )
    db.commit()
    return doctor


@router.patch("/me", response_model=DoctorPublic)
def update_own_profile(
    payload: DoctorRegistration,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Doctor:
    doctor = _get_own_doctor(db, current_user)
    for field, value in payload.model_dump().items():
        if field == "document_refs":
            continue
        setattr(doctor, field, value)
    db.commit()
    record_audit(
        db, action="PROVIDER_PROFILE_UPDATE", actor_user_id=current_user.id, actor_role="DOCTOR",
        resource_type="doctor", resource_id=doctor.id,
    )
    db.commit()
    return doctor


@router.post("/me/services", response_model=ServiceOut, status_code=201)
def create_own_service(
    payload: ServiceCreate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> ProviderService:
    doctor = _get_own_doctor(db, current_user)
    try:
        provider_service._ensure_specialties_exist(db, [payload.specialty_slug])
    except ProviderError as err:
        raise _provider_error(err) from None
    service = ProviderService(
        provider_kind="DOCTOR",
        provider_id=doctor.id,
        doctor_id=doctor.id,
        specialty_slug=payload.specialty_slug,
        name_en=payload.name_en,
        name_te=payload.name_te,
        name_hi=payload.name_hi,
        description_en=payload.description_en,
        duration_minutes=payload.duration_minutes,
        consultation_type=payload.consultation_type,
    )
    db.add(service)
    db.flush()
    if payload.price_amount is not None:
        # Provider-declared prices start UNVERIFIED — never shown as verified (spec §7).
        db.add(
            ServicePrice(
                service_id=service.id,
                amount=payload.price_amount,
                currency=payload.price_currency,
                verification_status="UNVERIFIED",
                source="provider_declared",
            )
        )
        db.flush()
    record_audit(
        db, action="SERVICE_CHANGE", actor_user_id=current_user.id, actor_role="DOCTOR",
        resource_type="provider_service", resource_id=service.id, detail="created service",
    )
    db.commit()
    return service


@router.post("/me/services/{service_id}/prices", response_model=ServicePriceOut, status_code=201)
def declare_price(
    service_id: str,
    payload: PriceDeclare,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> ServicePrice:
    doctor = _get_own_doctor(db, current_user)
    service = db.get(ProviderService, service_id)
    if service is None or service.provider_id != doctor.id:
        raise HTTPException(status_code=404, detail="Service not found for this doctor")
    price = ServicePrice(
        service_id=service.id,
        amount=payload.amount,
        currency=payload.currency,
        verification_status="UNVERIFIED",
        source="provider_declared",
    )
    db.add(price)
    db.commit()
    return price


@router.get("/me/availability", response_model=list[AvailabilityRuleOut])
def get_own_availability(
    current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> list:
    doctor = _get_own_doctor(db, current_user)
    return booking_service.list_availability(db, provider_kind="DOCTOR", provider_id=doctor.id)


@router.post("/me/availability", response_model=list[AvailabilityRuleOut], status_code=201)
def set_own_availability(
    rules: list[AvailabilityRule],
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list:
    doctor = _get_own_doctor(db, current_user)
    try:
        created = booking_service.set_availability(
            db, provider_kind="DOCTOR", provider_id=doctor.id, rules=rules
        )
    except BookingError as err:
        raise _provider_error(err) from None
    record_audit(
        db, action="AVAILABILITY_CHANGE", actor_user_id=current_user.id, actor_role="DOCTOR",
        resource_type="doctor", resource_id=doctor.id,
        detail=f"set {len(created)} weekly rules",
    )
    db.commit()
    return created


@router.post("/me/blocks", response_model=BlockOut, status_code=201)
def add_own_block(
    block: BlockCreate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    doctor = _get_own_doctor(db, current_user)
    try:
        row = booking_service.add_block(db, provider_kind="DOCTOR", provider_id=doctor.id, block=block)
    except BookingError as err:
        raise _provider_error(err) from None
    record_audit(
        db, action="AVAILABILITY_CHANGE", actor_user_id=current_user.id, actor_role="DOCTOR",
        resource_type="provider_block", resource_id=row.id, detail=f"block {row.block_date}",
    )
    db.commit()
    return row


# ---------------------------------------------------------------- public availability
# NOTE: registered AFTER the /me/* routes so "me" is never captured as {doctor_id}.

@router.get("/{doctor_id}/availability", response_model=list[DayAvailabilityOut])
def doctor_availability(
    doctor_id: str,
    db: Annotated[Session, Depends(get_db)],
    date: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    days: int = Query(default=1, ge=1, le=30),
) -> list[DayAvailabilityOut]:
    try:
        return booking_service.get_range_availability(
            db, doctor_id=doctor_id, start_date=date, days=days
        )
    except BookingError as err:
        raise _provider_error(err) from None
