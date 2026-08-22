# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `/verify-email` and `/reset-password` routes, and a forgot-password link on
  the sign-in form. The verification and reset emails had nowhere to land
  before this: every link 404'd.
- A test that asserts the paths hardcoded in email templates correspond to
  routes that actually exist in the Next.js tree, so renaming a route breaks
  the build instead of silently breaking every link in every inbox.
- Documents panel in the web client, making the retrieval feature reachable for
  the first time: file upload, pasted text, indexing status, retry, and delete.
  Status polling stops once nothing is mid-index rather than running forever.

### Changed

- Migrated every remaining model to SQLAlchemy 2.0 `Mapped[...]` and widened
  mypy to the **entire application**: 94 files, no excluded modules, no blanket
  ignores. The per-module override that loosened checking for models and tools
  is gone.

### Fixed

- Token counts reported by the AI provider were passed straight into
  `record_ai_usage`, which types them as integers. A provider returning
  `"1024"` as a string would have landed in the billing tables unchallenged.
  They are coerced now, and a non-numeric count raises. Found by mypy.
- `ai_tool_stream` reused a single variable for both the model result and a
  tool result, conflating the two types inside the streaming loop.
- Subscription reminder and downgrade emails linked to `/billing`, which was
  never a route — every renewal reminder would have landed on a 404. They now
  deep-link to `/?panel=billing`, which opens the billing tab on first paint.
  Caught by the new route-contract test.
- `ToolRegistry.list()` shadows the builtin `list`, so its own
  `-> list[ToolDefinition]` annotations resolved to the method rather than the
  type. Found by mypy the moment the module entered scope.

### Added (continued)

- **Data portability export** (`GET /api/v1/auth/me/export`), satisfying the
  UU PDP right to portability. Returns account, conversations, messages,
  documents, subscriptions, payments, usage, and audit history as a downloadable
  JSON archive. Password hashes, encrypted third-party tokens, refresh-token
  digests, and embedding vectors are excluded by construction, with tests
  asserting they never appear: an export file must be safe to treat as public.
  Rate limited to 3/hour and audited, because a bulk personal-data read is
  exactly what an incident investigation needs to see.
- Account panel in the web client: change password, list and revoke sessions,
  resend verification, download the data export, and close the account behind
  an email-confirmation prompt.
- Billing panel showing plan pricing in IDR and starting Midtrans checkout,
  with a visible sandbox-mode warning.
- Built-in SMTP transport for verification and password-reset email, selected
  automatically when `SMTP_HOST` is set. TLS certificate verification is
  mandatory; delivery failures are logged and alerted on rather than turning
  registration into a 500, and a failed send never writes the token to logs.
  Production now refuses to boot without a transport configured.
- Integrations panel in the web client: connect, replace, and disconnect
  provider tokens. Secrets are write-only, shown only as a masked fingerprint.

### Fixed

- **Session expiry regression.** Shortening access tokens to 15 minutes without
  teaching the client to refresh meant users were signed out every 15 minutes.
  The client now rotates the refresh token on a 401 and replays the request.
  Concurrent 401s share a single in-flight refresh, because a replayed refresh
  token is treated as theft and would revoke every session for the account.
- Streaming requests refresh the access token before opening the connection; an
  SSE body cannot be replayed after a mid-stream 401.
- The registration form enforced an 8-character minimum while the server
  required 12 plus three character classes, so valid-looking passwords failed
  with an opaque 422. The client now mirrors and explains the policy.
- Sign-out only cleared local storage, leaving the refresh session usable. It
  now calls the logout endpoint to revoke the token server side.

## [1.0.0] — 2026-08-22

The release that turns the repository from a working prototype into a
multi-tenant product with an auditable operational posture.

### Security

- **BREAKING — per-user third-party credentials.** Tools no longer read
  `GITHUB_TOKEN`, `VERCEL_TOKEN`, `RAILWAY_TOKEN`, `CLOUDFLARE_API_TOKEN`, or
  `SUPABASE_ACCESS_TOKEN` from the process environment. Previously *every*
  user's tool call authenticated as the operator, against the operator's
  resources. Credentials now live in `user_integrations`, encrypted with
  AES-256-GCM and bound to `user_id`+`provider` as associated data, and are
  resolved per request. See `docs/adr/0001-per-user-credentials.md`.
- Added `CREDENTIAL_ENCRYPTION_KEYS` with ordered multi-key support and a
  zero-downtime rotation script.
- Replaced `python-jose` with `PyJWT`, removing the unfixable `ecdsa` CVE.
- Migrated password hashing to Argon2id. Existing pbkdf2 hashes still verify
  and upgrade transparently on next login — no user is locked out.
