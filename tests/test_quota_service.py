from datetime import datetime, timedelta, timezone

import pytest

from app.models.ai_usage import AIUsage
from app.models.conversation import Conversation
from app.models.user import User
from app.services.quota_service import (
    QuotaExceededError,
    enforce_monthly_token_quota,
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


def test_tokens_used_since(db):
    user, conversation = _seed_user_and_conversation(db)
    now = datetime.now(timezone.utc)
    db.add(AIUsage(user_id=user.id, conversation_id=conversation.id, provider="mock", model="mock", input_tokens=10, output_tokens=5, total_tokens=15, created_at=now))
    db.add(AIUsage(user_id=user.id, conversation_id=conversation.id, provider="mock", model="mock", input_tokens=20, output_tokens=10, total_tokens=30, created_at=now - timedelta(days=60)))
    db.commit()
    assert tokens_used_since(db, user.id, now - timedelta(days=1)) == 15


def test_quota_allows_unlimited(db):
    user, _ = _seed_user_and_conversation(db)
    enforce_monthly_token_quota(db, user_id=user.id, monthly_limit=None)


def test_quota_blocks_when_limit_reached(db):
    user, conversation = _seed_user_and_conversation(db)
    db.add(AIUsage(user_id=user.id, conversation_id=conversation.id, provider="mock", model="mock", input_tokens=60, output_tokens=40, total_tokens=100, created_at=datetime.now(timezone.utc)))
    db.commit()
    with pytest.raises(QuotaExceededError):
        enforce_monthly_token_quota(db, user_id=user.id, monthly_limit=100)


def test_quota_rejects_negative_limit(db):
    with pytest.raises(ValueError):
        enforce_monthly_token_quota(db, user_id=1, monthly_limit=-1)
