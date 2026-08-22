# VeloraAi

AI assistant backend: authentication, conversations, streaming chat, retrieval
over your own documents, a governed tool system, and Midtrans billing.

Built as a **multi-tenant** service: every user's third-party credentials are
stored encrypted and bound to their account, and tools authenticate as the
requesting user — never as the operator.

[![CI](https://github.com/railsdead526-afk/VeloraAi/actions/workflows/ci.yml/badge.svg)](https://github.com/railsdead526-afk/VeloraAi/actions/workflows/ci.yml)

---

## Contents

- [Quick start](#quick-start)
- [Architecture](#architecture)
- [Security model](#security-model)
- [Billing model](#billing-model)
- [Configuration](#configuration)
- [API](#api)
- [Testing and quality gates](#testing-and-quality-gates)
- [Operations](#operations)
- [Production readiness](#production-readiness)
- [Documentation index](#documentation-index)

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
python -m scripts.generate_keys --write   # SECRET_KEY, CREDENTIAL_ENCRYPTION_KEYS, METRICS_TOKEN

alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd web && npm ci && npm run dev
```

Docs are at `http://localhost:8000/docs` (disabled in production).

## Architecture

```
web/                Next.js client
  │  HTTPS
app/
  api/v1/           HTTP routing, authz, rate limiting
  services/         business logic (auth, billing, RAG, credentials, AI)
  tools/            governed tool registry, policy, per-user credential context
  crud/             data access
  models/           SQLAlchemy ORM
  core/             config, database, crypto, security, metrics, logging
  │
PostgreSQL + pgvector · Redis (rate limits) · sandbox-service (isolated exec)
```

Requests never execute untrusted commands on the API host. Terminal tools are
proxied to `sandbox-service`, which runs each command in a container with
`--network=none --read-only --cap-drop=ALL --no-new-privileges`, a pid limit,
memory and CPU caps, and a per-workspace bind mount.

## Security model

| Concern | Mechanism |
| --- | --- |
| Passwords | Argon2id; legacy pbkdf2 hashes verify and upgrade on next login |
| Sessions | short-lived JWT with `jti` + opaque refresh token, hashed at rest, rotating |
| Token theft | replaying a rotated refresh token revokes the entire session family |
| Logout | access-token `jti` denylist — logout is immediate, not cosmetic |
| Brute force | per-email lockout on failed attempts, plus IP rate limiting |
| Account recovery | single-use, expiring reset tokens; reset revokes all sessions |
| Enumeration | password reset always returns 202; login failures are indistinguishable |
| Third-party tokens | AES-256-GCM, per user, with `user_id`+`provider` as associated data |
| Key rotation | ordered key list; zero-downtime re-encryption script |
| Tenant isolation | enforced in queries **and** cryptographically in the ciphertext binding |
| Transport | HSTS, CSP, COOP/CORP, frame denial, trusted-host allowlist |
| Auditing | append-only `audit_logs` with request correlation IDs |
| Logs | credential-shaped strings are redacted before emission |
| Supply chain | pinned deps, Dependabot, `pip-audit`, `npm audit`, Trivy, gitleaks in CI |

Full policy: [`SECURITY.md`](SECURITY.md). Rationale: [`docs/adr/0001-per-user-credentials.md`](docs/adr/0001-per-user-credentials.md).

### Connecting a provider

```http
PUT /api/v1/integrations
{ "provider": "github", "secret": "ghp_...", "display_name": "Personal" }
```

Secrets are write-only. Responses return a masked fingerprint (`****abcd`) and
never the value. Tools then resolve that user's credential automatically.

## Billing model

Paid plans are **bounded periods**, not one-off unlocks.

```
settlement ──▶ active ──(period ends)──▶ past_due ──(grace ends)──▶ expired
                  │                                                    │
                  └── cancel_at_period_end ──────────────────▶ canceled ┘
                                                                        ▼
                                                              role → free
```

- Renewals extend from `max(now, current_period_end)`, so paying early never
  forfeits remaining days.
- Cancellation keeps access until the paid period closes.
- `sweep_subscriptions()` runs hourly and is idempotent.
- Webhooks verify the Midtrans SHA-512 signature in constant time, re-verify
  against the Midtrans API, match the amount, and lock the row before mutating.
- Settlement assigns a sequential `invoice_number` and records the PPN
  component in `tax_amount`.

**The hourly maintenance job is revenue-critical.** If it stops, subscriptions
stop expiring. Alert on it (`docs/runbook.md` §8).

```bash
python -m scripts.run_maintenance   # cron: 0 * * * *
```

## Configuration

Every key is documented in [`.env.example`](.env.example). `Settings.validate()`
runs at import and refuses to boot on an unsafe production configuration.

Production is rejected unless all of the following hold:

| Requirement | Reason |
| --- | --- |
| PostgreSQL, non-`public` schema | isolation and migration safety |
| `SECRET_KEY` ≥ 32 chars | token forgery |
| `CREDENTIAL_ENCRYPTION_KEYS` set | credentials cannot be stored safely without it |
| `ALLOW_ENV_TOOL_CREDENTIALS=false` | shared operator tokens break tenant isolation |
| `REQUIRE_EMAIL_VERIFICATION=true` | abuse and deliverability |
| `RATE_LIMIT_STORAGE_URI` not `memory://` | limits must be shared across replicas |
| `CORS_ORIGINS` set, https, no `*` | credentialed CORS |
| `TRUSTED_HOSTS` set, no `*` | Host header attacks |
| `FRONTEND_BASE_URL` https | reset links |
| `METRICS_TOKEN` set when metrics enabled | ops data is commercially sensitive |
| Real AI provider and Midtrans keys | no mock money, no mock model |
| `PRO_PRICE_IDR`, `MAX_PRICE_IDR` > 0 | selling at zero |

## API

```text
System
  GET    /api/v1/health                     liveness
  GET    /api/v1/ready                      deep dependency check
  GET    /api/v1/info                       version and commit
  GET    /api/v1/metrics                    Prometheus (bearer token)

Auth
  POST   /api/v1/auth/register
  POST   /api/v1/auth/login                 -> access + refresh token
  POST   /api/v1/auth/refresh               rotating refresh
  POST   /api/v1/auth/logout                revokes access token + session(s)
  GET    /api/v1/auth/sessions
  POST   /api/v1/auth/verify-email
  POST   /api/v1/auth/resend-verification
  POST   /api/v1/auth/password-reset
  POST   /api/v1/auth/password-reset/confirm
  POST   /api/v1/auth/password
  GET    /api/v1/auth/me
  DELETE /api/v1/auth/me                    soft delete

Integrations
  GET    /api/v1/integrations/providers
  GET    /api/v1/integrations
  PUT    /api/v1/integrations               connect or replace (write-only secret)
  DELETE /api/v1/integrations/{provider}

Conversations
  POST   /api/v1/conversations
  GET    /api/v1/conversations
  PATCH  /api/v1/conversations/{id}
  DELETE /api/v1/conversations/{id}
  GET    /api/v1/conversations/{id}/messages
  POST   /api/v1/conversations/{id}/messages
  POST   /api/v1/conversations/{id}/messages/stream    SSE

RAG
  POST   /api/v1/rag/documents
  GET    /api/v1/rag/documents
  DELETE /api/v1/rag/documents/{id}
  POST   /api/v1/rag/search

Payments
  GET    /api/v1/payments/config
  POST   /api/v1/payments/create
  POST   /api/v1/payments/notification      Midtrans webhook
  POST   /api/v1/payments/{id}/refund       admin
```

## Testing and quality gates

```bash
pytest -q --cov=app --cov-fail-under=72
ruff check app tests scripts && ruff format --check app tests scripts
mypy
pip-audit -r requirements.txt --strict
```

> **One manual step is pending.** The hardened pipeline lives at
> `.github/workflows-proposed/ci.yml` because the automation used to prepare
> this release lacked GitHub's `workflows` permission. Move it into
> `.github/workflows/` and enable branch protection — see
> [`.github/workflows-proposed/README.md`](.github/workflows-proposed/README.md).

CI runs seven required jobs on every push and pull request: lint and types,
tests with an enforced coverage floor, PostgreSQL migrations **including a full
`downgrade base` reversibility check**, security scanning (`pip-audit`, bandit
rules, gitleaks), the sandbox service suite, frontend audit/typecheck/lint/build,
and a container build scanned with Trivy.

`main` is protected: no direct pushes, no merge without a green `CI passed`.

## Operations

- Incident response, rollback, backup/restore drills, key rotation: [`docs/runbook.md`](docs/runbook.md)
- Metrics: `GET /api/v1/metrics` (HTTP, AI tokens and cost, tool executions,
  auth events, payments, subscription counts, quota rejections)
- Every response carries `X-Request-ID`, echoed in logs and audit rows.
- Logs are JSON with automatic credential redaction.

```bash
python -m scripts.generate_keys            # bootstrap secrets
python -m scripts.run_maintenance          # hourly: expiry, purge, gauges
python -m scripts.rotate_credential_keys   # zero-downtime key rotation
```

## Production readiness

Honest status is tracked in [`docs/hardening-audit.md`](docs/hardening-audit.md)
and the original assessment in [`docs/company-readiness-audit.md`](docs/company-readiness-audit.md).

Still open before taking public money — none of these are code problems:

- legal entity, ToS and Privacy Policy in Bahasa Indonesia, PPN handling
  ([`docs/legal/compliance-checklist.md`](docs/legal/compliance-checklist.md))
- an email transport wired into `app/services/notification_service.py`
- user-facing pages for auth, billing, documents, and integrations
- recurring card-on-file billing
- external penetration test and a completed restore drill

## Documentation index

| Document | Purpose |
| --- | --- |
| [`SECURITY.md`](SECURITY.md) | vulnerability reporting and controls |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | workflow, IP assignment, definition of done |
| [`docs/runbook.md`](docs/runbook.md) | on-call procedures |
| [`docs/hardening-audit.md`](docs/hardening-audit.md) | verified controls and open gates |
| [`docs/company-readiness-audit.md`](docs/company-readiness-audit.md) | full readiness assessment |
| [`docs/adr/`](docs/adr) | architecture decisions and their trade-offs |
| [`docs/legal/`](docs/legal) | compliance checklist, ToS and Privacy drafts |
| [`docs/architecture/`](docs/architecture) | sandbox contract and integration |
| [`docs/production-database.md`](docs/production-database.md) | schema strategy |

## Licence

Proprietary. All rights reserved. See [`LICENSE`](LICENSE).
