import httpx
import pytest

from app.core.config import settings
from app.models.document import EMBEDDING_DIMENSIONS
from app.services.rag_service import RAGError, chunk_text, embed_texts


class _FakeEmbeddingClient:
    """Stands in for httpx.Client so embed_texts never touches the network."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):
        self.requests.append(json or {})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_chunk_text_normalizes_and_overlaps():
    chunks = chunk_text("a  b\n\nc", chunk_size=4, overlap=1)
    assert chunks
    assert all("  " not in chunk for chunk in chunks)


def test_chunk_text_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=10, overlap=10)


def test_embed_texts_rejects_incomplete_provider(monkeypatch):
    client = _FakeEmbeddingClient([_FakeResponse({"data": []})])
    monkeypatch.setattr("app.services.rag_service.httpx.Client", lambda **kwargs: client)
    monkeypatch.setattr(
        "app.services.rag_service._embedding_config",
        lambda: ("http://embedding.test/v1", "", "test-model"),
    )
    with pytest.raises(RAGError, match="incomplete"):
        embed_texts(["hello"])


def test_embed_texts_splits_long_input_into_batches(monkeypatch):
    """One request per batch; a 10 MB document would otherwise be a single call."""
    monkeypatch.setattr(settings, "embedding_batch_size", 2)
    monkeypatch.setattr(
        "app.services.rag_service._embedding_config",
        lambda: ("http://embedding.test/v1", "", "test-model"),
    )

    def _page(count, tokens):
        return _FakeResponse(
            {
                "data": [
                    {"index": i, "embedding": [0.0] * EMBEDDING_DIMENSIONS} for i in range(count)
                ],
                "usage": {"prompt_tokens": tokens},
            }
        )

    client = _FakeEmbeddingClient([_page(2, 10), _page(2, 10), _page(1, 5)])
    monkeypatch.setattr("app.services.rag_service.httpx.Client", lambda **kwargs: client)

    vectors, metadata = embed_texts([f"chunk {i}" for i in range(5)], return_metadata=True)

    assert len(vectors) == 5
    assert [len(request["input"]) for request in client.requests] == [2, 2, 1]
    # Usage is summed across every batch, not just the last one.
    assert metadata["input_tokens"] == 25


def test_embed_texts_retries_a_transient_failure(monkeypatch):
    monkeypatch.setattr(settings, "ai_max_retries", 1)
    monkeypatch.setattr("app.services.rag_service.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "app.services.rag_service._embedding_config",
        lambda: ("http://embedding.test/v1", "", "test-model"),
    )
    ok = _FakeResponse(
        {
            "data": [{"index": 0, "embedding": [0.0] * EMBEDDING_DIMENSIONS}],
            "usage": {"prompt_tokens": 4},
        }
    )
    client = _FakeEmbeddingClient([httpx.ConnectError("boom"), ok])
    monkeypatch.setattr("app.services.rag_service.httpx.Client", lambda **kwargs: client)

    vectors = embed_texts(["hello"])

    assert len(vectors) == 1
    assert len(client.requests) == 2


def test_embedding_dimension_constant_is_fixed():
    assert EMBEDDING_DIMENSIONS == 1536
