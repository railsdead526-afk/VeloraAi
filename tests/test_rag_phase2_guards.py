from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

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
    existing = Document(
        user_id=user.id,
        name="existing.txt",
        source="text",
        mime_type="text/plain",
        status="ready",
        content_hash="a" * 64,
        raw_text="same content",
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)

    original_commit = db.commit
    first_commit = True

    def simulated_race():
        nonlocal first_commit
        if first_commit:
            first_commit = False
            raise IntegrityError("INSERT", {}, RuntimeError("unique constraint"))
        original_commit()

    with patch.object(db, "commit", side_effect=simulated_race):
        with pytest.raises(DuplicateDocumentError) as exc:
            create_pending_document(
                db,
                user_id=user.id,
                name="race.txt",
                text="same content",
            )

    assert exc.value.document_id == existing.id


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
