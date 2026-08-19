from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_usage import AIUsage
from app.services.plan_service import PlanPolicy


class QuotaExceededError(Exception):
    """Raised when a configured AI usage quota is exceeded."""


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


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


def enforce_monthly_token_quota(
    db: Session,
    *,
    user_id: int,
    monthly_limit: int | None,
) -> None:
    if monthly_limit is None:
        return
    if monthly_limit < 0:
        raise ValueError("monthly_limit must be non-negative")

    used = tokens_used_since(db, user_id, _month_start())
    if used >= monthly_limit:
        raise QuotaExceededError("Monthly AI token quota exceeded")


def enforce_plan_quota(db: Session, *, user_id: int, policy: PlanPolicy) -> None:
    since = _month_start()
    if policy.monthly_token_limit is not None:
        enforce_monthly_token_quota(
            db,
            user_id=user_id,
            monthly_limit=policy.monthly_token_limit,
        )
    if policy.monthly_request_limit is not None:
        used = requests_used_since(db, user_id, since)
        if used >= policy.monthly_request_limit:
            raise QuotaExceededError("Monthly AI request quota exceeded")
