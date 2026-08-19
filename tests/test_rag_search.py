from types import SimpleNamespace

from app.services import rag_service


def test_hybrid_retrieve_prefers_overlap(monkeypatch):
    first = SimpleNamespace(id=1, content="FastAPI authentication middleware", document_id=1)
    second = SimpleNamespace(id=2, content="Railway deployment configuration", document_id=2)

    monkeypatch.setattr(
        rag_service,
        "embed_texts",
        lambda _texts: [[0.1] * rag_service.EMBEDDING_DIMENSIONS],
    )
    monkeypatch.setattr(
        rag_service,
        "_vector_candidates",
        lambda *_args, **_kwargs: [(second, 0.1), (first, 0.2)],
    )
    monkeypatch.setattr(
        rag_service,
        "_keyword_candidates",
        lambda *_args, **_kwargs: [first],
    )

    results = rag_service.hybrid_retrieve_chunks(
        object(), user_id=1, query="FastAPI authentication", limit=2
    )

    assert results[0][0].id == 1
    assert len(results) == 2


def test_retrieve_chunks_delegates_to_hybrid():
    sentinel = [(SimpleNamespace(id=7), 0.2)]
    called = {}

    def fake(*_args, **kwargs):
        called.update(kwargs)
        return sentinel

    original = rag_service.hybrid_retrieve_chunks
    rag_service.hybrid_retrieve_chunks = fake
    try:
        result = rag_service.retrieve_chunks(object(), user_id=3, query="abc", limit=4)
    finally:
        rag_service.hybrid_retrieve_chunks = original

    assert result == sentinel
    assert called == {"user_id": 3, "query": "abc", "limit": 4}
