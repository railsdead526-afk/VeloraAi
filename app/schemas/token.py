from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - scheme name, not a secret
    expires_in: int = 0
    refresh_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=16, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=512)
    all_sessions: bool = False
