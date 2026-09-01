import base64
import os
from typing import Any
from urllib.parse import quote

import httpx

from app.tools.providers import ToolProviderError, _request


def _token(required: bool = True) -> str:
    """GitHub token. Read-only operations on public repositories work
    unauthenticated, so callers pass required=False."""
    token = os.getenv("GITHUB_TOKEN", "")
    if not token and required:
        raise ToolProviderError("GITHUB_TOKEN is not configured")
    return token


def _read_token() -> str:
    return _token(required=False)


def _repo(arguments: dict[str, Any]) -> str:
    repo = str(arguments.get("repository", "")).strip()
    if repo.count("/") != 1:
        raise ToolProviderError("repository must use owner/repository format")
    return repo


def github_search_code(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _read_token()
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ToolProviderError("query is required")
    if arguments.get("repository"):
        query = f"{query} repo:{_repo(arguments)}"
    per_page = min(max(int(arguments.get("per_page", 20)), 1), 100)
    encoded_query = quote(query, safe="")
    return _request("GET", f"https://api.github.com/search/code?q={encoded_query}&per_page={per_page}", token=token)


def github_list_branches(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _read_token()
    repo = _repo(arguments)
    per_page = min(max(int(arguments.get("per_page", 30)), 1), 100)
    return _request("GET", f"https://api.github.com/repos/{repo}/branches?per_page={per_page}", token=token)


def github_list_issues(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _read_token()
    repo = _repo(arguments)
    state = str(arguments.get("state", "open"))
    if state not in {"open", "closed", "all"}:
        raise ToolProviderError("state must be open, closed, or all")
    per_page = min(max(int(arguments.get("per_page", 30)), 1), 100)
    return _request("GET", f"https://api.github.com/repos/{repo}/issues?state={state}&per_page={per_page}", token=token)


def github_list_pull_requests(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _read_token()
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
    source_data = _request("GET", f"https://api.github.com/repos/{repo}/git/ref/heads/{quote(source, safe='/-._')}", token=token)
    sha = ((source_data.get("object") or {}).get("sha"))
    if not sha:
        raise ToolProviderError("source branch was not found")
    return _request("POST", f"https://api.github.com/repos/{repo}/git/refs", token=token, json={"ref": f"refs/heads/{name}", "sha": sha})


def github_write_file(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    path = str(arguments.get("path", "")).strip().lstrip("/")
    content = arguments.get("content")
    branch = str(arguments.get("branch", "main")).strip()
    message = str(arguments.get("message", "Update file")).strip()
    if not path or not isinstance(content, str):
        raise ToolProviderError("path and string content are required")
    encoded_path = quote(path, safe="/")
    existing_sha = None
    try:
        response = httpx.get(
            f"https://api.github.com/repos/{repo}/contents/{encoded_path}?ref={quote(branch, safe='')}",
            headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if response.status_code == 200:
            existing_sha = response.json().get("sha")
        elif response.status_code != 404:
            response.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        raise ToolProviderError("Unable to inspect existing GitHub file") from exc
    payload: dict[str, Any] = {"message": message, "content": base64.b64encode(content.encode("utf-8")).decode("ascii"), "branch": branch}
    if existing_sha:
        payload["sha"] = existing_sha
    return _request("PUT", f"https://api.github.com/repos/{repo}/contents/{encoded_path}", token=token, json=payload)


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
    return _request("POST", f"https://api.github.com/repos/{repo}/pulls", token=token, json={"title": title, "head": head, "base": base, "body": body})


def github_create_issue_comment(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    issue_number = int(arguments.get("issue_number", 0))
    body = str(arguments.get("body", "")).strip()
    if issue_number < 1 or not body:
        raise ToolProviderError("issue_number and body are required")
    return _request("POST", f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments", token=token, json={"body": body})


def github_get_pr_reviews(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _read_token()
    repo = _repo(arguments)
    pr_number = int(arguments.get("pr_number", 0))
    if pr_number < 1:
        raise ToolProviderError("pr_number is required")
    return _request("GET", f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews", token=token)


def github_get_pr_comments(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _read_token()
    repo = _repo(arguments)
    pr_number = int(arguments.get("pr_number", 0))
    if pr_number < 1:
        raise ToolProviderError("pr_number is required")
    return _request("GET", f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments", token=token)


def github_get_commit_status(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _read_token()
    repo = _repo(arguments)
    sha = str(arguments.get("sha", "")).strip()
    if not sha:
        raise ToolProviderError("sha is required")
    return _request("GET", f"https://api.github.com/repos/{repo}/commits/{quote(sha, safe='')}/status", token=token)


def github_list_workflow_jobs(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _read_token()
    repo = _repo(arguments)
    run_id = int(arguments.get("run_id", 0))
    if run_id < 1:
        raise ToolProviderError("run_id is required")
    return _request("GET", f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token=token)


def github_rerun_failed_jobs(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    run_id = int(arguments.get("run_id", 0))
    if run_id < 1:
        raise ToolProviderError("run_id is required")
    return _request("POST", f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs", token=token, json={})


def github_merge_pull_request(arguments: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    repo = _repo(arguments)
    pr_number = int(arguments.get("pr_number", 0))
    method = str(arguments.get("merge_method", "squash"))
    expected_head_sha = str(arguments.get("expected_head_sha", "")).strip()
    if pr_number < 1 or method not in {"merge", "squash", "rebase"}:
        raise ToolProviderError("invalid merge arguments")
    payload: dict[str, Any] = {"merge_method": method}
    if expected_head_sha:
        payload["sha"] = expected_head_sha
    return _request("PUT", f"https://api.github.com/repos/{repo}/pulls/{pr_number}/merge", token=token, json=payload)
