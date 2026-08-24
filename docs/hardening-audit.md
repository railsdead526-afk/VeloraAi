# VeloraAi production hardening audit

Status: active engineering baseline. This document records controls that are
verified **in this repository** and gates that remain open. It is not a claim
that external infrastructure has been secured, nor that a third party has
audited it.

Last updated: 2026-08-22 (release 1.0.0)

## Verified in repository

### Tenant isolation
- Third-party credentials are stored per user, encrypted with AES-256-GCM.
- `user_id` and `provider` are bound into the ciphertext as associated data, so
  a ciphertext moved between rows fails authentication rather than decrypting.
- Tools resolve credentials from a request-scoped context, never from process
  environment. The unbound case raises instead of falling back.
- The development environment fallback is refused at boot in production.
- Every user-owned query (conversations, messages, documents, chunks, vector
  search, payments, integrations) filters on `user_id`.
- Regression tests cover cross-user read, cross-user delete, and ciphertext
  transplantation.

### Authentication
- Argon2id password hashing; legacy pbkdf2 hashes verify and upgrade on login.
- Access tokens are short lived and carry a revocable `jti`.
- Refresh tokens are opaque, stored as SHA-256 digests, and rotate on use.
- Refresh-token replay revokes the entire session family.
- Password change and reset revoke all sessions.
- Per-email lockout on repeated failures, on top of IP rate limiting.
- Password reset responses are constant regardless of account existence.
- Verification and reset tokens are single use and expiring.
- Account deletion is a soft delete that preserves financial and audit records.

### Cost control
- Every non-admin plan bounds embedding spend and stored document count.
  Indexing is refused before the provider is called, not after.
- Re-indexing consumes embedding budget like a first index, because it makes
  the same provider calls, but is not refused by the document count.
- The token estimate is deliberately conservative, so the ceiling is not
  overshot by an under-count.
- List endpoints are paginated with an enforced maximum page size.

### Billing
- Webhook signatures are verified in constant time, then re-verified against
  the provider API before any state change.
- Amounts are matched against the stored payment; the row is locked with
  `SELECT ... FOR UPDATE`.
- Terminal statuses make duplicate notifications idempotent.
- Subscriptions carry a bounded period, a grace window, and an expiry sweep.
- Entitlement is derived from period state, not from a payment having ever
  occurred.
- Renewals extend from the existing period end.
- Invoice numbers are sequential per month; VAT is recorded per payment.

### Configuration
- Production refuses: SQLite, `public` schema, weak or missing `SECRET_KEY`,
  debug mode, `memory://` rate limiting, wildcard or plaintext CORS, missing or
  wildcard trusted hosts, plaintext frontend URL, mock AI provider, missing
  provider or Midtrans credentials, zero prices, missing credential encryption
  keys, shared environment tool credentials, unverified signups, and an
  unprotected metrics endpoint.

### Execution safety
- Terminal execution is routed through the versioned `SandboxClient` boundary.
- The sandbox runs each command with network isolation, dropped capabilities,
  no-new-privileges, a read-only root filesystem, pid/CPU/memory limits,
  bounded output, and an isolated per-workspace mount.
- Ephemeral workspaces are removed in a `finally` block.
- Tool policy and approval checks run before execution.
- Persistent workspace IDs are not an authorization mechanism.

### Client
- Access tokens are refreshed transparently; a 401 rotates the refresh token
  once and replays the request, with concurrent 401s sharing one refresh so a
  replay is never mistaken for token theft.
- Sign-out revokes the session server side rather than only clearing storage.
- The client mirrors the server password policy before submitting.
- Third-party tokens are write-only in the UI; only a masked fingerprint is
  ever displayed.

### Transport and observability
- HSTS, CSP, COOP, CORP, frame denial, nosniff, and a trusted-host allowlist.
- API documentation is disabled in production.
- Structured JSON logging with automatic credential redaction.
- Request IDs correlate responses, logs, and audit rows.
- Deep readiness endpoint covering all five runtime dependencies.
- Prometheus metrics with bounded label cardinality, behind a bearer token.
- Append-only audit log for security and billing events.

