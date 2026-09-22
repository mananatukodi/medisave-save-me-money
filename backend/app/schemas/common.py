"""Consent, specialty, feature-flag, and admin schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.consent import CONSENT_TYPES


class ConsentCreate(BaseModel):
    consent_type: str = Field(description="One of: " + ", ".join(CONSENT_TYPES))
    purpose: str = Field(min_length=4, max_length=500)
    data_scope: str = Field(default="basic_profile", max_length=200)
    recipient: str = Field(default="MEDISAVE_AI", max_length=120)
    duration_days: int | None = Field(default=None, ge=1, le=3650)


class ConsentOut(BaseModel):
    id: str
    consent_type: str
    purpose: str
    data_scope: str
    recipient: str
    granted_at: datetime
    revoked_at: datetime | None
    expires_at: datetime | None
    is_active: bool

    model_config = {"from_attributes": True}


class ConsentRevoke(BaseModel):
    reason: str = Field(default="", max_length=300)


class SpecialtyServiceOut(BaseModel):
    code: str
    name_en: str
    name_te: str
    name_hi: str
    description_en: str

    model_config = {"from_attributes": True}


class SpecialtyOut(BaseModel):
    slug: str
    name_en: str
    name_te: str
    name_hi: str
    icon: str
    description_en: str
    services: list[SpecialtyServiceOut] = []

    model_config = {"from_attributes": True}


class FeatureFlagOut(BaseModel):
    key: str
    description: str
    is_enabled: bool

    model_config = {"from_attributes": True}


class FeatureFlagUpdate(BaseModel):
    is_enabled: bool


class AuditLogOut(BaseModel):
    id: str
    actor_user_id: str | None
    actor_role: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    created_at: datetime

    model_config = {"from_attributes": True}
