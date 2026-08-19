from __future__ import annotations

import re
from typing import Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentChunk, EMBEDDING_DIMENSIONS


class RAGError(RuntimeError):
    pass


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
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


def ingest_text(db: Session, *, user_id: int, name: str, text: str, source: str = "text", mime_type: str | None = "text/plain") -> Document:
    chunks = chunk_text(text)
    if not chunks:
        raise RAGError("Document text is empty")
    embeddings = embed_texts(chunks)
    document = Document(user_id=user_id, name=name.strip()[:255], source=source, mime_type=mime_type, status="ready")
    db.add(document)
    db.flush()
    for index, (content, embedding) in enumerate(zip(chunks, embeddings)):
        db.add(DocumentChunk(document_id=document.id, chunk_index=index, content=content, embedding=embedding))
    db.commit()
    db.refresh(document)
    return document


def retrieve_chunks(db: Session, *, user_id: int, query: str, limit: int = 5) -> list[tuple[DocumentChunk, float]]:
    query = query.strip()
    if not query:
        return []
    limit = min(max(limit, 1), 20)
    query_embedding = embed_texts([query])[0]
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    statement = (
        select(DocumentChunk, distance.label("distance"))
        .join(DocumentChunk.document)
        .where(Document.user_id == user_id, Document.status == "ready")
        .order_by(distance)
        .limit(limit)
    )
    rows = db.execute(statement).all()
    return [(chunk, float(distance_value)) for chunk, distance_value in rows]


def build_context(results: list[tuple[DocumentChunk, float]]) -> str:
    return "\n\n".join(
        f"[Source {chunk.document.name}#{chunk.chunk_index}]\n{chunk.content}"
        for chunk, _ in results
    )
