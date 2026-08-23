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
