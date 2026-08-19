from typing import Any

from app.tools.terminal import terminal_exec


def _run(command: str, arguments: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    return terminal_exec({"command": command, "cwd": arguments.get("cwd"), "timeout": arguments.get("timeout", timeout)})


def terminal_read_file(arguments: dict[str, Any]) -> dict[str, Any]:
    path = str(arguments.get("path", "")).strip()
    if not path:
        raise ValueError("path is required")
    return _run(f"sed -n '1,400p' -- {path!r}", arguments)


def terminal_list_directory(arguments: dict[str, Any]) -> dict[str, Any]:
    path = str(arguments.get("path", ".")).strip() or "."
    return _run(f"find {path!r} -maxdepth 2 -print | head -200", arguments)


def terminal_write_file(arguments: dict[str, Any]) -> dict[str, Any]:
    import base64
    path = str(arguments.get("path", "")).strip()
    content = arguments.get("content")
    if not path or not isinstance(content, str):
        raise ValueError("path and content are required")
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return _run(f"printf %s {encoded!r} | base64 -d > {path!r}", arguments)


def terminal_git_status(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run("git status --short --branch", arguments)


def terminal_git_diff(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run("git diff --", arguments)


def terminal_git_log(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run("git log -n 20 --oneline", arguments)


def terminal_git_branch(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run("git branch --all", arguments)


def terminal_git_checkout(arguments: dict[str, Any]) -> dict[str, Any]:
    branch = str(arguments.get("branch", "")).strip()
    if not branch:
        raise ValueError("branch is required")
    return _run(f"git checkout {branch!r}", arguments)


def terminal_git_commit(arguments: dict[str, Any]) -> dict[str, Any]:
    message = str(arguments.get("message", "")).strip()
    if not message:
        raise ValueError("message is required")
    return _run(f"git add -A && git commit -m {message!r}", arguments, 60)


def terminal_run_tests(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run(str(arguments.get("command", "pytest -q")).strip(), arguments, 60)


def terminal_run_lint(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run(str(arguments.get("command", "ruff check .")).strip(), arguments, 60)


def terminal_run_build(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "")).strip()
    if not command:
        raise ValueError("build command is required")
    return _run(command, arguments, 60)


def terminal_install_package(arguments: dict[str, Any]) -> dict[str, Any]:
    package = str(arguments.get("package", "")).strip()
    manager = str(arguments.get("manager", "")).strip().lower()
    commands = {"npm": "npm install", "pnpm": "pnpm add", "yarn": "yarn add", "pip": "python -m pip install"}
    if manager not in commands or not package:
        raise ValueError("manager and package are required")
    return _run(f"{commands[manager]} {package!r}", arguments, 120)
