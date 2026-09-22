"""Application settings loaded from environment variables (12-factor).

Secrets are NEVER hardcoded; see backend/.env.example.
"""

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEDISAVE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    secret_key: str = "dev-only-secret-change-me"  # MUST be overridden via env outside local dev
    database_url: str = "sqlite:///./medisave.db"

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    rate_limit_enabled: bool = True
    # TEST-ONLY: enables the MockAmbulanceProvider for automated tests.
    # Production dispatch requires a real configured provider + feature flag.
    ambulance_test_provider: bool = False
    seed_on_startup: bool = True
    demo_mode: bool = True

    # "none" = rule-based guidance engine only (no external LLM call).
    # Any other value REQUIRES INTEGRATION work before it functions.
    ai_provider: str = "none"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, value: Any) -> Any:
        if isinstance(value, str):
            import json

            return json.loads(value)
        return value

    @property
    def is_production(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
