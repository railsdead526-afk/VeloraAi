"""Tests for session lifecycle, revocation, reset, verification, and lockout."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    needs_rehash,
    verify_password,
)
from app.models.auth import RefreshToken
from app.models.user import User
from app.services.auth_tokens import (
    PURPOSE_PASSWORD_RESET,
    consume_verification_token,
    is_locked_out,
    issue_refresh_token,
    issue_verification_token,
    list_sessions,
    record_login_attempt,
    revoke_all_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
)
from tests.conftest import client

STRONG_PASSWORD = "Str0ng!Passw0rd"


def _register_and_login(email: str) -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": STRONG_PASSWORD})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _make_user(db, email: str) -> User:
    user = User(email=email, hashed_password=get_password_hash(STRONG_PASSWORD), role="free")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #


def test_argon2_hashes_verify_and_are_salted():
    first = get_password_hash(STRONG_PASSWORD)
    second = get_password_hash(STRONG_PASSWORD)
    assert first != second
    assert verify_password(STRONG_PASSWORD, first)
    assert not verify_password("wrong-password", first)
    assert needs_rehash(first) is False


def test_legacy_passlib_pbkdf2_hashes_still_verify():
    """Existing users must not be locked out by the Argon2 migration."""
    legacy = (
        "$pbkdf2-sha256$29000$.p8zBuD839sbYywlREgJIQ$YAUoT7vFWN2TBLakCsGCfJcg0Oii7zh9i/EkeLbY74o"
    )
    assert verify_password("secret123", legacy) is True
    assert verify_password("not-the-password", legacy) is False
    assert needs_rehash(legacy) is True


def test_login_transparently_upgrades_a_legacy_hash(db):
    legacy = (
        "$pbkdf2-sha256$29000$.p8zBuD839sbYywlREgJIQ$YAUoT7vFWN2TBLakCsGCfJcg0Oii7zh9i/EkeLbY74o"
    )
    user = User(email="legacy-hash@example.com", hashed_password=legacy, role="free")
    db.add(user)
    db.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "legacy-hash@example.com", "password": "secret123"},
    )
    assert response.status_code == 200

    db.expire_all()
    refreshed = db.query(User).filter(User.email == "legacy-hash@example.com").one()
    assert not refreshed.hashed_password.startswith("$pbkdf2-sha256$")
    assert verify_password("secret123", refreshed.hashed_password)


# --------------------------------------------------------------------------- #
# Password policy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "password",
    ["short1!A", "alllowercaseletters", "PASSWORD1234", "password", "            a1B"],
)
def test_weak_passwords_are_rejected_at_registration(password):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"weak-{abs(hash(password))}@example.com", "password": password},
    )
    assert response.status_code == 422


def test_strong_password_is_accepted():
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "strong-pw@example.com", "password": "Corr3ct-Horse-Battery"},
    )
    assert response.status_code == 201


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #


def test_login_returns_both_access_and_refresh_tokens():
    payload = _register_and_login("tokens@example.com")
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["expires_in"] == settings.access_token_expire_minutes * 60

    claims = decode_access_token(payload["access_token"])
    assert claims["sub"] == "tokens@example.com"
    assert claims["typ"] == "access"
    assert claims["jti"]


def test_refresh_rotates_the_token_and_invalidates_the_old_one():
    payload = _register_and_login("rotate@example.com")
    original = payload["refresh_token"]

    first = client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert first.status_code == 200
    rotated = first.json()["refresh_token"]
    assert rotated != original

    # The rotated-away token must no longer work.
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert replay.status_code == 401


def test_refresh_token_reuse_destroys_every_session(db):
    user = _make_user(db, "reuse@example.com")
    token = issue_refresh_token(db, user_id=user.id)
    other = issue_refresh_token(db, user_id=user.id)

    assert rotate_refresh_token(db, token=token) is not None
    # Replaying the consumed token is treated as theft.
    assert rotate_refresh_token(db, token=token) is None

    db.expire_all()
    assert list_sessions(db, user_id=user.id) == []
    assert rotate_refresh_token(db, token=other) is None


def test_logout_revokes_the_access_token_immediately():
    payload = _register_and_login("logout@example.com")
    headers = {"Authorization": f"Bearer {payload['access_token']}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": payload["refresh_token"]},
        headers=headers,
    )
    assert logout.status_code == 200

    # Same still-unexpired JWT must now be refused.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": payload["refresh_token"]}
        ).status_code
        == 401
    )


def test_logout_all_sessions_revokes_every_refresh_token(db):
    payload = _register_and_login("logout-all@example.com")
    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    client.post(
        "/api/v1/auth/login", json={"email": "logout-all@example.com", "password": STRONG_PASSWORD}
    )

    response = client.post("/api/v1/auth/logout", json={"all_sessions": True}, headers=headers)
    assert response.status_code == 200
    assert response.json()["sessions_revoked"] >= 2


def test_sessions_endpoint_lists_only_live_sessions():
    payload = _register_and_login("sessions@example.com")
    headers = {"Authorization": f"Bearer {payload['access_token']}"}

    listed = client.get("/api/v1/auth/sessions", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_expired_refresh_token_is_rejected(db):
    user = _make_user(db, "expired-refresh@example.com")
    token = issue_refresh_token(db, user_id=user.id)
    record = db.query(RefreshToken).filter(RefreshToken.user_id == user.id).one()
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    assert rotate_refresh_token(db, token=token) is None


def test_session_cap_evicts_the_oldest_sessions(db, monkeypatch):
    monkeypatch.setattr(settings, "max_active_sessions", 3)
    user = _make_user(db, "cap@example.com")
    for _ in range(5):
        issue_refresh_token(db, user_id=user.id)
    assert len(list_sessions(db, user_id=user.id)) <= 3


def test_revoke_helpers(db):
    user = _make_user(db, "revoke-helpers@example.com")
    token = issue_refresh_token(db, user_id=user.id)
    assert revoke_refresh_token(db, token=token) is True
    assert revoke_refresh_token(db, token=token) is False

    issue_refresh_token(db, user_id=user.id)
    assert revoke_all_sessions(db, user_id=user.id) == 1


def test_access_token_type_confusion_is_rejected():
    token = create_access_token({"sub": "typ@example.com"})
    from app.core.security import TokenError

    with pytest.raises(TokenError):
        decode_access_token(token, expected_type="refresh")


# --------------------------------------------------------------------------- #
# Password reset and change
# --------------------------------------------------------------------------- #


def test_password_reset_never_reveals_whether_an_account_exists():
    known = client.post("/api/v1/auth/password-reset", json={"email": "nobody@example.com"})
    assert known.status_code == 202
    assert known.json() == {"status": "accepted"}


def test_password_reset_flow_updates_the_password_and_kills_sessions(db):
    payload = _register_and_login("reset-flow@example.com")
    user = db.query(User).filter(User.email == "reset-flow@example.com").one()

    token = issue_verification_token(db, user_id=user.id, purpose=PURPOSE_PASSWORD_RESET)
    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "Brand-N3w-Secret"},
    )
    assert response.status_code == 200

    # Old password no longer works, new one does.
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "reset-flow@example.com", "password": STRONG_PASSWORD},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "reset-flow@example.com", "password": "Brand-N3w-Secret"},
        ).status_code
        == 200
    )
    # Pre-existing sessions are gone.
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": payload["refresh_token"]}
        ).status_code
        == 401
    )


def test_reset_token_is_single_use(db):
    user = _make_user(db, "single-use@example.com")
    token = issue_verification_token(db, user_id=user.id, purpose=PURPOSE_PASSWORD_RESET)

    assert consume_verification_token(db, token=token, purpose=PURPOSE_PASSWORD_RESET) is not None
    assert consume_verification_token(db, token=token, purpose=PURPOSE_PASSWORD_RESET) is None


def test_reset_token_expires(db, monkeypatch):
    monkeypatch.setattr(settings, "password_reset_ttl_minutes", 1)
    user = _make_user(db, "expiring-reset@example.com")
    token = issue_verification_token(db, user_id=user.id, purpose=PURPOSE_PASSWORD_RESET)

    from app.models.auth import UserVerificationToken

    record = db.query(UserVerificationToken).filter(UserVerificationToken.user_id == user.id).one()
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    assert consume_verification_token(db, token=token, purpose=PURPOSE_PASSWORD_RESET) is None


def test_issuing_a_new_reset_token_invalidates_the_previous_one(db):
    user = _make_user(db, "reissue@example.com")
    first = issue_verification_token(db, user_id=user.id, purpose=PURPOSE_PASSWORD_RESET)
    second = issue_verification_token(db, user_id=user.id, purpose=PURPOSE_PASSWORD_RESET)

    assert consume_verification_token(db, token=first, purpose=PURPOSE_PASSWORD_RESET) is None
    assert consume_verification_token(db, token=second, purpose=PURPOSE_PASSWORD_RESET) is not None


def test_change_password_requires_the_current_password():
    payload = _register_and_login("change-pw@example.com")
    headers = {"Authorization": f"Bearer {payload['access_token']}"}

    wrong = client.post(
        "/api/v1/auth/password",
        json={"current_password": "Wr0ng!Password", "new_password": "An0ther!Secret"},
        headers=headers,
    )
    assert wrong.status_code == 400

    correct = client.post(
        "/api/v1/auth/password",
        json={"current_password": STRONG_PASSWORD, "new_password": "An0ther!Secret"},
        headers=headers,
    )
    assert correct.status_code == 200


# --------------------------------------------------------------------------- #
# Email verification
# --------------------------------------------------------------------------- #


def test_email_verification_flow(db):
    from app.services.auth_tokens import PURPOSE_EMAIL_VERIFICATION

    client.post(
        "/api/v1/auth/register",
        json={"email": "verify-me@example.com", "password": STRONG_PASSWORD},
    )
    user = db.query(User).filter(User.email == "verify-me@example.com").one()
    assert user.is_email_verified is False

    token = issue_verification_token(db, user_id=user.id, purpose=PURPOSE_EMAIL_VERIFICATION)
    response = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 200

    db.expire_all()
    assert db.query(User).filter(User.email == "verify-me@example.com").one().is_email_verified


def test_verification_rejects_an_unknown_token():
    response = client.post("/api/v1/auth/verify-email", json={"token": "x" * 40})
    assert response.status_code == 400


def test_login_is_blocked_when_verification_is_required(monkeypatch):
    client.post(
        "/api/v1/auth/register",
        json={"email": "unverified@example.com", "password": STRONG_PASSWORD},
    )
    monkeypatch.setattr(settings, "require_email_verification", True)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "unverified@example.com", "password": STRONG_PASSWORD},
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Lockout
# --------------------------------------------------------------------------- #


def test_repeated_failures_trigger_lockout(db, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failed_attempts", 3)
    for _ in range(3):
        record_login_attempt(db, email="locked@example.com", ip="1.2.3.4", successful=False)
    assert is_locked_out(db, email="locked@example.com") is True


def test_lockout_is_scoped_to_the_targeted_email(db, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failed_attempts", 3)
    for _ in range(5):
        record_login_attempt(db, email="victim@example.com", ip="1.2.3.4", successful=False)
    assert is_locked_out(db, email="victim@example.com") is True
    assert is_locked_out(db, email="bystander@example.com") is False


def test_login_endpoint_returns_429_once_locked_out(monkeypatch):
    monkeypatch.setattr(settings, "login_max_failed_attempts", 2)
    client.post(
        "/api/v1/auth/register",
        json={"email": "lockout-api@example.com", "password": STRONG_PASSWORD},
    )
    for _ in range(2):
        client.post(
            "/api/v1/auth/login",
            json={"email": "lockout-api@example.com", "password": "Wr0ng!Password"},
        )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "lockout-api@example.com", "password": STRONG_PASSWORD},
    )
    assert response.status_code == 429
    assert "Retry-After" in response.headers


# --------------------------------------------------------------------------- #
# Account deletion
# --------------------------------------------------------------------------- #


def test_account_deletion_is_a_soft_delete(db):
    payload = _register_and_login("delete-me@example.com")
    headers = {"Authorization": f"Bearer {payload['access_token']}"}

    response = client.delete("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    db.expire_all()
    # The row survives for audit and billing reconciliation.
    tombstoned = db.query(User).filter(User.email.like("deleted+%@velora.invalid")).one()
    assert tombstoned.deleted_at is not None
    assert tombstoned.is_active is False

    # The token no longer authenticates, and the address can be reused.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"email": "delete-me@example.com", "password": STRONG_PASSWORD},
        ).status_code
        == 201
    )
