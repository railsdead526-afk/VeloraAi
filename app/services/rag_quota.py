"""Cost ceilings for retrieval.

Embedding calls are billed by the provider per token. Before this module
existed the usage was recorded in `embedding_usage` and never read back, so
nothing stopped a Free account from indexing documents until the provider bill
arrived. Measuring a cost without acting on it is not a control.

Two ceilings, checked before any provider call:

  * monthly embedding tokens — the direct spend
  * stored document count — bounds both storage and how much a single
    re-index request can cost

The token estimate is intentionally made *before* the work, from the text
length, because the real figure is only known after the money is spent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.plans import PlanPolicy
from app.models.document import Document
from app.models.embedding_usage import EmbeddingUsage

#: Rough characters-per-token for embedding models. Deliberately low, so the
#: estimate errs towards over-counting and the ceiling is never overshot.
CHARS_PER_TOKEN = 3


class EmbeddingQuotaExceededError(Exception):
    """Raised when indexing would exceed the plan's embedding budget."""


class DocumentLimitExceededError(Exception):
    """Raised when the account already holds as many documents as it may."""


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def estimate_tokens(text: str) -> int:
    """Upper-ish bound on the tokens embedding `text` will consume."""
    return max(1, len(text or "") // CHARS_PER_TOKEN)


def embedding_tokens_this_month(db: Session, *, user_id: int) -> int:
    total = (
        db.query(func.coalesce(func.sum(EmbeddingUsage.input_tokens), 0))
        .filter(
            EmbeddingUsage.user_id == user_id,
            EmbeddingUsage.created_at >= _month_start(),
        )
        .scalar()
    )
    return int(total or 0)


def document_count(db: Session, *, user_id: int) -> int:
    total = db.query(func.count(Document.id)).filter(Document.user_id == user_id).scalar()
    return int(total or 0)


def enforce_document_limit(db: Session, *, user_id: int, policy: PlanPolicy) -> None:
    if policy.max_documents is None:
        return
    if document_count(db, user_id=user_id) >= policy.max_documents:
        raise DocumentLimitExceededError(
            f"The {policy.name} plan allows {policy.max_documents} documents. "
            "Delete one or upgrade to add more."
        )


def enforce_embedding_quota(
    db: Session, *, user_id: int, policy: PlanPolicy, additional_tokens: int = 0
) -> None:
    if policy.monthly_embedding_token_limit is None:
        return

    used = embedding_tokens_this_month(db, user_id=user_id)
    if used + additional_tokens > policy.monthly_embedding_token_limit:
        raise EmbeddingQuotaExceededError(
            f"Monthly indexing quota reached for the {policy.name} plan "
            f"({used:,} of {policy.monthly_embedding_token_limit:,} tokens used). "
            "It resets at the start of next month."
        )


def enforce_indexing_allowed(
    db: Session, *, user_id: int, policy: PlanPolicy, text: str, is_new_document: bool
) -> None:
    """Single gate for every path that triggers embedding work.

    `is_new_document` is False for re-indexing, which must still consume
    embedding budget — re-indexing calls the provider exactly like a first
    index — but must not be refused for hitting the document count, since it
    adds no document.
    """
    if is_new_document:
        enforce_document_limit(db, user_id=user_id, policy=policy)
    enforce_embedding_quota(
        db, user_id=user_id, policy=policy, additional_tokens=estimate_tokens(text)
    )


def embedding_quota_snapshot(db: Session, *, user_id: int, policy: PlanPolicy) -> dict:
    """What the account has used, for display in the UI."""
    used = embedding_tokens_this_month(db, user_id=user_id)
    documents = document_count(db, user_id=user_id)
    return {
        "embedding_tokens_used": used,
        "embedding_token_limit": policy.monthly_embedding_token_limit,
        "documents_used": documents,
        "document_limit": policy.max_documents,
    }
