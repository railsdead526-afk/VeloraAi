import os
from typing import Any

from app.services.supabase_sql_policy import validate_read_only_sql
from app.tools.providers import ToolProviderError, _request


def _token() -> str:
    token = os.getenv("SUPABASE_ACCESS_TOKEN", "")
    if not token:
        raise ToolProviderError("SUPABASE_ACCESS_TOKEN is not configured")
    return token


def _project(arguments: dict[str, Any]) -> str:
    project = str(arguments.get("project_id", "")).strip()
    if not project:
        raise ToolProviderError("project_id is required")
    return project


def supabase_list_projects(_: dict[str, Any]) -> dict[str, Any]:
    return _request("GET", "https://api.supabase.com/v1/projects", token=_token())


def supabase_get_project(arguments: dict[str, Any]) -> dict[str, Any]:
    project = _project(arguments)
    return _request("GET", f"https://api.supabase.com/v1/projects/{project}", token=_token())


def supabase_list_branches(arguments: dict[str, Any]) -> dict[str, Any]:
    project = _project(arguments)
    return _request("GET", f"https://api.supabase.com/v1/projects/{project}/branches", token=_token())


def supabase_query_sql(arguments: dict[str, Any]) -> dict[str, Any]:
    project = _project(arguments)
    query = validate_read_only_sql(arguments.get("query", ""))
    return _request(
        "POST",
        f"https://api.supabase.com/v1/projects/{project}/database/query",
        token=_token(),
        json={"query": query},
    )


def supabase_execute_sql(arguments: dict[str, Any]) -> dict[str, Any]:
    project = _project(arguments)
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ToolProviderError("query is required")
    return _request(
        "POST",
        f"https://api.supabase.com/v1/projects/{project}/database/query",
        token=_token(),
        json={"query": query},
    )


def supabase_list_edge_functions(arguments: dict[str, Any]) -> dict[str, Any]:
    project = _project(arguments)
    return _request("GET", f"https://api.supabase.com/v1/projects/{project}/functions", token=_token())


def supabase_get_advisors(arguments: dict[str, Any]) -> dict[str, Any]:
    project = _project(arguments)
    advisor_type = str(arguments.get("type", "security"))
    if advisor_type not in {"security", "performance"}:
        raise ToolProviderError("type must be security or performance")
    return _request("GET", f"https://api.supabase.com/v1/projects/{project}/advisors/{advisor_type}", token=_token())
