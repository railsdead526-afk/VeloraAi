from datetime import datetime, timezone

from app.models.billing import Payment, Subscription
from app.models.user import User
from app.services.billing_service import apply_payment_notification, sync_user_role


def test_repeated_settlement_notification_reuses_existing_subscription(db):
    user = User(email="billing-idempotency@example.com", hashed_password="test", role="free")
    db.add(user)
    db.commit()
    db.refresh(user)

    payment = Payment(
        user_id=user.id,
        provider="midtrans",
        provider_order_id="velora-idempotency-1",
        amount=10000,
        currency="IDR",
        plan="pro",
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    first = apply_payment_notification(
        db,
        provider="midtrans",
        provider_order_id=payment.provider_order_id,
        provider_transaction_id="txn-1",
        transaction_status="settlement",
        payment_type="qris",
    )
    assert first is not None
    assert first.subscription_id is not None
    subscription_id = first.subscription_id

    second = apply_payment_notification(
        db,
        provider="midtrans",
        provider_order_id=payment.provider_order_id,
        provider_transaction_id="txn-1",
        transaction_status="settlement",
        payment_type="qris",
    )

    assert second is not None
    assert second.subscription_id == subscription_id
    assert db.query(Subscription).filter(Subscription.user_id == user.id).count() == 1


def test_new_settlement_replaces_previous_active_subscription(db):
    user = User(email="billing-downgrade@example.com", hashed_password="test", role="max")
    db.add(user)
    db.commit()
    db.refresh(user)

    old_subscription = Subscription(
        user_id=user.id,
        provider="midtrans",
        plan="max",
        status="active",
    )
    payment = Payment(
        user_id=user.id,
        provider="midtrans",
        provider_order_id="velora-downgrade-1",
        amount=10000,
        currency="IDR",
        plan="pro",
        status="pending",
    )
    db.add_all([old_subscription, payment])
    db.commit()
    db.refresh(payment)

    apply_payment_notification(
        db,
        provider="midtrans",
        provider_order_id=payment.provider_order_id,
        provider_transaction_id="txn-downgrade-1",
        transaction_status="settlement",
        payment_type="qris",
    )

    db.refresh(user)
    db.refresh(old_subscription)
    assert user.role == "pro"
    assert old_subscription.status == "canceled"
    assert db.query(Subscription).filter(Subscription.user_id == user.id, Subscription.status == "active").count() == 1


def test_refund_downgrades_role_when_no_other_subscription_is_active(db):
    user = User(email="billing-refund-downgrade@example.com", hashed_password="test", role="pro")
    db.add(user)
    db.commit()
    db.refresh(user)

    subscription = Subscription(
        user_id=user.id,
        provider="midtrans",
        plan="pro",
        status="active",
    )
    db.add(subscription)
    db.flush()
    payment = Payment(
        user_id=user.id,
        subscription_id=subscription.id,
        provider="midtrans",
        provider_order_id="velora-refund-downgrade-1",
        amount=10000,
        currency="IDR",
        plan="pro",
        status="settlement",
    )
    db.add(payment)
    db.commit()

    subscription.status = "canceled"
    subscription.canceled_at = datetime.now(timezone.utc)
    sync_user_role(db, user_id=user.id)
    db.commit()

    db.refresh(user)
    assert user.role == "free"
