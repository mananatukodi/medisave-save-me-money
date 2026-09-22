"""Admin verification workflow (Phase 3, spec §2, §14, §16) — SUPER_ADMIN only.

Every decision writes an immutable verification-history row AND an audit entry.
SUSPENDED providers never appear in verified search results.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.providers import (
    Doctor,
    DoctorVerification,
    Hospital,
    HospitalVerification,
)
from app.schemas.providers import (
    DoctorPublic,
    DoctorVerificationDecision,
    HospitalPublic,
    HospitalVerificationDecision,
    VerificationHistoryOut,
)
from app.security.deps import CurrentUser, record_audit, require_roles
from app.services.provider_service import (
    ProviderError,
    decide_doctor_verification,
    decide_hospital_verification,
)

router = APIRouter(
    prefix="/admin/verifications",
    tags=["admin-verifications"],
    dependencies=[Depends(require_roles("SUPER_ADMIN"))],
)


class QueueDoctorRow(DoctorPublic):
    registration_number: str = ""
    registration_council: str = ""


@router.get("/doctors", response_model=list[QueueDoctorRow])
def doctor_queue(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None),
) -> list[Doctor]:
    query = db.query(Doctor).order_by(Doctor.created_at.asc())
    if status:
        query = query.filter(Doctor.verification_status == status)
    return query.limit(100).all()


@router.get("/hospitals", response_model=list[HospitalPublic])
def hospital_queue(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None),
) -> list[Hospital]:
    query = db.query(Hospital).order_by(Hospital.created_at.asc())
    if status:
        query = query.filter(Hospital.verification_status == status)
    return query.limit(100).all()


@router.get("/doctors/{doctor_id}/history", response_model=list[VerificationHistoryOut])
def doctor_history(doctor_id: str, db: Annotated[Session, Depends(get_db)]) -> list:
    return (
        db.query(DoctorVerification)
        .filter(DoctorVerification.doctor_id == doctor_id)
        .order_by(DoctorVerification.created_at.desc())
        .all()
    )


@router.get("/hospitals/{hospital_id}/history", response_model=list[VerificationHistoryOut])
def hospital_history(hospital_id: str, db: Annotated[Session, Depends(get_db)]) -> list:
    return (
        db.query(HospitalVerification)
        .filter(HospitalVerification.hospital_id == hospital_id)
        .order_by(HospitalVerification.created_at.desc())
        .all()
    )


@router.post("/doctors/{doctor_id}/decision", response_model=DoctorPublic)
def doctor_decision(
    doctor_id: str,
    payload: DoctorVerificationDecision,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Doctor:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Doctor not found")
    try:
        doctor = decide_doctor_verification(db, doctor, payload, admin_user_id=admin.id)
    except ProviderError as err:
        from fastapi import HTTPException

        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db, action="VERIFICATION_DECISION", actor_user_id=admin.id, actor_role="SUPER_ADMIN",
        resource_type="doctor", resource_id=doctor.id,
        detail=f"-> {payload.new_status}: {payload.decision_note[:200]}",
    )
    db.commit()
    return doctor


@router.post("/hospitals/{hospital_id}/decision", response_model=HospitalPublic)
def hospital_decision(
    hospital_id: str,
    payload: HospitalVerificationDecision,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Hospital:
    hospital = db.get(Hospital, hospital_id)
    if hospital is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Hospital not found")
    try:
        hospital = decide_hospital_verification(db, hospital, payload, admin_user_id=admin.id)
    except ProviderError as err:
        from fastapi import HTTPException

        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db, action="VERIFICATION_DECISION", actor_user_id=admin.id, actor_role="SUPER_ADMIN",
        resource_type="hospital", resource_id=hospital.id,
        detail=f"-> {payload.new_status}: {payload.decision_note[:200]}",
    )
    db.commit()
    return hospital
