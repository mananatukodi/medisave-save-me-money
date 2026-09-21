"""JWT token creation/verification (access + refresh). Tokens are never logged."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]

ALGORITHM = "HS256"


def _create_token(
    subject: str, token_type: TokenType, expires_delta: timedelta, extra: dict[str, Any] | None = None
) -> tuple[str, str, datetime]:
    jti = str(uuid.uuid4())
    expires_at = datetime.now(UTC) + expires_delta
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "jti": jti,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), jti, expires_at


def create_access_token(user_id: str, roles: list[str]) -> str:
    return _create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        {"roles": roles},
    )[0]


def create_refresh_token(user_id: str) -> str:
    return _create_token(user_id, "refresh", timedelta(days=settings.refresh_token_expire_days))[0]


def decode_token(token: str) -> dict[str, Any]:
    """Raises jwt.InvalidTokenError (expired/invalid/signature) on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def is_refresh_token(payload: dict[str, Any]) -> bool:
    return payload.get("type") == "refresh"


def is_access_token(payload: dict[str, Any]) -> bool:
    return payload.get("type") == "access"
