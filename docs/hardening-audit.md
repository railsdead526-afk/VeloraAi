# VeloraAi production hardening audit

Status: active engineering baseline. This document records verified repository controls and remaining production gates. It is not a claim that external infrastructure has been secured or audited by a third party.

## Verified in repository

- Production configuration rejects SQLite and requires PostgreSQL.
- Production configuration rejects missing or weak `SECRET_KEY` values and debug mode.
- Production configuration rejects `memory://` rate limiting.
- Production configuration rejects wildcard CORS when credentials are enabled.
- Production configuration requires AI provider credentials when using OpenAI/Llama.
- Production configuration requires non-zero Pro and Max prices.
- Terminal execution is routed through the versioned `SandboxClient` boundary.
- Ephemeral terminal workspaces are deleted in a `finally` block.
- Persistent workspace IDs are not an authorization mechanism and must be bound by orchestration.
- Sandbox runtime is designed around network isolation, dropped capabilities, no-new-privileges, read-only root, resource limits, bounded output, and isolated workspaces.
- Tool policy and approval checks are enforced before tool execution.
- CI currently exercises SQLite tests, PostgreSQL migrations, frontend build/lint, and sandbox-service tests.

## Production gates still open

- Set `AI_PROVIDER` to a real provider in production and perform an end-to-end provider smoke test.
- Provision production OpenAI/Llama credentials through deployment secrets only.
- Configure production Midtrans credentials and production endpoints only after pricing is finalized.
- Set real Pro/Max prices and verify server-side plan enforcement against payment state.
- Provision shared rate-limit storage such as Redis.
- Deploy and verify the sandbox service on a dedicated host with Docker isolation enforced by runtime configuration.
- Lock the deployment platform and document the canonical production architecture and rollback procedure.
- Replace the legacy FastAPI/Pydantic dependency stack through a dedicated compatibility-tested migration.
- Complete external security review, backup/restore test, monitoring, alerting, and incident-response procedures.

## Release rule

A production deployment is not considered ready while any required production gate above remains open.