### Supply chain and CI
- All dependencies pinned; Dependabot across pip, npm, Actions, and Docker.
- CI enforces: ruff lint and format, mypy on the critical surface, tests with a
  coverage floor, PostgreSQL migrations **including full reversibility**,
  `pip-audit` on both requirement sets, bandit rules, gitleaks secret scanning,
  `npm audit`, frontend typecheck and build, and a Trivy-scanned image build.
- A single `CI passed` gate aggregates every required job.
- Zero known vulnerabilities in pinned dependencies at release.

## Production gates still open

These are deliberately listed as open. None is satisfied by code alone.

### Blocking public launch
- [ ] Legal entity, ToS, and Privacy Policy in Bahasa Indonesia; PPN
      registration and e-Faktur. See `docs/legal/compliance-checklist.md`.
- [x] Email transport. SMTP is built in and selected automatically when
      `SMTP_HOST` is set; production refuses to boot without it. A hosted
      provider can still be installed through `set_email_sender`.
- [x] Integrations UI, so users can actually connect their own credentials.
- [x] Account panel: password change, session list, sign-out everywhere,
      resend verification, data export, account closure.
- [x] Billing panel wired to Midtrans Snap.
- [x] Document management panel: upload, paste, retry indexing, delete, with
      live status polling that stops when nothing is in flight.
- [x] Email-verification and password-reset landing routes, plus a
      forgot-password entry point on the sign-in form.
- [ ] Provision production credentials through the platform secret store and
      run an end-to-end AI provider smoke test.
- [ ] Configure production Midtrans and set real Pro/Max prices.
- [ ] Provision Redis for shared rate limiting.
- [ ] Deploy the sandbox service on a dedicated host with Docker isolation
      enforced by runtime configuration.
- [ ] Schedule `scripts/run_maintenance.py` hourly **and alert on failure**.
      Without it, subscriptions never expire. See `docs/deployment.md` §3.
- [ ] Move `.github/workflows-proposed/ci.yml` into `.github/workflows/`.
      The committed workflow is stale and will fail until this is done.
- [ ] Enable branch protection on `main`: required `CI passed`, required
      review, no force push.
- [ ] Make the repository private.

### Blocking scale
- [ ] External penetration test.
- [ ] Complete and record a backup restore drill (`docs/runbook.md` §5).
- [ ] Stand up monitoring, alerting, and on-call rotation against §8 of the
      runbook.
- [ ] Recurring card-on-file billing via Midtrans tokenisation.
- [x] Data export endpoint for UU PDP portability rights
      (`GET /api/v1/auth/me/export`), excluding password hashes and
      third-party secrets by construction.
- [ ] OAuth flows per provider, so VeloraAi never handles a pasted long-lived
      personal access token.
- [ ] Organisation and team model for B2B sales.
- [x] Extend mypy across the whole model layer, `app/crud`, and the
      billing/quota/audit/export services — 52 files, no blanket ignores.
- [x] mypy now covers the entire application: 94 files, no exclusions, no
      blanket ignores.
- [ ] Raise the coverage floor; `app/tools/*` provider modules remain thin.

## Release rule

A production deployment is not ready while any gate under **Blocking public
launch** remains open.

## Foundation sweep — August 2026

A systematic pass over the modules that had never been reviewed in depth. Every
finding below was reproduced before it was fixed, and each carries a regression
test.

### Fixed

