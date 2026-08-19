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
from app.tools.providers import (
    cloudflare_list_zones,
    github_list_repositories,
    github_read_file,
    railway_list_projects,
    supabase_list_projects,
    vercel_list_projects,
)
from app.tools.terminal import terminal_exec


READ_PLANS = frozenset({"free", "pro", "max", "admin"})
WRITE_PLANS = frozenset({"pro", "max", "admin"})
TERMINAL_PLANS = frozenset({"pro", "max", "admin"})


def register_platform_tools(registry) -> None:
    definitions = [
        ToolDefinition(
            name="github_list_repositories",
            description="List repositories available to the authenticated GitHub account.",
            handler=github_list_repositories,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {"per_page": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="github_read_file",
            description="Read a file from a repository. Read-only operation.",
            handler=github_read_file,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {"repository": {"type": "string", "description": "owner/repository"}, "path": {"type": "string"}}, "required": ["repository", "path"], "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=5,
        ),
        ToolDefinition(
            name="github_search_code",
            description="Search code visible to the authenticated GitHub account.",
            handler=github_search_code,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {"query": {"type": "string"}, "repository": {"type": "string"}, "per_page": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["query"], "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=5,
        ),
        ToolDefinition(
            name="github_list_branches",
            description="List branches for a repository.",
            handler=github_list_branches,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {"repository": {"type": "string"}, "per_page": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["repository"], "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=5,
        ),
        ToolDefinition(
            name="github_list_issues",
            description="List repository issues.",
            handler=github_list_issues,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {"repository": {"type": "string"}, "state": {"type": "string", "enum": ["open", "closed", "all"]}, "per_page": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["repository"], "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=5,
        ),
        ToolDefinition(
            name="github_list_pull_requests",
            description="List pull requests for a repository.",
            handler=github_list_pull_requests,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {"repository": {"type": "string"}, "state": {"type": "string", "enum": ["open", "closed", "all"]}, "per_page": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["repository"], "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=5,
        ),
        ToolDefinition(
            name="github_create_branch",
            description="Create a branch from an existing branch or ref.",
            handler=github_create_branch,
            allowed_plans=WRITE_PLANS,
            parameters={"type": "object", "properties": {"repository": {"type": "string"}, "name": {"type": "string"}, "source": {"type": "string"}}, "required": ["repository", "name"], "additionalProperties": False},
            requires_confirmation=True,
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="github_write_file",
            description="Create or update a repository file on a branch.",
            handler=github_write_file,
            allowed_plans=WRITE_PLANS,
            parameters={"type": "object", "properties": {"repository": {"type": "string"}, "path": {"type": "string"}, "content": {"type": "string"}, "branch": {"type": "string"}, "message": {"type": "string"}}, "required": ["repository", "path", "content"], "additionalProperties": False},
            requires_confirmation=True,
            timeout_seconds=20,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="github_create_issue",
            description="Create a repository issue.",
            handler=github_create_issue,
            allowed_plans=WRITE_PLANS,
            parameters={"type": "object", "properties": {"repository": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, "required": ["repository", "title"], "additionalProperties": False},
            requires_confirmation=True,
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="github_create_pull_request",
            description="Create a pull request from a branch into a base branch.",
            handler=github_create_pull_request,
            allowed_plans=WRITE_PLANS,
            parameters={"type": "object", "properties": {"repository": {"type": "string"}, "title": {"type": "string"}, "head": {"type": "string"}, "base": {"type": "string"}, "body": {"type": "string"}}, "required": ["repository", "title", "head"], "additionalProperties": False},
            requires_confirmation=True,
            timeout_seconds=20,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="vercel_list_projects",
            description="List Vercel projects for the authenticated account.",
            handler=vercel_list_projects,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="railway_list_projects",
            description="List Railway projects for the authenticated account.",
            handler=railway_list_projects,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="cloudflare_list_zones",
            description="List Cloudflare zones for the authenticated account.",
            handler=cloudflare_list_zones,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="supabase_list_projects",
            description="List Supabase projects for the authenticated account.",
            handler=supabase_list_projects,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=3,
        ),
        ToolDefinition(
            name="terminal_exec",
            description="Execute a command inside the configured isolated terminal sandbox.",
            handler=terminal_exec,
            allowed_plans=TERMINAL_PLANS,
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 60},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            requires_confirmation=True,
            timeout_seconds=65,
            max_calls_per_request=3,
        ),
    ]

    for definition in definitions:
        try:
            registry.register(definition)
        except ValueError as exc:
            if not str(exc).startswith("Tool already registered:"):
                raise
