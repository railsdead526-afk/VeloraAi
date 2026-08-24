"""Scheduled subscription lifecycle transitions.

This closes the revenue leak where a single settled payment granted a paid
plan forever: subscriptions now have a period, move to `past_due` when it
lapses, and are downgraded once the grace window closes.

Run `sweep_subscriptions()` from the maintenance job (see
`scripts/run_maintenance.py`). It is idempotent, so running it more than once
in a period is harmless.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.billing import Subscription
from app.models.user import User
from app.services.audit_service import record_audit_event_best_effort
from app.services.billing_service import sync_user_role
from app.services.notification_service import (
    send_subscription_downgraded_email,
    send_subscription_expiring_email,
)

logger = logging.getLogger("veloraai.billing")

#: How many days before period end the renewal reminder goes out.
REMINDER_DAYS = (7, 3, 1)


@dataclass
class SweepResult:
    marked_past_due: int = 0
    expired: int = 0
    canceled_at_period_end: int = 0
    reminders_sent: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def sweep_subscriptions(db: Session, *, now: datetime | None = None) -> SweepResult:
    moment = now or datetime.now(UTC)
    result = SweepResult()
    touched_users: set[int] = set()

    subscriptions = list(
        db.execute(
            select(Subscription).where(Subscription.status.in_(("active", "past_due")))
        ).scalars()
    )

    for subscription in subscriptions:
        period_end = subscription.current_period_end
        grace_until = subscription.grace_until

        # Legacy rows written before periods existed: backfill instead of
        # granting an unbounded entitlement.
        if period_end is None:
            period_end = moment + timedelta(days=settings.subscription_period_days)
            subscription.current_period_start = moment
            subscription.current_period_end = period_end
            grace_until = period_end + timedelta(days=settings.subscription_grace_days)
            subscription.grace_until = grace_until
            logger.info("backfilled subscription period subscription_id=%s", subscription.id)
            continue

        if grace_until is None:
            grace_until = period_end + timedelta(days=settings.subscription_grace_days)
            subscription.grace_until = grace_until

        # 1. Grace window closed -> terminate entitlement.
        if grace_until <= moment:
            subscription.status = "canceled" if subscription.cancel_at_period_end else "expired"
            if subscription.canceled_at is None:
                subscription.canceled_at = moment
            touched_users.add(subscription.user_id)
            result.expired += 1
            if subscription.cancel_at_period_end:
                result.canceled_at_period_end += 1
            _notify_downgrade(db, subscription)
            continue

        # 2. Period lapsed but still inside grace -> past_due.
        if period_end <= moment and subscription.status == "active":
            subscription.status = "past_due"
            touched_users.add(subscription.user_id)
            result.marked_past_due += 1
            continue

        # 3. Renewal reminder. The sweep runs hourly, so a naive
        # `days_left in REMINDER_DAYS` fires 24 times per milestone. Only send
        # when this milestone is closer than the last one already sent.
        if subscription.status == "active":
            days_left = (period_end - moment).days
            already_sent = subscription.last_reminder_days_left
            due = days_left in REMINDER_DAYS and (already_sent is None or days_left < already_sent)
            if due:
                user = db.get(User, subscription.user_id)
                if user is not None and not user.is_deleted:
                    send_subscription_expiring_email(
                        email=user.email, plan=subscription.plan, days_left=days_left
                    )
                    result.reminders_sent += 1
                # Recorded even when the user has gone, so a deleted account
                # cannot make the sweep retry every hour.
                subscription.last_reminder_days_left = days_left

    for user_id in touched_users:
        sync_user_role(db, user_id=user_id)

    db.commit()

    if any(result.as_dict().values()):
        logger.info("subscription sweep %s", result.as_dict())
        record_audit_event_best_effort(
            user_id=None, event="billing.subscription_sweep", metadata=result.as_dict()
        )
    return result


def _notify_downgrade(db: Session, subscription: Subscription) -> None:
    user = db.get(User, subscription.user_id)
    if user is not None and not user.is_deleted:
        send_subscription_downgraded_email(email=user.email, plan=subscription.plan)


def cancel_at_period_end(db: Session, *, user_id: int, subscription_id: int) -> Subscription:
    """User-initiated cancellation: keep access until the paid period ends."""
    subscription = db.execute(
        select(Subscription).where(
            Subscription.id == subscription_id, Subscription.user_id == user_id
        )
    ).scalar_one_or_none()
    if subscription is None:
        raise LookupError("Subscription not found")

    subscription.cancel_at_period_end = True
    db.commit()
    record_audit_event_best_effort(
        user_id=user_id,
        event="billing.cancel_scheduled",
        resource_type="subscription",
        resource_id=str(subscription_id),
    )
    return subscription


def resume_subscription(db: Session, *, user_id: int, subscription_id: int) -> Subscription:
    subscription = db.execute(
        select(Subscription).where(
            Subscription.id == subscription_id, Subscription.user_id == user_id
        )
    ).scalar_one_or_none()
    if subscription is None:
        raise LookupError("Subscription not found")

    subscription.cancel_at_period_end = False
    db.commit()
    return subscription
