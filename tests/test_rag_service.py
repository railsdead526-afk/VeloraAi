import pytest

from app.models.document import EMBEDDING_DIMENSIONS
from app.services.rag_service import chunk_text, embed_texts


def test_chunk_text_normalizes_and_overlaps():
    chunks = chunk_text("a  b\n\nc", chunk_size=4, overlap=1)
    assert chunks
    assert all("  " not in chunk for chunk in chunks)


def test_chunk_text_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=10, overlap=10)


def test_embed_texts_rejects_incomplete_provider(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": []}

    monkeypatch.setattr("app.services.rag_service.httpx.post", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        "app.services.rag_service._embedding_config",
        lambda: ("http://embedding.test/v1", "", "test-model"),
    )
    with pytest.raises(Exception, match="incomplete"):
        embed_texts(["hello"])


def test_embedding_dimension_constant_is_fixed():
    assert EMBEDDING_DIMENSIONS == 1536
