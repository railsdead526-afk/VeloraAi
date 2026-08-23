from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.billing import Payment, Subscription
from app.models.user import User
from app.services.payments.base import PaymentOutcome

#: Once a payment reaches one of these, later notifications cannot change it.
#: Providers legitimately resend, and out-of-order delivery is normal.
TERMINAL_PAYMENT_STATUSES = {"settlement", "refunded"}
PLAN_PRIORITY = {"free": 0, "pro": 1, "max": 2}


def tax_component(gross_amount: int) -> int:
    """VAT/PPN already included inside a tax-inclusive gross amount."""
    rate = settings.vat_percent
    if rate <= 0:
        return 0
    return round(gross_amount - (gross_amount / (1 + rate / 100)))


def next_invoice_number(db: Session, *, now: datetime | None = None) -> str:
    """Sequential per-month invoice reference, e.g. ``INV-2026-08-000042``.

    Racy on its own: two settlements reading before either commits both compute
    the same number. Use :func:`assign_invoice_number`, which retries.
    """
    moment = now or datetime.now(UTC)
    prefix = f"INV-{moment:%Y-%m}-"
    latest = db.execute(
        select(Payment.invoice_number)
        .where(Payment.invoice_number.like(f"{prefix}%"))
        .order_by(Payment.invoice_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    sequence = int(latest.rsplit("-", 1)[1]) + 1 if latest else 1
    return f"{prefix}{sequence:06d}"


#: Enough to absorb realistic contention; each retry re-reads the high-water mark.
_INVOICE_ATTEMPTS = 8


def assign_invoice_number(db: Session, payment: Payment, *, now: datetime | None = None) -> str:
    """Give the payment a unique invoice number, retrying on collision.

    invoice_number carries a UNIQUE constraint, and the number is derived from
    the current maximum. Two provider notifications settling at the same moment
    therefore computed the same value and the second commit died with an
    IntegrityError, failing a webhook for a payment that had genuinely been
    made.

    Each attempt runs inside a SAVEPOINT so a collision rolls back only the
    failed assignment, leaving the caller's surrounding transaction intact.
    """
    for _ in range(_INVOICE_ATTEMPTS):
        candidate = next_invoice_number(db, now=now)
        savepoint = db.begin_nested()
        try:
            payment.invoice_number = candidate
            db.flush()
        except IntegrityError:
            savepoint.rollback()
            continue
        savepoint.commit()
        return candidate

    raise RuntimeError("Unable to allocate a unique invoice number")


def create_payment_intent(
    db: Session,
    *,
    user_id: int,
    plan: str,
    amount: int,
    provider: str = "midtrans",
) -> Payment:
    order_id = f"velora-{user_id}-{int(datetime.now(UTC).timestamp() * 1000)}"
    payment = Payment(
        user_id=user_id,
        provider=provider,
        provider_order_id=order_id,
        amount=amount,
        tax_amount=tax_component(amount),
        currency="IDR",
        plan=plan,
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


#: Statuses that still entitle the user to their paid plan. `past_due` is
#: included deliberately: the subscription is inside its grace window.
ENTITLED_STATUSES = ("active", "past_due")


def sync_user_role(db: Session, *, user_id: int) -> None:
    """Recompute the user's role from subscriptions that are still entitled."""
    user = db.get(User, user_id)
    if user is None or user.role == "admin":
        return

    now = datetime.now(UTC)
    subscriptions = (
        db.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status.in_(ENTITLED_STATUSES),
            )
        )
        .scalars()
        .all()
    )

    entitled_plans = []
    for subscription in subscriptions:
        boundary = subscription.grace_until or subscription.current_period_end
        # A subscription with no recorded period is legacy data; honour it.
        if boundary is None or boundary > now:
            entitled_plans.append(subscription.plan)

    user.role = max(entitled_plans, key=lambda plan: PLAN_PRIORITY.get(plan, 0), default="free")


def apply_payment_notification(
    db: Session,
    *,
    provider: str,
    provider_order_id: str,
    provider_transaction_id: str | None,
    transaction_status: str,
    outcome: PaymentOutcome,
    payment_type: str | None = None,
) -> Payment | None:
    """Apply a verified provider notification to a payment and its subscription.

    `outcome` is the canonical meaning, decided by the provider adapter.
    `transaction_status` is the provider's own wording, stored as-is so support
    and reconciliation can see exactly what the gateway said.
    """
    payment = db.execute(
        select(Payment)
        .where(
            Payment.provider == provider,
            Payment.provider_order_id == provider_order_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if payment is None:
        return None

    normalized = transaction_status.lower()
    if payment.status in TERMINAL_PAYMENT_STATUSES:
        if payment.status == "settlement" and outcome is PaymentOutcome.PAID:
            payment.provider_transaction_id = (
                provider_transaction_id or payment.provider_transaction_id
            )
            payment.payment_type = payment_type or payment.payment_type
            db.commit()
            db.refresh(payment)
        return payment

    if outcome is PaymentOutcome.PAID:
        # Normalised so downstream reads do not have to know each provider's
        # word for "money received".
        payment.status = "settlement"
        payment.paid_at = payment.paid_at or datetime.now(UTC)
        payment.provider_transaction_id = provider_transaction_id or payment.provider_transaction_id
        payment.payment_type = payment_type or payment.payment_type
        if payment.invoice_number is None:
            assign_invoice_number(db, payment)
        if not payment.tax_amount:
            payment.tax_amount = tax_component(payment.amount)

        now = datetime.now(UTC)
        period = timedelta(days=settings.subscription_period_days)
        grace = timedelta(days=settings.subscription_grace_days)

        subscription = payment.subscription
        if subscription is None:
            # Reuse the user's existing subscription for this plan if there is
            # one, so repeat purchases extend rather than duplicate.
            subscription = (
                db.execute(
                    select(Subscription).where(
                        Subscription.user_id == payment.user_id,
                        Subscription.plan == payment.plan,
                        Subscription.provider == provider,
                    )
                )
                .scalars()
                .first()
            )

        if subscription is None:
            subscription = Subscription(
                user_id=payment.user_id,
                plan=payment.plan,
                provider=provider,
                status="active",
                current_period_start=now,
                current_period_end=now + period,
                grace_until=now + period + grace,
            )
            db.add(subscription)
            db.flush()
        else:
            # Extend from the later of "now" and the current period end, so a
            # renewal paid early does not silently forfeit remaining days.
            current_end = subscription.current_period_end
            anchor = current_end if current_end and current_end > now else now
            subscription.plan = payment.plan
            subscription.status = "active"
            subscription.current_period_start = subscription.current_period_start or now
            subscription.current_period_end = anchor + period
            subscription.grace_until = anchor + period + grace
            subscription.canceled_at = None

        payment.subscription_id = subscription.id
        sync_user_role(db, user_id=payment.user_id)
    elif outcome is PaymentOutcome.REFUNDED:
        payment.status = "refunded"
        payment.provider_transaction_id = provider_transaction_id or payment.provider_transaction_id
        payment.payment_type = payment_type or payment.payment_type
        if payment.subscription is not None:
            payment.subscription.status = "canceled"
        sync_user_role(db, user_id=payment.user_id)
    else:
        # PENDING, FAILED, and UNKNOWN all keep the provider's own wording.
        # UNKNOWN deliberately does not revoke anything: an unrecognised status
        # must never cost a paying customer their plan.
        payment.status = normalized
        payment.provider_transaction_id = provider_transaction_id or payment.provider_transaction_id
        payment.payment_type = payment_type or payment.payment_type

    db.commit()
    db.refresh(payment)
    return payment
