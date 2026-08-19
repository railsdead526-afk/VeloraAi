from dataclasses import dataclass


@dataclass(frozen=True)
class PlanPolicy:
    monthly_token_limit: int | None
    monthly_request_limit: int | None


PLAN_POLICIES: dict[str, PlanPolicy] = {
    "free": PlanPolicy(monthly_token_limit=None, monthly_request_limit=100),
    "pro": PlanPolicy(monthly_token_limit=None, monthly_request_limit=1000),
    "max": PlanPolicy(monthly_token_limit=None, monthly_request_limit=10000),
    "admin": PlanPolicy(monthly_token_limit=None, monthly_request_limit=None),
}


def get_plan_policy(role: str) -> PlanPolicy:
    return PLAN_POLICIES.get(role.lower(), PLAN_POLICIES["free"])
