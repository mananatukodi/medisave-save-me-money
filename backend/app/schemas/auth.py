"""Auth and user schemas."""

from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: str | None = Field(default=None, max_length=20)
    primary_language: str = Field(default="te", pattern="^(te|en|hi)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = settings.access_token_expire_minutes * 60


class UserOut(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    phone_number: str | None
    primary_language: str
    roles: list[str] = Field(validation_alias="role_ids")
    is_active: bool

    model_config = {"from_attributes": True}
