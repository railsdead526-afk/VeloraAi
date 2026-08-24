"""Refresh token rotation must distinguish theft from two tabs racing.

Rotation plus reuse detection is the defence against a stolen refresh token: if
a token that has already been rotated turns up again, the whole family is torn
down. That is correct for theft, but the same signature is produced by ordinary
use.

Two browser tabs share localStorage and their access tokens expire together, so
both refresh with the same stored token; the loser arrives milliseconds after
the winner. Measured before this change: a user signed in on a phone, a laptop
and a tablet lost all three sessions because two laptop tabs refreshed at once.

A short grace window separates the two. Inside it the loser just gets a 401 and
can retry with the token the winner stored. Outside it - a token replayed
minutes or hours later - the family is still revoked.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.config import settings
from app.models.auth import RefreshToken
from app.models.user import User
from app.services import auth_tokens


@pytest.fixture
def user(db):
    account = User(email="rotation@example.com", hashed_password="hash", role="free")
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _active_sessions(db, user_id: int) -> int:
    return (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .count()
    )


def test_rotation_issues_a_new_token(db, user):
    token = auth_tokens.issue_refresh_token(db, user_id=user.id)
    rotated = auth_tokens.rotate_refresh_token(db, token=token)

    assert rotated is not None
    rotated_user, replacement = rotated
    assert rotated_user.id == user.id
    assert replacement != token
    assert _active_sessions(db, user.id) == 1


def test_a_racing_second_tab_does_not_sign_out_other_devices(db, user):
    """The exact scenario: three devices, two tabs on one of them."""
    auth_tokens.issue_refresh_token(db, user_id=user.id)  # phone
    laptop = auth_tokens.issue_refresh_token(db, user_id=user.id)
    auth_tokens.issue_refresh_token(db, user_id=user.id)  # tablet
    assert _active_sessions(db, user.id) == 3

    winner = auth_tokens.rotate_refresh_token(db, token=laptop)
    loser = auth_tokens.rotate_refresh_token(db, token=laptop)

    assert winner is not None
    assert loser is None, "the losing tab must not receive a second token"
    # Phone, tablet and the laptop's new token all survive.
    assert _active_sessions(db, user.id) == 3


def test_replay_after_the_grace_window_still_revokes_everything(db, user):
    """Theft detection must survive the fix."""
    auth_tokens.issue_refresh_token(db, user_id=user.id)
    stolen = auth_tokens.issue_refresh_token(db, user_id=user.id)

    rotated = auth_tokens.rotate_refresh_token(db, token=stolen)
    assert rotated is not None

    # Age the rotation past the grace window.
    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == auth_tokens.hash_opaque_token(stolen))
        .one()
    )
    record.revoked_at = record.revoked_at - timedelta(
        seconds=settings.refresh_rotation_grace_seconds + 60
    )
    db.commit()

    assert auth_tokens.rotate_refresh_token(db, token=stolen) is None
    assert _active_sessions(db, user.id) == 0, "a genuine replay must revoke the family"


def test_a_logged_out_token_is_not_treated_as_a_race(db, user):
    """Only 'rotated' is benign; an explicit revocation replayed is not."""
    auth_tokens.issue_refresh_token(db, user_id=user.id)
    token = auth_tokens.issue_refresh_token(db, user_id=user.id)

    assert auth_tokens.revoke_refresh_token(db, token=token) is True
    assert auth_tokens.rotate_refresh_token(db, token=token) is None
    assert _active_sessions(db, user.id) == 0


def test_grace_window_is_short(db):
    """Long enough for a slow request, useless to an attacker."""
    assert 0 < settings.refresh_rotation_grace_seconds <= 60


def test_an_unknown_token_never_revokes_anything(db, user):
    auth_tokens.issue_refresh_token(db, user_id=user.id)

    assert auth_tokens.rotate_refresh_token(db, token="not-a-real-token") is None
    assert _active_sessions(db, user.id) == 1
