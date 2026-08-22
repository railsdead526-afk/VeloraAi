import pytest

from app.models.billing import Payment, Subscription
from app.models.document import Document
from app.models.user import User
from app.services.billing_service import apply_payment_notification, sync_user_role
from app.services.rag_jobs import process_document_index
from app.services.rag_service import RAGError, create_pending_document


def test_create_pending_document_enforces_text_size_and_name(db, monkeypatch):
    monkeypatch.setattr("app.services.rag_service.settings.document_max_upload_bytes", 16)
    user = User(email="rag-size@example.com", hashed_password="hash", role="free")
    db.add(user)
    db.commit()
    db.refresh(user)

    with pytest.raises(RAGError, match="upload size limit"):
        create_pending_document(db, user_id=user.id, name="doc.txt", text="0123456789abcdefghi")

    with pytest.raises(RAGError, match="name is empty"):
        create_pending_document(db, user_id=user.id, name="   ", text="small")


def test_rag_index_failure_persists_failed_state_even_when_usage_record_fails(db, monkeypatch):
    user = User(email="rag-failure@example.com", hashed_password="hash", role="free")
    db.add(user)
    db.commit()
    db.refresh(user)
    document = Document(
        user_id=user.id,
        name="broken.txt",
        source="text",
        mime_type="text/plain",
        status="queued",
        content_hash="b" * 64,
        raw_text="will fail",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    def failing_embed(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    def failing_usage(*args, **kwargs):
        raise RuntimeError("usage database unavailable")

    monkeypatch.setattr("app.services.rag_jobs.embed_texts", failing_embed)
    monkeypatch.setattr("app.services.rag_jobs.record_embedding_usage", failing_usage)

    process_document_index(document.id, db=db)
    db.refresh(document)

    assert document.status == "failed"
    assert document.last_index_error == "RuntimeError"
    assert document.indexing_attempts == 1


def test_settled_payment_cannot_be_regressed_by_late_failure(db):
    user = User(email="billing-order@example.com", hashed_password="hash", role="free")
    db.add(user)
    db.commit()
    db.refresh(user)
    payment = Payment(
        user_id=user.id,
        provider="midtrans",
        provider_order_id="order-state-machine",
        amount=19900,
        currency="IDR",
        plan="pro",
        status="pending",
    )
    db.add(payment)
    db.commit()

    apply_payment_notification(
        db,
        provider="midtrans",
        provider_order_id=payment.provider_order_id,
        provider_transaction_id="tx-settled",
        transaction_status="settlement",
    )
    apply_payment_notification(
        db,
        provider="midtrans",
        provider_order_id=payment.provider_order_id,
        provider_transaction_id="tx-late",
        transaction_status="expire",
    )
    db.refresh(payment)
    db.refresh(user)

    assert payment.status == "settlement"
    assert user.role == "pro"


def test_sync_user_role_downgrades_after_subscription_cancellation(db):
    user = User(email="billing-refund@example.com", hashed_password="hash", role="pro")
    db.add(user)
    db.commit()
    db.refresh(user)
    subscription = Subscription(
        user_id=user.id,
        plan="pro",
        provider="midtrans",
        status="canceled",
    )
    db.add(subscription)
    db.commit()

    sync_user_role(db, user_id=user.id)
    assert user.role == "free"
    db.commit()
    db.refresh(user)
    assert user.role == "free"
