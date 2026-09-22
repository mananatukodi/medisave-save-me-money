"""Authentication endpoints (spec §5 module 1, §36)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import Role, User, UserRole
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.security.deps import client_ip, get_current_user, record_audit
from app.security.hashing import hash_password, verify_password
from app.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    is_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role_ids),
        refresh_token=create_refresh_token(user.id),
    )


def _default_role_assignment(db: Session, user: User, requested_role: str | None) -> None:
    """Only SUPER_ADMIN may grant elevated roles; new users always start as PATIENT."""
    allowed = {"PATIENT"}
    role_id = requested_role if requested_role in allowed else "PATIENT"
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "System role missing; run seed")
    db.add(UserRole(user_id=user.id, role_id=role.id))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        phone_number=payload.phone_number,
        password_hash=hash_password(payload.password),
        primary_language=payload.primary_language,
    )
    db.add(user)
    db.flush()
    _default_role_assignment(db, user, None)
    db.commit()

    record_audit(
        db, action="REGISTER", actor_user_id=user.id, actor_role="PATIENT",
        resource_type="user", resource_id=user.id, ip_address=client_ip(request),
    )
    db.commit()
    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    email = payload.email.lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        record_audit(
            db, action="LOGIN_FAILED", actor_user_id=None, outcome="DENIED",
            ip_address=client_ip(request), detail="Invalid credentials",
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    record_audit(
        db, action="LOGIN", actor_user_id=user.id, actor_role=(user.role_ids[0] if user.role_ids else None),
        resource_type="user", resource_id=user.id, ip_address=client_ip(request),
    )
    db.commit()
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Annotated[Session, Depends(get_db)]):
    try:
        payload_jwt = decode_token(payload.refresh_token)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token") from exc
    if not is_refresh_token(payload_jwt):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
    user = db.get(User, payload_jwt.get("sub", ""))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return _issue_tokens(user)



@router.get("/me", response_model=UserOut)
def me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
