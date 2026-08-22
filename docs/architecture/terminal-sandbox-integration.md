# Terminal Sandbox Integration

Terminal tools execute through `SandboxClient` rather than calling the sandbox HTTP API directly.

## Workspace lifecycle

- Without `workspace_id`, an execution receives a new ephemeral workspace and the workspace is deleted in `finally`.
- With an explicit `workspace_id`, multiple tool calls may reuse the same isolated workspace.
- Workspace IDs are execution context, not global application state.
- The caller is responsible for lifecycle termination of persistent workspaces.

## Security boundary

The terminal tool never receives Docker access or host filesystem access. The backend only knows the sandbox control API and its service token.

Persistent workspaces must be bound to an authenticated user/conversation/session by the orchestration layer before being exposed to model-driven workflows. Do not accept arbitrary user-supplied workspace IDs as an authorization mechanism.
