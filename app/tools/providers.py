import os
from typing import Any
from urllib.parse import quote

import httpx


class ToolProviderError(Exception):
    """Raised when an external tool provider cannot be reached safely."""


def _request(
    method: str,
    url: str,
    *,
    token: str,
    headers: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json"}
    # Read-only GitHub endpoints work unauthenticated for public repositories;
    # only attach the Authorization header when a token is configured.
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    if headers:
        request_headers.update(headers)
    try:
        response = httpx.request(method, url, headers=request_headers, json=json, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}
    except (httpx.HTTPError, ValueError) as exc:
        raise ToolProviderError("External provider request failed") from exc


def _optional_token() -> str:
    """Token for read-only operations: unauthenticated access is allowed for
    public repositories, so a missing GITHUB_TOKEN is not fatal here."""
    return os.getenv("GITHUB_TOKEN", "")


def github_list_repositories(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _optional_token()
    if not token:
        raise ToolProviderError("GITHUB_TOKEN is not configured")
    per_page = min(max(int(arguments.get("per_page", 20)), 1), 100)
    data = _request("GET", f"https://api.github.com/user/repos?per_page={per_page}", token=token)
    return {"repositories": data.get("data", data)}


def github_read_file(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _optional_token()
    repo = str(arguments.get("repository", "")).strip()
    path = str(arguments.get("path", "")).strip().lstrip("/")
    if not repo or not path or repo.count("/") != 1:
        raise ToolProviderError("Invalid GitHub tool arguments")
    data = _request("GET", f"https://api.github.com/repos/{repo}/contents/{path}", token=token)
    return {
        "name": data.get("name"),
        "path": data.get("path"),
        "sha": data.get("sha"),
        "content": data.get("content"),
        "encoding": data.get("encoding"),
    }


def github_list_contents(arguments: dict[str, Any]) -> dict[str, Any]:
    """List files/directories at a repository path (read-only, low risk)."""
    token = _optional_token()
    repo = str(arguments.get("repository", "")).strip()
    path = str(arguments.get("path", "")).strip().lstrip("/")
    ref = str(arguments.get("ref", "")).strip()
    if not repo or repo.count("/") != 1:
        raise ToolProviderError("Invalid GitHub tool arguments")
    encoded_path = quote(path, safe="/") if path else ""
    suffix = f"?ref={quote(ref, safe='')}" if ref else ""
    data = _request(
        "GET",
        f"https://api.github.com/repos/{repo}/contents/{encoded_path}{suffix}",
        token=token,
    )
    items = data.get("data", data)
    if isinstance(items, dict):
        items = [items]
    entries = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            entries.append(
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "type": item.get("type"),
                    "size": item.get("size"),
                }
            )
    return {"repository": repo, "path": path or "/", "entries": entries}


def vercel_list_projects(arguments: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("VERCEL_TOKEN", "")
    if not token:
        raise ToolProviderError("VERCEL_TOKEN is not configured")
    limit = min(max(int(arguments.get("limit", 20)), 1), 100)
    return _request("GET", f"https://api.vercel.com/v9/projects?limit={limit}", token=token)


def railway_list_projects(arguments: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("RAILWAY_TOKEN", "")
    if not token:
        raise ToolProviderError("RAILWAY_TOKEN is not configured")
    query = "query { projects { nodes { id name description } } }"
    return _request("POST", "https://backboard.railway.com/graphql/v2", token=token, json={"query": query})


def cloudflare_list_zones(arguments: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if not token:
        raise ToolProviderError("CLOUDFLARE_API_TOKEN is not configured")
    return _request(
        "GET",
        "https://api.cloudflare.com/client/v4/zones?per_page=50",
        token=token,
        headers={"Authorization": f"Bearer {token}"},
    )


def supabase_list_projects(arguments: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("SUPABASE_ACCESS_TOKEN", "")
    if not token:
        raise ToolProviderError("SUPABASE_ACCESS_TOKEN is not configured")
    return _request(
        "GET",
        "https://api.supabase.com/v1/projects",
        token=token,
        headers={"Authorization": f"Bearer {token}"},
    )
