from app.core.plans import get_plan_policy
from app.tools.bootstrap import get_registry


def test_plan_quota_matrix_is_explicit():
    assert get_plan_policy("free").daily_request_limit == 20
    assert get_plan_policy("pro").daily_request_limit == 200
    assert get_plan_policy("max").daily_request_limit == 1_000
    assert get_plan_policy("admin").daily_request_limit is None


def test_tool_matrix_prevents_free_writes_and_terminal():
    registry = get_registry()

    assert registry.get("github_read_file").allows_plan("free")
    assert not registry.get("github_write_file").allows_plan("free")
    assert not registry.get("supabase_execute_sql").allows_plan("free")
    assert not registry.get("terminal_read_file").allows_plan("free")


def test_tool_matrix_gives_pro_write_and_terminal_but_not_merge():
    registry = get_registry()

    assert registry.get("github_write_file").allows_plan("pro")
    assert registry.get("terminal_read_file").allows_plan("pro")
    assert not registry.get("github_merge_pull_request").allows_plan("pro")


def test_tool_matrix_gives_max_merge_access():
    registry = get_registry()

    assert registry.get("github_merge_pull_request").allows_plan("max")
    assert registry.get("github_merge_pull_request").allows_plan("admin")
