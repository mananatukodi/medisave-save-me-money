"""Phase 5 schemas: health records, files, shares, signed URLs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.vault import RECORD_CATEGORIES, SHARE_SCOPES


class HealthRecordCreate(BaseModel):
    category: str
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(default="", max_length=4000)
    record_date: str = Field(default="", max_length=10)  # ISO YYYY-MM-DD when known
    provider_id: str | None = None
    hospital_id: str | None = None

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str) -> str:
        if value not in RECORD_CATEGORIES:
            raise ValueError(f"category must be one of {RECORD_CATEGORIES}")
        return value


class HealthRecordUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    record_date: str | None = Field(default=None, max_length=10)
    category: str | None = None

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str | None) -> str | None:
        if value is not None and value not in RECORD_CATEGORIES:
            raise ValueError(f"category must be one of {RECORD_CATEGORIES}")
        return value


class StoredFileOut(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    storage_provider: str
    upload_status: str
    scan_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HealthRecordOut(BaseModel):
    id: str
    patient_id: str
    category: str
    title: str
    description: str
    record_date: str
    provider_id: str | None
    hospital_id: str | None
    source: str
    status: str
    file: StoredFileOut | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ShareCreate(BaseModel):
    record_id: str
    grantee_user_id: str
    grantee_type: str = Field(default="DOCTOR")
    scope: str = Field(default="VIEW_RECORD")
    category_filter: str = Field(default="", max_length=400)
    purpose: str = Field(default="", max_length=1000)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, value: str) -> str:
        if value not in SHARE_SCOPES:
            raise ValueError(f"scope must be one of {SHARE_SCOPES}")
        return value


class ShareOut(BaseModel):
    id: str
    record_id: str
    grantee_user_id: str
    grantee_type: str
    scope: str
    category_filter: str
    purpose: str
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DownloadUrlOut(BaseModel):
    url: str
    expires_at: str
    ttl_seconds: int
    filename: str
    mime_type: str
    scan_status: str


class VaultEventOut(BaseModel):
    id: str
    record_id: str
    actor_user_id: str | None
    action: str
    result: str
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
