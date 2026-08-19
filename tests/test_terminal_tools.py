from app.tools.bootstrap import get_registry


def test_terminal_capabilities_are_registered():
    names = {tool.name for tool in get_registry().list()}
    assert {
        "terminal_list_directory",
        "terminal_read_file",
        "terminal_git_status",
        "terminal_git_diff",
        "terminal_git_log",
        "terminal_run_tests",
        "terminal_run_build",
    } <= names


def test_terminal_read_operations_do_not_require_confirmation():
    registry = get_registry()
    for name in ("terminal_list_directory", "terminal_read_file", "terminal_git_status", "terminal_git_diff", "terminal_git_log"):
        assert registry.get(name).requires_confirmation is False


def test_terminal_test_and_build_require_confirmation():
    registry = get_registry()
    assert registry.get("terminal_run_tests").requires_confirmation is True
    assert registry.get("terminal_run_build").requires_confirmation is True
