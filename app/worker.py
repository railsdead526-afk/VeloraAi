from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document
from app.services.rag_jobs import process_document_index

logger = logging.getLogger("veloraai.worker")


def recover_stale_documents(db, *, now: datetime | None = None) -> int:
    """Requeue documents abandoned by a crashed or restarted worker."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=settings.rag_processing_stale_seconds)
    recovered = (
        db.query(Document)
        .filter(
            Document.status == "processing",
            Document.updated_at < cutoff,
        )
        .update(
            {
                Document.status: "queued",
                Document.last_index_error: "recovered_after_worker_timeout",
            },
            synchronize_session=False,
        )
    )
    if recovered:
        db.commit()
    return recovered


def queued_document_ids(db, *, limit: int | None = None) -> list[int]:
    query = (
        db.query(Document.id)
        .filter(
            or_(
                Document.status == "queued",
                and_(
                    Document.status == "processing",
                    Document.updated_at
                    < datetime.now(timezone.utc)
                    - timedelta(seconds=settings.rag_processing_stale_seconds),
                ),
            )
        )
        .order_by(Document.created_at.asc(), Document.id.asc())
    )
    return [document_id for (document_id,) in query.limit(limit or settings.rag_worker_batch_size).all()]


def run_worker_once() -> int:
    with SessionLocal() as db:
        recover_stale_documents(db)
        document_ids = queued_document_ids(db)

    for document_id in document_ids:
        try:
            process_document_index(document_id)
        except Exception:
            # process_document_index persists failure state itself; this guard
            # keeps one bad document from stopping the worker loop.
            logger.exception("RAG worker failed document_id=%s", document_id)
    return len(document_ids)


def run_worker_forever() -> None:
    logger.info(
        "RAG worker started poll_seconds=%s batch_size=%s stale_seconds=%s",
        settings.rag_worker_poll_seconds,
        settings.rag_worker_batch_size,
        settings.rag_processing_stale_seconds,
    )
    while True:
        processed = run_worker_once()
        if processed == 0:
            time.sleep(settings.rag_worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker_forever()
