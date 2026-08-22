# Terminal Sandbox Contract

VeloraAi never executes user/model terminal commands inside the application process.
The terminal tool delegates execution to an external sandbox service through `TERMINAL_SANDBOX_URL` and `TERMINAL_SANDBOX_TOKEN`.

## Required isolation

The sandbox implementation MUST:

- execute in an isolated per-user or per-session workspace;
- deny access to the VeloraAi host filesystem;
- deny access to backend environment secrets, including API keys and database credentials;
- run without privileged host/container capabilities;
- enforce CPU, memory, process-count, and execution-time limits;
- enforce workspace and output-size limits;
- default outbound network access to disabled, enabling it only through an explicit future tool policy;
- return structured output without exposing host paths or secrets.

## Current application contract

The application-side policy defaults are:

| Limit / capability | Contract |
| --- | --- |
| Max execution time | 60 seconds |
| Max command output | 1 MiB |
| Max workspace | 500 MiB |
| Network | Disabled by default |
| Host filesystem | Denied |
| Backend secrets | Denied |
| Privileged operations | Denied |

These values define the security contract for the eventual sandbox service. They are not a claim that the current external sandbox already enforces every limit.

## Trust boundary

```text
User / Model
    |
    v
Tool Policy + Approval
    |
    v
VeloraAi Backend
    |
    | authenticated sandbox request
    v
External Sandbox
    |
    +-- isolated workspace
    +-- resource limits
    +-- restricted network
    +-- no host secrets
    +-- no host filesystem
```

Future coding, package-install, test, build, and automation tools should reuse this boundary instead of creating their own execution mechanism.
