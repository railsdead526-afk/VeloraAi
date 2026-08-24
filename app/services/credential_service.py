"""Storage and retrieval of per-user third-party credentials.

Every secret is encrypted with AES-256-GCM before it touches the database, and
the owning `user_id` plus `provider` are bound in as associated data. That
binding means a ciphertext lifted from one row cannot be pasted into another
user's row and still decrypt, which is the property that actually enforces
tenant isolation here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import CryptoError, get_secret_box
from app.models.integration import SUPPORTED_PROVIDERS, UserIntegration

MAX_SECRET_LENGTH = 4096


class CredentialError(RuntimeError):
    """Raised when a credential cannot be stored or retrieved."""


class CredentialNotFound(CredentialError):
    """Raised when the user has not connected the requested provider."""


def normalize_provider(provider: str) -> str:
    value = (provider or "").strip().lower()
    if value not in SUPPORTED_PROVIDERS:
        raise CredentialError(f"Unsupported provider: {provider!r}")
    return value


def _associated_data(user_id: int, provider: str) -> str:
    return f"user:{user_id}|provider:{provider}"


def _fingerprint(secret: str) -> str:
    """Non-reversible display hint, e.g. ``****abcd``."""
    tail = secret[-4:] if len(secret) >= 8 else ""
    return f"****{tail}" if tail else "****"


def store_credential(
    db: Session,
    *,
    user_id: int,
    provider: str,
    secret: str,
    display_name: str | None = None,
    scopes: str | None = None,
    expires_at: datetime | None = None,
    commit: bool = True,
) -> UserIntegration:
    provider = normalize_provider(provider)
    secret = (secret or "").strip()
    if not secret:
        raise CredentialError("Secret must not be empty")
    if len(secret) > MAX_SECRET_LENGTH:
        raise CredentialError("Secret is too long")

    ciphertext = get_secret_box().encrypt(
        secret, associated_data=_associated_data(user_id, provider)
    )

    integration = db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == provider,
        )
    ).scalar_one_or_none()

    if integration is None:
        integration = UserIntegration(user_id=user_id, provider=provider)
        db.add(integration)

    integration.secret_ciphertext = ciphertext
    integration.secret_fingerprint = _fingerprint(secret)
    integration.display_name = (display_name or "").strip()[:120] or None
    integration.scopes = (scopes or "").strip()[:512] or None
    integration.expires_at = expires_at
    integration.status = "active"
    integration.last_error = None

    if commit:
        db.commit()
        db.refresh(integration)
    else:
        db.flush()
    return integration


def get_integration(db: Session, *, user_id: int, provider: str) -> UserIntegration | None:
    provider = normalize_provider(provider)
    return db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == provider,
        )
    ).scalar_one_or_none()


def list_integrations(db: Session, *, user_id: int) -> list[UserIntegration]:
    return list(
        db.execute(
            select(UserIntegration)
            .where(UserIntegration.user_id == user_id)
            .order_by(UserIntegration.provider)
        ).scalars()
    )


def get_secret(db: Session, *, user_id: int, provider: str, touch: bool = True) -> str:
    """Decrypt and return the user's secret for `provider`."""
    provider = normalize_provider(provider)
    integration = get_integration(db, user_id=user_id, provider=provider)
    if integration is None:
        raise CredentialNotFound(
            f"No {provider} credential is connected for this account. "
            f"Connect it under account integrations before using {provider} tools."
        )
    if integration.status != "active":
        raise CredentialError(f"The {provider} credential is {integration.status}")
    if integration.expires_at is not None and integration.expires_at <= datetime.now(UTC):
        integration.status = "expired"
        db.commit()
        raise CredentialError(f"The {provider} credential has expired")

    try:
        secret = get_secret_box().decrypt(
            integration.secret_ciphertext,
            associated_data=_associated_data(user_id, provider),
        )
    except CryptoError as exc:
        integration.status = "invalid"
        integration.last_error = "Secret could not be decrypted"
        db.commit()
        raise CredentialError(
            f"The stored {provider} credential could not be decrypted; reconnect the provider"
        ) from exc

    if touch:
        integration.last_used_at = datetime.now(UTC)
        db.commit()
    return secret


def delete_credential(db: Session, *, user_id: int, provider: str) -> bool:
    integration = get_integration(db, user_id=user_id, provider=provider)
    if integration is None:
        return False
    db.delete(integration)
    db.commit()
    return True


def rotate_encryption(db: Session, *, batch_size: int = 500) -> int:
    """Re-encrypt any credential still sealed with a retired key.

    Run after prepending a new key to `CREDENTIAL_ENCRYPTION_KEYS`, and before
    removing the old one. Returns the number of rows re-encrypted.
    """
    box = get_secret_box()
    rotated = 0
    rows = list(db.execute(select(UserIntegration).limit(batch_size)).scalars())
    for integration in rows:
        aad = _associated_data(integration.user_id, integration.provider)
        if not box.needs_rotation(integration.secret_ciphertext, associated_data=aad):
            continue
        try:
            plaintext = box.decrypt(integration.secret_ciphertext, associated_data=aad)
        except CryptoError:
            integration.status = "invalid"
            integration.last_error = "Secret could not be decrypted during rotation"
            continue
        integration.secret_ciphertext = box.encrypt(plaintext, associated_data=aad)
        rotated += 1
    db.commit()
    return rotated
