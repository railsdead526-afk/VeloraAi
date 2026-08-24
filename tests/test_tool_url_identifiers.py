"""Every identifier that reaches an outbound URL must reject path traversal.

Tool arguments are chosen by the model, and the model can be steered by content
it reads - a repository file, an issue comment, a fetched page. A value such as
``..`` climbs a level once httpx resolves dot segments, redirecting the request
to a different provider endpoint while still sending the user's bearer token.

Percent-encoding does not close this: ``quote("..", safe="")`` returns ``..``
because a dot is unreserved. The tests below therefore assert that no HTTP
request is attempted at all for a hostile identifier.
"""

from __future__ import annotations

import httpx
import pytest

from app.tools import cloudflare_tools, github_tools, platform_tools, providers, supabase_tools
from app.tools.errors import ToolProviderError
from app.tools.identifiers import (
    encode_repository_path,
    validate_identifier,
    validate_ref,
    validate_repository,
)

#: Values that must never be accepted as a single opaque URL segment.
HOSTILE_ID = ["..", ".", "../..", "a/../..", "x/..", "", "   ", "a?b", "a#b", "a b", "a/b"]
#: Values that must never be accepted as an owner/repository pair.
HOSTILE_REPO = ["..", "../x", "a/../b", "owner", "a/b/c", "", "   ", "own er/x", "owner/", "/x"]
#: Values that must never be accepted as a repository-relative file path.
HOSTILE_PATH = ["../secret", "a/../../b", "", "   ", "a\\b", "a//b", "..", "."]


@pytest.fixture(autouse=True)
def credential(monkeypatch):
    monkeypatch.setattr(
        "app.tools.credentials.resolve_credential", lambda provider: "token", raising=False
    )
    for module in (providers, github_tools, platform_tools, supabase_tools, cloudflare_tools):
        if hasattr(module, "resolve_credential"):
            monkeypatch.setattr(module, "resolve_credential", lambda provider: "token")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any outbound call from a rejected identifier is a test failure."""

    def fail(*args, **kwargs):
        raise AssertionError(f"unexpected outbound request: {args} {kwargs}")

    for attribute in ("request", "get", "post", "put", "patch", "delete"):
        monkeypatch.setattr(httpx, attribute, fail)
    monkeypatch.setattr(providers, "_request", fail)


class TestIdentifierHelpers:
    @pytest.mark.parametrize("value", HOSTILE_ID)
    def test_validate_identifier_rejects(self, value):
        with pytest.raises(ToolProviderError):
            validate_identifier(value, field="project")

    @pytest.mark.parametrize("value", ["abc", "dpl_A1", "proj.name", "a~b", "x" * 128])
    def test_validate_identifier_accepts(self, value):
        assert validate_identifier(value, field="project") == value

    @pytest.mark.parametrize("value", HOSTILE_REPO)
    def test_validate_repository_rejects(self, value):
        with pytest.raises(ToolProviderError):
            validate_repository(value)

    @pytest.mark.parametrize("value", ["owner/name", "a.b/c-d", "A_1/B_2"])
    def test_validate_repository_accepts(self, value):
        assert validate_repository(value) == value

    @pytest.mark.parametrize("value", ["..", "a/../b", "a//b", "", "a b", "a?b"])
    def test_validate_ref_rejects(self, value):
        with pytest.raises(ToolProviderError):
            validate_ref(value)

    @pytest.mark.parametrize("value", ["main", "feature/x", "release-1.2"])
    def test_validate_ref_accepts(self, value):
        assert validate_ref(value) == value

    @pytest.mark.parametrize("value", HOSTILE_PATH)
    def test_encode_repository_path_rejects(self, value):
        with pytest.raises(ToolProviderError):
            encode_repository_path(value)

    def test_encode_repository_path_escapes_reserved_characters(self):
        # A '?' would otherwise start a query string and truncate the path.
        assert encode_repository_path("dir/a b?c#d.txt") == "dir/a%20b%3Fc%23d.txt"

    def test_encode_repository_path_keeps_separators(self):
        assert encode_repository_path("/src/app/main.py") == "src/app/main.py"


@pytest.mark.parametrize("value", HOSTILE_REPO)
class TestRepositoryArgumentsAreRejected:
    def test_github_read_file(self, value):
        with pytest.raises(ToolProviderError):
            providers.github_read_file({"repository": value, "path": "README.md"})

    def test_github_list_branches(self, value):
        with pytest.raises(ToolProviderError):
            github_tools.github_list_branches({"repository": value})

    def test_github_merge_pull_request(self, value):
        with pytest.raises(ToolProviderError):
            github_tools.github_merge_pull_request({"repository": value, "pr_number": 1})


@pytest.mark.parametrize("value", HOSTILE_PATH)
class TestPathArgumentsAreRejected:
    def test_github_read_file(self, value):
        with pytest.raises(ToolProviderError):
            providers.github_read_file({"repository": "owner/name", "path": value})

    def test_github_write_file(self, value):
        with pytest.raises(ToolProviderError):
            github_tools.github_write_file(
                {"repository": "owner/name", "path": value, "content": "x"}
            )


@pytest.mark.parametrize("value", HOSTILE_ID)
class TestOpaqueIdentifiersAreRejected:
    def test_github_commit_status_sha(self, value):
        with pytest.raises(ToolProviderError):
            github_tools.github_get_commit_status({"repository": "owner/name", "sha": value})

    def test_vercel_get_project(self, value):
        with pytest.raises(ToolProviderError):
            platform_tools.vercel_get_project({"project": value})

    def test_vercel_cancel_deployment(self, value):
        with pytest.raises(ToolProviderError):
            platform_tools.vercel_cancel_deployment({"deployment": value})

    def test_supabase_get_project(self, value):
        with pytest.raises(ToolProviderError):
            supabase_tools.supabase_get_project({"project_id": value})

    def test_cloudflare_list_dns_records(self, value):
        with pytest.raises(ToolProviderError):
            cloudflare_tools.cloudflare_list_dns_records({"zone_id": value})

    def test_cloudflare_delete_dns_record(self, value):
        with pytest.raises(ToolProviderError):
            cloudflare_tools.cloudflare_delete_dns_record({"zone_id": "abc", "record_id": value})


def test_traversal_would_have_reached_another_endpoint():
    """Documents the concrete behaviour the validation exists to prevent."""
    assert httpx.URL("https://api.supabase.com/v1/projects/../database/query").path == (
        "/v1/database/query"
    )
    assert httpx.URL("https://api.github.com/repos/owner/name/contents/../../../user").path == (
        "/repos/user"
    )
