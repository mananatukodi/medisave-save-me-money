"""Family accounts & caregiver access schemas (Phase 6)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.family import RELATIONSHIP_TYPES


class InvitationCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    relationship_type: str = Field(max_length=40)
    invited_email: str | None = Field(default=None, max_length=255)
    member_user_id: str | None = Field(default=None, max_length=36)

    @field_validator("relationship_type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in RELATIONSHIP_TYPES:
            allowed = ", ".join(RELATIONSHIP_TYPES)
            raise ValueError(f"relationship_type must be one of: {allowed}")
        return value


class RelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_user_id: str
    member_user_id: str | None
    display_name: str
    relationship_type: str
    invited_email: str | None
    status: str
    accepted_at: datetime | None
    declined_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InvitationOut(RelationshipOut):
    # Shown exactly once at creation; list endpoints deliberately omit it.
    invitation_token: str | None = None


class ConsentPut(BaseModel):
    scopes: list[str] = Field(min_length=1, max_length=12)
    category_filter: list[str] = Field(default_factory=list, max_length=15)
    purpose: str = Field(default="", max_length=500)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    relationship_id: str
    scopes: str
    category_filter: str
    purpose: str
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime
