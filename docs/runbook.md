# VeloraAi operations runbook

Audience: whoever is on call. Written to be followed at 02:00 without prior context.

---

## 1. System at a glance

| Component | What it is | Failure impact |
| --- | --- | --- |
| API (`app/`) | FastAPI, stateless, horizontally scalable | Total outage |
| PostgreSQL + pgvector | System of record, RAG vectors | Total outage |
| Redis | Shared rate-limit counters | Rate limiting degrades; API still serves |
| Sandbox service | Isolated command execution | Terminal tools fail; chat unaffected |
| AI provider | OpenAI / Llama-compatible | Chat fails; auth and billing unaffected |
| Midtrans | Payments | Upgrades fail; existing plans unaffected |
| Maintenance job | Hourly `scripts/run_maintenance.py` | Subscriptions stop expiring (revenue leak) |

## 2. First five minutes of any incident

```bash
curl -fsS https://api.example.com/api/v1/health          # process alive?
curl -fsS https://api.example.com/api/v1/ready | jq .    # which dependency is down?
```

`/ready` names the failing dependency in `.failed`. Go straight to that section below.

Then:

1. Declare severity (§9).
2. Open an incident channel and start a timeline.
3. Mitigate first, diagnose second. Rollback is always an acceptable mitigation.

## 3. Deploy and rollback

### Deploy

Migrations run automatically at container start (`docker-entrypoint.sh` → `alembic upgrade head`).

```bash
git tag -a v1.2.3 -m "release: v1.2.3" && git push origin v1.2.3
```

Verify: `/api/v1/info` reports the expected `version` and `commit`, and `/api/v1/ready` is 200.

### Rollback

```bash
# 1. Redeploy the previous image tag on the platform.
# 2. Only if the release contained a schema change that must be undone:
alembic downgrade -1
```

**Rule:** never roll back a migration that has already deleted data. Restore from backup instead (§5). Prefer forward fixes; expansion/contraction migrations exist so code and schema can be rolled back independently.

## 4. Dependency-specific procedures

### Database unavailable

```bash
psql "$DATABASE_URL" -c "SELECT 1"
psql "$DATABASE_URL" -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state"
```

- Connection pool exhausted → look for long transactions:
  `SELECT pid, now()-xact_start AS age, query FROM pg_stat_activity WHERE state<>'idle' ORDER BY age DESC LIMIT 10;`
- Terminate a stuck query: `SELECT pg_terminate_backend(<pid>);`
- Raise `DATABASE_POOL_SIZE` only after confirming the database has headroom.

### Redis unavailable

Rate limiting fails open. Not user-visible, but the API is unprotected against abuse. Restore Redis, or temporarily reduce `RATE_LIMIT_DEFAULT` and scale down public exposure.

### AI provider failing

Check the provider status page. Mitigations, in order: raise `AI_TIMEOUT_SECONDS`, switch `AI_PROVIDER` to a healthy compatible endpoint, then redeploy. Never set `AI_PROVIDER=mock` in production — the config validator refuses to boot.

### Sandbox service failing

Terminal tools return errors; nothing else is affected. Confirm the host has Docker running and disk headroom under `SANDBOX_ROOT`. Ephemeral workspaces are deleted in a `finally` block, but a crashed host can leak them:

```bash
find "$SANDBOX_ROOT" -maxdepth 1 -type d -mtime +1 -exec rm -rf {} +
```

### Payments failing

Check Midtrans status. Webhook problems are the dangerous case: users pay and are not upgraded. Payments are idempotent, so replaying a notification is safe. Reconcile manually:

```bash
psql "$DATABASE_URL" -c "SELECT id, provider_order_id, status, created_at FROM payments WHERE status='pending' AND created_at < now() - interval '1 hour';"
```

For each, query Midtrans status and replay the notification to `/api/v1/payments/notification`.

### Maintenance job not running

Symptom: expired subscriptions still entitled — direct revenue loss. Run manually:

```bash
python -m scripts.run_maintenance
```

The job is idempotent. Alert if it has not succeeded in 3 hours.

## 5. Backup and restore

### Targets

| Metric | Target |
| --- | --- |
| RPO (max data loss) | 5 minutes |
| RTO (max downtime) | 1 hour |
| Backup retention | 30 daily, 12 monthly |
| Restore drill cadence | Quarterly, **mandatory** |

### Backup

Point-in-time recovery must be enabled on the managed PostgreSQL instance. Additionally:

```bash
pg_dump --format=custom --no-owner "$DATABASE_URL" > "velora-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

Store off-platform, encrypted. A backup that lives only with the primary provider is not a backup.

### Restore drill (run quarterly, record the result)

```bash
createdb velora_restore_test
pg_restore --no-owner --dbname=velora_restore_test velora-YYYYMMDDTHHMMSSZ.dump
psql velora_restore_test -c "SELECT count(*) FROM users;"
psql velora_restore_test -c "SELECT max(created_at) FROM payments;"
DATABASE_URL=postgresql://.../velora_restore_test alembic current
dropdb velora_restore_test
```

**A backup is not verified until it has been restored.** Record the drill date, duration, and row counts in the incident log.

### Secrets are not in the database

`SECRET_KEY` and `CREDENTIAL_ENCRYPTION_KEYS` live only in the platform secret store. **A database restore without those keys leaves every stored integration undecryptable.** Back the keys up separately, in a password manager or KMS, with the same retention.

## 6. Key rotation

### `CREDENTIAL_ENCRYPTION_KEYS` (zero downtime)

```bash
python -m scripts.generate_keys                       # 1. new key
# 2. set CREDENTIAL_ENCRYPTION_KEYS="<new>,<old>", redeploy
python -m scripts.rotate_credential_keys              # 3. re-encrypt everything
# 4. set CREDENTIAL_ENCRYPTION_KEYS="<new>", redeploy
```

Never remove the old key before step 3 reports 0 remaining.

### `SECRET_KEY`

Rotating it invalidates every access token, refresh token, verification token, and login-attempt digest. All users are logged out. Schedule it, announce it, and expect a support spike.

### Compromised third-party token

The blast radius is one user. Delete the row and tell them to reconnect:

```sql
DELETE FROM user_integrations WHERE user_id = <id> AND provider = '<provider>';
```

## 7. Common operational tasks

```bash
# Promote a user to admin
psql "$DATABASE_URL" -c "UPDATE users SET role='admin' WHERE email='ops@example.com';"

# Terminate every session for a compromised account
psql "$DATABASE_URL" -c "UPDATE refresh_tokens SET revoked_at=now(), revoked_reason='incident' WHERE user_id=<id>;"

# Investigate an account's recent activity
psql "$DATABASE_URL" -c "SELECT created_at, event, status, resource_type, resource_id FROM audit_logs WHERE user_id=<id> ORDER BY created_at DESC LIMIT 50;"

# Trace one request end to end
# Every response carries X-Request-ID; every log line and audit row includes it.
```

## 8. Monitoring and alerting

Scrape `GET /api/v1/metrics` with `Authorization: Bearer $METRICS_TOKEN`.

| Alert | Condition | Severity |
| --- | --- | --- |
| API down | `/health` failing for 2 min | SEV1 |
| Not ready | `/ready` non-200 for 5 min | SEV1 |
| Error rate | 5xx > 2% over 5 min | SEV2 |
| Latency | p95 `velora_http_request_duration_seconds` > 3s for 10 min | SEV2 |
| DB pool | active connections > 80% of pool for 5 min | SEV2 |
| Auth abuse | `velora_auth_events_total{outcome="failed"}` spike ×10 | SEV2 |
| Payment failures | any `velora_payment_events_total{status="failure"}` | SEV2 |
| Maintenance stalled | no successful run in 3 h | SEV2 |
| AI spend | daily token cost > budget | SEV3 |
| Certificate expiry | < 14 days | SEV3 |

## 9. Severity and escalation

| Severity | Definition | Response | Comms |
| --- | --- | --- | --- |
| SEV1 | Full outage, data loss, or active breach | Immediate, all hands | Status page within 30 min |
| SEV2 | Major feature broken or degraded for many users | Within 1 hour | Status page if > 1 h |
| SEV3 | Minor or cosmetic | Next business day | None |

Security incidents additionally follow `SECURITY.md`. Suspected personal-data breaches must be reported to the Indonesian authority within **3×24 hours** under UU PDP 27/2022 — start that clock immediately and involve counsel.

## 10. Post-incident

Within 48 hours of any SEV1 or SEV2, write a blameless postmortem covering: timeline, user impact, root cause, why detection took as long as it did, and action items with owners and dates. File it under `docs/postmortems/YYYY-MM-DD-title.md`.
