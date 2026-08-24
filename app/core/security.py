"""Password hashing and JWT issuance.

Passwords use Argon2id. Hashes produced by the previous passlib
`pbkdf2_sha256` scheme still verify, and are transparently upgraded to Argon2id
on the next successful login (see `needs_rehash`).

Access tokens are short-lived JWTs carrying a `jti` so they can be revoked.
Refresh tokens are opaque high-entropy strings stored only as SHA-256 digests;
see `app/services/auth_tokens.py`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from app.core.config import settings

TOKEN_TYPE_ACCESS = "access"  # noqa: S105 - a token type label, not a secret
TOKEN_TYPE_REFRESH = "refresh"  # noqa: S105 - a token type label, not a secret

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

_PBKDF2_PREFIX = "$pbkdf2-sha256$"


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or of the wrong type."""


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #


def _ab64_decode(value: str) -> bytes:
    """Decode passlib's adapted base64 (``.`` instead of ``+``, no padding)."""
    data = value.replace(".", "+")
    return base64.b64decode(data + "=" * (-len(data) % 4))


def _verify_legacy_pbkdf2(password: str, hashed: str) -> bool:
    try:
        _, scheme, rounds, salt, checksum = hashed.split("$")
        if scheme != "pbkdf2-sha256":
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            _ab64_decode(salt),
            int(rounds),
            dklen=len(_ab64_decode(checksum)),
        )
        return hmac.compare_digest(derived, _ab64_decode(checksum))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    if hashed_password.startswith(_PBKDF2_PREFIX):
        return _verify_legacy_pbkdf2(plain_password, hashed_password)
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A hash of an unguessable value, computed once per process."""
    return _hasher.hash(secrets.token_urlsafe(32))


def verify_password_dummy(plain_password: str) -> bool:
    """Spend the same work as a real verification, and always fail.

    Argon2 is deliberately expensive - measured at roughly 90 ms here. Skipping
    it when no account matches made an unknown address answer in 9 ms and a
    known one in 114 ms, so a single request revealed whether an email was
    registered. Callers must run this on the account-not-found branch so both
    outcomes cost the same.
    """
    try:
        _hasher.verify(_dummy_hash(), plain_password or "")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return False


def needs_rehash(hashed_password: str) -> bool:
    """True when the stored hash should be upgraded after a successful login."""
    if hashed_password.startswith(_PBKDF2_PREFIX):
        return True
    try:
        return _hasher.check_needs_rehash(hashed_password)
    except InvalidHashError:
        return True


# --------------------------------------------------------------------------- #
# Opaque tokens (refresh, password reset, email verification)
# --------------------------------------------------------------------------- #


def generate_opaque_token(num_bytes: int = 48) -> str:
    return secrets.token_urlsafe(num_bytes)


def hash_opaque_token(token: str) -> str:
    """Digest used for storage. Tokens are high entropy, so SHA-256 is correct here."""
    return hashlib.sha256(token.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# JWT access tokens
# --------------------------------------------------------------------------- #


def new_jti() -> str:
    return uuid4().hex


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
    *,
    jti: str | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {
        **data,
        "iat": now,
        "nbf": now,
        "exp": expire,
        "jti": jti or new_jti(),
        "typ": TOKEN_TYPE_ACCESS,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str, *, expected_type: str = TOKEN_TYPE_ACCESS) -> dict[str, Any]:
    """Decode and validate a JWT. Raises `TokenError` on any problem."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            leeway=timedelta(seconds=10),
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Token is not valid") from exc

    token_type = payload.get("typ", TOKEN_TYPE_ACCESS)
    if token_type != expected_type:
        raise TokenError("Unexpected token type")
    return payload