| Area | Finding |
|---|---|
| `ai_tool_loop` | The sync and async copies had drifted; the sync one had lost its retry backoff, so a 429 was retried instantly. Collapsed into one implementation. |
| `ai_tool_loop`, `ai_tool_stream` | Exhausting the tool-round budget raised a 500 and discarded every token already paid for. The final round now withholds tools so the model must answer. |
| `ai_tool_stream` | A retried streaming round appended partial tool-call arguments onto those of the aborted attempt, producing invalid JSON — the tool then never ran at all. It also billed the failed attempt's tokens. |
| `rag_service` | Every chunk of a document was sent as one embeddings call. At the 10 MB upload default that is ~10,000 inputs, past every provider limit, so large documents could not be indexed. Now batched. |
| `rag_service` | Embeddings was the only provider call with no retry; one blip failed a document permanently. |
| `rag_service` | `ingest_text` was dead outside the tests and, unlike the real job, never recorded embedding usage. Removed. |
| `sandbox_client` | `workspace_id` was interpolated into a URL path. httpx resolves dot segments, so `../../v1/admin` reached a different sandbox endpoint with the operator token. Not reachable from a model today — no tool exposes the argument — but the plumbing accepted one. |
| `providers`, `github_tools`, `platform_tools`, `supabase_tools`, `cloudflare_tools` | Same class of bug for repository names, project/deployment/zone/record ids, shas and file paths. Counting slashes accepted `../x`; `quote(safe='')` left `..` untouched because a dot is unreserved. Centralised in `app/tools/identifiers.py`. |
| API | `default_limits` applied to nothing: it needs SlowAPIMiddleware, which never fires on this FastAPI version. 200 posts to the unauthenticated payment webhook produced zero 429s. Explicit decorators added. |
| `Chat.tsx` | Unguarded `JSON.parse` in the SSE loop — one malformed line discarded the reply already on screen. The reader was never released on error or abort. |
| `Chat.tsx` | Every token committed to React state, re-rendering the whole transcript per token. Now batched per animation frame. |

### Verified healthy, no change needed

- Production configuration gates reject every unsafe combination tried:
  default/short `SECRET_KEY`, wildcard or plaintext CORS, SQLite, in-memory rate
  limit storage, missing `CREDENTIAL_ENCRYPTION_KEYS`, `ALLOW_ENV_TOOL_CREDENTIALS`,
  `APP_DEBUG`, missing SMTP or trusted hosts. Docs and OpenAPI are off in production.
- `alembic check` on PostgreSQL reports no drift between migrations and models.
- `pip-audit` clean on both requirement sets; `npm audit` reports no
  vulnerabilities.
- `bandit` reports only false positives (token-type and provider name strings).
- No XSS in the frontend: React escapes message content and nothing uses
  `dangerouslySetInnerHTML`.
- `railway_*` tools were already safe — ids travel as GraphQL variables.
- The refresh path shares a single in-flight promise, so concurrent 401s cannot
  trip the server's refresh-reuse theft detection.
- Streaming failure is atomic by design: the user message is only persisted once
  the reply succeeds. Tested, deliberate, left alone.

### Second pass — services, billing and the remaining panels

| Area | Finding |
|---|---|
| `auth.login` | `user is not None and verify_password(...)` skipped Argon2 when no account matched. Measured 114 ms for a registered address against 9 ms for an unregistered one — a 12x gap visible in one request. Account enumeration, and cheaper targeted credential stuffing. Now 1.05x. |
| `rag_service` | `build_context` reads `chunk.document.name`; neither candidate query loaded the document, so five hits cost five extra SELECTs on every RAG-backed message. |
| `quota_service` | Completing a reservation that had been swept raised, and `agent_stream` rolls back on RuntimeError — so a long agent turn streamed its reply to the screen and then discarded the messages and the usage row. Paid the provider, could not charge the user. |
| `quota_service` | Settled reservation rows had no retention policy. |
| `billing_service` | Invoice numbers derived from `max()+1` with no lock. Two settlements at the same moment produced the same number and the second commit died on the UNIQUE constraint, failing a webhook for money already received. |
| `subscription_lifecycle` | Renewal reminders keyed on `(period_end - now).days`, which holds for a whole day while the sweep runs hourly. One 30-day period simulated at hourly resolution sent **72** emails: 24 per milestone. Sender reputation damage lands on verification and password-reset mail. Now 3. |
| `DocumentsPanel` | Polled for `pending`/`processing`/`indexing`; the backend emits `queued`/`processing`/`ready`/`failed`. Two names were fiction and `queued` — the state every new document starts in — was missing. The effect also had an empty dependency list, so an upload never armed the timer. Status never updated in the UI. |
| `payments` | `redirect_url` went from the gateway response through the backend to `window.location` unvalidated. A `javascript:` URL there runs in our origin, and tokens live in localStorage. |
| migrations | `0017_subscription_reminder_marker` was 33 characters; `alembic_version.version_num` is VARCHAR(32). SQLite ignores declared lengths, so the whole local suite and the SQLite job passed while only the PostgreSQL job went red. |

