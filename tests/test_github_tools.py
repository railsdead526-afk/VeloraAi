import pytest

from app.tools.errors import ToolProviderError
from app.tools.github_tools import _repo


def test_repo_requires_owner_and_name():
    assert _repo({"repository": "owner/repo"}) == "owner/repo"

    with pytest.raises(ToolProviderError):
        _repo({"repository": "repo-only"})


def test_repo_rejects_extra_path_segments():
    with pytest.raises(ToolProviderError):
        _repo({"repository": "owner/repo/file"})
