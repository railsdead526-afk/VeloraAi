from datetime import UTC, datetime, timedelta

import pytest

from app.core.plans import PlanPolicy
from app.models.ai_request_reservation import AIRequestReservation
from app.services.quota_service import (
    QuotaExceededError,
    release_request_reservation,
    reserve_plan_request_quota,
)


def _policy(daily: int = 1, monthly: int = 10) -> PlanPolicy:
    return PlanPolicy(
        name="test",
        monthly_token_limit=100_000,
        monthly_request_limit=monthly,
        daily_request_limit=daily,
        monthly_embedding_token_limit=None,
        max_documents=None,
    )


def test_reservation_blocks_second_request(db, user):
    policy = _policy(daily=1, monthly=10)

    first = reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    assert first is not None

    with pytest.raises(QuotaExceededError, match="Daily AI request quota exceeded"):
        reserve_plan_request_quota(db, user_id=user.id, policy=policy)


def test_released_reservation_returns_slot(db, user):
    policy = _policy(daily=1, monthly=10)

    first = reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    assert first is not None
    release_request_reservation(db, first)
    db.commit()

    second = reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    assert second is not None


def test_expired_reservation_does_not_block_quota(db, user):
    policy = _policy(daily=1, monthly=10)

    first = reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    assert first is not None

    reservation = db.query(AIRequestReservation).filter(AIRequestReservation.id == first).one()
    reservation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    second = reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    assert second is not None

    expired = db.query(AIRequestReservation).filter(AIRequestReservation.id == first).one()
    assert expired.status == "released"
