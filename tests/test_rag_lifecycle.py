from unittest.mock import patch

import pytest

from app.models.document import Document
from app.models.user import User
from app.services.rag_jobs import process_document_index
from app.services.rag_service import DuplicateDocumentError, RAGError, delete_document, ingest_text, reindex_document


@pytest.fixture
def users(db):
    owner = User(email="owner@example.com", hashed_password="hash", role="free")
    other = User(email="other@example.com", hashed_password="hash", role="free")
    db.add_all([owner, other])
    db.commit()
    db.refresh(owner)
    db.refresh(other)
    return owner, other


def test_ingest_document_rejects_duplicate_content(db, users):
    owner, _ = users
    with patch("app.services.rag_service.embed_texts", return_value=[[0.0] * 1536]):
        document = ingest_text(db, user_id=owner.id, name="one", text="same content")
        with pytest.raises(DuplicateDocumentError) as exc:
            ingest_text(db, user_id=owner.id, name="two", text="same content")

    assert exc.value.document_id == document.id


def test_reindex_queues_and_job_rebuilds_chunks(db, users):
    owner, _ = users
    with patch("app.services.rag_service.embed_texts", return_value=[[0.0] * 1536]):
        document = ingest_text(db, user_id=owner.id, name="one", text="first content")
        document.raw_text = "changed content"
        db.commit()
        queued = reindex_document(db, user_id=owner.id, document_id=document.id)
        assert queued.status == "queued"
        process_document_index(document.id)

    db.refresh(document)
    assert document.status == "ready"
    assert document.chunks[0].content == "changed content"


def test_delete_document_is_user_scoped(db, users):
    owner, other = users
    with patch("app.services.rag_service.embed_texts", return_value=[[0.0] * 1536]):
        document = ingest_text(db, user_id=owner.id, name="one", text="owned")
        with pytest.raises(RAGError, match="Document not found"):
            delete_document(db, user_id=other.id, document_id=document.id)
        delete_document(db, user_id=owner.id, document_id=document.id)

    assert db.query(Document).filter(Document.id == document.id).first() is None
