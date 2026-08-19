from app.tools.base import ToolDefinition
from app.tools.github_tools import (
    github_create_branch,
    github_create_issue,
    github_create_pull_request,
    github_list_branches,
    github_list_issues,
    github_list_pull_requests,
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
    terminal_git_diff,
    terminal_git_log,
    terminal_git_status,
    terminal_list_directory,
    terminal_read_file,
    terminal_run_build,
    terminal_run_tests,
)


READ_PLANS = frozenset({"free", "pro", "max", "admin"})
WRITE_PLANS = frozenset({"pro", "max", "admin"})
TERMINAL_PLANS = frozenset({"pro", "max", "admin"})


def register_platform_tools(registry) -> None:
    definitions = [
        # GitHub
        ToolDefinition(name="github_list_repositories", description="List repositories available to the authenticated GitHub account.", handler=github_list_repositories, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"per_page":{"type":"integer","minimum":1,"maximum":100}},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="github_read_file", description="Read a file from a repository. Read-only operation.", handler=github_read_file, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string","description":"owner/repository"},"path":{"type":"string"}},"required":["repository","path"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_search_code", description="Search code visible to the authenticated GitHub account.", handler=github_search_code, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"query":{"type":"string"},"repository":{"type":"string"},"per_page":{"type":"integer","minimum":1,"maximum":100}},"required":["query"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_list_branches", description="List branches for a repository.", handler=github_list_branches, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"per_page":{"type":"integer","minimum":1,"maximum":100}},"required":["repository"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_list_issues", description="List repository issues.", handler=github_list_issues, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"state":{"type":"string","enum":["open","closed","all"]},"per_page":{"type":"integer","minimum":1,"maximum":100}},"required":["repository"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_list_pull_requests", description="List pull requests for a repository.", handler=github_list_pull_requests, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"state":{"type":"string","enum":["open","closed","all"]},"per_page":{"type":"integer","minimum":1,"maximum":100}},"required":["repository"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="github_create_branch", description="Create a branch from an existing branch or ref.", handler=github_create_branch, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"name":{"type":"string"},"source":{"type":"string"}},"required":["repository","name"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="github_write_file", description="Create or update a repository file on a branch.", handler=github_write_file, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"path":{"type":"string"},"content":{"type":"string"},"branch":{"type":"string"},"message":{"type":"string"}},"required":["repository","path","content"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=20, max_calls_per_request=3),
        ToolDefinition(name="github_create_issue", description="Create a repository issue.", handler=github_create_issue, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"title":{"type":"string"},"body":{"type":"string"}},"required":["repository","title"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="github_create_pull_request", description="Create a pull request from a branch into a base branch.", handler=github_create_pull_request, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"repository":{"type":"string"},"title":{"type":"string"},"head":{"type":"string"},"base":{"type":"string"},"body":{"type":"string"}},"required":["repository","title","head"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=20, max_calls_per_request=3),

        # Vercel
        ToolDefinition(name="vercel_list_projects", description="List Vercel projects for the authenticated account.", handler=vercel_list_projects, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":100}},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="vercel_get_project", description="Get a Vercel project by name or id.", handler=vercel_get_project, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project":{"type":"string"}},"required":["project"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="vercel_list_deployments", description="List Vercel deployments, optionally filtered by project.", handler=vercel_list_deployments, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":100}},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="vercel_get_deployment", description="Get details for a Vercel deployment.", handler=vercel_get_deployment, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"deployment":{"type":"string"}},"required":["deployment"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="vercel_list_domains", description="List domains visible to the authenticated Vercel account.", handler=vercel_list_domains, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="vercel_create_deployment", description="Create a Vercel deployment for a project.", handler=vercel_create_deployment, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"project":{"type":"string"},"target":{"type":"string"},"git_source":{"type":"object"}},"required":["project"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=2),
        ToolDefinition(name="vercel_cancel_deployment", description="Cancel a running or queued Vercel deployment.", handler=vercel_cancel_deployment, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"deployment":{"type":"string"}},"required":["deployment"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=20, max_calls_per_request=2),

        # Railway
        ToolDefinition(name="railway_list_projects", description="List Railway projects for the authenticated account.", handler=railway_list_projects, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="railway_list_services", description="List services in a Railway project.", handler=railway_list_services, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"}},"required":["project_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="railway_get_deployments", description="List recent deployments for a Railway service.", handler=railway_get_deployments, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"service_id":{"type":"string"}},"required":["service_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="railway_get_deployment", description="Get a Railway deployment by id.", handler=railway_get_deployment, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"deployment_id":{"type":"string"}},"required":["deployment_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="railway_redeploy", description="Redeploy an existing Railway deployment.", handler=railway_redeploy, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"deployment_id":{"type":"string"}},"required":["deployment_id"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=2),
        ToolDefinition(name="railway_restart_service", description="Restart a Railway service instance.", handler=railway_restart_service, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"service_id":{"type":"string"}},"required":["service_id"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=2),

        # Cloudflare
        ToolDefinition(name="cloudflare_list_zones", description="List Cloudflare zones for the authenticated account.", handler=cloudflare_list_zones, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),

        # Supabase
        ToolDefinition(name="supabase_list_projects", description="List Supabase projects for the authenticated account.", handler=supabase_list_projects, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{},"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=3),
        ToolDefinition(name="supabase_get_project", description="Get details for a Supabase project.", handler=supabase_get_project, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"}},"required":["project_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="supabase_list_branches", description="List development branches for a Supabase project.", handler=supabase_list_branches, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"}},"required":["project_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="supabase_list_edge_functions", description="List Edge Functions for a Supabase project.", handler=supabase_list_edge_functions, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"}},"required":["project_id"],"additionalProperties":False}, timeout_seconds=15, max_calls_per_request=5),
        ToolDefinition(name="supabase_get_advisors", description="Read Supabase security or performance advisor findings.", handler=supabase_get_advisors, allowed_plans=READ_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"},"type":{"type":"string","enum":["security","performance"]}},"required":["project_id","type"],"additionalProperties":False}, timeout_seconds=20, max_calls_per_request=3),
        ToolDefinition(name="supabase_execute_sql", description="Execute SQL against a Supabase Postgres project. Treat as high-risk database access.", handler=supabase_execute_sql, allowed_plans=WRITE_PLANS, parameters={"type":"object","properties":{"project_id":{"type":"string"},"query":{"type":"string"}},"required":["project_id","query"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=30, max_calls_per_request=2),

        # Terminal sandbox
        ToolDefinition(name="terminal_list_directory", description="List files in the isolated terminal sandbox.", handler=terminal_list_directory, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"path":{"type":"string"},"cwd":{"type":"string"}},"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=5),
        ToolDefinition(name="terminal_read_file", description="Read a file from the isolated terminal sandbox.", handler=terminal_read_file, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"path":{"type":"string"},"cwd":{"type":"string"}},"required":["path"],"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=5),
        ToolDefinition(name="terminal_git_status", description="Read git status in the sandbox workspace.", handler=terminal_git_status, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"cwd":{"type":"string"}},"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=5),
        ToolDefinition(name="terminal_git_diff", description="Read git diff in the sandbox workspace.", handler=terminal_git_diff, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"cwd":{"type":"string"}},"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=5),
        ToolDefinition(name="terminal_git_log", description="Read recent git history in the sandbox workspace.", handler=terminal_git_log, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"cwd":{"type":"string"}},"additionalProperties":False}, timeout_seconds=30, max_calls_per_request=3),
        ToolDefinition(name="terminal_run_tests", description="Run tests inside the isolated terminal sandbox.", handler=terminal_run_tests, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"},"timeout":{"type":"integer","minimum":1,"maximum":60}},"additionalProperties":False}, requires_confirmation=True, timeout_seconds=65, max_calls_per_request=3),
        ToolDefinition(name="terminal_run_build", description="Run a build command inside the isolated terminal sandbox.", handler=terminal_run_build, allowed_plans=TERMINAL_PLANS, parameters={"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"},"timeout":{"type":"integer","minimum":1,"maximum":60}},"required":["command"],"additionalProperties":False}, requires_confirmation=True, timeout_seconds=65, max_calls_per_request=2),
    ]

    for definition in definitions:
        try:
            registry.register(definition)
        except ValueError as exc:
            if not str(exc).startswith("Tool already registered:"):
                raise
