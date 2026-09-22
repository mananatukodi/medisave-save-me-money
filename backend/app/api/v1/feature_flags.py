"""Feature flag endpoints (spec §41)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ops import FeatureFlag
from app.schemas.common import FeatureFlagOut, FeatureFlagUpdate
from app.security.deps import CurrentUser, record_audit, require_roles

router = APIRouter(prefix="/feature-flags", tags=["feature-flags"])


@router.get("", response_model=list[FeatureFlagOut])
def list_flags(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[FeatureFlag]:
    return db.query(FeatureFlag).order_by(FeatureFlag.key.asc()).all()


@router.patch("/{key}", response_model=FeatureFlagOut)
def update_flag(
    key: str,
    payload: FeatureFlagUpdate,
    current_user: Annotated[object, Depends(require_roles("SUPER_ADMIN"))],
    db: Annotated[Session, Depends(get_db)],
) -> FeatureFlag:
    flag = db.get(FeatureFlag, key)
    if flag is None:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    flag.is_enabled = payload.is_enabled
    db.commit()
    record_audit(
        db, action="ADMIN_CHANGE", actor_user_id=current_user.id,  # type: ignore[attr-defined]
        actor_role="SUPER_ADMIN", resource_type="feature_flag", resource_id=key,
        detail=f"set is_enabled={payload.is_enabled}",
    )
    db.commit()
    return flag
