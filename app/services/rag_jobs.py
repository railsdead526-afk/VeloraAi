import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document, DocumentChunk
from app.services.embedding_usage_service import record_embedding_usage
from app.services.rag_service import RAGError, embed_texts, chunk_text, normalize_text, content_hash


def process_document_index(document_id: int) -> None:
    db: Session = SessionLocal()
    document = None
    started = time.perf_counter()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            return
        if document.status not in {"queued", "processing"}:
            return

        document.status = "processing"
        document.indexing_attempts = int(document.indexing_attempts or 0) + 1
        document.last_index_error = None
        db.commit()

        normalized = normalize_text(document.raw_text)
        chunks = chunk_text(normalized)
        if not chunks:
            raise RAGError("Document text is empty")

        embeddings_started = time.perf_counter()
        embeddings, embedding_meta = embed_texts(chunks, return_metadata=True)
        duration_ms = int((time.perf_counter() - embeddings_started) * 1000)
        record_embedding_usage(
            db,
            user_id=document.user_id,
            document_id=document.id,
            provider=embedding_meta["provider"],
            model=embedding_meta["model"],
            input_tokens=embedding_meta["input_tokens"],
            item_count=len(chunks),
            duration_ms=duration_ms,
            status="success",
            commit=False,
        )

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete(synchronize_session=False)
        for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk_content,
                    embedding=embedding,
                )
            )
        document.content_hash = content_hash(normalized)
        document.status = "ready"
        document.last_index_error = None
        document.last_indexed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        if document is not None:
            try:
                record_embedding_usage(
                    db,
                    user_id=document.user_id,
                    document_id=document.id,
                    provider=settings.ai_provider,
                    model=settings.embedding_model,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    status="failed",
                    error_type=type(exc).__name__,
                    commit=False,
                )
                document.status = "failed"
                document.last_index_error = type(exc).__name__
                db.commit()
            except Exception:
                db.rollback()
    finally:
        db.close()
