"""AI Health Assistant endpoints (spec §10, §11).

Every request passes the full safety pipeline: consent gate → emergency
screening → intent classification → guidance → safety validation → audit.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.engine import PipelineContext, run_pipeline
from app.db.session import get_db
from app.models.ai import AIEvent, AIMessage, AISession
from app.models.consent import Consent
from app.models.ops import FeatureFlag
from app.security.deps import CurrentUser, record_audit

router = APIRouter(prefix="/ai", tags=["ai"])


class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    language: str = Field(default="te", pattern="^(te|en|hi)$")


class NavigationAction(BaseModel):
    label_en: str
    label_te: str
    label_hi: str
    route: str


class AIChatResponse(BaseModel):
    session_id: str
    intent: str
    urgency: str
    message: str
    disclaimer: str
    red_flags: list[str]
    recommended_actions: list[str]
    navigation: list[NavigationAction]
    requires_human_review: bool
    confidence: float


def has_active_ai_consent(db: Session, user_id: str) -> bool:
    rows = (
        db.query(Consent)
        .filter(
            Consent.user_id == user_id,
            Consent.consent_type == "AI_ACCESS",
            Consent.revoked_at.is_(None),
        )
        .all()
    )
    now = datetime.now(UTC)
    return any(row.expires_at is None or row.expires_at > now for row in rows)


def _flag_enabled(db: Session, key: str) -> bool:
    flag = db.get(FeatureFlag, key)
    return bool(flag and flag.is_enabled)


def _get_or_create_session(
    db: Session, session_id: str | None, user_id: str, language: str
) -> AISession:
    if session_id:
        session = db.get(AISession, session_id)
        if session is None or session.user_id != user_id or not session.is_active:
            raise HTTPException(status_code=404, detail="AI session not found")
        return session
    session = AISession(user_id=user_id, language=language)
    db.add(session)
    db.flush()
    return session


@router.post("/chat", response_model=AIChatResponse)
def chat(
    payload: AIChatRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> AIChatResponse:
    if not _flag_enabled(db, "AI_ENABLED"):
        raise HTTPException(status_code=503, detail="AI assistant is disabled by feature flag")

    consent_active = has_active_ai_consent(db, current_user.id)
    session = _get_or_create_session(db, payload.session_id, current_user.id, payload.language)

    # Persist the user's message before processing.
    db.add(AIMessage(session_id=session.id, role="user", content=payload.message))

    try:
        result = run_pipeline(
            PipelineContext(
                user_id=current_user.id,
                language=payload.language,
                message=payload.message,
                session_id=session.id,
                consent_active=consent_active,
            )
        )
    except PermissionError:
        # Consent gate: log and return a structured, actionable error (spec §11, §30).
        record_audit(
            db,
            action="AI_CONSENT_BLOCKED",
            actor_user_id=current_user.id,
            resource_type="ai_session",
            resource_id=session.id,
            outcome="DENIED",
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="AI_ACCESS consent is required. Grant consent to use the assistant.",
        ) from None

    # Persist the assistant message + audit event.
    db.add(
        AIMessage(
            session_id=session.id,
            role="assistant",
            content=result.message,
            intent=result.intent,
            urgency=result.urgency,
            safety_flagged=result.requires_human_review,
        )
    )
    db.add(
        AIEvent(
            user_id=current_user.id,
            session_id=session.id,
            event_type="AI_RESPONSE",
            intent=result.intent,
            urgency=result.urgency,
            detail=f"red_flags={result.red_flags}",
        )
    )
    if result.urgency == "EMERGENCY":
        db.add(
            AIEvent(
                user_id=current_user.id,
                session_id=session.id,
                event_type="EMERGENCY_SCREENED",
                intent=result.intent,
                urgency=result.urgency,
                detail="emergency signals detected in user message",
            )
        )
    record_audit(
        db,
        action="AI_INTERACTION",
        actor_user_id=current_user.id,
        resource_type="ai_session",
        resource_id=session.id,
        detail=f"intent={result.intent} urgency={result.urgency}",
    )
    db.commit()

    return AIChatResponse(
        session_id=session.id,
        intent=result.intent,
        urgency=result.urgency,
        message=result.message,
        disclaimer=result.disclaimer,
        red_flags=result.red_flags,
        recommended_actions=result.recommended_actions,
        navigation=[
            NavigationAction(
                label_en=nav.label_en, label_te=nav.label_te, label_hi=nav.label_hi, route=nav.route
            )
            for nav in result.navigation
        ],
        requires_human_review=result.requires_human_review,
        confidence=result.confidence,
    )
