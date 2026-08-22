from datetime import UTC, datetime, timedelta

import pytest

from app.core.plans import get_plan_policy
from app.models.ai_usage import AIUsage
from app.models.conversation import Conversation
from app.models.user import User
from app.services.quota_service import (
    QuotaExceededError,
    enforce_monthly_token_quota,
    enforce_plan_quota,
    tokens_used_since,
)


def _seed_user_and_conversation(db):
    user = User(email="quota-test@example.com", hashed_password="test", role="free")
    db.add(user)
    db.flush()
    conversation = Conversation(title="Quota Test", user_id=user.id)
    db.add(conversation)
    db.flush()
    return user, conversation


def _add_usage(db, user, conversation, *, created_at):
    db.add(
        AIUsage(
            user_id=user.id,
            conversation_id=conversation.id,
            provider="mock",
            model="mock",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            created_at=created_at,
        )
    )
    db.commit()


def test_tokens_used_since(db):
    user, conversation = _seed_user_and_conversation(db)
    now = datetime.now(UTC)
    _add_usage(db, user, conversation, created_at=now)
    _add_usage(db, user, conversation, created_at=now - timedelta(days=60))
    assert tokens_used_since(db, user.id, now - timedelta(days=1)) == 15


def test_quota_allows_unlimited(db):
    user, _ = _seed_user_and_conversation(db)
    enforce_monthly_token_quota(db, user_id=user.id, monthly_limit=None)


def test_quota_blocks_when_limit_reached(db):
    user, conversation = _seed_user_and_conversation(db)
    db.add(
        AIUsage(
            user_id=user.id,
            conversation_id=conversation.id,
            provider="mock",
            model="mock",
            input_tokens=60,
            output_tokens=40,
            total_tokens=100,
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    with pytest.raises(QuotaExceededError):
        enforce_monthly_token_quota(db, user_id=user.id, monthly_limit=100)


def test_quota_allows_request_that_exactly_reaches_limit(db):
    user, conversation = _seed_user_and_conversation(db)
    db.add(
        AIUsage(
            user_id=user.id,
            conversation_id=conversation.id,
            provider="mock",
            model="mock",
            input_tokens=60,
            output_tokens=30,
            total_tokens=90,
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    enforce_monthly_token_quota(db, user_id=user.id, monthly_limit=100, additional_tokens=10)


def test_quota_blocks_request_that_would_exceed_limit(db):
    user, conversation = _seed_user_and_conversation(db)
    db.add(
        AIUsage(
            user_id=user.id,
            conversation_id=conversation.id,
            provider="mock",
            model="mock",
            input_tokens=60,
            output_tokens=30,
            total_tokens=90,
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    with pytest.raises(QuotaExceededError):
        enforce_monthly_token_quota(db, user_id=user.id, monthly_limit=100, additional_tokens=11)


def test_quota_rejects_negative_limit(db):
    with pytest.raises(ValueError):
        enforce_monthly_token_quota(db, user_id=1, monthly_limit=-1)


def test_quota_rejects_negative_additional_tokens(db):
    user, _ = _seed_user_and_conversation(db)
    with pytest.raises(ValueError):
        enforce_monthly_token_quota(db, user_id=user.id, monthly_limit=100, additional_tokens=-1)


def test_free_plan_daily_request_limit(db):
    user, conversation = _seed_user_and_conversation(db)
    now = datetime.now(UTC)
    for _ in range(20):
        _add_usage(db, user, conversation, created_at=now)

    with pytest.raises(QuotaExceededError, match="Daily AI request quota exceeded"):
        enforce_plan_quota(db, user_id=user.id, policy=get_plan_policy("free"))


def test_free_plan_daily_request_limit_resets_after_day_boundary(db):
    user, conversation = _seed_user_and_conversation(db)
    yesterday = datetime.now(UTC) - timedelta(days=1, minutes=1)
    for _ in range(20):
        _add_usage(db, user, conversation, created_at=yesterday)

    enforce_plan_quota(db, user_id=user.id, policy=get_plan_policy("free"))


def test_admin_is_unlimited(db):
    user, _ = _seed_user_and_conversation(db)
    enforce_plan_quota(db, user_id=user.id, policy=get_plan_policy("admin"))
