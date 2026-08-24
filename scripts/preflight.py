"""Check a production configuration before deploying it.

`Settings.validate()` already refuses to boot on an unsafe configuration, but
it stops at the *first* problem. On a platform like Railway that means a slow
loop: deploy, read one error, fix, redeploy.

This reports everything wrong at once, from the outside, without booting the
app or touching the database.

    python -m scripts.preflight                 # check the current environment
    python -m scripts.preflight --env-file .env # check a file before pasting it
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

# Checks are (key, required_when, explanation). `required_when` receives the
# resolved environment so a key can be conditional on another.
Env = dict[str, str]

OK = "  ok   "
FAIL = " FAIL  "
WARN = " warn  "


def _load_env_file(path: pathlib.Path) -> Env:
    values: Env = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _problems(env: Env) -> list[tuple[str, str, str]]:
    """Return (level, key, message) for everything that would block a deploy."""
    out: list[tuple[str, str, str]] = []

    def need(key: str, message: str, *, level: str = FAIL) -> str:
        value = env.get(key, "").strip()
        if not value:
            out.append((level, key, message))
        return value

    if env.get("APP_ENV", "").strip().lower() != "production":
        out.append((WARN, "APP_ENV", "not 'production'; production gates are not being checked"))
        return out

    secret = need("SECRET_KEY", "required; generate with scripts.generate_keys")
    if secret and len(secret) < 32:
        out.append((FAIL, "SECRET_KEY", f"only {len(secret)} chars, needs at least 32"))

    need(
        "CREDENTIAL_ENCRYPTION_KEYS",
        "required; without it no user can connect an integration. BACK IT UP SEPARATELY",
    )

    database_url = need("DATABASE_URL", "required")
    if database_url and not database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        out.append((FAIL, "DATABASE_URL", "production requires PostgreSQL"))
    if database_url and "db." in database_url and "supabase.co" in database_url:
        out.append(
            (
                FAIL,
                "DATABASE_URL",
                "this is Supabase's direct endpoint, which is IPv6-only and unreachable "
                "from Railway. Use the Session pooler string (pooler.supabase.com)",
            )
        )

    schema = env.get("DATABASE_SCHEMA", "").strip()
    if not schema or schema == "public":
        out.append((FAIL, "DATABASE_SCHEMA", "must be set and must not be 'public'"))
    elif not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        out.append((FAIL, "DATABASE_SCHEMA", "not a valid PostgreSQL identifier"))

    rate_limit = need("RATE_LIMIT_STORAGE_URI", "required")
    if rate_limit == "memory://":
        out.append((FAIL, "RATE_LIMIT_STORAGE_URI", "must be shared storage such as redis://"))

    cors = need("CORS_ORIGINS", "required; the browser origin that calls the API")
    for origin in [o.strip() for o in cors.split(",") if o.strip()]:
        if origin == "*":
            out.append((FAIL, "CORS_ORIGINS", "'*' is refused when credentials are enabled"))
        elif not origin.startswith("https://"):
            out.append((FAIL, "CORS_ORIGINS", f"{origin} must use https"))
        elif origin.endswith("/"):
            out.append(
                (FAIL, "CORS_ORIGINS", f"{origin} has a trailing slash; origins compare exactly")
            )

    hosts = need("TRUSTED_HOSTS", "required; your API hostname, no scheme")
    if "*" in hosts:
        out.append((FAIL, "TRUSTED_HOSTS", "'*' is refused in production"))
    for host in [h.strip() for h in hosts.split(",") if h.strip()]:
        if "://" in host:
            out.append((FAIL, "TRUSTED_HOSTS", f"{host} must be a hostname, not a URL"))

    frontend = need("FRONTEND_BASE_URL", "required; used in verification and reset links")
    if frontend and not frontend.startswith("https://"):
        out.append((FAIL, "FRONTEND_BASE_URL", "must use https"))

    if env.get("REQUIRE_EMAIL_VERIFICATION", "").strip().lower() != "true":
        out.append((FAIL, "REQUIRE_EMAIL_VERIFICATION", "must be 'true' in production"))

    if env.get("METRICS_ENABLED", "true").strip().lower() != "false":
        need("METRICS_TOKEN", "required while metrics are enabled")

    need("SMTP_HOST", "required; verification and reset links are undeliverable without it")
    if not env.get("SMTP_FROM", "").strip() and not env.get("SMTP_USERNAME", "").strip():
        out.append((FAIL, "SMTP_FROM", "set SMTP_FROM or SMTP_USERNAME to address outbound mail"))
    if (
        env.get("SMTP_USE_SSL", "").strip().lower() == "true"
        and env.get("SMTP_USE_STARTTLS", "true").strip().lower() == "true"
    ):
        out.append((FAIL, "SMTP_USE_SSL", "mutually exclusive with SMTP_USE_STARTTLS"))

    provider = env.get("AI_PROVIDER", "").strip().lower()
    if provider in ("", "mock"):
        out.append((FAIL, "AI_PROVIDER", "must be a real provider in production"))
    elif provider == "openai":
        need("OPENAI_API_KEY", "required when AI_PROVIDER=openai")

    payment = env.get("PAYMENT_PROVIDER", "midtrans").strip().lower()
    if payment == "disabled":
        out.append((OK, "PAYMENT_PROVIDER", "disabled; gateway and pricing checks are skipped"))
    elif payment == "midtrans":
        need("MIDTRANS_SERVER_KEY", "required while PAYMENT_PROVIDER=midtrans")
        need("MIDTRANS_CLIENT_KEY", "required while PAYMENT_PROVIDER=midtrans")
        for key in ("PRO_PRICE_IDR", "MAX_PRICE_IDR"):
            try:
                if int(env.get(key, "0")) <= 0:
                    out.append((FAIL, key, "must be greater than zero while selling"))
            except ValueError:
                out.append((FAIL, key, "must be a whole number"))

    if env.get("ALLOW_ENV_TOOL_CREDENTIALS", "").strip().lower() == "true":
        out.append(
            (FAIL, "ALLOW_ENV_TOOL_CREDENTIALS", "must be false; it breaks tenant isolation")
        )
    if env.get("APP_DEBUG", "").strip().lower() == "true":
        out.append((FAIL, "APP_DEBUG", "must be false in production"))

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=pathlib.Path, help="check a file instead of os.environ")
    args = parser.parse_args()

    env: Env = dict(os.environ)
    source = "the current environment"
    if args.env_file:
        if not args.env_file.exists():
            print(f"No such file: {args.env_file}")
            return 2
        env = _load_env_file(args.env_file)
        source = str(args.env_file)

    print(f"Pre-flight check against {source}\n")
    problems = _problems(env)

    failures = [p for p in problems if p[0] == FAIL]
    for level, key, message in problems:
        print(f"[{level}] {key}: {message}")

    print()
    if failures:
        print(f"{len(failures)} problem(s) would stop the service from starting.")
        print("Fix these before deploying; the app refuses to boot on any one of them.")
        return 1

    print("No blocking problems found.")
    print("Reminder: back up CREDENTIAL_ENCRYPTION_KEYS somewhere other than the platform.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
