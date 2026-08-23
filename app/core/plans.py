from dataclasses import dataclass


@dataclass(frozen=True)
class PlanPolicy:
    """What a plan is allowed to consume.

    `None` means unbounded and is reserved for `admin`. Every other limit is a
    real ceiling: anything the service pays a provider for must have one, or
    the cost is unbounded by construction.
    """

    name: str

    # Chat.
    monthly_token_limit: int | None
    monthly_request_limit: int | None
    daily_request_limit: int | None

    # Retrieval. Embeddings are billed by the provider per token, so they need
    # their own ceiling: they are not covered by the chat token limit, and
    # indexing one large document can cost more than a month of conversation.
    monthly_embedding_token_limit: int | None
    #: Stored documents. Caps both storage and the re-indexing blast radius.
    max_documents: int | None


PLANS: dict[str, PlanPolicy] = {
    "free": PlanPolicy(
        name="free",
        monthly_token_limit=100_000,
        monthly_request_limit=100,
        daily_request_limit=20,
        monthly_embedding_token_limit=200_000,
        max_documents=10,
    ),
    "pro": PlanPolicy(
        name="pro",
        monthly_token_limit=1_000_000,
        monthly_request_limit=1_000,
        daily_request_limit=200,
        monthly_embedding_token_limit=5_000_000,
        max_documents=200,
    ),
    "max": PlanPolicy(
        name="max",
        monthly_token_limit=5_000_000,
        monthly_request_limit=10_000,
        daily_request_limit=1_000,
        monthly_embedding_token_limit=25_000_000,
        max_documents=2_000,
    ),
    "admin": PlanPolicy(
        name="admin",
        monthly_token_limit=None,
        monthly_request_limit=None,
        daily_request_limit=None,
        monthly_embedding_token_limit=None,
        max_documents=None,
    ),
}


def get_plan_policy(role: str | None) -> PlanPolicy:
    normalized = (role or "free").lower()
    return PLANS.get(normalized, PLANS["free"])
