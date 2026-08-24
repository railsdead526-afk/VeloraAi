"""Query-count regressions for the retrieval path.

`build_context` reads `chunk.document.name` for every hit it formats. If the
candidate queries do not eagerly load the document, SQLAlchemy issues one extra
SELECT per chunk — measured at five extra queries for five hits, on the hot path
of every RAG-backed chat message.

Counting queries rather than timing them keeps the test deterministic.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.services import rag_service
from app.services.rag_service import build_context


@pytest.fixture
def query_counter(db):
    """Counts statements issued on the session's own connection."""
    bind = db.get_bind()
    counter = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        # SAVEPOINT/RELEASE from the test transaction are noise here.
        if statement.lstrip().upper().startswith("SELECT"):
            counter["n"] += 1

    event.listen(bind, "before_cursor_execute", _count)
    try:
        yield counter
    finally:
        event.remove(bind, "before_cursor_execute", _count)


@pytest.fixture
def library(db):
    """Five documents with one chunk each — what retrieval typically returns."""
    user = User(email="retrieval@example.com", hashed_password="hash", role="free")
    db.add(user)
    db.commit()
    db.refresh(user)

    for index in range(5):
        document = Document(
            user_id=user.id,
            name=f"doc-{index}",
            source="text",
            mime_type="text/plain",
            status="ready",
            content_hash=f"hash-{index}",
            raw_text="pengetahuan penting",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content=f"pengetahuan penting nomor {index}",
                embedding=[0.0] * 1536,
            )
        )
        db.commit()
    return user


def test_build_context_does_not_query_per_chunk(db, library, query_counter):
    user_id = library.id
    chunks = db.query(DocumentChunk).join(DocumentChunk.document).all()
    db.expire_all()
    # Reload through the production query so the eager loading under test applies.
    candidates = rag_service._keyword_candidates(
        db, user_id=user_id, query="pengetahuan penting", candidate_limit=5
    )
    assert len(candidates) == 5

    query_counter["n"] = 0
    context = build_context([(chunk, 0.1) for chunk in candidates])

    assert query_counter["n"] == 0, (
        f"build_context issued {query_counter['n']} queries; the document should "
        "already be loaded by the candidate query"
    )
    for index in range(5):
        assert f"doc-{index}" in context
    assert len(chunks) == 5


def test_keyword_candidates_load_documents_in_one_query(db, library, query_counter):
    # Read the id before expiring, otherwise touching library.id reloads the
    # User row and shows up as an extra SELECT that has nothing to do with the
    # query under test.
    user_id = library.id
    db.expire_all()

    query_counter["n"] = 0
    candidates = rag_service._keyword_candidates(
        db, user_id=user_id, query="pengetahuan penting", candidate_limit=5
    )

    assert len(candidates) == 5
    assert query_counter["n"] == 1, f"expected a single query, got {query_counter['n']}"
