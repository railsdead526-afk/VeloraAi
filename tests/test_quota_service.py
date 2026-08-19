from datetime import datetime, timedelta, timezone

import pytest

from app.models.ai_usage import AIUsage
from app.services.quota_service import (
    QuotaExceededError,
    enforce_monthly_token_quota,
    tokens_used_since,
)
from tests.conftest import TestingSessionLocal


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_tokens_used_since(db):
    user_id = 1
    now = datetime.now(timezone.utc)
    db.add(
        AIUsage(
            user_id=user_id,
            conversation_id=1,
            provider="mock",
            model="mock",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            created_at=now,
        )
    )
    db.add(
        AIUsage(
            user_id=user_id,
            conversation_id=1,
            provider="mock",
            model="mock",
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
            created_at=now - timedelta(days=60),
        )
    )
    db.commit()

    since = now - timedelta(days=1)
    assert tokens_used_since(db, user_id, since) == 15


def test_quota_allows_unlimited(db):
    enforce_monthly_token_quota(db, user_id=1, monthly_limit=None)


def test_quota_blocks_when_limit_reached(db):
    now = datetime.now(timezone.utc)
    db.add(
        AIUsage(
            user_id=1,
            conversation_id=1,
            provider="mock",
            model="mock",
            input_tokens=60,
            output_tokens=40,
            total_tokens=100,
            created_at=now,
        )
    )
    db.commit()

    with pytest.raises(QuotaExceededError):
        enforce_monthly_token_quota(db, user_id=1, monthly_limit=100)


def test_quota_rejects_negative_limit(db):
    with pytest.raises(ValueError):
        enforce_monthly_token_quota(db, user_id=1, monthly_limit=-1)
