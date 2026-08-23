import logging
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document, DocumentChunk
from app.services.embedding_usage_service import record_embedding_usage
from app.services.rag_service import RAGError, chunk_text, content_hash, embed_texts, normalize_text

logger = logging.getLogger(__name__)


def process_document_index(document_id: int, db: Session | None = None) -> None:
    owns_session = db is None
    if db is None:
        db = SessionLocal()

    document = None
    started = time.perf_counter()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None or document.status != "queued":
            return

        claimed = (
            db.query(Document)
            .filter(Document.id == document_id, Document.status == "queued")
            .update(
                {
                    "status": "processing",
                    "indexing_attempts": Document.indexing_attempts + 1,
                    "last_index_error": None,
                },
                synchronize_session=False,
            )
        )
        if claimed != 1:
            db.rollback()
            return
        db.commit()
        db.refresh(document)

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

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete(
            synchronize_session=False
        )
        for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
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
        document.last_indexed_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("RAG indexing failed document_id=%s", document_id)

        failed = db.query(Document).filter(Document.id == document_id).first()
        if failed is None:
            return

        try:
            record_embedding_usage(
                db,
                user_id=failed.user_id,
                document_id=failed.id,
                provider=settings.ai_provider,
                model=settings.embedding_model,
                duration_ms=int((time.perf_counter() - started) * 1000),
                status="failed",
                error_type=type(exc).__name__,
                commit=False,
            )
        except Exception:
            db.rollback()
            logger.exception("Failed to record RAG indexing failure document_id=%s", document_id)

        failed = db.query(Document).filter(Document.id == document_id).first()
        if failed is not None:
            failed.status = "failed"
            # RAGError messages are written for the user and carry no provider
            # internals; anything else is reported by type only.
            detail = str(exc) if isinstance(exc, RAGError) and str(exc) else type(exc).__name__
            failed.last_index_error = detail[:255]
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Failed to persist RAG failure state document_id=%s", document_id)
    finally:
        if owns_session:
            db.close()
