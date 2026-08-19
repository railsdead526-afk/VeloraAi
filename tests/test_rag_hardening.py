from app.models.document import Document
from app.models.user import User
from app.services.embedding_usage_service import embedding_usage_summary, record_embedding_usage
from app.services.rag_service import embed_texts, reindex_document


def test_reindex_resets_failure_metadata(db):
    user = User(email="rag-hardening@example.com", hashed_password="test", role="free")
    db.add(user)
    db.commit()
    db.refresh(user)

    document = Document(
        user_id=user.id,
        name="failed.txt",
        source="text",
        mime_type="text/plain",
        status="failed",
        content_hash="a" * 64,
        raw_text="hello",
        indexing_attempts=3,
        last_index_error="RAGError",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    result = reindex_document(db, user_id=user.id, document_id=document.id)

    assert result.status == "queued"
    assert result.last_index_error is None
    assert result.indexing_attempts == 3


def test_embedding_usage_summary_tracks_query_embeddings(db):
    record_embedding_usage(
        db,
        user_id=7,
        document_id=None,
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=25,
        item_count=1,
    )

    summary = embedding_usage_summary(db, user_id=7)

    assert summary == {"input_tokens": 25, "item_count": 1, "requests": 1}


def test_embed_texts_returns_usage_metadata(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [{"index": 0, "embedding": [0.0] * 1536}],
                "usage": {"prompt_tokens": 17},
            }

    monkeypatch.setattr("app.services.rag_service._embedding_config", lambda: ("https://example.test/v1", "key", "test-model"))
    monkeypatch.setattr("app.services.rag_service.httpx.post", lambda *args, **kwargs: Response())

    vectors, metadata = embed_texts(["hello"], return_metadata=True)

    assert len(vectors) == 1
    assert metadata["model"] == "test-model"
    assert metadata["input_tokens"] == 17
    assert metadata["provider"] == "mock"
