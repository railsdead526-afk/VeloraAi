from app.core.plans import get_plan_policy


def test_free_plan_policy():
    policy = get_plan_policy("free")
    assert policy.monthly_token_limit == 100_000
    assert policy.monthly_request_limit == 100


def test_pro_plan_policy():
    policy = get_plan_policy("pro")
    assert policy.monthly_token_limit == 1_000_000
    assert policy.monthly_request_limit == 1_000


def test_max_plan_policy():
    policy = get_plan_policy("max")
    assert policy.monthly_token_limit == 5_000_000
    assert policy.monthly_request_limit == 10_000


def test_admin_is_unlimited():
    policy = get_plan_policy("admin")
    assert policy.monthly_token_limit is None
    assert policy.monthly_request_limit is None


def test_unknown_role_falls_back_to_free():
    assert get_plan_policy("unknown").name == "free"
