from __future__ import annotations

import re
from pathlib import PurePosixPath


_MAX_COMMAND_LENGTH = 4096
_MAX_PATH_LENGTH = 512
_SAFE_PACKAGE = re.compile(r"^[A-Za-z0-9_@./:+-]+$")
_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/-]+$")


class TerminalSafetyError(ValueError):
    """Raised when terminal input would escape the intended sandbox contract."""


def validate_relative_path(value: str, *, field: str, allow_current: bool = True) -> str:
    value = value.strip()
    if not value:
        if allow_current and field == "cwd":
            return "."
        raise TerminalSafetyError(f"{field} is required")
    if len(value) > _MAX_PATH_LENGTH:
        raise TerminalSafetyError(f"{field} is too long")
    if value.startswith("/") or value.startswith("~"):
        raise TerminalSafetyError(f"{field} must stay inside the terminal workspace")
    parts = PurePosixPath(value.replace("\\", "/")).parts
    if any(part in {"..", ""} for part in parts):
        raise TerminalSafetyError(f"{field} must not contain parent traversal")
    return value


def validate_branch(value: str) -> str:
    value = value.strip()
    if not value or len(value) > _MAX_PATH_LENGTH or not _SAFE_BRANCH.fullmatch(value):
        raise TerminalSafetyError("invalid git branch")
    if any(part == ".." for part in value.replace("\\", "/").split("/")):
        raise TerminalSafetyError("invalid git branch")
    return value


def validate_commit_message(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 1000:
        raise TerminalSafetyError("invalid commit message")
    return value


def validate_package(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 200 or not _SAFE_PACKAGE.fullmatch(value):
        raise TerminalSafetyError("invalid package name")
    return value


def validate_fixed_command(command: str, *, allowed_prefixes: tuple[tuple[str, ...], ...]) -> str:
    command = command.strip()
    if not command or len(command) > _MAX_COMMAND_LENGTH:
        raise TerminalSafetyError("invalid terminal command")
    forbidden = (";", "&&", "||", "|", ">", "<", "`", "$(")
    if any(token in command for token in forbidden):
        raise TerminalSafetyError("shell operators are not allowed")
    parts = tuple(command.split())
    if not parts or not any(parts[: len(prefix)] == prefix for prefix in allowed_prefixes):
        raise TerminalSafetyError("terminal command is not allowed")
    return command
