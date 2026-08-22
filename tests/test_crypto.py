import base64
import os

import pytest

from app.core.crypto import CryptoError, SecretBox, generate_key


def _box(count: int = 1) -> SecretBox:
    return SecretBox.from_env_value(",".join(generate_key() for _ in range(count)))


def test_roundtrip_returns_original_plaintext():
    box = _box()
    token = box.encrypt("ghp_super_secret_value")
    assert token != "ghp_super_secret_value"
    assert box.decrypt(token) == "ghp_super_secret_value"


def test_ciphertext_is_not_deterministic():
    box = _box()
    assert box.encrypt("same-value") != box.encrypt("same-value")


def test_associated_data_binds_the_ciphertext_to_its_owner():
    box = _box()
    token = box.encrypt("secret", associated_data="user:1|provider:github")

    # The correct binding works.
    assert box.decrypt(token, associated_data="user:1|provider:github") == "secret"

    # Replaying the ciphertext under another user must fail.
    with pytest.raises(CryptoError):
        box.decrypt(token, associated_data="user:2|provider:github")

    # So must replaying it under a different provider.
    with pytest.raises(CryptoError):
        box.decrypt(token, associated_data="user:1|provider:vercel")


def test_tampered_ciphertext_is_rejected():
    box = _box()
    token = box.encrypt("secret")
    raw = bytearray(base64.urlsafe_b64decode(token))
    raw[-1] ^= 0x01
    tampered = base64.urlsafe_b64encode(bytes(raw)).decode()
    with pytest.raises(CryptoError):
        box.decrypt(tampered)


def test_unknown_key_cannot_decrypt():
    written = _box()
    token = written.encrypt("secret")
    with pytest.raises(CryptoError):
        _box().decrypt(token)


def test_retired_keys_still_decrypt_after_rotation():
    old_key = generate_key()
    new_key = generate_key()

    old_box = SecretBox.from_env_value(old_key)
    token = old_box.encrypt("legacy-secret")

    # New key first, old key retained: decryption must keep working.
    rotated = SecretBox.from_env_value(f"{new_key},{old_key}")
    assert rotated.decrypt(token) == "legacy-secret"
    assert rotated.needs_rotation(token) is True

    refreshed = rotated.encrypt("legacy-secret")
    assert rotated.needs_rotation(refreshed) is False


def test_needs_rotation_respects_associated_data():
    box = _box()
    token = box.encrypt("v", associated_data="aad")
    assert box.needs_rotation(token, associated_data="aad") is False
    assert box.needs_rotation(token) is True


def test_empty_plaintext_is_refused():
    with pytest.raises(CryptoError):
        _box().encrypt("")


def test_malformed_configuration_is_rejected():
    with pytest.raises(CryptoError):
        SecretBox.from_env_value("")
    with pytest.raises(CryptoError):
        SecretBox.from_env_value("not-base64!!")
    # Correct base64 but wrong length.
    short = base64.urlsafe_b64encode(os.urandom(16)).decode()
    with pytest.raises(CryptoError):
        SecretBox.from_env_value(short)
