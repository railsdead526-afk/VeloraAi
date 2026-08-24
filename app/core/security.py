from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


def _jwt_secret() -> str:
    if settings.secret_key:
        return settings.secret_key
    if settings.is_production:
        raise RuntimeError("SECRET_KEY must be configured before issuing tokens in production")
    return "velora-non-production-test-secret"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
):
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, _jwt_secret(), algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, _jwt_secret(), algorithms=[settings.algorithm])
