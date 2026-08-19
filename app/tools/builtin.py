from app.tools.base import ToolDefinition
from app.tools.github_tools import (
    github_create_branch,
    github_create_issue,
    github_create_issue_comment,
    github_create_pull_request,
    github_get_commit_status,
    github_get_pr_comments,
    github_get_pr_reviews,
    github_list_branches,
    github_list_issues,
    github_list_pull_requests,
    github_list_workflow_jobs,
    github_merge_pull_request,
    github_rerun_failed_jobs,
    github_search_code,
    github_write_file,
)
from app.tools.platform_tools import (
    railway_get_deployment,
    railway_get_deployments,
    railway_list_services,
    railway_redeploy,
    railway_restart_service,
    vercel_cancel_deployment,
    vercel_create_deployment,
    vercel_get_deployment,
    vercel_get_project,
    vercel_list_deployments,
    vercel_list_domains,
)
from app.tools.providers import (
    cloudflare_list_zones,
    github_list_repositories,
    github_read_file,
    railway_list_projects,
    supabase_list_projects,
    vercel_list_projects,
)
from app.tools.supabase_tools import (
    supabase_execute_sql,
    supabase_get_advisors,
    supabase_get_project,
    supabase_list_branches,
    supabase_list_edge_functions,
)
from app.tools.terminal_tools import (
    terminal_git_branch,
    terminal_git_checkout,
    terminal_git_commit,
    terminal_git_diff,
    terminal_git_log,
    terminal_git_status,
    terminal_install_package,
    terminal_list_directory,
    terminal_read_file,
    terminal_run_build,
    terminal_run_lint,
    terminal_run_tests,
    terminal_write_file,
)

READ_PLANS = frozenset({"free", "pro", "max", "admin"})
WRITE_PLANS = frozenset({"pro", "max", "admin"})
TERMINAL_PLANS = frozenset({"pro", "max", "admin"})


