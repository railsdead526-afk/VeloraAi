from app.tools.base import ToolDefinition
from app.tools.providers import (
    cloudflare_list_zones,
    github_list_repositories,
    github_read_file,
    railway_list_projects,
    supabase_list_projects,
    vercel_list_projects,
)


READ_PLANS = frozenset({"free", "pro", "max", "admin"})


def register_platform_tools(registry) -> None:
    registry.register(
        ToolDefinition(
            name="github_list_repositories",
            description="List repositories available to the authenticated GitHub account.",
            handler=github_list_repositories,
            allowed_plans=READ_PLANS,
            parameters={
                "type": "object",
                "properties": {"per_page": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
            timeout_seconds=15,
            max_calls_per_request=3,
        )
    )
    registry.register(
        ToolDefinition(
            name="github_read_file",
            description="Read a file from a repository. Read-only operation.",
            handler=github_read_file,
            allowed_plans=READ_PLANS,
            parameters={
                "type": "object",
                "properties": {
                    "repository": {"type": "string", "description": "owner/repository"},
                    "path": {"type": "string"},
                },
                "required": ["repository", "path"],
                "additionalProperties": False,
            },
            timeout_seconds=15,
            max_calls_per_request=5,
        )
    )
    registry.register(
        ToolDefinition(
            name="vercel_list_projects",
            description="List Vercel projects for the authenticated account.",
            handler=vercel_list_projects,
            allowed_plans=READ_PLANS,
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
            timeout_seconds=15,
            max_calls_per_request=3,
        )
    )
    registry.register(
        ToolDefinition(
            name="railway_list_projects",
            description="List Railway projects for the authenticated account.",
            handler=railway_list_projects,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=3,
        )
    )
    registry.register(
        ToolDefinition(
            name="cloudflare_list_zones",
            description="List Cloudflare zones for the authenticated account.",
            handler=cloudflare_list_zones,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=3,
        )
    )
    registry.register(
        ToolDefinition(
            name="supabase_list_projects",
            description="List Supabase projects for the authenticated account.",
            handler=supabase_list_projects,
            allowed_plans=READ_PLANS,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            timeout_seconds=15,
            max_calls_per_request=3,
        )
    )
