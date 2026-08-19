from app.api.v1.conversations import _history_with_rag_context
from app.models.document import Document


def test_rag_context_is_skipped_when_disabled(db):
    history = [{"role": "user", "content": "hello"}]
    result = _history_with_rag_context(
        db,
        user_id=1,
        history_payload=history,
        query="hello",
        use_rag=False,
    )
    assert result == history


def test_rag_context_is_skipped_without_documents(db):
    history = [{"role": "user", "content": "hello"}]
    result = _history_with_rag_context(
        db,
        user_id=1,
        history_payload=history,
        query="hello",
        use_rag=True,
    )
    assert result == history


def test_document_belongs_to_user(db):
    document = Document(user_id=1, name="Owned", source="text", status="ready")
    db.add(document)
    db.commit()
    assert document.user_id == 1