def register_platform_tools(registry) -> None:
    definitions = [
        ToolDefinition(name="github_list_repositories", description="List repositories available to the authenticated GitHub account.", handler=github_list_repositories, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"per_page":{"type":"integer","minimum":1,"maximum":100}},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="github_read_file", description="Read a file from a repository.", handler=github_read_file, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"path":{"type":"string"}},"required":["repository","path"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_search_code", description="Search code visible to the authenticated GitHub account.", handler=github_search_code, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"query":{"type":"string"},"repository":{"type":"string"},"per_page":{"type":"integer","minimum":1,"maximum":100}},"required":["query"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_list_branches", description="List repository branches.", handler=github_list_branches, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"}},"required":["repository"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_list_issues", description="List repository issues.", handler=github_list_issues, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"state":{"type":"string","enum":["open","closed","all"]}},"required":["repository"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_list_pull_requests", description="List pull requests.", handler=github_list_pull_requests, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"state":{"type":"string","enum":["open","closed","all"]}},"required":["repository"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_get_pr_reviews", description="Read pull request reviews.", handler=github_get_pr_reviews, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"pr_number":{"type":"integer","minimum":1}},"required":["repository","pr_number"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_get_pr_comments", description="Read pull request review comments.", handler=github_get_pr_comments, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"pr_number":{"type":"integer","minimum":1}},"required":["repository","pr_number"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_get_commit_status", description="Read combined commit CI status.", handler=github_get_commit_status, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"sha":{"type":"string"}},"required":["repository","sha"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_list_workflow_jobs", description="List jobs for a GitHub Actions workflow run.", handler=github_list_workflow_jobs, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"run_id":{"type":"integer","minimum":1}},"required":["repository","run_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_create_branch", description="Create a branch.", handler=github_create_branch, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"name":{"type":"string"},"source":{"type":"string"}},"required":["repository","name"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="github_write_file", description="Create or update a repository file on a branch.", handler=github_write_file, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"path":{"type":"string"},"content":{"type":"string"},"branch":{"type":"string"},"message":{"type":"string"}},"required":["repository","path","content"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=20, max_calls_per_request=3),
        ToolDefinition(name="github_create_issue", description="Create an issue.", handler=github_create_issue, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"title":{"type":"string"},"body":{"type":"string"}},"required":["repository","title"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="github_create_issue_comment", description="Add a comment to an issue or pull request.", handler=github_create_issue_comment, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"issue_number":{"type":"integer","minimum":1},"body":{"type":"string"}},"required":["repository","issue_number","body"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_create_pull_request", description="Create a pull request.", handler=github_create_pull_request, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"title":{"type":"string"},"head":{"type":"string"},"base":{"type":"string"},"body":{"type":"string"}},"required":["repository","title","head"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=20, max_calls_per_request=3),
        ToolDefinition(name="github_merge_pull_request", description="Merge a pull request after CI/review checks pass.", handler=github_merge_pull_request, allowed_plans=frozenset({"max","admin"}), parameters={"type":"object","properties":{"repository":{"type":"string"},"pr_number":{"type":"integer","minimum":1},"merge_method":{"type":"string","enum":["merge","squash","rebase"]},"expected_head_sha":{"type":"string"}},"required":["repository","pr_number"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=20, max_calls_per_request=1),
        ToolDefinition(name="github_rerun_failed_jobs", description="Re-run failed GitHub Actions jobs for a workflow run.", handler=github_rerun_failed_jobs, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"run_id":{"type":"integer","minimum":1}},"required":["repository","run_id"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=20, max_calls_per_request=2),

        ToolDefinition(name="vercel_list_projects", description="List Vercel projects.", handler=vercel_list_projects, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":100}},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="vercel_get_project", description="Get a Vercel project.", handler=vercel_get_project, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project":{"type":"string"}},"required":["project"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="vercel_list_deployments", description="List Vercel deployments.", handler=vercel_list_deployments, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":100}},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="vercel_get_deployment", description="Get a Vercel deployment.", handler=vercel_get_deployment, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"deployment":{"type":"string"}},"required":["deployment"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="vercel_list_domains", description="List Vercel domains.", handler=vercel_list_domains, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="vercel_create_deployment", description="Create a Vercel deployment.", handler=vercel_create_deployment, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"project":{"type":"string"},"target":{"type":"string"},"git_source":{"type":"object"}},"required":["project"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=2),
        ToolDefinition(name="vercel_cancel_deployment", description="Cancel a Vercel deployment.", handler=vercel_cancel_deployment, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"deployment":{"type":"string"}},"required":["deployment"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=20, max_calls_per_request=2),

        ToolDefinition(name="railway_list_projects", description="List Railway projects.", handler=railway_list_projects, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="railway_list_services", description="List Railway services.", handler=railway_list_services, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"}},"required":["project_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="railway_get_deployments", description="List Railway deployments.", handler=railway_get_deployments, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"service_id":{"type":"string"}},"required":["service_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="railway_get_deployment", description="Get a Railway deployment.", handler=railway_get_deployment, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"deployment_id":{"type":"string"}},"required":["deployment_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="railway_redeploy", description="Redeploy a Railway deployment.", handler=railway_redeploy, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"deployment_id":{"type":"string"}},"required":["deployment_id"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=2),
        ToolDefinition(name="railway_restart_service", description="Restart a Railway service.", handler=railway_restart_service, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"service_id":{"type":"string"}},"required":["service_id"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=2),

        ToolDefinition(name="cloudflare_list_zones", description="List Cloudflare zones.", handler=cloudflare_list_zones, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),

        ToolDefinition(name="supabase_list_projects", description="List Supabase projects.", handler=supabase_list_projects, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="supabase_get_project", description="Get Supabase project details.", handler=supabase_get_project, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"}},"required":["project_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="supabase_list_branches", description="List Supabase branches.", handler=supabase_list_branches, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"}},"required":["project_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="supabase_list_edge_functions", description="List Supabase Edge Functions.", handler=supabase_list_edge_functions, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"}},"required":["project_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="supabase_get_advisors", description="Read Supabase security or performance advisors.", handler=supabase_get_advisors, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"},"type":{"type":"string","enum":["security","performance"]}},"required":["project_id","type"],"additionalProperties":False}, timeout_seconds=20, max_calls_per_request=3),
        ToolDefinition(name="supabase_execute_sql", description="Execute SQL against Supabase Postgres.", handler=supabase_execute_sql, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"},"query":{"type":"string"}},"required":["project_id","query"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=2),

        ToolDefinition(name="terminal_list_directory", description="List files in the isolated terminal sandbox.", handler=terminal_list_directory, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"path":{"type":"string"},"cwd":{"type":"string"}},"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=5),
        ToolDefinition(name="terminal_read_file", description="Read a file from the isolated terminal sandbox.", handler=terminal_read_file, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"path":{"type":"string"},"cwd":{"type":"string"}},"required":["path"],"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=5),
        ToolDefinition(name="terminal_write_file", description="Write a file inside the isolated terminal sandbox.", handler=terminal_write_file, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"},"cwd":{"type":"string"}},"required":["path","content"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=4),
        ToolDefinition(name="terminal_git_status", description="Read git status.", handler=terminal_git_status, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"cwd":{"type":"string"}},"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=5),
        ToolDefinition(name="terminal_git_diff", description="Read git diff.", handler=terminal_git_diff, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"cwd":{"type":"string"}},"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=5),
        ToolDefinition(name="terminal_git_log", description="Read recent git history.", handler=terminal_git_log, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"cwd":{"type":"string"}},"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=3),
        ToolDefinition(name="terminal_git_branch", description="List git branches.", handler=terminal_git_branch, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"cwd":{"type":"string"}},"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=5),
        ToolDefinition(name="terminal_git_checkout", description="Checkout a branch in the sandbox workspace.", handler=terminal_git_checkout, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"branch":{"type":"string"},"cwd":{"type":"string"}},"required":["branch"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=3),
        ToolDefinition(name="terminal_git_commit", description="Commit staged workspace changes in the sandbox.", handler=terminal_git_commit, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"message":{"type":"string"},"cwd":{"type":"string"}},"required":["message"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=60, max_calls_per_request=2),
        ToolDefinition(name="terminal_run_tests", description="Run tests in the isolated sandbox.", handler=terminal_run_tests, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"},"timeout":{"type":"integer","minimum":1,"maximum":60}},"additionalProperties":False}, requires_confirmation=True, timeout_seconds=65, max_calls_per_request=3),
        ToolDefinition(name="terminal_run_lint", description="Run lint checks in the isolated sandbox.", handler=terminal_run_lint, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"},"timeout":{"type":"integer","minimum":1,"maximum":60}},"additionalProperties":False}, requires_confirmation=True, timeout_seconds=65, max_calls_per_request=3),
        ToolDefinition(name="terminal_run_build", description="Run a build in the isolated sandbox.", handler=terminal_run_build, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"},"timeout":{"type":"integer","minimum":1,"maximum":60}},"required":["command"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=65, max_calls_per_request=2),
        ToolDefinition(name="terminal_install_package", description="Install a package in the isolated sandbox.", handler=terminal_install_package, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"manager":{"type":"string","enum":["npm","pnpm","yarn","pip"]},"package":{"type":"string"},"cwd":{"type":"string"}},"required":["manager","package"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=65, max_calls_per_request=2),
    ]

    for definition in definitions:
        try:
            registry.register(definition)
        except ValueError as exc:
            if not str(exc).startswith("Tool already registered:"):
                raise
