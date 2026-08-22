# VeloraAi Security Hardening Baseline

Audit baseline: 2026-08-22

This document records verified controls and remaining production work. A checked item means the repository currently enforces or implements the control; it does not claim that external infrastructure has been configured.

## Authentication
- [x] Production rejects the default/weak `SECRET_KEY`.
- [x] Production requires a minimum 32-character signing secret.
- [x] Production rejects debug mode.
- [x] Production currently supports HS256 only and validates the configured algorithm.
- [ ] Add refresh-token rotation and revocation.
- [ ] Add user session/device management.

## AI provider
- [x] Provider boundary supports `mock`, `openai`, and Llama-compatible endpoints.
- [x] Production must use a non-mock provider.
- [x] OpenAI production configuration requires `OPENAI_API_KEY`.
- [ ] Add startup/readiness health checks for the configured provider.
- [ ] Add provider-specific spend/latency monitoring.

## Database and API
- [x] Production requires PostgreSQL.
- [x] Database changes use Alembic migrations.
- [x] Credentialed production CORS rejects `*`.
- [x] Document upload size is bounded.
- [x] Production rejects in-memory rate limiting.
- [ ] Configure Redis/shared rate-limit storage in production.
- [ ] Add backup, restore, and disaster-recovery verification.

## Tool execution and sandbox
- [x] Tool access is centralized through policy/capability checks.
- [x] Risky tools require confirmation.
- [x] Terminal execution uses the isolated sandbox service.
- [x] Default terminal executions use ephemeral workspaces with cleanup.
- [x] Sandbox control is separated from the FastAPI application host.
- [ ] Bind persistent workspace IDs to user + conversation + session before exposing them to model-driven workflows.
- [ ] Add persistent sandbox execution audit records.
- [ ] Add sandbox host monitoring and capacity limits.

## Payments
- [x] Production requires Midtrans credentials.
- [x] Production requires non-zero Pro and Max prices.
- [x] Production rejects Midtrans sandbox endpoints.
- [ ] Configure live Midtrans credentials after account activation.
- [ ] Set real Pro/Max prices and verify checkout end-to-end.
- [ ] Add payment reconciliation/idempotency monitoring.
- [ ] Add webhook failure/latency alerts.

## Deployment and operations
- [x] Backend deployment target is Railway.
- [x] Railway health check targets `/api/v1/health`.
- [x] Docker image runs the application as a non-root user.
- [ ] Provision PostgreSQL + Redis + sandbox runtime in the production environment.
- [ ] Configure secrets through deployment infrastructure, never Git.
- [ ] Add alerting for API 5xx, AI provider failures, payment failures, and sandbox failures.

## Supply chain
- [ ] Add dependency vulnerability scanning to CI.
- [ ] Regularly refresh pinned dependencies.
- [ ] Keep FastAPI/Pydantic on supported releases; Pydantic v1 is no longer appropriate for the modern FastAPI line.
