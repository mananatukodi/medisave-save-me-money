"""Generic provider search (Phase 3, spec §11): doctors or hospitals in one query."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.provider_service import ProviderError, search_providers

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
def list_providers(
    db: Annotated[Session, Depends(get_db)],
    kind: str = Query(default="doctor", pattern="^(doctor|hospital)$"),
    specialty: str | None = None,
    city: str | None = None,
    consultation_type: str | None = None,
    verification_status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    try:
        return search_providers(
            db, kind=kind, specialty=specialty, city=city,
            consultation_type=consultation_type, verification_status=verification_status,
            limit=limit, offset=offset,
        )
    except ProviderError as err:
        from fastapi import HTTPException

        raise HTTPException(status_code=err.status_code, detail=str(err)) from None
