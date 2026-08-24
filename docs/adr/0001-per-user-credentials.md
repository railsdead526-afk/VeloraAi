# ADR 0001: Per-user encrypted third-party credentials

Status: Accepted
Date: 2026-08-22

## Context

Every tool in `app/tools/` resolved its access token from process environment
variables (`GITHUB_TOKEN`, `VERCEL_TOKEN`, `CLOUDFLARE_API_TOKEN`,
`SUPABASE_ACCESS_TOKEN`, `RAILWAY_TOKEN`).

The product, however, has user accounts, roles, plans, and paid subscriptions.
The combination meant that any authenticated user who triggered a GitHub tool
authenticated **as the operator**, against the operator's repositories. One
account could read and mutate resources visible to every other account.

This was not a hardening gap. It made the product structurally single-tenant
while it was being sold as multi-tenant, and it blocked public signup entirely.

## Decision

1. Credentials are stored per user in `user_integrations`, encrypted with
   AES-256-GCM (`app/core/crypto.py`).
2. The owning `user_id` and `provider` are bound into the ciphertext as
   *associated data*. A ciphertext copied onto another user's row fails to
   decrypt, so tenant isolation is enforced cryptographically rather than only
   by a `WHERE` clause.
3. `CREDENTIAL_ENCRYPTION_KEYS` holds an ordered key list. The first key
   encrypts; all keys decrypt. Rotation is therefore zero-downtime.
4. Tools call `resolve_credential(provider)`, which reads a `ContextVar` bound
   to the requesting user for the duration of the request.
5. `ALLOW_ENV_TOOL_CREDENTIALS=true` restores the old behaviour for local
   development only. Production refuses to boot with it enabled.

## Why a ContextVar

The alternative was threading a credential argument through roughly fifty tool
handler signatures and every intermediate call site. A `ContextVar` avoids that
churn and, critically, is copied into worker threads by `asyncio.to_thread`,
which is how the executor runs synchronous handlers. The binding therefore
survives the async-to-thread hop without extra plumbing.

The risk of ambient context is that a missing binding fails *open*. It is
mitigated by making the unbound case raise: `resolve_credential` refuses to
return anything when no context is bound, and the production config gate blocks
the environment fallback.

## Consequences

Positive: public signup becomes safe; a leaked database yields no usable
tokens; per-user revocation is a single row delete; the audit log attributes
tool use to a real user.

Negative: users must connect their own providers before tools work, which is
additional onboarding friction. Losing `CREDENTIAL_ENCRYPTION_KEYS` makes every
stored credential unrecoverable, so key custody is now a first-class
operational concern (see `docs/runbook.md` §5, §6).

Follow-up: replace pasted personal access tokens with proper OAuth flows per
provider, so VeloraAi never handles a long-lived user secret at all.
