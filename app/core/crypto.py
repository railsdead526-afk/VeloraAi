"""Authenticated encryption for secrets stored at rest.

Third-party credentials (GitHub, Vercel, Railway, Cloudflare, Supabase tokens)
must never be persisted in plaintext. This module provides AES-256-GCM
envelope encryption with support for key rotation.

`CREDENTIAL_ENCRYPTION_KEYS` holds a comma-separated list of urlsafe-base64
encoded 32-byte keys. The first key is the *active* key used for encryption;
every key in the list can decrypt. Rotating a key therefore means prepending a
new key, re-encrypting, and only then removing the old one.

Generate a key with:

    python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12
_KEY_BYTES = 32
_VERSION = b"\x01"


class CryptoError(RuntimeError):
    """Raised when encryption or decryption cannot be performed safely."""


def generate_key() -> str:
    """Return a fresh urlsafe-base64 encoded 256-bit key."""
    return base64.urlsafe_b64encode(os.urandom(_KEY_BYTES)).decode()


def _decode_key(raw: str, *, index: int) -> bytes:
    try:
        key = base64.urlsafe_b64decode(raw.strip().encode())
    except Exception as exc:
        raise CryptoError(
            f"CREDENTIAL_ENCRYPTION_KEYS[{index}] is not valid urlsafe base64"
        ) from exc
    if len(key) != _KEY_BYTES:
        raise CryptoError(
            f"CREDENTIAL_ENCRYPTION_KEYS[{index}] must decode to exactly {_KEY_BYTES} bytes"
        )
    return key


@dataclass(frozen=True)
class SecretBox:
    """Encrypts with the active key, decrypts with any configured key."""

    keys: tuple[bytes, ...]

    @classmethod
    def from_env_value(cls, value: str) -> SecretBox:
        parts = [part for part in (value or "").split(",") if part.strip()]
        if not parts:
            raise CryptoError("CREDENTIAL_ENCRYPTION_KEYS is not configured")
        return cls(keys=tuple(_decode_key(part, index=i) for i, part in enumerate(parts)))

    @property
    def active_key(self) -> bytes:
        return self.keys[0]

    def encrypt(self, plaintext: str, *, associated_data: str | None = None) -> str:
        if not plaintext:
            raise CryptoError("Refusing to encrypt an empty value")
        nonce = os.urandom(_NONCE_BYTES)
        aad = associated_data.encode() if associated_data else None
        ciphertext = AESGCM(self.active_key).encrypt(nonce, plaintext.encode(), aad)
        return base64.urlsafe_b64encode(_VERSION + nonce + ciphertext).decode()

    def decrypt(self, token: str, *, associated_data: str | None = None) -> str:
        try:
            blob = base64.urlsafe_b64decode(token.encode())
        except Exception as exc:
            raise CryptoError("Stored secret is not decodable") from exc
        if len(blob) < 1 + _NONCE_BYTES + 16 or blob[:1] != _VERSION:
            raise CryptoError("Stored secret has an unsupported format")

        nonce = blob[1 : 1 + _NONCE_BYTES]
        ciphertext = blob[1 + _NONCE_BYTES :]
        aad = associated_data.encode() if associated_data else None

        for key in self.keys:
            try:
                return AESGCM(key).decrypt(nonce, ciphertext, aad).decode()
            except (InvalidTag, ValueError):
                continue
        raise CryptoError("Stored secret could not be decrypted with any configured key")

    def needs_rotation(self, token: str, *, associated_data: str | None = None) -> bool:
        """True when `token` decrypts with a non-active key."""
        try:
            blob = base64.urlsafe_b64decode(token.encode())
            nonce = blob[1 : 1 + _NONCE_BYTES]
            ciphertext = blob[1 + _NONCE_BYTES :]
        except Exception:
            return True
        aad = associated_data.encode() if associated_data else None
        try:
            AESGCM(self.active_key).decrypt(nonce, ciphertext, aad)
        except (InvalidTag, ValueError):
            return True
        return False


_box: SecretBox | None = None


def get_secret_box() -> SecretBox:
    """Return the process-wide SecretBox, building it on first use."""
    global _box
    if _box is None:
        from app.core.config import settings

        _box = SecretBox.from_env_value(settings.credential_encryption_keys)
    return _box


def reset_secret_box() -> None:
    """Test hook: force the box to be rebuilt from configuration."""
    global _box
    _box = None
