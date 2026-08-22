# Security Policy

## Reporting a vulnerability

**Do not open a public GitHub issue for security problems.**

Report privately to **security@veloraai.com** (replace with your production
address before launch) or through GitHub's private vulnerability reporting on
this repository.

Include, where possible:

- affected component and version/commit,
- reproduction steps or proof of concept,
- observed and expected behaviour,
- assessed impact.

### Response targets

| Stage | Target |
| --- | --- |
| Acknowledgement | 48 hours |
| Initial assessment and severity rating | 5 business days |
| Fix or documented mitigation (critical) | 7 days |
| Fix or documented mitigation (high) | 30 days |
| Public disclosure | coordinated, after a fix ships |

We ask that you give us a reasonable window to remediate before any public
disclosure. We will credit reporters who request it.

## Supported versions

Only the current `main` branch and the latest production deployment receive
security fixes.

## Scope

In scope: this repository's backend (`app/`), sandbox service
(`sandbox-service/`), web client (`web/`), migrations, and CI configuration.

Out of scope: third-party services (GitHub, Midtrans, Supabase, Cloudflare,
Vercel, Railway), denial of service through volumetric traffic, and findings
that require a compromised host or physical access.

## Security controls in this repository

- Production configuration validation refuses unsafe settings at boot
  (`app/core/config.py`).
- Per-user third-party credentials are encrypted at rest with authenticated
  encryption and never read from process environment in production
  (`app/core/crypto.py`, `app/services/credential_service.py`).
- JWTs carry a `jti` and are revocable; refresh tokens are stored hashed and
  rotate on use (`app/core/security.py`, `app/services/auth_tokens.py`).
- Untrusted command execution is confined to an isolated sandbox service with
  network isolation, dropped capabilities, read-only root filesystem, and
  resource limits.
- Payment webhooks verify provider signatures in constant time and re-verify
  against the provider API before mutating state.
- Tenant isolation is enforced at query level on every user-owned resource.
- CI runs dependency vulnerability scanning (`pip-audit`, `npm audit`), static
  analysis (`ruff`, `mypy`), and secret scanning on every push and pull
  request.

## Handling secrets

Secrets belong in the deployment platform's secret store. They must never be
committed, logged, or placed in `.env.example`. `CREDENTIAL_ENCRYPTION_KEYS`
and `SECRET_KEY` are the highest-value secrets in the system; rotating them is
documented in `docs/runbook.md`.
