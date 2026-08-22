from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxPolicy:
    """Runtime contract expected from the external terminal sandbox."""

    max_execution_seconds: int = 60
    max_output_bytes: int = 1_048_576
    max_workspace_bytes: int = 524_288_000
    network_access: bool = False
    allow_host_filesystem: bool = False
    allow_backend_secrets: bool = False
    allow_privileged_operations: bool = False


policy = SandboxPolicy()
