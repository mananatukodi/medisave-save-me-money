"""Specialty care catalog endpoints (spec §6, §9)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.healthcare import Specialty
from app.schemas.common import SpecialtyOut
from app.security.deps import CurrentUser

router = APIRouter(prefix="/specialties", tags=["specialties"])


@router.get("", response_model=list[SpecialtyOut])
def list_specialties(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[Specialty]:
    return (
        db.query(Specialty)
        .filter(Specialty.is_active.is_(True))
        .order_by(Specialty.sort_order.asc())
        .all()
    )


@router.get("/{slug}", response_model=SpecialtyOut)
def get_specialty(
    slug: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Specialty:
    specialty = db.query(Specialty).filter(Specialty.slug == slug, Specialty.is_active.is_(True)).first()
    if specialty is None:
        raise HTTPException(status_code=404, detail="Specialty not found")
    return specialty
