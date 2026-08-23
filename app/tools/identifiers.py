"""Validation for identifiers that end up inside an outbound URL path.

Tool arguments come from the model, and the model can be steered by whatever it
reads: a repository file, an issue comment, a web page. Any such value that is
interpolated into a provider URL is therefore untrusted input.

The failure mode is specific. httpx resolves dot segments while building a URL,
so a project id of ``..`` turns ``/v1/projects/../database`` into
``/v1/database`` - a different endpoint, still carrying the user's bearer token.
``?`` and ``#`` truncate the path in the same way.

Percent-encoding alone does not save us: ``quote("..", safe="")`` returns ``..``
unchanged, because a dot is an unreserved character. These helpers therefore
reject the dangerous shapes outright rather than trying to escape them.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from app.tools.errors import ToolProviderError

#: Opaque provider ids: Vercel deployments, Supabase project refs, Cloudflare
#: zone and record ids, commit shas. All are alphanumeric with mild punctuation.
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
#: A single ``owner`` or ``repository`` component.
_SAFE_REPO_COMPONENT = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
#: Git refs. Deliberately narrower than what git itself allows.
_SAFE_REF = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")

_MAX_PATH_LENGTH = 1024


def _reject_traversal(value: str, *, field: str) -> None:
    if any(segment in {"", ".", ".."} for segment in value.split("/")):
        raise ToolProviderError(f"{field} must not contain path traversal")


def validate_identifier(value: str, *, field: str) -> str:
    """Accept one opaque path segment and nothing that could reshape the URL."""
    value = str(value).strip()
    if not value:
        raise ToolProviderError(f"{field} is required")
    if not _SAFE_IDENTIFIER.fullmatch(value) or value in {".", ".."}:
        raise ToolProviderError(f"{field} contains unsupported characters")
    return value


def validate_repository(value: str, *, field: str = "repository") -> str:
    """Accept exactly ``owner/repository``.

    Counting slashes is not enough on its own: ``../x`` has one slash and would
    otherwise climb out of ``/repos/``.
    """
    value = str(value).strip()
    if not value:
        raise ToolProviderError(f"{field} is required")
    parts = value.split("/")
    if len(parts) != 2 or not all(_SAFE_REPO_COMPONENT.fullmatch(part) for part in parts):
        raise ToolProviderError(f"{field} must use owner/repository format")
    if any(part in {".", ".."} for part in parts):
        raise ToolProviderError(f"{field} must use owner/repository format")
    return value


def validate_ref(value: str, *, field: str = "branch") -> str:
    """Accept a branch or tag name."""
    value = str(value).strip()
    if not value:
        raise ToolProviderError(f"{field} is required")
    if not _SAFE_REF.fullmatch(value):
        raise ToolProviderError(f"{field} contains unsupported characters")
    _reject_traversal(value, field=field)
    return value


def encode_repository_path(value: str, *, field: str = "path") -> str:
    """Validate a repository-relative file path and percent-encode it for a URL.

    Slashes are preserved because the path spans several URL segments; every
    other reserved character is escaped so it cannot start a query or fragment.
    """
    value = str(value).strip().lstrip("/")
    if not value:
        raise ToolProviderError(f"{field} is required")
    if len(value) > _MAX_PATH_LENGTH:
        raise ToolProviderError(f"{field} is too long")
    if "\\" in value or "\x00" in value:
        raise ToolProviderError(f"{field} contains unsupported characters")
    _reject_traversal(value, field=field)
    return quote(value, safe="/")
