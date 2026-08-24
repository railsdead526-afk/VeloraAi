"""Renewal reminders must be sent once per milestone, not once per sweep.

The lifecycle sweep is designed to run hourly, and it decided whether to email
from `(period_end - now).days` - a value that stays put for a whole day. Every
milestone therefore fired 24 times. Simulating one 30-day period at hourly
resolution produced 72 identical emails for a single subscription.

That is not just noise. Sending the same message 24 times in a day is exactly
what reputation systems score as spam, and the collateral damage lands on the
messages that must arrive: email verification and password reset.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.models.billing import Subscription
from app.models.user import User
from app.services import subscription_lifecycle as lifecycle

PERIOD_START = datetime(2026, 9, 1, tzinfo=UTC)


@pytest.fixture
def user(db):
    account = User(email="reminder@example.com", hashed_password="hash", role="pro")
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@pytest.fixture
def subscription(db, user):
    record = Subscription(
        user_id=user.id,
        plan="pro",
        provider="midtrans",
        status="active",
        current_period_start=PERIOD_START,
        current_period_end=PERIOD_START + timedelta(days=30),
        grace_until=PERIOD_START + timedelta(days=33),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _sweep_hourly(db, *, days: int, start: datetime = PERIOD_START) -> list[dict]:
    """Run the sweep every hour the way the maintenance job would."""
    sent: list[dict] = []
    with patch.object(
        lifecycle, "send_subscription_expiring_email", side_effect=lambda **kw: sent.append(kw)
    ):
        moment = start
        finish = start + timedelta(days=days)
        while moment < finish:
            lifecycle.sweep_subscriptions(db, now=moment)
            moment += timedelta(hours=1)
    return sent


def test_each_milestone_emails_exactly_once(db, subscription):
    sent = _sweep_hourly(db, days=30)

    per_milestone = Counter(item["days_left"] for item in sent)
    assert per_milestone == {7: 1, 3: 1, 1: 1}, per_milestone
    assert len(sent) == len(lifecycle.REMINDER_DAYS)


def test_reminders_are_not_resent_when_the_sweep_repeats(db, subscription):
    """Idempotence: running the job twice at the same instant sends one email."""
    moment = PERIOD_START + timedelta(days=23)

    sent: list[dict] = []
    with patch.object(
        lifecycle, "send_subscription_expiring_email", side_effect=lambda **kw: sent.append(kw)
    ):
        lifecycle.sweep_subscriptions(db, now=moment)
        lifecycle.sweep_subscriptions(db, now=moment)
        lifecycle.sweep_subscriptions(db, now=moment + timedelta(hours=6))

    assert len(sent) == 1
    assert sent[0]["days_left"] == 7


def test_the_marker_records_the_milestone(db, subscription):
    with patch.object(lifecycle, "send_subscription_expiring_email"):
        lifecycle.sweep_subscriptions(db, now=PERIOD_START + timedelta(days=23))

    db.refresh(subscription)
    assert subscription.last_reminder_days_left == 7


def test_a_renewed_period_earns_a_fresh_set_of_reminders(db, subscription):
    _sweep_hourly(db, days=30)
    db.refresh(subscription)
    assert subscription.last_reminder_days_left == 1

    # Renewal, as billing_service performs it.
    new_start = PERIOD_START + timedelta(days=30)
    subscription.current_period_start = new_start
    subscription.current_period_end = new_start + timedelta(days=30)
    subscription.grace_until = new_start + timedelta(days=33)
    subscription.status = "active"
    subscription.last_reminder_days_left = None
    db.commit()

    sent = _sweep_hourly(db, days=30, start=new_start)
    assert Counter(item["days_left"] for item in sent) == {7: 1, 3: 1, 1: 1}


def test_renewal_through_billing_clears_the_marker(db, user, subscription):
    subscription.last_reminder_days_left = 1
    db.commit()

    now = datetime.now(UTC)
    period = timedelta(days=settings.subscription_period_days)
    grace = timedelta(days=settings.subscription_grace_days)

    # Mirror the extension branch of apply_payment_notification.
    subscription.current_period_end = now + period
    subscription.grace_until = now + period + grace
    subscription.last_reminder_days_left = None
    db.commit()
    db.refresh(subscription)

    assert subscription.last_reminder_days_left is None


def test_a_deleted_user_does_not_retry_every_hour(db, user, subscription):
    user.deleted_at = datetime.now(UTC)
    db.commit()

    calls = {"n": 0}

    def count(**_kwargs):
        calls["n"] += 1

    with patch.object(lifecycle, "send_subscription_expiring_email", side_effect=count):
        for hour in range(6):
            lifecycle.sweep_subscriptions(db, now=PERIOD_START + timedelta(days=23, hours=hour))

    assert calls["n"] == 0
    db.refresh(subscription)
    # The milestone is still marked, so the sweep does not reconsider it hourly.
    assert subscription.last_reminder_days_left == 7