- Added rotating refresh tokens, stored only as SHA-256 digests. Replaying a
  rotated token is treated as theft and revokes the whole session family.
- Added real logout: access tokens carry a `jti` checked against a denylist.
- Added password reset, email verification, password change, and per-email
  login lockout. Password changes revoke every session.
- Added a password strength policy (12+ characters, 3 character classes).
- Hardened production config gates: `TRUSTED_HOSTS`, https-only CORS and
  frontend URL, mandatory email verification, protected metrics endpoint, and
  a hard refusal of `ALLOW_ENV_TOOL_CREDENTIALS`.
- Added CSP, COOP, CORP, and trusted-host middleware; disabled API docs in
  production.
- Added automatic credential redaction in structured logs.
- Resolved 55 known dependency vulnerabilities across 7 packages, including 34
  in `pypdf` and 6 in `python-multipart` — both on the document upload path.

### Added

- **Subscription lifecycle.** Settlement now writes `current_period_start`,
  `current_period_end`, and `grace_until`. `sweep_subscriptions()` moves lapsed
  subscriptions to `past_due`, expires them after grace, and downgrades the
  user. Previously a single payment granted a paid plan permanently.
  See `docs/adr/0003-subscription-lifecycle.md`.
- Renewals extend from the existing period end rather than discarding unused days.
- `cancel_at_period_end` and resume.
- Sequential invoice numbers and PPN/VAT extraction (`VAT_PERCENT`).
- Renewal reminders at 7, 3, and 1 days before period end.
- `/api/v1/integrations` — connect, list, and disconnect providers. Secrets are
  write-only; responses expose only a masked fingerprint.
- Deep `/api/v1/ready` covering database, Redis, AI provider, credential
  encryption, and the sandbox service. Returns 503 when any dependency fails.
- Prometheus metrics at `/api/v1/metrics`, bearer-token protected, with bounded
  path cardinality.
- Soft account deletion that preserves billing and audit records.
- `GET /api/v1/auth/sessions` and a configurable active-session cap.
- Scripts: `generate_keys`, `run_maintenance`, `rotate_credential_keys`.
- `LICENSE` (proprietary), `SECURITY.md`, `CONTRIBUTING.md` with IP assignment,
  `CODEOWNERS`, and this changelog.
- Dependabot across pip, npm, GitHub Actions, and Docker.
- `docs/runbook.md`, three ADRs, and `docs/legal/` (compliance checklist plus
  ToS and Privacy Policy drafts).

### Changed

- CI expanded from 4 jobs to 7 required jobs: lint and types, tests with an
  enforced 72% coverage floor, PostgreSQL migrations with a full
  `downgrade base` reversibility check, security scanning (`pip-audit`, bandit
  rules, gitleaks), sandbox service, frontend (audit, typecheck, lint, build),
  and a Trivy-scanned container build.
- Added `ruff` (lint + format) and `mypy`, with type checking enforced on the
  security- and money-critical modules. Models on that path migrated to
  SQLAlchemy 2.0 `Mapped[...]`. See `docs/adr/0002-typing.md`.
- Access token lifetime reduced from 30 to 15 minutes, now paired with refresh
  tokens.
- Structured JSON logging installed application-wide.
- Test suite grew from 196 to 303 tests; coverage from 70% to 75%.

### Fixed

- Two tests failing on `main` since `5a2f9f6`: the production settings helper
  did not set `DATABASE_SCHEMA`, so the schema gate fired before the assertion
  under test.
- Partial refunds overwrote `refund_amount` instead of accumulating it, so a
  second partial refund reported the wrong total.
- `DATABASE_SCHEMA` was required in production but absent from `.env.example`,
  guaranteeing a first-deploy crash with no hint.
- Session cap ordered by `issued_at`, which is ambiguous at second resolution;
  it now orders by primary key and enforces correctly.

### Migration notes

`alembic upgrade head` applies `0015_company_hardening`. Backward compatible;
no data loss. After deploying:

1. Set `CREDENTIAL_ENCRYPTION_KEYS` — integrations cannot be stored without it.
2. Tell existing users to reconnect providers via `PUT /api/v1/integrations`;
   shared operator tokens no longer apply to their requests.
3. Schedule `python -m scripts.run_maintenance` hourly. **Without it,
   subscriptions never expire.**
4. Set `TRUSTED_HOSTS`, `METRICS_TOKEN`, and `REQUIRE_EMAIL_VERIFICATION=true`,
   or production will refuse to boot.
