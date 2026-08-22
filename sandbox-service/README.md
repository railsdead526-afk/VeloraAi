# VeloraAi Sandbox Service

The sandbox service is an isolated execution boundary for high-risk tools such as terminal execution, coding agents, test runners, and future automation.

## Trust boundary

This service is a **privileged controller** because it talks to a Docker Engine. It must run on a dedicated sandbox host and must not share a Docker socket with the main VeloraAi API service.

The caller is authenticated with `SANDBOX_SERVICE_TOKEN`.

## Runtime guarantees

Each execution creates an ephemeral Docker container with:

- `--network=none`
- read-only container root filesystem
- all Linux capabilities dropped
- `no-new-privileges`
- PID limit of 128
- 1 CPU
- 512 MiB memory and no additional swap
- 64 MiB `tmpfs` at `/tmp`
- only the selected workspace bind-mounted at `/workspace`
- non-privileged UID/GID inside the execution container
- `--rm` cleanup after exit
- 60 second maximum request timeout
- 1 MiB maximum combined output per stream

These restrictions are applied by the controller and are not supplied by the caller.

## Required deployment environment

```text
SANDBOX_SERVICE_TOKEN=<long random secret>
SANDBOX_ROOT=/var/lib/velora-sandbox
SANDBOX_IMAGE=<pinned execution image>
```

The service should be reachable only from the VeloraAi backend over a private network. The Docker Engine should be dedicated to sandbox workloads. Do not pass application secrets, database credentials, provider API keys, or deployment credentials into execution containers.

## Future hardening

Before public exposure, add image digest pinning, image allowlists, workspace quotas, execution concurrency limits, seccomp/AppArmor policy validation, artifact scanning, lifecycle cleanup, and sandbox-host monitoring.
