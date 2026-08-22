import base64
import shlex
from typing import Any

from app.tools.terminal import terminal_exec
from app.tools.terminal_safety import (
    TerminalSafetyError,
    validate_branch,
    validate_commit_message,
    validate_fixed_command,
    validate_package,
    validate_relative_path,
)


def _quote(value: str) -> str:
    return shlex.quote(value)


def _workspace_path(arguments: dict[str, Any], *, field: str = "cwd") -> str | None:
    value = arguments.get(field)
    if value is None:
        return None
    return validate_relative_path(str(value), field=field)


def _run(command: str, arguments: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    cwd = _workspace_path(arguments)
    execution = {"command": command, "cwd": cwd, "timeout": arguments.get("timeout", timeout)}
    workspace_id = arguments.get("workspace_id")
    if isinstance(workspace_id, str) and workspace_id.strip():
        execution["workspace_id"] = workspace_id.strip()
    return terminal_exec(execution)


def terminal_read_file(arguments: dict[str, Any]) -> dict[str, Any]:
    path = validate_relative_path(str(arguments.get("path", "")), field="path", allow_current=False)
    return _run(f"sed -n '1,400p' -- {_quote(path)}", arguments)


def terminal_list_directory(arguments: dict[str, Any]) -> dict[str, Any]:
    path = validate_relative_path(str(arguments.get("path", ".")), field="path")
    return _run(f"find {_quote(path)} -maxdepth 2 -print | head -200", arguments)


def terminal_write_file(arguments: dict[str, Any]) -> dict[str, Any]:
    path = validate_relative_path(str(arguments.get("path", "")), field="path", allow_current=False)
    content = arguments.get("content")
    if not isinstance(content, str):
        raise TerminalSafetyError("content is required")
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return _run(f"printf %s {_quote(encoded)} | base64 -d > {_quote(path)}", arguments)


def terminal_git_status(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run("git status --short --branch", arguments)


def terminal_git_diff(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run("git diff --", arguments)


def terminal_git_log(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run("git log -n 20 --oneline", arguments)


def terminal_git_branch(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run("git branch --all", arguments)


def terminal_git_checkout(arguments: dict[str, Any]) -> dict[str, Any]:
    branch = validate_branch(str(arguments.get("branch", "")))
    return _run(f"git checkout {_quote(branch)}", arguments)


def terminal_git_commit(arguments: dict[str, Any]) -> dict[str, Any]:
    message = validate_commit_message(str(arguments.get("message", "")))
    return _run(f"git add -A && git commit -m {_quote(message)}", arguments, 60)


def terminal_run_tests(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "pytest -q")).strip()
    command = validate_fixed_command(
        command,
        allowed_prefixes=(
            ("pytest",),
            ("python", "-m", "pytest"),
            ("python3", "-m", "pytest"),
            ("npm", "test"),
            ("pnpm", "test"),
            ("yarn", "test"),
        ),
    )
    return _run(command, arguments, 60)


def terminal_run_lint(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "ruff check .")).strip()
    command = validate_fixed_command(
        command,
        allowed_prefixes=(
            ("ruff",),
            ("python", "-m", "ruff"),
            ("python3", "-m", "ruff"),
            ("npm", "run", "lint"),
            ("pnpm", "run", "lint"),
            ("yarn", "lint"),
        ),
    )
    return _run(command, arguments, 60)


def terminal_run_build(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "")).strip()
    if not command:
        raise TerminalSafetyError("build command is required")
    command = validate_fixed_command(
        command,
        allowed_prefixes=(
            ("npm", "run", "build"),
            ("pnpm", "run", "build"),
            ("yarn", "build"),
            ("python", "-m", "build"),
            ("python3", "-m", "build"),
        ),
    )
    return _run(command, arguments, 60)


def terminal_install_package(arguments: dict[str, Any]) -> dict[str, Any]:
    package = validate_package(str(arguments.get("package", "")))
    manager = str(arguments.get("manager", "")).strip().lower()
    commands = {
        "npm": "npm install",
        "pnpm": "pnpm add",
        "yarn": "yarn add",
        "pip": "python -m pip install",
    }
    if manager not in commands:
        raise TerminalSafetyError("unsupported package manager")
    return _run(f"{commands[manager]} {_quote(package)}", arguments, 120)
