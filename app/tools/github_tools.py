import base64
import os
from typing import Any

from app.tools.providers import ToolProviderError, _request


def _token() -> str:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise ToolProviderError("GITHUB_TOKEN is not configured")
    return token


def _repo(arguments: dict[str, Any]) -> str:
    repo = str(arguments.get("repository", "")).strip()
    if repo.count("/") != 1:
        raise ToolProviderError("repository must use owner/repository format")
    return repo


def github_search_code(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ToolProviderError("query is required")
    if arguments.get("repository"):
        query = f"{query} repo:{_repo(arguments)}"
    per_page = min(max(int(arguments.get("per_page", 20)), 1), 100)
    return _request("GET", f"https://api.github.com/search/code?q={query}&per_page={per_page}", token=token)


def github_list_branches(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    per_page = min(max(int(arguments.get("per_page", 30)), 1), 100)
    return _request("GET", f"https://api.github.com/repos/{repo}/branches?per_page={per_page}", token=token)


def github_list_issues(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    state = str(arguments.get("state", "open"))
    if state not in {"open", "closed", "all"}:
        raise ToolProviderError("state must be open, closed, or all")
    per_page = min(max(int(arguments.get("per_page", 30)), 1), 100)
    return _request("GET", f"https://api.github.com/repos/{repo}/issues?state={state}&per_page={per_page}", token=token)


def github_list_pull_requests(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    state = str(arguments.get("state", "open"))
    if state not in {"open", "closed", "all"}:
        raise ToolProviderError("state must be open, closed, or all")
    per_page = min(max(int(arguments.get("per_page", 30)), 1), 100)
    return _request("GET", f"https://api.github.com/repos/{repo}/pulls?state={state}&per_page={per_page}", token=token)


def github_create_branch(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    name = str(arguments.get("name", "")).strip()
    source = str(arguments.get("source", "main")).strip()
    if not name:
        raise ToolProviderError("name is required")
    source_data = _request("GET", f"https://api.github.com/repos/{repo}/git/ref/heads/{source}", token=token)
    sha = ((source_data.get("object") or {}).get("sha"))
    if not sha:
        raise ToolProviderError("source branch was not found")
    return _request(
        "POST",
        f"https://api.github.com/repos/{repo}/git/refs",
        token=token,
        json={"ref": f"refs/heads/{name}", "sha": sha},
    )


def github_write_file(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    path = str(arguments.get("path", "")).strip().lstrip("/")
    content = arguments.get("content")
    branch = str(arguments.get("branch", "main")).strip()
    message = str(arguments.get("message", "Update file")).strip()
    if not path or not isinstance(content, str):
        raise ToolProviderError("path and string content are required")
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    payload: dict[str, Any] = {"message": message, "content": encoded, "branch": branch}
    existing = None
    try:
        existing = _request("GET", f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}", token=token)
    except ToolProviderError:
        existing = None
    if isinstance(existing, dict) and existing.get("sha"):
        payload["sha"] = existing["sha"]
    return _request("PUT", f"https://api.github.com/repos/{repo}/contents/{path}", token=token, json=payload)


def github_create_issue(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    title = str(arguments.get("title", "")).strip()
    body = str(arguments.get("body", ""))
    if not title:
        raise ToolProviderError("title is required")
    return _request("POST", f"https://api.github.com/repos/{repo}/issues", token=token, json={"title": title, "body": body})


def github_create_pull_request(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    title = str(arguments.get("title", "")).strip()
    head = str(arguments.get("head", "")).strip()
    base = str(arguments.get("base", "main")).strip()
    body = str(arguments.get("body", ""))
    if not title or not head:
        raise ToolProviderError("title and head are required")
    return _request(
        "POST",
        f"https://api.github.com/repos/{repo}/pulls",
        token=token,
        json={"title": title, "head": head, "base": base, "body": body},
    )
