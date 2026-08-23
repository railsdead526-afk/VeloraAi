"""Tests for the subscription lifecycle.

The bug these lock down: a single settled payment used to grant a paid plan
forever, because `current_period_end` was never written and nothing ever
expired a subscription.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models.billing import Payment, Subscription
from app.models.user import User
from app.services.billing_service import (
    apply_payment_notification,
    create_payment_intent,
    next_invoice_number,
    sync_user_role,
    tax_component,
)
from app.services.payments import PaymentOutcome
from app.services.subscription_lifecycle import (
    cancel_at_period_end,
    resume_subscription,
    sweep_subscriptions,
)


def _make_user(db, email: str, role: str = "free") -> User:
    user = User(email=email, hashed_password="x", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _settle(db, user: User, plan: str = "pro", amount: int = 99_000) -> Payment:
    payment = create_payment_intent(db, user_id=user.id, plan=plan, amount=amount)
    apply_payment_notification(
        db,
        provider="midtrans",
        provider_order_id=payment.provider_order_id,
        provider_transaction_id=f"txn-{payment.id}",
        transaction_status="settlement",
        outcome=PaymentOutcome.PAID,
    )
    db.refresh(payment)
    return payment


# --------------------------------------------------------------------------- #
# Period assignment
# --------------------------------------------------------------------------- #


def test_settlement_writes_a_bounded_billing_period(db):
    user = _make_user(db, "period@example.com")
    payment = _settle(db, user)

    subscription = db.get(Subscription, payment.subscription_id)
    assert subscription is not None
    assert subscription.status == "active"
    assert subscription.current_period_start is not None
    assert subscription.current_period_end is not None
    assert subscription.grace_until is not None

    span = subscription.current_period_end - subscription.current_period_start
    assert span == timedelta(days=settings.subscription_period_days)

    db.refresh(user)
    assert user.role == "pro"


def test_renewal_extends_from_the_existing_period_end(db):
    user = _make_user(db, "renew@example.com")
    first = _settle(db, user)
    subscription = db.get(Subscription, first.subscription_id)
    first_end = subscription.current_period_end

    _settle(db, user)
    db.refresh(subscription)

    # Paying early must add a period rather than forfeit remaining days.
    assert subscription.current_period_end > first_end
    assert db.query(Subscription).filter(Subscription.user_id == user.id).count() == 1


def test_failed_payment_grants_no_period(db):
    user = _make_user(db, "failed@example.com")
    payment = create_payment_intent(db, user_id=user.id, plan="pro", amount=99_000)
    apply_payment_notification(
        db,
        provider="midtrans",
        provider_order_id=payment.provider_order_id,
        provider_transaction_id="txn-fail",
        transaction_status="deny",
        outcome=PaymentOutcome.FAILED,
    )
    db.refresh(user)
    assert user.role == "free"
    assert db.query(Subscription).filter(Subscription.user_id == user.id).count() == 0


# --------------------------------------------------------------------------- #
# Expiry
# --------------------------------------------------------------------------- #


def test_lapsed_period_moves_the_subscription_to_past_due(db):
    user = _make_user(db, "pastdue@example.com")
    payment = _settle(db, user)
    subscription = db.get(Subscription, payment.subscription_id)

    now = datetime.now(UTC)
    subscription.current_period_end = now - timedelta(hours=1)
    subscription.grace_until = now + timedelta(days=2)
    db.commit()

    result = sweep_subscriptions(db, now=now)
    assert result.marked_past_due == 1

    db.refresh(subscription)
    db.refresh(user)
    assert subscription.status == "past_due"
    # Still entitled: the grace window is the whole point.
    assert user.role == "pro"


def test_grace_expiry_downgrades_the_user(db):
    user = _make_user(db, "expired@example.com")
    payment = _settle(db, user)
    subscription = db.get(Subscription, payment.subscription_id)

    now = datetime.now(UTC)
    subscription.current_period_end = now - timedelta(days=5)
    subscription.grace_until = now - timedelta(days=1)
    db.commit()

    result = sweep_subscriptions(db, now=now)
    assert result.expired == 1

    db.refresh(subscription)
    db.refresh(user)
    assert subscription.status == "expired"
    assert user.role == "free"


def test_sweep_is_idempotent(db):
    user = _make_user(db, "idempotent@example.com")
    payment = _settle(db, user)
    subscription = db.get(Subscription, payment.subscription_id)

    now = datetime.now(UTC)
    subscription.current_period_end = now - timedelta(days=5)
    subscription.grace_until = now - timedelta(days=1)
    db.commit()

    assert sweep_subscriptions(db, now=now).expired == 1
    assert sweep_subscriptions(db, now=now).expired == 0

    db.refresh(user)
    assert user.role == "free"


def test_admin_role_is_never_downgraded_by_the_sweep(db):
    user = _make_user(db, "admin-sweep@example.com", role="admin")
    payment = _settle(db, user)
    subscription = db.get(Subscription, payment.subscription_id)

    now = datetime.now(UTC)
    subscription.current_period_end = now - timedelta(days=10)
    subscription.grace_until = now - timedelta(days=5)
    db.commit()

    sweep_subscriptions(db, now=now)
    db.refresh(user)
    assert user.role == "admin"


def test_legacy_subscription_without_a_period_is_backfilled_not_granted_forever(db):
    user = _make_user(db, "legacy-sub@example.com", role="pro")
    subscription = Subscription(user_id=user.id, plan="pro", provider="midtrans", status="active")
    db.add(subscription)
    db.commit()

    sweep_subscriptions(db)
    db.refresh(subscription)
    assert subscription.current_period_end is not None
    assert subscription.grace_until is not None


def test_highest_entitled_plan_wins(db):
    user = _make_user(db, "multi-plan@example.com")
    now = datetime.now(UTC)
    for plan in ("pro", "max"):
        db.add(
            Subscription(
                user_id=user.id,
                plan=plan,
                provider="midtrans",
                status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                grace_until=now + timedelta(days=33),
            )
        )
    db.commit()

    sync_user_role(db, user_id=user.id)
    db.commit()
    db.refresh(user)
    assert user.role == "max"


# --------------------------------------------------------------------------- #
# Cancellation
# --------------------------------------------------------------------------- #


def test_cancel_at_period_end_keeps_access_until_the_period_closes(db):
    user = _make_user(db, "cancel@example.com")
    payment = _settle(db, user)
    subscription = db.get(Subscription, payment.subscription_id)

    cancel_at_period_end(db, user_id=user.id, subscription_id=subscription.id)
    db.refresh(subscription)
    assert subscription.cancel_at_period_end is True

    # Access is untouched while the period is live.
    sweep_subscriptions(db)
    db.refresh(user)
    assert user.role == "pro"

    now = datetime.now(UTC)
    subscription.current_period_end = now - timedelta(days=5)
    subscription.grace_until = now - timedelta(days=1)
    db.commit()

    result = sweep_subscriptions(db, now=now)
    assert result.canceled_at_period_end == 1
    db.refresh(subscription)
    db.refresh(user)
    assert subscription.status == "canceled"
    assert user.role == "free"


def test_resume_clears_a_scheduled_cancellation(db):
    user = _make_user(db, "resume@example.com")
    payment = _settle(db, user)
    subscription = db.get(Subscription, payment.subscription_id)

    cancel_at_period_end(db, user_id=user.id, subscription_id=subscription.id)
    resume_subscription(db, user_id=user.id, subscription_id=subscription.id)
    db.refresh(subscription)
    assert subscription.cancel_at_period_end is False


def test_cancelling_another_users_subscription_is_refused(db):
    owner = _make_user(db, "owner-sub@example.com")
    attacker = _make_user(db, "attacker-sub@example.com")
    payment = _settle(db, owner)

    with pytest.raises(LookupError):
        cancel_at_period_end(db, user_id=attacker.id, subscription_id=payment.subscription_id)


# --------------------------------------------------------------------------- #
# Invoicing and tax
# --------------------------------------------------------------------------- #


def test_settlement_assigns_a_unique_sequential_invoice_number(db):
    first_user = _make_user(db, "inv1@example.com")
    second_user = _make_user(db, "inv2@example.com")

    first = _settle(db, first_user)
    second = _settle(db, second_user)

    assert first.invoice_number is not None
    assert second.invoice_number is not None
    assert first.invoice_number != second.invoice_number
    assert first.invoice_number.startswith("INV-")
    assert int(second.invoice_number.rsplit("-", 1)[1]) == (
        int(first.invoice_number.rsplit("-", 1)[1]) + 1
    )


def test_invoice_number_restarts_each_month(db):
    january = datetime(2026, 1, 15, tzinfo=UTC)
    february = datetime(2026, 2, 15, tzinfo=UTC)
    assert next_invoice_number(db, now=january).startswith("INV-2026-01-")
    assert next_invoice_number(db, now=february).startswith("INV-2026-02-")


def test_vat_is_extracted_from_the_tax_inclusive_amount(monkeypatch):
    monkeypatch.setattr(settings, "vat_percent", 0.0)
    assert tax_component(100_000) == 0

    monkeypatch.setattr(settings, "vat_percent", 12.0)
    # 112,000 gross at 12% inclusive -> 12,000 tax.
    assert tax_component(112_000) == 12_000


def test_payment_records_the_tax_component(db, monkeypatch):
    monkeypatch.setattr(settings, "vat_percent", 12.0)
    user = _make_user(db, "vat@example.com")
    payment = _settle(db, user, amount=112_000)
    assert payment.tax_amount == 12_000
