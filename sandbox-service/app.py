from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="VeloraAi Sandbox Service", version="1.0.0")

SANDBOX_ROOT = Path(os.getenv("SANDBOX_ROOT", "/var/lib/velora-sandbox")).resolve()
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "python:3.11-slim")
SANDBOX_TOKEN = os.getenv("SANDBOX_SERVICE_TOKEN", "")
MAX_TIMEOUT_SECONDS = 60
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_COMMAND_LENGTH = 4096
WORKSPACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
FORBIDDEN_SHELL_TOKENS = (";", "&&", "||", "|", ">", "<", "`", "$()")


class WorkspaceResponse(BaseModel):
    workspace_id: str


class ExecuteRequest(BaseModel):
    command: str = Field(min_length=1, max_length=MAX_COMMAND_LENGTH)
    cwd: str = Field(default=".", max_length=512)
    timeout: int = Field(default=30, ge=1, le=MAX_TIMEOUT_SECONDS)


class ExecuteResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not SANDBOX_TOKEN:
        raise HTTPException(status_code=503, detail="Sandbox service token is not configured")
    expected = f"Bearer {SANDBOX_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def validate_workspace_id(workspace_id: str) -> str:
    if not WORKSPACE_ID_RE.fullmatch(workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace id")
    return workspace_id


def workspace_path(workspace_id: str) -> Path:
    path = (SANDBOX_ROOT / workspace_id).resolve()
    try:
        path.relative_to(SANDBOX_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid workspace path") from exc
    return path


def validate_cwd(workspace: Path, cwd: str) -> Path:
    relative = cwd.strip() or "."
    candidate = (workspace / relative).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="cwd must stay inside workspace") from exc
    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(status_code=400, detail="cwd does not exist")
    return candidate


def validate_command(command: str) -> list[str]:
    command = command.strip()
    if not command:
        raise HTTPException(status_code=400, detail="command is required")
    if len(command) > MAX_COMMAND_LENGTH:
        raise HTTPException(status_code=400, detail="command is too long")
    if any(token in command for token in FORBIDDEN_SHELL_TOKENS):
        raise HTTPException(status_code=400, detail="shell operators are not allowed")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid command syntax") from exc
    if not argv:
        raise HTTPException(status_code=400, detail="command is required")
    return argv


def bounded_text(data: bytes) -> tuple[str, bool]:
    truncated = len(data) > MAX_OUTPUT_BYTES
    return data[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"), truncated


def docker_command(argv: list[str], workspace: Path, cwd: Path, timeout: int) -> list[str]:
    relative_cwd = cwd.relative_to(workspace)
    workdir = "/workspace" if str(relative_cwd) == "." else f"/workspace/{relative_cwd.as_posix()}"
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--pids-limit=128",
        "--cpus=1.0",
        "--memory=512m",
        "--memory-swap=512m",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
        "--mount",
        f"type=bind,src={workspace},dst=/workspace,rw",
        "--workdir",
        workdir,
        "--user=1000:1000",
        "--init",
        SANDBOX_IMAGE,
        *argv,
    ]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/workspaces", response_model=WorkspaceResponse, dependencies=[Depends(require_auth)])
def create_workspace() -> WorkspaceResponse:
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    workspace_id = uuid.uuid4().hex
    path = SANDBOX_ROOT / workspace_id
    path.mkdir(mode=0o700)
    return WorkspaceResponse(workspace_id=workspace_id)


@app.delete("/v1/workspaces/{workspace_id}", dependencies=[Depends(require_auth)])
def delete_workspace(workspace_id: str) -> dict[str, bool]:
    workspace = workspace_path(validate_workspace_id(workspace_id))
    if workspace.exists():
        shutil.rmtree(workspace)
    return {"deleted": True}


@app.post("/v1/workspaces/{workspace_id}/execute", response_model=ExecuteResponse, dependencies=[Depends(require_auth)])
def execute(workspace_id: str, request: ExecuteRequest) -> ExecuteResponse:
    workspace = workspace_path(validate_workspace_id(workspace_id))
    if not workspace.exists() or not workspace.is_dir():
        raise HTTPException(status_code=404, detail="Workspace not found")

    cwd = validate_cwd(workspace, request.cwd)
    argv = validate_command(request.command)
    command = docker_command(argv, workspace, cwd, request.timeout)

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=request.timeout + 5,
            check=False,
            text=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        out, out_truncated = bounded_text(stdout if isinstance(stdout, bytes) else str(stdout).encode())
        err, err_truncated = bounded_text(stderr if isinstance(stderr, bytes) else str(stderr).encode())
        return ExecuteResponse(
            exit_code=124,
            stdout=out,
            stderr=err,
            timed_out=True,
            truncated=out_truncated or err_truncated,
        )
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Sandbox runtime unavailable") from exc

    stdout, stdout_truncated = bounded_text(completed.stdout)
    stderr, stderr_truncated = bounded_text(completed.stderr)
    return ExecuteResponse(
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=stdout_truncated or stderr_truncated,
    )
