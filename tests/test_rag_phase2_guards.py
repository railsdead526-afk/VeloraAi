from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.document import Document
from app.models.user import User
from app.services.rag_service import (
    DocumentIndexInProgressError,
    DuplicateDocumentError,
    create_pending_document,
    reindex_document,
)


def _seed_user(db):
    user = User(
        email="rag-phase2-guard@example.com",
        hashed_password="test",
        role="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_duplicate_ingest_race_returns_domain_error(db):
    user = _seed_user(db)
    user_id = user.id
    existing = Document(
        user_id=user_id,
        name="existing.txt",
        source="text",
        mime_type="text/plain",
        status="ready",
        content_hash="a636bd7cd42060a4d07fa1bfbcc010eb7794c2ba721e1e3e4c20335a15b66eaf",
        raw_text="same content",
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)

    real_execute = db.execute
    first_lookup = True

    def simulated_stale_read(statement, *args, **kwargs):
        nonlocal first_lookup
        if first_lookup:
            first_lookup = False

            class EmptyResult:
                def scalar_one_or_none(self):
                    return None

            return EmptyResult()
        return real_execute(statement, *args, **kwargs)

    with (
        patch.object(db, "execute", side_effect=simulated_stale_read),
        pytest.raises(DuplicateDocumentError) as exc,
    ):
        create_pending_document(
            db,
            user_id=user_id,
            name="race.txt",
            text="same content",
        )

    assert exc.value.document_id == existing.id
    persisted = real_execute(select(Document).where(Document.id == existing.id)).scalar_one()
    assert (
        persisted.content_hash == "a636bd7cd42060a4d07fa1bfbcc010eb7794c2ba721e1e3e4c20335a15b66eaf"
    )


def test_reindex_rejects_document_already_queued(db):
    user = _seed_user(db)
    document = Document(
        user_id=user.id,
        name="queued.txt",
        source="text",
        mime_type="text/plain",
        status="queued",
        content_hash="b" * 64,
        raw_text="queued",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    with pytest.raises(DocumentIndexInProgressError):
        reindex_document(db, user_id=user.id, document_id=document.id)


def test_reindex_rejects_document_currently_processing(db):
    user = _seed_user(db)
    document = Document(
        user_id=user.id,
        name="processing.txt",
        source="text",
        mime_type="text/plain",
        status="processing",
        content_hash="c" * 64,
        raw_text="processing",
        indexing_attempts=1,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    with pytest.raises(DocumentIndexInProgressError):
        reindex_document(db, user_id=user.id, document_id=document.id)


def test_failed_document_can_be_requeued(db):
    user = _seed_user(db)
    document = Document(
        user_id=user.id,
        name="failed.txt",
        source="text",
        mime_type="text/plain",
        status="failed",
        content_hash="d" * 64,
        raw_text="failed",
        indexing_attempts=2,
        last_index_error="RAGError",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    result = reindex_document(db, user_id=user.id, document_id=document.id)

    assert result.status == "queued"
    assert result.last_index_error is None
    assert result.indexing_attempts == 2
