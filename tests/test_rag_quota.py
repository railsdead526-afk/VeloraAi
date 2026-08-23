"""Cost ceilings for retrieval.

The gap these close: embedding usage was written to `embedding_usage` and never
read back. Nothing capped how much a single account could spend on indexing,
and no plan had an embedding limit at all. Measuring a cost without acting on
it is not a control.
"""

import pytest

from app.core.plans import PLANS, get_plan_policy
from app.models.document import Document
from app.models.embedding_usage import EmbeddingUsage
from app.models.user import User
from app.services.rag_quota import (
    DocumentLimitExceededError,
    EmbeddingQuotaExceededError,
    embedding_quota_snapshot,
    enforce_indexing_allowed,
    estimate_tokens,
)
from tests.conftest import client

STRONG_PASSWORD = "Str0ng!Passw0rd"


def _make_user(db, email: str, role: str = "free") -> User:
    user = User(email=email, hashed_password="x", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _burn_embedding_tokens(db, user_id: int, tokens: int) -> None:
    db.add(
        EmbeddingUsage(
            user_id=user_id,
            document_id=None,
            provider="openai",
            model="text-embedding-3-small",
            input_tokens=tokens,
            item_count=1,
        )
    )
    db.commit()


def _add_documents(db, user_id: int, count: int) -> None:
    for index in range(count):
        db.add(
            Document(
                user_id=user_id,
                name=f"doc-{index}",
                source="text",
                status="ready",
                content_hash=f"hash-{user_id}-{index}",
                raw_text="content",
            )
        )
    db.commit()


# --------------------------------------------------------------------------- #
# Every paid plan must have a ceiling
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("plan", ["free", "pro", "max"])
def test_non_admin_plans_bound_embedding_spend(plan):
    policy = PLANS[plan]
    assert policy.monthly_embedding_token_limit is not None, (
        f"{plan} has no embedding ceiling; provider spend would be unbounded"
    )
    assert policy.max_documents is not None


def test_admin_is_the_only_unbounded_plan():
    assert PLANS["admin"].monthly_embedding_token_limit is None
    assert PLANS["admin"].max_documents is None


def test_limits_increase_with_plan_tier():
    assert (
        PLANS["free"].monthly_embedding_token_limit
        < PLANS["pro"].monthly_embedding_token_limit
        < PLANS["max"].monthly_embedding_token_limit
    )
    assert PLANS["free"].max_documents < PLANS["pro"].max_documents < PLANS["max"].max_documents


# --------------------------------------------------------------------------- #
# Estimation
# --------------------------------------------------------------------------- #


def test_estimate_never_returns_zero():
    """A zero estimate would let unlimited tiny requests through the gate."""
    assert estimate_tokens("") >= 1
    assert estimate_tokens("a") >= 1


def test_estimate_grows_with_length():
    assert estimate_tokens("x" * 3000) > estimate_tokens("x" * 30)


# --------------------------------------------------------------------------- #
# Enforcement
# --------------------------------------------------------------------------- #


def test_indexing_is_allowed_within_budget(db):
    user = _make_user(db, "within-budget@example.com")
    enforce_indexing_allowed(
        db,
        user_id=user.id,
        policy=get_plan_policy("free"),
        text="short document",
        is_new_document=True,
    )


def test_embedding_quota_blocks_once_exhausted(db):
    user = _make_user(db, "embed-exhausted@example.com")
    policy = get_plan_policy("free")
    _burn_embedding_tokens(db, user.id, policy.monthly_embedding_token_limit)

    with pytest.raises(EmbeddingQuotaExceededError):
        enforce_indexing_allowed(
            db, user_id=user.id, policy=policy, text="more text", is_new_document=True
        )


def test_quota_accounts_for_the_incoming_document(db):
    """The check happens before the provider call, so the estimate must count."""
    user = _make_user(db, "incoming@example.com")
    policy = get_plan_policy("free")
    _burn_embedding_tokens(db, user.id, policy.monthly_embedding_token_limit - 10)

    with pytest.raises(EmbeddingQuotaExceededError):
        enforce_indexing_allowed(
            db, user_id=user.id, policy=policy, text="x" * 10_000, is_new_document=True
        )


def test_document_limit_blocks_new_documents(db):
    user = _make_user(db, "doc-limit@example.com")
    policy = get_plan_policy("free")
    _add_documents(db, user.id, policy.max_documents)

    with pytest.raises(DocumentLimitExceededError):
        enforce_indexing_allowed(
            db, user_id=user.id, policy=policy, text="tiny", is_new_document=True
        )


def test_reindex_is_not_blocked_by_the_document_count(db):
    """Re-indexing adds no document, so the count must not refuse it..."""
    user = _make_user(db, "reindex-count@example.com")
    policy = get_plan_policy("free")
    _add_documents(db, user.id, policy.max_documents)

    enforce_indexing_allowed(db, user_id=user.id, policy=policy, text="tiny", is_new_document=False)


def test_reindex_still_consumes_embedding_budget(db):
    """...but it calls the provider, so the token ceiling still applies."""
    user = _make_user(db, "reindex-tokens@example.com")
    policy = get_plan_policy("free")
    _burn_embedding_tokens(db, user.id, policy.monthly_embedding_token_limit)

    with pytest.raises(EmbeddingQuotaExceededError):
        enforce_indexing_allowed(
            db, user_id=user.id, policy=policy, text="tiny", is_new_document=False
        )


def test_admin_is_never_blocked(db):
    user = _make_user(db, "admin-rag@example.com", role="admin")
    _burn_embedding_tokens(db, user.id, 999_000_000)
    _add_documents(db, user.id, 5)

    enforce_indexing_allowed(
        db,
        user_id=user.id,
        policy=get_plan_policy("admin"),
        text="x" * 100_000,
        is_new_document=True,
    )


def test_quota_is_scoped_per_user(db):
    heavy = _make_user(db, "heavy@example.com")
    light = _make_user(db, "light@example.com")
    policy = get_plan_policy("free")
    _burn_embedding_tokens(db, heavy.id, policy.monthly_embedding_token_limit)

    enforce_indexing_allowed(db, user_id=light.id, policy=policy, text="tiny", is_new_document=True)


def test_snapshot_reports_usage_against_the_ceiling(db):
    user = _make_user(db, "snapshot@example.com")
    _burn_embedding_tokens(db, user.id, 1234)
    _add_documents(db, user.id, 2)

    snapshot = embedding_quota_snapshot(db, user_id=user.id, policy=get_plan_policy("free"))
    assert snapshot["embedding_tokens_used"] == 1234
    assert snapshot["embedding_token_limit"] == PLANS["free"].monthly_embedding_token_limit
    assert snapshot["documents_used"] == 2
    assert snapshot["document_limit"] == PLANS["free"].max_documents


# --------------------------------------------------------------------------- #
# The API enforces it
# --------------------------------------------------------------------------- #


def _headers(email: str) -> dict[str, str]:
    client.post("/api/v1/auth/register", json={"email": email, "password": STRONG_PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_is_refused_once_the_document_limit_is_reached(db):
    headers = _headers("api-doc-limit@example.com")
    user = db.query(User).filter(User.email == "api-doc-limit@example.com").one()
    _add_documents(db, user.id, PLANS["free"].max_documents)

    response = client.post(
        "/api/v1/rag/documents",
        headers=headers,
        json={"name": "one too many", "content": "hello"},
    )
    assert response.status_code == 409
    assert "documents" in response.json()["detail"]


def test_upload_is_refused_once_the_embedding_quota_is_spent(db):
    headers = _headers("api-embed-limit@example.com")
    user = db.query(User).filter(User.email == "api-embed-limit@example.com").one()
    _burn_embedding_tokens(db, user.id, PLANS["free"].monthly_embedding_token_limit)

    response = client.post(
        "/api/v1/rag/documents",
        headers=headers,
        json={"name": "over budget", "content": "hello"},
    )
    assert response.status_code == 429
    assert "quota" in response.json()["detail"].lower()


def test_usage_endpoint_exposes_the_ceilings():
    headers = _headers("api-usage@example.com")
    body = client.get("/api/v1/rag/usage", headers=headers).json()
    assert body["embedding_token_limit"] == PLANS["free"].monthly_embedding_token_limit
    assert body["document_limit"] == PLANS["free"].max_documents
    assert body["documents_used"] == 0


def test_document_list_is_paginated(db):
    headers = _headers("api-page@example.com")
    user = db.query(User).filter(User.email == "api-page@example.com").one()
    _add_documents(db, user.id, 5)

    first = client.get("/api/v1/rag/documents?limit=2", headers=headers).json()
    assert len(first) == 2

    second = client.get("/api/v1/rag/documents?limit=2&offset=2", headers=headers).json()
    assert len(second) == 2
    assert {d["id"] for d in first}.isdisjoint({d["id"] for d in second})


def test_document_page_size_is_capped():
    headers = _headers("api-page-cap@example.com")
    assert client.get("/api/v1/rag/documents?limit=5000", headers=headers).status_code == 422


def test_conversation_list_is_paginated():
    """The CRUD layer always paged; the endpoint never exposed it, so anything
    past the newest 50 conversations was unreachable."""
    headers = _headers("api-conv-page@example.com")
    for index in range(4):
        client.post("/api/v1/conversations", headers=headers, json={"title": f"chat {index}"})

    first = client.get("/api/v1/conversations?limit=2", headers=headers).json()
    second = client.get("/api/v1/conversations?limit=2&offset=2", headers=headers).json()
    assert len(first) == 2
    assert len(second) == 2
    assert {c["id"] for c in first}.isdisjoint({c["id"] for c in second})
