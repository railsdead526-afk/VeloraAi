"""The regression suite for the tenant-isolation failure this refactor fixed.

Before per-user credentials existed, every tool read `os.environ`, so any user
who triggered a GitHub tool authenticated as the operator. These tests exist to
make that impossible to reintroduce silently.
"""

import pytest

from app.core.config import settings
from app.core.crypto import generate_key, reset_secret_box
from app.models.user import User
from app.services.credential_service import (
    CredentialError,
    CredentialNotFound,
    delete_credential,
    get_secret,
    list_integrations,
    rotate_encryption,
    store_credential,
)
from app.tools.credentials import resolve_credential, user_credential_scope
from app.tools.errors import ToolProviderError


@pytest.fixture(autouse=True)
def encryption_keys(monkeypatch):
    monkeypatch.setattr(settings, "credential_encryption_keys", generate_key())
    reset_secret_box()
    yield
    reset_secret_box()


def _make_user(db, email: str) -> User:
    user = User(email=email, hashed_password="x", role="pro")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_secret_is_never_stored_in_plaintext(db):
    user = _make_user(db, "cred-owner@example.com")
    integration = store_credential(
        db, user_id=user.id, provider="github", secret="ghp_plaintext_token_value"
    )
    assert "ghp_plaintext_token_value" not in integration.secret_ciphertext
    assert integration.secret_fingerprint == "****alue"
    assert get_secret(db, user_id=user.id, provider="github") == "ghp_plaintext_token_value"


def test_one_user_cannot_read_another_users_credential(db):
    alice = _make_user(db, "alice-cred@example.com")
    bob = _make_user(db, "bob-cred@example.com")

    store_credential(db, user_id=alice.id, provider="github", secret="alice-token")
    store_credential(db, user_id=bob.id, provider="github", secret="bob-token")

    assert get_secret(db, user_id=alice.id, provider="github") == "alice-token"
    assert get_secret(db, user_id=bob.id, provider="github") == "bob-token"

    with pytest.raises(CredentialNotFound):
        get_secret(db, user_id=alice.id, provider="vercel")


def test_ciphertext_transplanted_between_users_is_rejected(db):
    alice = _make_user(db, "alice-transplant@example.com")
    bob = _make_user(db, "bob-transplant@example.com")

    alice_integration = store_credential(
        db, user_id=alice.id, provider="github", secret="alice-secret"
    )
    bob_integration = store_credential(db, user_id=bob.id, provider="github", secret="bob-secret")

    # Simulate an attacker with write access copying Alice's ciphertext onto Bob.
    bob_integration.secret_ciphertext = alice_integration.secret_ciphertext
    db.commit()

    with pytest.raises(CredentialError):
        get_secret(db, user_id=bob.id, provider="github")

    db.refresh(bob_integration)
    assert bob_integration.status == "invalid"


def test_replacing_a_credential_overwrites_rather_than_duplicates(db):
    user = _make_user(db, "rotate-cred@example.com")
    store_credential(db, user_id=user.id, provider="github", secret="first-token")
    store_credential(db, user_id=user.id, provider="github", secret="second-token")

    integrations = list_integrations(db, user_id=user.id)
    assert len(integrations) == 1
    assert get_secret(db, user_id=user.id, provider="github") == "second-token"


def test_unsupported_provider_is_rejected(db):
    user = _make_user(db, "bad-provider@example.com")
    with pytest.raises(CredentialError):
        store_credential(db, user_id=user.id, provider="dropbox", secret="token")


def test_delete_removes_the_credential(db):
    user = _make_user(db, "delete-cred@example.com")
    store_credential(db, user_id=user.id, provider="supabase", secret="sbp_token")

    assert delete_credential(db, user_id=user.id, provider="supabase") is True
    assert delete_credential(db, user_id=user.id, provider="supabase") is False
    with pytest.raises(CredentialNotFound):
        get_secret(db, user_id=user.id, provider="supabase")


def test_rotation_reencrypts_under_the_new_active_key(db, monkeypatch):
    user = _make_user(db, "rotation@example.com")
    old_key = settings.credential_encryption_keys
    store_credential(db, user_id=user.id, provider="cloudflare", secret="cf-token")

    new_key = generate_key()
    monkeypatch.setattr(settings, "credential_encryption_keys", f"{new_key},{old_key}")
    reset_secret_box()

    assert rotate_encryption(db) == 1
    # Still readable, and now sealed with the active key.
    assert get_secret(db, user_id=user.id, provider="cloudflare") == "cf-token"
    assert rotate_encryption(db) == 0


# --------------------------------------------------------------------------- #
# Context binding
# --------------------------------------------------------------------------- #


def test_tools_refuse_to_run_without_a_bound_user():
    with pytest.raises(ToolProviderError, match="No user credential context"):
        resolve_credential("github")


def test_scope_resolves_the_bound_users_credential(db, monkeypatch):
    user = _make_user(db, "scoped@example.com")
    store_credential(db, user_id=user.id, provider="github", secret="scoped-token")

    monkeypatch.setattr("app.core.database.SessionLocal", lambda: _SessionProxy(db))
    with user_credential_scope(user.id):
        assert resolve_credential("github") == "scoped-token"

    # Binding is released on exit.
    with pytest.raises(ToolProviderError):
        resolve_credential("github")


def test_scope_reports_a_missing_connection_clearly(db, monkeypatch):
    user = _make_user(db, "unconnected@example.com")
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: _SessionProxy(db))

    with (
        user_credential_scope(user.id),
        pytest.raises(ToolProviderError, match="No github credential is connected"),
    ):
        resolve_credential("github")


def test_env_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "operator-wide-token")
    monkeypatch.setattr(settings, "allow_env_tool_credentials", False)
    with pytest.raises(ToolProviderError):
        resolve_credential("github")


def test_env_fallback_never_applies_in_production(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "operator-wide-token")
    monkeypatch.setattr(settings, "allow_env_tool_credentials", True)
    monkeypatch.setattr(settings, "app_env", "production")
    try:
        with pytest.raises(ToolProviderError):
            resolve_credential("github")
    finally:
        monkeypatch.setattr(settings, "app_env", "test")


def test_env_fallback_works_in_development(monkeypatch):
    monkeypatch.setenv("VERCEL_TOKEN", "dev-token")
    monkeypatch.setattr(settings, "allow_env_tool_credentials", True)
    monkeypatch.setattr(settings, "app_env", "development")
    try:
        assert resolve_credential("vercel") == "dev-token"
    finally:
        monkeypatch.setattr(settings, "app_env", "test")


class _SessionProxy:
    """Hands the test's session to code that expects to own its own session."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):  # the caller closes it; the fixture owns the real lifetime
        return None
