import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.plans import PlanPolicy
from app.models.ai_request_reservation import AIRequestReservation
from app.models.ai_usage import AIUsage
from app.models.user import User

logger = logging.getLogger(__name__)

RESERVATION_TTL = timedelta(minutes=30)
#: Reservation rows are audit-free bookkeeping; once settled they only need to
#: survive long enough to debug a recent incident.
RESERVATION_RETENTION = timedelta(days=7)


class QuotaExceededError(Exception):
    """Raised when a configured AI usage quota is exceeded."""


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _day_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _now() -> datetime:
    return datetime.now(UTC)


def tokens_used_since(db: Session, user_id: int, since: datetime) -> int:
    total = (
        db.query(func.coalesce(func.sum(AIUsage.total_tokens), 0))
        .filter(AIUsage.user_id == user_id, AIUsage.created_at >= since)
        .scalar()
    )
    return int(total or 0)


def requests_used_since(db: Session, user_id: int, since: datetime) -> int:
    total = (
        db.query(func.count(AIUsage.id))
        .filter(AIUsage.user_id == user_id, AIUsage.created_at >= since)
        .scalar()
    )
    return int(total or 0)


def _active_reservations_since(db: Session, user_id: int, since: datetime, now: datetime) -> int:
    total = (
        db.query(func.count(AIRequestReservation.id))
        .filter(
            AIRequestReservation.user_id == user_id,
            AIRequestReservation.status == "reserved",
            AIRequestReservation.created_at >= since,
            AIRequestReservation.expires_at > now,
        )
        .scalar()
    )
    return int(total or 0)


def _release_expired_reservations(db: Session, user_id: int, now: datetime) -> None:
    (
        db.query(AIRequestReservation)
        .filter(
            AIRequestReservation.user_id == user_id,
            AIRequestReservation.status == "reserved",
            AIRequestReservation.expires_at <= now,
        )
        .update(
            {
                AIRequestReservation.status: "released",
                AIRequestReservation.released_at: now,
            },
            synchronize_session=False,
        )
    )


def enforce_monthly_token_quota(
    db: Session,
    *,
    user_id: int,
    monthly_limit: int | None,
    additional_tokens: int = 0,
) -> None:
    if monthly_limit is None:
        return
    if monthly_limit < 0:
        raise ValueError("monthly_limit must be non-negative")
    if additional_tokens < 0:
        raise ValueError("additional_tokens must be non-negative")

    used = tokens_used_since(db, user_id, _month_start())
    if additional_tokens == 0:
        exceeded = used >= monthly_limit
    else:
        exceeded = used + additional_tokens > monthly_limit
    if exceeded:
        raise QuotaExceededError("Monthly AI token quota exceeded")


def enforce_plan_quota(
    db: Session,
    *,
    user_id: int,
    policy: PlanPolicy,
    additional_tokens: int = 0,
    check_request_limits: bool = True,
) -> None:
    """Check token/request quota without reserving a new request slot."""
    if policy.monthly_token_limit is not None:
        enforce_monthly_token_quota(
            db,
            user_id=user_id,
            monthly_limit=policy.monthly_token_limit,
            additional_tokens=additional_tokens,
        )
    if not check_request_limits:
        return

    month_since = _month_start()
    day_since = _day_start()
    now = _now()
    if policy.monthly_request_limit is not None:
        used = requests_used_since(db, user_id, month_since)
        active = _active_reservations_since(db, user_id, month_since, now)
        if used + active >= policy.monthly_request_limit:
            raise QuotaExceededError("Monthly AI request quota exceeded")
    if policy.daily_request_limit is not None:
        used = requests_used_since(db, user_id, day_since)
        active = _active_reservations_since(db, user_id, day_since, now)
        if used + active >= policy.daily_request_limit:
            raise QuotaExceededError("Daily AI request quota exceeded")


def reserve_plan_request_quota(db: Session, *, user_id: int, policy: PlanPolicy) -> int | None:
    """Atomically reserve one request slot before model/tool execution."""
    if policy.daily_request_limit is None and policy.monthly_request_limit is None:
        return None

    now = _now()
    month_since = _month_start()
    day_since = _day_start()

    # UPDATE obtains a real write lock on SQLite and a row lock on PostgreSQL.
    updated = (
        db.query(User)
        .filter(User.id == user_id)
        .update({User.quota_lock_version: User.quota_lock_version + 1}, synchronize_session=False)
    )
    if updated != 1:
        raise QuotaExceededError("Unable to reserve AI request quota")

    _release_expired_reservations(db, user_id, now)

    if policy.monthly_request_limit is not None:
        monthly_used = requests_used_since(db, user_id, month_since)
        monthly_active = _active_reservations_since(db, user_id, month_since, now)
        if monthly_used + monthly_active >= policy.monthly_request_limit:
            db.rollback()
            raise QuotaExceededError("Monthly AI request quota exceeded")

    if policy.daily_request_limit is not None:
        daily_used = requests_used_since(db, user_id, day_since)
        daily_active = _active_reservations_since(db, user_id, day_since, now)
        if daily_used + daily_active >= policy.daily_request_limit:
            db.rollback()
            raise QuotaExceededError("Daily AI request quota exceeded")

    reservation = AIRequestReservation(
        user_id=user_id,
        status="reserved",
        expires_at=now + RESERVATION_TTL,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation.id


def complete_request_reservation(db: Session, reservation_id: int) -> None:
    """Mark a reservation as completed.

    Deliberately forgiving. A reservation that expired mid-flight is swept to
    ``released`` by the next request from the same account, and raising here
    used to abort the caller's transaction: the reply was already streamed to
    the user, but the messages were rolled back and the usage never recorded.
    That loses the user's answer and bills us for a provider call we cannot
    charge for.

    The reservation only exists to stop a single account over-committing while
    a request is in flight. Once the work is done, the accounting is settled by
    ``record_ai_usage``, so completing late is always the right outcome.
    """
    now = _now()
    reservation = (
        db.query(AIRequestReservation)
        .filter(AIRequestReservation.id == reservation_id)
        .one_or_none()
    )
    if reservation is None:
        logger.warning(
            "AI request reservation vanished before completion",
            extra={"reservation_id": reservation_id},
        )
        return
    if reservation.status == "completed":
        return
    if reservation.status != "reserved":
        logger.info(
            "Completing an AI request reservation that had already been swept",
            extra={"reservation_id": reservation_id, "previous_status": reservation.status},
        )
        reservation.released_at = None
    reservation.status = "completed"
    reservation.completed_at = now


def purge_settled_reservations(db: Session, *, now: datetime | None = None) -> int:
    """Delete old completed/released rows so the table does not grow forever."""
    cutoff = (now or _now()) - RESERVATION_RETENTION
    deleted = (
        db.query(AIRequestReservation)
        .filter(
            AIRequestReservation.status.in_(("completed", "released")),
            AIRequestReservation.created_at < cutoff,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted or 0)


def release_request_reservation(db: Session, reservation_id: int) -> None:
    now = _now()
    reservation = (
        db.query(AIRequestReservation)
        .filter(AIRequestReservation.id == reservation_id)
        .one_or_none()
    )
    if reservation is None or reservation.status != "reserved":
        return
    reservation.status = "released"
    reservation.released_at = now
