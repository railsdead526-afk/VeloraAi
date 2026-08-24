from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

#: Minimum length aligned with NIST SP 800-63B guidance (length over complexity).
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_COMMON_PASSWORDS = {
    "password",
    "password1",
    "passw0rd",
    "123456789012",
    "qwertyuiop12",
    "administrator",
    "letmeinplease",
    "veloraai12345",
}


def validate_password_strength(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")
    if value.lower() in _COMMON_PASSWORDS:
        raise ValueError("Password is too common")
    if value.strip() != value:
        raise ValueError("Password must not start or end with whitespace")
    classes = sum(
        [
            any(c.islower() for c in value),
            any(c.isupper() for c in value),
            any(c.isdigit() for c in value),
            any(not c.isalnum() for c in value),
        ]
    )
    if classes < 3:
        raise ValueError(
            "Password must combine at least three of: lowercase, uppercase, digits, symbols"
        )
    return value


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        return validate_password_strength(value)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=MAX_PASSWORD_LENGTH)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=16, max_length=256)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, value: str) -> str:
        return validate_password_strength(value)


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, value: str) -> str:
        return validate_password_strength(value)


class EmailVerificationRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=256)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool
    role: str
    email_verified: bool = False
    daily_requests_used: int = 0
    daily_request_limit: int | None = None
    daily_reset_at: datetime | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    user_agent: str | None = None


def next_daily_reset(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)
    day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start + timedelta(days=1)
