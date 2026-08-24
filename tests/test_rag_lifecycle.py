"""Document lifecycle tests.

These exercise the real production path: the API creates a pending document and
the background job indexes it. An older ``ingest_text`` helper did both in one
call, but nothing outside the tests used it and it never recorded embedding
usage, so a document indexed through it consumed quota for free.
"""

from unittest.mock import patch

import pytest

from app.models.document import Document
from app.models.user import User
from app.services.rag_jobs import process_document_index
from app.services.rag_service import (
    DuplicateDocumentError,
    RAGError,
    create_pending_document,
    delete_document,
    reindex_document,
)


@pytest.fixture
def users(db):
    owner = User(email="owner@example.com", hashed_password="hash", role="free")
    other = User(email="other@example.com", hashed_password="hash", role="free")
    db.add_all([owner, other])
    db.commit()
    db.refresh(owner)
    db.refresh(other)
    return owner, other


def _mock_embed(texts, *, return_metadata=False):
    vectors = [[0.0] * 1536 for _ in texts]
    if return_metadata:
        return vectors, {"provider": "test", "model": "test-embedding", "input_tokens": 3}
    return vectors


def _index(db, document):
    with patch("app.services.rag_jobs.embed_texts", side_effect=_mock_embed):
        process_document_index(document.id, db=db)
    db.refresh(document)
    return document


def test_ingest_document_rejects_duplicate_content(db, users):
    owner, _ = users
    document = create_pending_document(db, user_id=owner.id, name="one", text="same content")
    _index(db, document)

    with pytest.raises(DuplicateDocumentError) as exc:
        create_pending_document(db, user_id=owner.id, name="two", text="same content")

    assert exc.value.document_id == document.id


def test_indexing_records_embedding_usage(db, users):
    """Indexing must bill the tokens it consumes, otherwise quotas never fill up."""
    from app.services.embedding_usage_service import embedding_usage_summary

    owner, _ = users
    document = create_pending_document(db, user_id=owner.id, name="one", text="first content")
    _index(db, document)

    summary = embedding_usage_summary(db, user_id=owner.id)
    assert summary["requests"] == 1
    assert summary["input_tokens"] == 3


def test_reindex_queues_and_job_rebuilds_chunks(db, users):
    owner, _ = users
    document = create_pending_document(db, user_id=owner.id, name="one", text="first content")
    _index(db, document)
    assert document.status == "ready"

    document.raw_text = "changed content"
    db.commit()
    queued = reindex_document(db, user_id=owner.id, document_id=document.id)
    assert queued.status == "queued"

    _index(db, document)
    assert document.status == "ready"
    assert document.chunks[0].content == "changed content"


def test_delete_document_is_user_scoped(db, users):
    owner, other = users
    document = create_pending_document(db, user_id=owner.id, name="one", text="owned")
    _index(db, document)

    with pytest.raises(RAGError, match="Document not found"):
        delete_document(db, user_id=other.id, document_id=document.id)
    delete_document(db, user_id=owner.id, document_id=document.id)

    assert db.query(Document).filter(Document.id == document.id).first() is None
