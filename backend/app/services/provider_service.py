"""Provider registration, verification, and search logic (Phase 3).

Verification rule (spec §1, §2.20): a provider's `verification_status` column is
only ever changed through `decide_doctor_verification` / `decide_hospital_verification`,
each of which writes an immutable verification-history row AND an audit log entry.
Nothing here fabricates provider data.
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.healthcare import Specialty
from app.models.providers import (
    CONSULTATION_TYPES,
    VERIFICATION_STATES,
    Doctor,
    DoctorVerification,
    Hospital,
    HospitalVerification,
    ProviderSpecialtyLink,
)
from app.schemas.providers import (
    DoctorPublic,
    DoctorRegistration,
    DoctorVerificationDecision,
    HospitalPublic,
    HospitalRegistration,
    HospitalVerificationDecision,
)


class ProviderError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _ensure_specialties_exist(db: Session, slugs: list[str]) -> None:
    for slug in slugs:
        if db.query(Specialty).filter(Specialty.slug == slug).first() is None:
            raise ProviderError(f"Unknown specialty: {slug}", 422)


# ---------------------------------------------------------------- doctor

def register_doctor(db: Session, payload: DoctorRegistration, user_id: str | None = None) -> Doctor:
    _ensure_specialties_exist(db, [payload.specialty_slug])
    doctor = Doctor(
        user_id=user_id,
        full_name=payload.full_name.strip(),
        gender=payload.gender,
        specialty_slug=payload.specialty_slug,
        sub_specialty=payload.sub_specialty,
        qualifications=payload.qualifications,
        registration_number=payload.registration_number,
        registration_council=payload.registration_council,
        years_experience=payload.years_experience,
        languages=payload.languages,
        consultation_modes=payload.consultation_modes,
        about=payload.about,
        phone_number=payload.phone_number,
        address_line=payload.address_line,
        city=payload.city,
        state=payload.state,
        pincode=payload.pincode,
        hospital_id=payload.hospital_id,
        verification_status="PENDING",
    )
    db.add(doctor)
    db.flush()
    db.add(
        ProviderSpecialtyLink(
            provider_kind="DOCTOR", provider_id=doctor.id, specialty_slug=payload.specialty_slug
        )
    )
    db.flush()
    return doctor


def decide_doctor_verification(
    db: Session,
    doctor: Doctor,
    decision: DoctorVerificationDecision,
    admin_user_id: str,
) -> Doctor:
    if doctor.verification_status == decision.new_status:
        raise ProviderError(f"Doctor is already {decision.new_status}", 409)
    db.add(
        DoctorVerification(
            doctor_id=doctor.id,
            previous_status=doctor.verification_status,
            new_status=decision.new_status,
            decided_by_user_id=admin_user_id,
            decision_note=decision.decision_note,
            document_refs=",".join(decision.document_refs),
        )
    )
    doctor.verification_status = decision.new_status
    return doctor


def search_doctors(
    db: Session,
    *,
    specialty: str | None = None,
    city: str | None = None,
    consultation_type: str | None = None,
    verification_status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Doctor]:
    query = db.query(Doctor).filter(Doctor.is_active.is_(True))
    if specialty:
        query = query.filter(Doctor.specialty_slug == specialty)
    if city:
        query = query.filter(Doctor.city.ilike(f"%{city}%"))
    if verification_status:
        if verification_status not in VERIFICATION_STATES:
            raise ProviderError(f"verification_status must be one of {VERIFICATION_STATES}", 422)
        query = query.filter(Doctor.verification_status == verification_status)
    if consultation_type:
        if consultation_type not in CONSULTATION_TYPES:
            raise ProviderError(f"consultation_type must be one of {CONSULTATION_TYPES}", 422)
        # Match against the CSV modes column (IN_PERSON,VIDEO,...).
        query = query.filter(Doctor.consultation_modes.ilike(f"%{consultation_type}%"))
    return (
        query.order_by(Doctor.created_at.desc())
        .offset(offset)
        .limit(min(limit, 100))
        .all()
    )


# ---------------------------------------------------------------- hospital

def register_hospital(
    db: Session, payload: HospitalRegistration, admin_user_id: str | None = None
) -> Hospital:
    departments = [d.strip() for d in payload.departments.split(",") if d.strip()]
    _ensure_specialties_exist(db, departments)
    hospital = Hospital(
        admin_user_id=admin_user_id,
        name=payload.name.strip(),
        hospital_type=payload.hospital_type,
        registration_number=payload.registration_number,
        address_line=payload.address_line,
        city=payload.city,
        state=payload.state,
        pincode=payload.pincode,
        phone_number=payload.phone_number,
        email=payload.email,
        departments=payload.departments,
        services_summary=payload.services_summary,
        emergency_available=payload.emergency_available,
        insurance_info=payload.insurance_info,
        verification_status="PENDING",
    )
    db.add(hospital)
    db.flush()
    for slug in departments:
        db.add(
            ProviderSpecialtyLink(provider_kind="HOSPITAL", provider_id=hospital.id, specialty_slug=slug)
        )
    db.flush()
    return hospital


def decide_hospital_verification(
    db: Session,
    hospital: Hospital,
    decision: HospitalVerificationDecision,
    admin_user_id: str,
) -> Hospital:
    if hospital.verification_status == decision.new_status:
        raise ProviderError(f"Hospital is already {decision.new_status}", 409)
    db.add(
        HospitalVerification(
            hospital_id=hospital.id,
            previous_status=hospital.verification_status,
            new_status=decision.new_status,
            decided_by_user_id=admin_user_id,
            decision_note=decision.decision_note,
            document_refs=",".join(decision.document_refs),
        )
    )
    hospital.verification_status = decision.new_status
    return hospital


def search_hospitals(
    db: Session,
    *,
    specialty: str | None = None,
    city: str | None = None,
    verification_status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Hospital]:
    query = db.query(Hospital).filter(Hospital.is_active.is_(True))
    if specialty:
        query = query.filter(Hospital.departments.ilike(f"%{specialty}%"))
    if city:
        query = query.filter(Hospital.city.ilike(f"%{city}%"))
    if verification_status:
        if verification_status not in VERIFICATION_STATES:
            raise ProviderError(f"verification_status must be one of {VERIFICATION_STATES}", 422)
        query = query.filter(Hospital.verification_status == verification_status)
    return query.order_by(Hospital.created_at.desc()).offset(offset).limit(min(limit, 100)).all()


def search_providers(
    db: Session,
    *,
    kind: str,
    specialty: str | None,
    city: str | None,
    consultation_type: str | None,
    verification_status: str | None,
    limit: int,
    offset: int,
) -> dict:
    kind = (kind or "doctor").lower()
    if kind == "doctor":
        return {
            "kind": "doctor",
            "items": [
                DoctorPublic.model_validate(d)
                for d in search_doctors(
                    db, specialty=specialty, city=city,
                    consultation_type=consultation_type,
                    verification_status=verification_status, limit=limit, offset=offset,
                )
            ],
        }
    if kind == "hospital":
        return {
            "kind": "hospital",
            "items": [
                HospitalPublic.model_validate(h)
                for h in search_hospitals(
                    db, specialty=specialty, city=city,
                    verification_status=verification_status, limit=limit, offset=offset,
                )
            ],
        }
    raise ProviderError("kind must be 'doctor' or 'hospital'", 422)


# ---------------------------------------------------------------- multi-specialty

def link_provider_specialty(
    db: Session, *, provider_kind: str, provider_id: str, specialty_slug: str
) -> None:
    _ensure_specialties_exist(db, [specialty_slug])
    exists = (
        db.query(ProviderSpecialtyLink)
        .filter(
            ProviderSpecialtyLink.provider_kind == provider_kind,
            ProviderSpecialtyLink.provider_id == provider_id,
            ProviderSpecialtyLink.specialty_slug == specialty_slug,
        )
        .first()
    )
    if exists is None:
        db.add(
            ProviderSpecialtyLink(
                provider_kind=provider_kind, provider_id=provider_id, specialty_slug=specialty_slug
            )
        )
        db.flush()


def provider_specialty_slugs(db: Session, *, provider_kind: str, provider_id: str) -> list[str]:
    rows = (
        db.query(ProviderSpecialtyLink)
        .filter(
            ProviderSpecialtyLink.provider_kind == provider_kind,
            ProviderSpecialtyLink.provider_id == provider_id,
        )
        .all()
    )
    return sorted(row.specialty_slug for row in rows)


def or_condition_for_active_providers():
    """Helper for any code needing a combined active filter."""
    return or_(Doctor.is_active.is_(True), Hospital.is_active.is_(True))
