from __future__ import annotations

import hashlib
import re
from typing import Iterable

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentChunk, EMBEDDING_DIMENSIONS


class RAGError(RuntimeError):
    pass


class DuplicateDocumentError(RAGError):
    def __init__(self, document_id: int):
        self.document_id = document_id
        super().__init__(f"Document already exists as document {document_id}")


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


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    items = [text for text in texts if text.strip()]
    if not items:
        return []
    base_url, api_key, model = _embedding_config()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = httpx.post(
            f"{base_url}/embeddings",
            headers=headers,
            json={"model": model, "input": items},
            timeout=settings.ai_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = [item["embedding"] for item in sorted(data.get("data", []), key=lambda item: item.get("index", 0))]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise RAGError("Embedding provider request failed") from exc
    if len(embeddings) != len(items):
        raise RAGError("Embedding provider returned an incomplete response")
    if any(len(vector) != EMBEDDING_DIMENSIONS for vector in embeddings):
        raise RAGError(f"Embedding dimensions must be {EMBEDDING_DIMENSIONS}")
    return embeddings


def _get_document(db: Session, *, user_id: int, document_id: int) -> Document:
    document = db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    ).scalar_one_or_none()
    if not document:
        raise RAGError("Document not found")
    return document


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
    digest = content_hash(normalized)
    existing = db.execute(
        select(Document).where(Document.user_id == user_id, Document.content_hash == digest)
    ).scalar_one_or_none()
    if existing:
        raise DuplicateDocumentError(existing.id)

    document = Document(
        user_id=user_id,
        name=name.strip()[:255],
        source=source,
        mime_type=mime_type,
        status="queued",
        content_hash=digest,
        raw_text=normalized,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def ingest_text(
    db: Session,
    *,
    user_id: int,
    name: str,
    text: str,
    source: str = "text",
    mime_type: str | None = "text/plain",
) -> Document:
    document = create_pending_document(
        db,
        user_id=user_id,
        name=name,
        text=text,
        source=source,
        mime_type=mime_type,
    )
    try:
        chunks = chunk_text(document.raw_text)
        embeddings = embed_texts(chunks)
        for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(DocumentChunk(document_id=document.id, chunk_index=index, content=chunk_content, embedding=embedding))
        document.status = "ready"
        db.commit()
        db.refresh(document)
        return document
    except Exception:
        db.rollback()
        document = _get_document(db, user_id=user_id, document_id=document.id)
        document.status = "failed"
        db.commit()
        raise


def reindex_document(db: Session, *, user_id: int, document_id: int) -> Document:
    document = _get_document(db, user_id=user_id, document_id=document_id)
    document.status = "queued"
    db.commit()
    return document


def delete_document(db: Session, *, user_id: int, document_id: int) -> None:
    document = _get_document(db, user_id=user_id, document_id=document_id)
    db.delete(document)
    db.commit()


def _vector_candidates(db: Session, *, user_id: int, query_embedding: list[float], candidate_limit: int) -> list[tuple[DocumentChunk, float]]:
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    statement = (
        select(DocumentChunk, distance.label("distance"))
        .join(DocumentChunk.document)
        .where(Document.user_id == user_id, Document.status == "ready", DocumentChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(candidate_limit)
    )
    return [(chunk, float(distance_value)) for chunk, distance_value in db.execute(statement).all()]


def _keyword_candidates(db: Session, *, user_id: int, query: str, candidate_limit: int) -> list[DocumentChunk]:
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
    rows.sort(key=lambda chunk: sum(1 for term in query_terms if term in chunk.content.lower()), reverse=True)
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

    query_embedding = embed_texts([query])[0]
    vector_rows = _vector_candidates(db, user_id=user_id, query_embedding=query_embedding, candidate_limit=candidate_limit)
    keyword_rows = _keyword_candidates(db, user_id=user_id, query=query, candidate_limit=candidate_limit)

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


def retrieve_chunks(db: Session, *, user_id: int, query: str, limit: int = 5) -> list[tuple[DocumentChunk, float]]:
    return hybrid_retrieve_chunks(db, user_id=user_id, query=query, limit=limit)


def build_context(results: list[tuple[DocumentChunk, float]]) -> str:
    return "\n\n".join(
        f"[Source {chunk.document.name}#{chunk.chunk_index}]\n{chunk.content}"
        for chunk, _ in results
    )
