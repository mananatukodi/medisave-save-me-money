"""Consent management endpoints (spec §30 — consent-first)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.consent import CONSENT_TYPES, Consent
from app.schemas.common import ConsentCreate, ConsentOut, ConsentRevoke
from app.security.deps import CurrentUser, record_audit

router = APIRouter(prefix="/consents", tags=["consents"])


@router.get("", response_model=list[ConsentOut])
def list_consents(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[Consent]:
    return (
        db.query(Consent)
        .filter(Consent.user_id == current_user.id)
        .order_by(Consent.granted_at.desc())
        .all()
    )


@router.post("", response_model=ConsentOut, status_code=201)
def grant_consent(
    payload: ConsentCreate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Consent:
    if payload.consent_type not in CONSENT_TYPES:
        allowed = ", ".join(CONSENT_TYPES)
        raise HTTPException(status_code=422, detail=f"consent_type must be one of: {allowed}")
    consent = Consent(
        user_id=current_user.id,
        consent_type=payload.consent_type,
        purpose=payload.purpose,
        data_scope=payload.data_scope,
        recipient=payload.recipient,
        duration_days=payload.duration_days,
        expires_at=(
            datetime.now(UTC) + timedelta(days=payload.duration_days)
            if payload.duration_days
            else None
        ),
    )
    db.add(consent)
    db.commit()
    record_audit(
        db, action="CONSENT_CHANGE", actor_user_id=current_user.id,
        resource_type="consent", resource_id=consent.id,
        detail=f"granted {payload.consent_type} scope={payload.data_scope}",
    )
    db.commit()
    return consent


@router.post("/{consent_id}/revoke", response_model=ConsentOut)
def revoke_consent(
    consent_id: str,
    payload: ConsentRevoke,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Consent:
    consent = db.get(Consent, consent_id)
    if consent is None or consent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Consent not found")
    if consent.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Consent already revoked")
    consent.revoked_at = datetime.now(UTC)
    db.commit()
    record_audit(
        db, action="CONSENT_CHANGE", actor_user_id=current_user.id,
        resource_type="consent", resource_id=consent.id,
        outcome="SUCCESS", detail=f"revoked {consent.consent_type}: {payload.reason[:200]}",
    )
    db.commit()
    return consent
