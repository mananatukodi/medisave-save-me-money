"""User profile endpoints (spec §5 module 2)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import UserOut
from app.security.deps import CurrentUser
from app.security.hashing import hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone_number: str | None = Field(default=None, max_length=20)
    primary_language: str | None = Field(default=None, pattern="^(te|en|hi)$")


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/me", response_model=UserOut)
def get_profile(current_user: CurrentUser) -> User:
    return current_user


@router.patch("/me", response_model=UserOut)
def update_profile(
    payload: ProfileUpdate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if payload.full_name is not None:
        current_user.full_name = payload.full_name.strip()
    if payload.phone_number is not None:
        current_user.phone_number = payload.phone_number
    if payload.primary_language is not None:
        current_user.primary_language = payload.primary_language
    db.commit()
    return current_user


@router.post("/me/password")
def change_password(
    payload: PasswordChange,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "updated"}
