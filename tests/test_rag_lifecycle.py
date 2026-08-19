from unittest.mock import patch

import pytest

from app.models.document import Document
from app.services.rag_service import DuplicateDocumentError, delete_document, ingest_text, reindex_document


@pytest.mark.usefixtures("db")
def test_ingest_document_rejects_duplicate_content(db):
    with patch("app.services.rag_service.embed_texts", return_value=[[0.0] * 1536]):
        document = ingest_text(db, user_id=1, name="one", text="same content")
        with pytest.raises(DuplicateDocumentError) as exc:
            ingest_text(db, user_id=1, name="two", text="same content")

    assert exc.value.document_id == document.id


@pytest.mark.usefixtures("db")
def test_reindex_rebuilds_chunks(db):
    with patch("app.services.rag_service.embed_texts", return_value=[[0.0] * 1536]):
        document = ingest_text(db, user_id=1, name="one", text="first content")
        document.raw_text = "changed content"
        db.commit()
        reindexed = reindex_document(db, user_id=1, document_id=document.id)

    assert reindexed.status == "ready"
    assert reindexed.chunks[0].content == "changed content"


@pytest.mark.usefixtures("db")
def test_delete_document_is_user_scoped(db):
    with patch("app.services.rag_service.embed_texts", return_value=[[0.0] * 1536]):
        document = ingest_text(db, user_id=1, name="one", text="owned")
        with pytest.raises(Exception):
            delete_document(db, user_id=2, document_id=document.id)
        delete_document(db, user_id=1, document_id=document.id)

    assert db.query(Document).filter(Document.id == document.id).first() is None
