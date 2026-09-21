"""Server-side authorization dependencies (spec §4, §36) and audit helper (§37).

Frontend role checks are cosmetic only — every protected operation must pass
through require_current_user / require_roles here.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ops import AuditLog
from app.models.user import User
from app.security.jwt import decode_token, is_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise _unauthorized()
    try:
        payload = decode_token(credentials.credentials)
    except Exception as exc:  # jwt.PyJWTError and subclasses
        raise _unauthorized("Invalid or expired token") from exc
    if not is_access_token(payload):
        raise _unauthorized("Invalid token type")
    user = db.get(User, payload.get("sub", ""))
    if user is None or not user.is_active:
        raise _unauthorized("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed_roles: str) -> Callable[[User], User]:
    """Dependency factory: allow only users holding one of the given roles."""

    def checker(user: CurrentUser) -> User:
        user_role_ids = set(user.role_ids)
        if not user_role_ids.intersection(allowed_roles):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this operation",
            )
        return user

    return checker


def record_audit(
    db: Session,
    *,
    action: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    resource_type: str = "",
    resource_id: str | None = None,
    outcome: str = "SUCCESS",
    ip_address: str | None = None,
    detail: str = "",
) -> None:
    """Append an audit log row. Never include passwords, tokens, OTPs, or secrets."""
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            ip_address=ip_address,
            detail=detail[:2000],
        )
    )


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
