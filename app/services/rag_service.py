from __future__ import annotations

import hashlib
import logging
import re
import time
from collections.abc import Iterable

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import EMBEDDING_DIMENSIONS, Document, DocumentChunk
from app.services.embedding_usage_service import record_embedding_usage

logger = logging.getLogger(__name__)

EMBEDDING_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
EMBEDDING_MAX_BACKOFF_SECONDS = 4.0


class RAGError(RuntimeError):
    pass


class DuplicateDocumentError(RAGError):
    def __init__(self, document_id: int):
        self.document_id = document_id
        super().__init__(f"Document already exists as document {document_id}")


class DocumentIndexInProgressError(RAGError):
    pass


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = end - overlap
    return chunks


def _embedding_config() -> tuple[str, str, str]:
    base_url = settings.embedding_base_url
    api_key = settings.embedding_api_key
    model = settings.embedding_model
    if not base_url:
        if settings.ai_provider == "openai":
            base_url, api_key = settings.openai_base_url, settings.openai_api_key
        elif settings.ai_provider == "llama":
            base_url, api_key = settings.llama_base_url, settings.llama_api_key
    if not base_url or not model:
        raise RAGError("Embedding provider is not configured")
    return base_url.rstrip("/"), api_key, model


def _is_retryable_embedding_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in EMBEDDING_RETRYABLE_STATUS_CODES
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
        ),
    )


def _embed_batch(
    client: httpx.Client,
    batch: list[str],
    *,
    url: str,
    headers: dict[str, str],
    model: str,
) -> tuple[list[list[float]], int]:
    """Embed one batch, retrying transient provider failures.

    Without the retry a single network blip anywhere in a long document left the
    whole document permanently marked as failed.
    """
    attempts = settings.ai_max_retries + 1
    for attempt in range(attempts):
        try:
            response = client.post(url, headers=headers, json={"model": model, "input": batch})
            response.raise_for_status()
            data = response.json()
            embeddings = [
                item["embedding"]
                for item in sorted(data.get("data", []), key=lambda item: item.get("index", 0))
            ]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if attempt >= attempts - 1 or not _is_retryable_embedding_error(exc):
                raise RAGError("Embedding provider request failed") from exc
            logger.warning(
                "Retrying embedding request",
                extra={"attempt": attempt + 1, "batch_size": len(batch)},
            )
            time.sleep(min(2.0**attempt, EMBEDDING_MAX_BACKOFF_SECONDS))
            continue

        if len(embeddings) != len(batch):
            raise RAGError("Embedding provider returned an incomplete response")
        if any(len(vector) != EMBEDDING_DIMENSIONS for vector in embeddings):
            raise RAGError(f"Embedding dimensions must be {EMBEDDING_DIMENSIONS}")

        usage = data.get("usage") or {}
        tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        return embeddings, tokens

    raise RAGError("Embedding provider request failed")


def embed_texts(texts: Iterable[str], *, return_metadata: bool = False):
    items = [text for text in texts if text.strip()]
    if not items:
        empty_metadata = {
            "provider": settings.ai_provider,
            "model": settings.embedding_model,
            "input_tokens": 0,
        }
        return ([], empty_metadata) if return_metadata else []
    base_url, api_key, model = _embedding_config()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    batch_size = max(1, settings.embedding_batch_size)
    embeddings: list[list[float]] = []
    total_tokens = 0
    # A 10 MB document produces roughly ten thousand chunks. Sending them as one
    # array exceeds every provider's per-request array and token limits, so large
    # documents could never be indexed at all.
    with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            batch_embeddings, batch_tokens = _embed_batch(
                client,
                batch,
                url=f"{base_url}/embeddings",
                headers=headers,
                model=model,
            )
            embeddings.extend(batch_embeddings)
            total_tokens += batch_tokens

    metadata = {
        "provider": settings.ai_provider,
        "model": model,
        "input_tokens": total_tokens,
    }
    return (embeddings, metadata) if return_metadata else embeddings


def _get_document(db: Session, *, user_id: int, document_id: int) -> Document:
    document = db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    ).scalar_one_or_none()
    if not document:
        raise RAGError("Document not found")
    return document


def _validate_document_payload(*, name: str, normalized_text: str) -> str:
    clean_name = name.strip()
    if not clean_name:
        raise RAGError("Document name is empty")
    if len(clean_name) > 255:
        clean_name = clean_name[:255]
    text_size = len(normalized_text.encode("utf-8"))
    if text_size > settings.document_max_upload_bytes:
        raise RAGError("Document exceeds the upload size limit")
    return clean_name