Guards added so these classes cannot recur silently:

- `tests/test_document_status_contract.py` parses `web/lib/documents.ts` and
  compares it against `app/models/document.py`. The drift above produced no
  exception, no log line and no test failure; only a cross-language contract
  test could have caught it.
- `tests/test_migration_chain.py` checks revision id length, a single head, no
  duplicate ids and a real downgrade — all from the SQLite job.
- `tests/test_rag_query_counts.py` counts queries rather than timing them.
- `tests/test_login_timing.py` asserts the timing ratio stays under 2x.

Every fix in this table was reproduced before being changed, and each test was
verified to fail against the previous implementation.

## Payments-off foundation pass — August 2026

Scope: the product is being deployed **without payments** while the Midtrans
business review is pending, so "no payments" had to be a first-class mode, not
a broken checkout.

| Issue | Found by | Fix |
| --- | --- | --- |
| With `PAYMENT_PROVIDER=disabled`, `/payments/config` answered `{enabled: false, reason}` but the frontend type had no `enabled` field: the billing tab rendered `Rp NaN` price buttons and a misleading "Sandbox mode" banner, and clicking upgrade dead-ended in a 502 | Contract review while wiring the first component tests | `PaymentConfigResponse` response model whitelists one shape for every provider (enabled → pricing, disabled → reason, never both); `AccountPanel` renders an honest "upgrades unavailable" state with no price buttons; regression is locked by `AccountPanel.test.tsx` |
| Provider `client_config()` dicts passed through to the browser unfiltered | Same change | The response model drops unknown keys, so a future slip (a credential landing in a provider's config dict) cannot leak to clients |
| No component-level frontend tests; the `DocumentsPanel` polling bug class would recur silently | — | React Testing Library + jsdom wired into the existing vitest run (`// @vitest-environment jsdom` per file); tests cover billing-disabled states, price rendering, safe external navigation on checkout, polling lifecycle including re-arm after upload, and failed-document error display |

Backend 728 tests green, frontend 93 (84 module + 9 component), ruff/mypy/tsc/eslint clean.

### Known limitations, accepted for now

- **Rate limits bind authenticated abuse, not anonymous traffic.** A
  `@limiter.limit` decorator wraps the endpoint function, and FastAPI resolves
  dependencies first, so an anonymous flood is rejected with 401 — and a
  malformed body with 422 — before the limiter is consulted. Blocking that needs
  a limiter at the edge.
- **Tokens live in `localStorage`.** Vulnerable to XSS by construction. There is
  no XSS today, and moving to httpOnly cookies pulls in CSRF defences; revisit
  before handling other people's production credentials at scale.
- **Frontend tests do not run in CI.** `npm test` needs adding to the Frontend
  job in `.github/workflows/ci.yml`; the change is staged in
  `.github/workflows-proposed/ci.yml`.
- **`/register` still discloses whether an email is registered**, via its 400
  "Email already registered". Unlike the login timing gap this is deliberate and
  rate limited, but it means closing the timing oracle does not by itself stop
  enumeration. Closing it properly means always answering 201 and sending a
  different email when the account already exists.
- **Quota windows are UTC.** "Daily" therefore resets at 07:00 WIB rather than
  midnight for Indonesian users. Consistent and predictable, but worth revisiting
  before selling daily-limited plans domestically.
- **Component tests cover the billing and documents panels only.** The suite now
  includes React Testing Library tests (`web/__tests__/components/`), and they
  caught the payment-disabled rendering gap below, but `Chat` and
  `IntegrationsPanel` are still exercised only through their pure modules.

