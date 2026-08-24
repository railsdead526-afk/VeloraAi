from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.integration import SUPPORTED_PROVIDERS


class IntegrationCreate(BaseModel):
    provider: str = Field(..., max_length=32)
    secret: str = Field(..., min_length=8, max_length=4096)
    display_name: str | None = Field(default=None, max_length=120)
    scopes: str | None = Field(default=None, max_length=512)

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError(f"provider must be one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}")
        return normalized

    @field_validator("secret")
    @classmethod
    def _clean_secret(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("secret must not be empty")
        return cleaned


class IntegrationResponse(BaseModel):
    """Never exposes the secret itself, only a masked fingerprint."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    display_name: str | None = None
    secret_fingerprint: str | None = None
    scopes: str | None = None
    status: str
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
