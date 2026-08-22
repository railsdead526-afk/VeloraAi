from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.embedding_usage import EmbeddingUsage


def record_embedding_usage(
    db: Session,
    *,
    user_id: int,
    document_id: int | None,
    provider: str,
    model: str,
    input_tokens: int = 0,
    item_count: int = 0,
    duration_ms: int = 0,
    status: str = "success",
    error_type: str | None = None,
    commit: bool = True,
) -> EmbeddingUsage:
    entry = EmbeddingUsage(
        user_id=user_id,
        document_id=document_id,
        provider=provider,
        model=model,
        input_tokens=max(0, int(input_tokens)),
        item_count=max(0, int(item_count)),
        duration_ms=max(0, int(duration_ms)),
        status=status,
        error_type=error_type,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def embedding_usage_summary(
    db: Session, *, user_id: int, since: datetime | None = None
) -> dict[str, int]:
    query = db.query(
        func.coalesce(func.sum(EmbeddingUsage.input_tokens), 0),
        func.coalesce(func.sum(EmbeddingUsage.item_count), 0),
        func.count(EmbeddingUsage.id),
    ).filter(EmbeddingUsage.user_id == user_id)
    if since is not None:
        query = query.filter(EmbeddingUsage.created_at >= since)
    tokens, items, requests = query.one()
    return {
        "input_tokens": int(tokens or 0),
        "item_count": int(items or 0),
        "requests": int(requests or 0),
    }
