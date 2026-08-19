from datetime import datetime, timezone

from app.models.embedding_usage import EmbeddingUsage
from app.services.embedding_usage_service import embedding_usage_summary, record_embedding_usage


def test_embedding_usage_summary(db, user):
    record_embedding_usage(
        db,
        user_id=user.id,
        document_id=None,
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=120,
        item_count=3,
        duration_ms=200,
    )
    record_embedding_usage(
        db,
        user_id=user.id,
        document_id=None,
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=80,
        item_count=2,
        duration_ms=100,
    )

    summary = embedding_usage_summary(db, user_id=user.id, since=datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0))

    assert summary == {"input_tokens": 200, "item_count": 5, "requests": 2}
    assert db.query(EmbeddingUsage).count() == 2
