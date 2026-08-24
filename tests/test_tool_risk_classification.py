"""Every registered tool must be classified before it can run.

The protection here used to depend on one thing: whoever added a tool
remembering to set `requires_confirmation=True`. Forget it once on a tool that
deletes DNS records or executes SQL, and it runs against a user's real
infrastructure with no prompt, silently.

These tests replace that convention with a gate. The read-only set below is
explicit, so adding a tool forces a deliberate decision rather than inheriting
a permissive default.
"""

import pytest

from app.tools.base import ToolRisk
from app.tools.bootstrap import get_registry
from app.tools.policy import policy

#: Tools that only read. Anything registered and NOT listed here must require
#: approval. Adding a name to this list is a security decision: it means the
#: tool cannot change anything the user would want to be asked about.
READ_ONLY_TOOLS = {
    "cloudflare_list_dns_records",
    "cloudflare_list_zones",
    "github_get_commit_status",
    "github_get_pr_comments",
    "github_get_pr_reviews",
    "github_list_branches",
    "github_list_issues",
    "github_list_pull_requests",
    "github_list_repositories",
    "github_list_workflow_jobs",
    "github_read_file",
    "github_search_code",
    "railway_get_deployment",
    "railway_get_deployments",
    "railway_list_projects",
    "railway_list_services",
    "supabase_get_advisors",
    "supabase_get_project",
    "supabase_list_branches",
    "supabase_list_edge_functions",
    "supabase_list_projects",
    "terminal_git_branch",
    "terminal_git_diff",
    "terminal_git_log",
    "terminal_git_status",
    "terminal_list_directory",
    "terminal_read_file",
    "vercel_get_deployment",
    "vercel_get_project",
    "vercel_list_deployments",
    "vercel_list_domains",
    "vercel_list_projects",
}


def _tools():
    return {tool.name: tool for tool in get_registry().list()}


def test_every_tool_is_either_read_only_or_requires_approval():
    """The gate. A new mutating tool fails here until it is classified."""
    unguarded = sorted(
        name
        for name, tool in _tools().items()
        if name not in READ_ONLY_TOOLS and not policy.requires_approval(tool)
    )
    assert not unguarded, (
        "These tools can act without user approval and are not declared read-only. "
        "Either add requires_confirmation=True with a risk level, or add the name "
        f"to READ_ONLY_TOOLS after confirming it only reads: {unguarded}"
    )


def test_the_read_only_list_has_no_stale_entries():
    """A removed or renamed tool must not leave a permanent hole in the list."""
    stale = sorted(READ_ONLY_TOOLS - set(_tools()))
    assert not stale, f"READ_ONLY_TOOLS names tools that no longer exist: {stale}"


def test_approval_is_backed_by_a_risk_level_not_just_a_flag():
    """`requires_confirmation` alone is a bare boolean with no severity.

    Carrying a risk level too means the UI, the audit log, and any future
    policy can distinguish "writes a file" from "drops a table".
    """
    unclassified = sorted(
        name
        for name, tool in _tools().items()
        if tool.requires_confirmation and tool.risk_level is ToolRisk.LOW
    )
    assert not unclassified, (
        f"These require confirmation but are still risk_level=LOW: {unclassified}"
    )


def test_read_only_tools_are_not_marked_risky():
    """The inverse: a tool declared read-only must not claim to mutate."""
    contradictory = sorted(
        name
        for name, tool in _tools().items()
        if name in READ_ONLY_TOOLS and tool.risk_level is not ToolRisk.LOW
    )
    assert not contradictory, f"Declared read-only but classified risky: {contradictory}"


@pytest.mark.parametrize(
    "name",
    [
        "github_write_file",
        "supabase_execute_sql",
        "cloudflare_delete_dns_record",
        "github_merge_pull_request",
        "terminal_write_file",
    ],
)
def test_known_dangerous_tools_are_gated(name):
    """Named explicitly so a refactor cannot quietly downgrade them."""
    tools = _tools()
    if name not in tools:
        pytest.skip(f"{name} is not registered in this build")
    tool = tools[name]
    assert policy.requires_approval(tool), f"{name} must require approval"
    assert tool.risk_level is not ToolRisk.LOW, f"{name} must carry a risk level"


def test_destructive_tools_are_labelled_destructive():
    """Deleting and executing arbitrary SQL are not merely 'write'."""
    tools = _tools()
    for name in ("cloudflare_delete_dns_record", "supabase_execute_sql"):
        if name in tools:
            assert tools[name].risk_level is ToolRisk.DESTRUCTIVE, (
                f"{name} should be DESTRUCTIVE, not {tools[name].risk_level}"
            )


#: The sandbox service caps command execution at 60s, and SandboxClient allows
#: another 5s for network overhead. A terminal tool's own timeout must exceed
#: that chain, or the executor gives up while the sandbox is still working.
SANDBOX_EXECUTION_CAP_SECONDS = 60
SANDBOX_CLIENT_OVERHEAD_SECONDS = 5
MAX_TOOL_TIMEOUT_SECONDS = 90


def test_every_tool_has_a_bounded_timeout_and_call_limit():
    """An unbounded tool call is a way to hang a request or burn provider quota."""
    for name, tool in _tools().items():
        assert 0 < tool.timeout_seconds <= MAX_TOOL_TIMEOUT_SECONDS, (
            f"{name} has an unreasonable timeout: {tool.timeout_seconds}s"
        )
        assert 1 <= tool.max_calls_per_request <= 10, f"{name} has an unreasonable call limit"


def test_terminal_tools_outlive_the_sandbox_they_wait_on():
    """Otherwise the executor times out while the sandbox is still running.

    The user would see a generic failure for work that actually completed.
    """
    floor = SANDBOX_EXECUTION_CAP_SECONDS + SANDBOX_CLIENT_OVERHEAD_SECONDS
    for name, tool in _tools().items():
        if not name.startswith("terminal_"):
            continue
        # Short, fixed commands may legitimately budget less than the cap.
        if tool.timeout_seconds < SANDBOX_EXECUTION_CAP_SECONDS:
            continue
        assert tool.timeout_seconds >= floor, (
            f"{name} allows {tool.timeout_seconds}s but the sandbox chain needs {floor}s"
        )
