from dataclasses import dataclass


@dataclass(frozen=True)
class PlanPolicy:
    name: str
    monthly_token_limit: int | None
    monthly_request_limit: int | None


PLANS: dict[str, PlanPolicy] = {
    "free": PlanPolicy(name="free", monthly_token_limit=100_000, monthly_request_limit=100),
    "pro": PlanPolicy(name="pro", monthly_token_limit=1_000_000, monthly_request_limit=1_000),
    "max": PlanPolicy(name="max", monthly_token_limit=5_000_000, monthly_request_limit=10_000),
    "admin": PlanPolicy(name="admin", monthly_token_limit=None, monthly_request_limit=None),
}


def get_plan_policy(role: str | None) -> PlanPolicy:
    normalized = (role or "free").lower()
    return PLANS.get(normalized, PLANS["free"])
