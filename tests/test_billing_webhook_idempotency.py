from app.models.billing import Payment, Subscription
from app.models.user import User
from app.services.billing_service import apply_payment_notification
from app.services.payments import PaymentOutcome


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
        outcome=PaymentOutcome.PAID,
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
        outcome=PaymentOutcome.PAID,
        payment_type="qris",
    )

    assert second is not None
    assert second.subscription_id == subscription_id
    assert db.query(Subscription).filter(Subscription.user_id == user.id).count() == 1
