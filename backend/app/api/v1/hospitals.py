"""Hospital registration, discovery, and admin self-service (Phase 3, spec §3, §11, §14)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.providers import Hospital
from app.models.user import User
from app.schemas.providers import HospitalPublic, HospitalRegistration
from app.security.deps import record_audit, require_roles
from app.services.provider_service import ProviderError, register_hospital, search_hospitals

router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@router.get("", response_model=list[HospitalPublic])
def list_hospitals(
    db: Annotated[Session, Depends(get_db)],
    specialty: str | None = None,
    city: str | None = None,
    verification_status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Hospital]:
    try:
        return search_hospitals(
            db, specialty=specialty, city=city,
            verification_status=verification_status, limit=limit, offset=offset,
        )
    except ProviderError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None


@router.get("/{hospital_id}", response_model=HospitalPublic)
def get_hospital(hospital_id: str, db: Annotated[Session, Depends(get_db)]) -> Hospital:
    hospital = db.get(Hospital, hospital_id)
    if hospital is None or not hospital.is_active:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return hospital


@router.post("/register", response_model=HospitalPublic, status_code=201)
def register(
    payload: HospitalRegistration,
    current_user: Annotated[User, Depends(require_roles("HOSPITAL_ADMIN"))],
    db: Annotated[Session, Depends(get_db)],
) -> Hospital:
    try:
        hospital = register_hospital(db, payload, admin_user_id=current_user.id)
    except ProviderError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
    record_audit(
        db, action="PROVIDER_REGISTER", actor_user_id=current_user.id, actor_role="HOSPITAL_ADMIN",
        resource_type="hospital", resource_id=hospital.id, detail=hospital.name,
    )
    db.commit()
    return hospital
