from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing import Payment, Subscription
from app.models.user import User


PAID_STATUSES = {"settlement", "capture"}
FAILED_STATUSES = {"deny", "cancel", "expire", "failure"}
TERMINAL_PAYMENT_STATUSES = {"settlement", "refunded"}
PLAN_PRIORITY = {"free": 0, "pro": 1, "max": 2}


def create_payment_intent(
    db: Session,
    *,
    user_id: int,
    plan: str,
    amount: int,
    provider: str = "midtrans",
) -> Payment:
    order_id = f"velora-{user_id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    payment = Payment(
        user_id=user_id,
        provider=provider,
        provider_order_id=order_id,
        amount=amount,
        currency="IDR",
        plan=plan,
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def sync_user_role(db: Session, *, user_id: int) -> None:
    user = db.get(User, user_id)
    if user is None or user.role == "admin":
        return

    active_plans = db.execute(
        select(Subscription.plan).where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
        )
    ).scalars().all()
    user.role = max(active_plans, key=lambda plan: PLAN_PRIORITY.get(plan, 0), default="free")


def apply_payment_notification(
    db: Session,
    *,
    provider: str,
    provider_order_id: str,
    provider_transaction_id: str | None,
    transaction_status: str,
    payment_type: str | None = None,
) -> Payment | None:
    payment = db.execute(
        select(Payment).where(
            Payment.provider == provider,
            Payment.provider_order_id == provider_order_id,
        )
    ).scalar_one_or_none()
    if payment is None:
        return None

    normalized = transaction_status.lower()
    if payment.status in TERMINAL_PAYMENT_STATUSES:
        if payment.status == "settlement" and normalized in PAID_STATUSES:
            payment.provider_transaction_id = provider_transaction_id or payment.provider_transaction_id
            payment.payment_type = payment_type or payment.payment_type
            db.commit()
            db.refresh(payment)
        return payment

    if normalized in PAID_STATUSES:
        payment.status = "settlement"
        payment.paid_at = payment.paid_at or datetime.now(timezone.utc)
        payment.provider_transaction_id = provider_transaction_id or payment.provider_transaction_id
        payment.payment_type = payment_type or payment.payment_type
        subscription = payment.subscription
        if subscription is None:
            subscription = Subscription(
                user_id=payment.user_id,
                plan=payment.plan,
                provider=provider,
                status="active",
            )
            db.add(subscription)
            db.flush()
            payment.subscription_id = subscription.id
        else:
            subscription.plan = payment.plan
            subscription.status = "active"

        sync_user_role(db, user_id=payment.user_id)
    elif normalized in FAILED_STATUSES:
        payment.status = normalized
        payment.provider_transaction_id = provider_transaction_id or payment.provider_transaction_id
        payment.payment_type = payment_type or payment.payment_type
    else:
        payment.status = normalized
        payment.provider_transaction_id = provider_transaction_id or payment.provider_transaction_id
        payment.payment_type = payment_type or payment.payment_type

    db.commit()
    db.refresh(payment)
    return payment