def create_pending_document(
    db: Session,
    *,
    user_id: int,
    name: str,
    text: str,
    source: str = "text",
    mime_type: str | None = "text/plain",
) -> Document:
    normalized = normalize_text(text)
    if not normalized:
        raise RAGError("Document text is empty")
    clean_name = _validate_document_payload(name=name, normalized_text=normalized)
    digest = content_hash(normalized)
    existing = db.execute(
        select(Document).where(Document.user_id == user_id, Document.content_hash == digest)
    ).scalar_one_or_none()
    if existing:
        raise DuplicateDocumentError(existing.id)

    document = Document(
        user_id=user_id,
        name=clean_name,
        source=source,
        mime_type=mime_type,
        status="queued",
        content_hash=digest,
        raw_text=normalized,
    )
    db.add(document)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.execute(
            select(Document).where(Document.user_id == user_id, Document.content_hash == digest)
        ).scalar_one_or_none()
        if existing:
            raise DuplicateDocumentError(existing.id) from exc
        raise
    db.refresh(document)
    return document


def reindex_document(db: Session, *, user_id: int, document_id: int) -> Document:
    document = _get_document(db, user_id=user_id, document_id=document_id)
    if document.status in {"queued", "processing"}:
        raise DocumentIndexInProgressError("Document indexing is already in progress")
    document.status = "queued"
    document.last_index_error = None
    db.commit()
    return document


def delete_document(db: Session, *, user_id: int, document_id: int) -> None:
    document = _get_document(db, user_id=user_id, document_id=document_id)
    db.delete(document)
    db.commit()


def _vector_candidates(
    db: Session, *, user_id: int, query_embedding: list[float], candidate_limit: int
) -> list[tuple[DocumentChunk, float]]:
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    statement = (
        select(DocumentChunk, distance.label("distance"))
        .join(DocumentChunk.document)
        .where(
            Document.user_id == user_id,
            Document.status == "ready",
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(candidate_limit)
    )
    return [(chunk, float(distance_value)) for chunk, distance_value in db.execute(statement).all()]


def _keyword_candidates(
    db: Session, *, user_id: int, query: str, candidate_limit: int
) -> list[DocumentChunk]:
    terms = [term for term in re.findall(r"[\w.-]+", query.lower()) if len(term) >= 2][:8]
    if not terms:
        return []
    conditions = [func.lower(DocumentChunk.content).contains(term) for term in terms]
    statement = (
        select(DocumentChunk)
        .join(DocumentChunk.document)
        .where(Document.user_id == user_id, Document.status == "ready", or_(*conditions))
        .limit(candidate_limit * 2)
    )
    rows = list(db.execute(statement).scalars())
    query_terms = set(terms)
    rows.sort(
        key=lambda chunk: sum(1 for term in query_terms if term in chunk.content.lower()),
        reverse=True,
    )
    return rows[:candidate_limit]


def hybrid_retrieve_chunks(
    db: Session,
    *,
    user_id: int,
    query: str,
    limit: int = 5,
    candidate_limit: int = 20,
) -> list[tuple[DocumentChunk, float]]:
    query = query.strip()
    if not query:
        return []
    limit = min(max(limit, 1), 20)
    candidate_limit = min(max(candidate_limit, limit), 50)

    try:
        query_embedding, embedding_meta = embed_texts([query], return_metadata=True)
        vector = query_embedding[0]
        record_embedding_usage(
            db,
            user_id=user_id,
            document_id=None,
            provider=embedding_meta["provider"],
            model=embedding_meta["model"],
            input_tokens=embedding_meta["input_tokens"],
            item_count=1,
            status="success",
            commit=True,
        )
    except Exception as exc:
        try:
            db.rollback()
            record_embedding_usage(
                db,
                user_id=user_id,
                document_id=None,
                provider=settings.ai_provider,
                model=settings.embedding_model,
                item_count=1,
                status="failed",
                error_type=type(exc).__name__,
                commit=True,
            )
        except Exception:
            db.rollback()
        raise

    vector_rows = _vector_candidates(
        db, user_id=user_id, query_embedding=vector, candidate_limit=candidate_limit
    )
    keyword_rows = _keyword_candidates(
        db, user_id=user_id, query=query, candidate_limit=candidate_limit
    )

    fused: dict[int, float] = {}
    chunks: dict[int, DocumentChunk] = {}
    distances: dict[int, float] = {}
    rrf_k = 60.0

    for rank, (chunk, distance) in enumerate(vector_rows, start=1):
        fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (rrf_k + rank)
        chunks[chunk.id] = chunk
        distances[chunk.id] = distance

    for rank, chunk in enumerate(keyword_rows, start=1):
        fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (rrf_k + rank)
        chunks[chunk.id] = chunk
        distances.setdefault(chunk.id, 1.0)

    ranked = sorted(fused.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [(chunks[chunk_id], distances.get(chunk_id, 1.0)) for chunk_id, _score in ranked]


def retrieve_chunks(
    db: Session, *, user_id: int, query: str, limit: int = 5
) -> list[tuple[DocumentChunk, float]]:
    return hybrid_retrieve_chunks(db, user_id=user_id, query=query, limit=limit)


def build_context(results: list[tuple[DocumentChunk, float]]) -> str:
    return "\n\n".join(
        f"[Source {chunk.document.name}#{chunk.chunk_index}]\n{chunk.content}"
        for chunk, _ in results
    )
