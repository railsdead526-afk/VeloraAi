from typing import Any

from app.tools.terminal import terminal_exec


def terminal_read_file(arguments: dict[str, Any]) -> dict[str, Any]:
    path = str(arguments.get("path", "")).strip()
    if not path:
        raise ValueError("path is required")
    return terminal_exec({"command": f"cat -- {path}", "cwd": arguments.get("cwd"), "timeout": arguments.get("timeout", 30)})


def terminal_list_directory(arguments: dict[str, Any]) -> dict[str, Any]:
    path = str(arguments.get("path", ".")).strip() or "."
    return terminal_exec({"command": f"ls -la -- {path}", "cwd": arguments.get("cwd"), "timeout": arguments.get("timeout", 30)})


def terminal_git_status(arguments: dict[str, Any]) -> dict[str, Any]:
    return terminal_exec({"command": "git status --short --branch", "cwd": arguments.get("cwd"), "timeout": arguments.get("timeout", 30)})


def terminal_git_diff(arguments: dict[str, Any]) -> dict[str, Any]:
    return terminal_exec({"command": "git diff --", "cwd": arguments.get("cwd"), "timeout": arguments.get("timeout", 30)})


def terminal_run_tests(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "pytest -q")).strip()
    return terminal_exec({"command": command, "cwd": arguments.get("cwd"), "timeout": arguments.get("timeout", 60)})


def terminal_run_build(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "")).strip()
    if not command:
        raise ValueError("build command is required")
    return terminal_exec({"command": command, "cwd": arguments.get("cwd"), "timeout": arguments.get("timeout", 60)})


def terminal_git_log(arguments: dict[str, Any]) -> dict[str, Any]:
    return terminal_exec({"command": "git log -n 20 --oneline", "cwd": arguments.get("cwd"), "timeout": arguments.get("timeout", 30)})
