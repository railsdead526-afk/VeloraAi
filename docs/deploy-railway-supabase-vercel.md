# Deploying VeloraAi on Railway + Supabase + Vercel

The exact stack in use. Written in the order things must be done, because
several steps fail confusingly if done out of order.

---

## 0. Three traps in this stack

Read these first. Each costs an hour if you meet it blind.

**1. Supabase installs pgvector into the `extensions` schema, not `public`.**
The RAG migrations create `vector` columns, and they fail with
`type "vector" does not exist` unless `extensions` is on the search path. The
application and Alembic now append it automatically, so this is handled — but
only if you deploy a build that includes that change.

**2. Supabase direct connections are IPv6-only.** Railway egress is IPv4, so a
direct connection string times out with no useful error. Use a **pooler**
connection string. Use the **Session pooler**, not the transaction pooler:
Alembic runs DDL, and transaction-mode pooling breaks that.

**3. `DATABASE_SCHEMA` must not be `public`.** Production refuses to boot
otherwise. You must create the schema yourself before the first deploy.

---

## 1. Supabase

**SQL Editor → New query**, run once:

```sql
create extension if not exists vector;
create schema if not exists velora;
```

**Settings → Database → Connection string → Session pooler.** Copy it. It
looks like:

```
postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Confirm the host contains `pooler.supabase.com`. If it reads
`db.<ref>.supabase.co`, that is the direct IPv6 endpoint and Railway cannot
reach it.

---

## 2. Railway — web service

**New → GitHub Repo → VeloraAi.** It picks up `railway.toml` automatically.

**Variables.** Generate the secrets locally first:

```bash
python -m scripts.generate_keys
```

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | the Supabase **session pooler** string |
| `DATABASE_SCHEMA` | `velora` |
| `DATABASE_POOL_SIZE` | `5` |
| `SECRET_KEY` | from generate_keys |
| `CREDENTIAL_ENCRYPTION_KEYS` | from generate_keys — **back this up separately** |
| `METRICS_TOKEN` | from generate_keys |
| `AI_PROVIDER` | `openai` |
| `OPENAI_API_KEY` | your key |
| `RATE_LIMIT_STORAGE_URI` | from the Redis step below |
| `CORS_ORIGINS` | your Vercel URL, https, no trailing slash |
| `TRUSTED_HOSTS` | your Railway domain, no scheme |
| `FRONTEND_BASE_URL` | your Vercel URL |
| `REQUIRE_EMAIL_VERIFICATION` | `true` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` | your mail provider |
| `PAYMENT_PROVIDER` | `disabled` until you are ready to sell (see §5) |
| `VAT_PERCENT` | `12` once registered as PKP, else `0` |
| `APP_VERSION` / `GIT_SHA` | optional, shown at `/api/v1/info` |

`DATABASE_POOL_SIZE=5` is deliberate: with 2 replicas plus overflow that is
already up to 50 connections, and Supabase pooler limits are not generous.

**Redis:** `New → Database → Redis` in the same project, then set
`RATE_LIMIT_STORAGE_URI` to its `REDIS_URL`. Production refuses `memory://`
because rate limits must be shared across replicas.

### Verify before going further

```bash
curl https://<your-app>.up.railway.app/api/v1/health
curl https://<your-app>.up.railway.app/api/v1/ready | jq .
```

`/ready` names the failing dependency in `.failed`. If the service will not
start at all, read the deploy log: `Settings.validate()` prints exactly which
variable is wrong and why.

---

## 3. Railway — maintenance cron

**Revenue-critical.** Without this, subscriptions never expire and every paid
plan becomes permanent.

Railway runs cron as a service that starts, works, and exits. A web server
never exits, so it cannot double as the cron target.

1. **New → GitHub Repo →** the same repository. Name it `maintenance`.
2. **Settings → Config-as-code →** `railway.maintenance.toml`
3. **Variables →** copy every variable from the web service, then add:
   ```
   RUN_MIGRATIONS=false
   ```
   The web service owns migrations. Without this the cron would run
   `alembic upgrade head` hourly and could race a deploy.
4. **Settings → Cron Schedule** should read `0 * * * *` from the config file.
5. Deploy, then check the logs for `maintenance_completed`.

Add a dead-man's switch so a silent failure is visible — a cron you believe is
running but is not is worse than no cron:

```bash
python -m scripts.run_maintenance && curl -fsS -m 10 https://hc-ping.com/<uuid>
```

---

## 4. Vercel

**Root Directory: `web`** — this matters, the repository root is the backend.

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `https://<your-app>.up.railway.app` |

Deploy, then go back to Railway and make sure `CORS_ORIGINS` and
`FRONTEND_BASE_URL` hold the real Vercel URL. Both must be https, and
`CORS_ORIGINS` must not have a trailing slash — the browser compares the origin
string exactly.

---

## 5. Payments — skip this until you are ready to sell

Deploy with `PAYMENT_PROVIDER=disabled`. Production then skips the gateway and
pricing checks, `/api/v1/payments/config` reports `enabled: false` so the UI can
show an honest "upgrades unavailable" state, and every user stays on Free.

This is deliberately an explicit setting rather than "leave the credentials
blank": blank credentials plus zero prices is how a system ends up granting paid
plans for free.

### When you are ready

You do **not** need a PT. Tripay and iPaymu register individuals with a KTP;
Midtrans accepts a KTP plus a personal bank account and has a product,
Midtrans GO, aimed at unincorporated businesses. Since NIK now doubles as a
personal NPWP, the tax-number requirement is usually already met.

If your Midtrans account is tied to another site, one account may serve several
websites only within the same domain and business scope. Otherwise use the
Partner dashboard's **+ Add merchant** to create a second merchant with its own
keys, or register with another gateway.

Then set `PAYMENT_PROVIDER=midtrans`, the credentials, and non-zero prices.

**Dashboard → Settings → Access Keys**, with the environment toggle set to
**Sandbox**. Copy the Server Key (`SB-Mid-server-...`) and Client Key
(`SB-Mid-client-...`).

Set both on Railway with `MIDTRANS_IS_PRODUCTION=false`.

**Settings → Configuration → Payment Notification URL:**

```
https://<your-app>.up.railway.app/api/v1/payments/notification
```

The webhook verifies the signature and then re-queries Midtrans before
changing any state, so a forged notification cannot grant a plan.

### Enabling the sandbox E2E test

Do **not** paste keys into chat or commit them. Add a repository secret:

**Settings → Secrets and variables → Actions → New repository secret**

- Name: `MIDTRANS_SERVER_KEY`
- Value: your sandbox server key

Then **Actions → Midtrans Sandbox E2E → Run workflow**.

The workflow skips itself when the secret is absent, so nothing breaks until
you add it. Once it is green, recurring billing can be built against a verified
integration rather than against assumptions.

---

## 6. Order of operations

1. Supabase SQL (extension + schema)
2. Railway web service + Redis → `/ready` returns 200
3. Vercel → then fix `CORS_ORIGINS` and `FRONTEND_BASE_URL`
4. Railway maintenance cron → confirm one run in the logs
5. Midtrans keys + webhook URL → one sandbox payment end to end
6. Branch protection on `main`, and make the repository private

## 7. Back up the encryption key now

`CREDENTIAL_ENCRYPTION_KEYS` exists only in Railway's variable store. **A
database restore without it leaves every user's connected integration
permanently undecryptable.** Put a copy in a password manager today, with the
same retention as your backups. See `docs/runbook.md` §5 and §6.
