"""Timestamps must behave identically on SQLite and PostgreSQL.

PostgreSQL round-trips `timestamptz` as an aware datetime; SQLite has no
timezone type and returns a naive one. Comparing naive to aware raises
TypeError, so the divergence shows up as a crash in whichever environment the
author did not test.

Three services had each grown a private `_as_aware()` helper to patch this at
the call site. `UtcDateTime` fixes it once at the column boundary, which is the
only place it cannot be forgotten.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import StatementError

from app.models.auth import RefreshToken
from app.models.billing import Payment, Subscription
from app.models.user import User


def _make_user(db, email: str) -> User:
    user = User(email=email, hashed_password="x", role="free")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_timestamps_come_back_timezone_aware(db):
    user = _make_user(db, "tz-aware@example.com")
    expires = datetime.now(UTC) + timedelta(days=1)
    db.add(RefreshToken(user_id=user.id, token_hash="a" * 64, expires_at=expires))
    db.commit()
    db.expire_all()

    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == "a" * 64).one()
    assert stored.expires_at.tzinfo is not None
    assert stored.issued_at.tzinfo is not None


def test_a_stored_timestamp_compares_against_now_without_crashing(db):
    """The exact operation that used to raise TypeError on SQLite."""
    user = _make_user(db, "tz-compare@example.com")
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash="b" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    db.commit()
    db.expire_all()

    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == "b" * 64).one()
    assert stored.expires_at > datetime.now(UTC)


def test_a_naive_datetime_is_refused_rather_than_guessed(db):
    """Assuming an offset silently stores the wrong instant."""
    user = _make_user(db, "tz-naive@example.com")
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash="c" * 64,
            expires_at=datetime(2030, 1, 1, 12, 0, 0),  # no tzinfo
        )
    )
    with pytest.raises(StatementError, match="naive datetime"):
        db.commit()
    db.rollback()


def test_a_non_utc_offset_is_normalised_not_dropped(db):
    """Jakarta is UTC+7; the stored instant must be the same moment."""
    user = _make_user(db, "tz-offset@example.com")
    jakarta = timezone(timedelta(hours=7))
    moment = datetime(2026, 6, 1, 19, 0, 0, tzinfo=jakarta)  # 12:00 UTC

    db.add(RefreshToken(user_id=user.id, token_hash="d" * 64, expires_at=moment))
    db.commit()
    db.expire_all()

    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == "d" * 64).one()
    assert stored.expires_at == moment
    assert stored.expires_at.hour == 12  # normalised to UTC, same instant


def test_billing_periods_are_aware_end_to_end(db):
    """Subscription expiry compares stored periods against now on every sweep."""
    from app.services.subscription_lifecycle import sweep_subscriptions

    user = _make_user(db, "tz-billing@example.com")
    now = datetime.now(UTC)
    db.add(
        Subscription(
            user_id=user.id,
            plan="pro",
            provider="midtrans",
            status="active",
            current_period_start=now - timedelta(days=40),
            current_period_end=now - timedelta(days=10),
            grace_until=now - timedelta(days=7),
        )
    )
    db.commit()

    result = sweep_subscriptions(db, now=now)
    assert result.expired == 1


def test_payment_timestamps_survive_the_round_trip(db):
    user = _make_user(db, "tz-payment@example.com")
    paid = datetime.now(UTC)
    db.add(
        Payment(
            user_id=user.id,
            provider="midtrans",
            provider_order_id="tz-order",
            amount=1000,
            plan="pro",
            status="settlement",
            paid_at=paid,
        )
    )
    db.commit()
    db.expire_all()

    stored = db.query(Payment).filter(Payment.provider_order_id == "tz-order").one()
    assert stored.paid_at.tzinfo is not None
    assert abs((stored.paid_at - paid).total_seconds()) < 1


def test_server_defaults_are_also_aware(db):
    """`server_default=func.now()` bypasses the bind hook, so check the read."""
    _make_user(db, "tz-default@example.com")
    db.expire_all()
    stored = db.query(User).filter(User.email == "tz-default@example.com").one()
    assert stored.created_at is not None
    assert stored.created_at.tzinfo is not None
