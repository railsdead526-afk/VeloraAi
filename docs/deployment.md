# Deployment and activation guide

Two things in release 1.0.0 cannot be finished by a commit. This document is
the exact procedure for both, plus verification for each.

| # | Task | Why it cannot be automated | Time |
| --- | --- | --- | --- |
| 1 | Move the CI workflow into place | GitHub rejects pushes that touch `.github/workflows/` from an app without the `workflows` permission | 2 min |
| 2 | Enable branch protection on `main` | Requires repository admin rights | 3 min |
| 3 | Schedule the maintenance job | Platform configuration, outside the repo | 10 min |

---

## 1. Activate the CI pipeline

The workflow currently committed at `.github/workflows/ci.yml` is **stale** — it
installs `requirements.txt` and runs `pytest`, but test and lint tooling moved
to `requirements-dev.txt`. Until you replace it, CI cannot pass.

The replacement is already in the repository at
`.github/workflows-proposed/ci.yml`. You only need to move it.

### Option A — GitHub web UI (no local clone needed)

1. Open `.github/workflows-proposed/ci.yml` on the branch
   `arena/01a0295a-veloraai`.
2. Click the **Copy raw file** icon.
3. Navigate to `.github/workflows/ci.yml` on the same branch, click the pencil
   (**Edit**), select everything, and paste.
4. Commit to `arena/01a0295a-veloraai`.
5. Delete `.github/workflows-proposed/` (open each file → **Delete file** →
   commit).

### Option B — a separate worktree (safe with uncommitted work)

Use this when your checkout has local changes. It never touches your current
working tree or branch.

```bash
cd ~/VeloraAi
git fetch origin                       # without this, the branch does not exist locally

git worktree add /tmp/velora-ci arena/01a0295a-veloraai
cd /tmp/velora-ci

git mv .github/workflows-proposed/ci.yml .github/workflows/ci.yml
git rm .github/workflows-proposed/README.md
git commit -m "ci: apply hardened pipeline"
git push origin HEAD:arena/01a0295a-veloraai

cd ~/VeloraAi
git worktree remove /tmp/velora-ci
```

### Option C — switch branches (clean checkout only)

```bash
git fetch origin
git status                             # must report a clean tree first
git checkout arena/01a0295a-veloraai

git mv .github/workflows-proposed/ci.yml .github/workflows/ci.yml
git rm .github/workflows-proposed/README.md
git commit -m "ci: apply hardened pipeline"
git push origin arena/01a0295a-veloraai
```

If `git status` shows modified files, commit or stash them on your current
branch first. `git checkout` refuses to discard uncommitted work, and forcing
it with `-f` throws that work away permanently.

```bash
git stash push -u -m "wip before CI switch"
# ... do the work above, then:
git checkout <your-branch> && git stash pop
```

All routes work from Termux. Your own credentials carry the `workflow` scope
that the automation lacked.

> A classic personal access token needs the `workflow` scope, or the push is
> rejected with the same message the automation hit.

### Troubleshooting

| Message | Cause | Fix |
| --- | --- | --- |
| `pathspec 'arena/...' did not match any file(s)` | branch not fetched | `git fetch origin` |
| `Your local changes would be overwritten` | uncommitted work on shared files | commit, stash, or use Option B |
| `bad source, source=.github/workflows-proposed/ci.yml` | you are on the wrong branch | check `git branch --show-current` |
| `refusing to allow ... without workflows permission` | token lacks `workflow` scope | regenerate the token with that scope |

### Verify

Open the **Actions** tab. The run for your commit must show eight jobs:
`lint`, `tests`, `migrations`, `security`, `sandbox-service`, `frontend`,
`docker`, and `CI passed`. All should be green.

If `security` fails on the gitleaks step, that is the secret scanner working —
read the finding before assuming it is a false positive.

---

## 2. Protect `main`

This is what stops a red commit from landing again — which is exactly how the
two failing tests fixed in this release got onto `main`.

### Web UI

**Settings → Branches → Add branch protection rule**

- Branch name pattern: `main`
- ☑ Require a pull request before merging → Required approvals: **1**
- ☑ Require status checks to pass before merging
  - ☑ Require branches to be up to date before merging
  - Search for and select **`CI passed`**
- ☑ Require conversation resolution before merging
- ☑ Do not allow bypassing the above settings *(applies the rule to admins too)*
- ☐ Allow force pushes — leave **off**
- ☐ Allow deletions — leave **off**

Click **Create**.

> Select `CI passed` rather than the individual jobs. It is an aggregate gate,
> so adding or renaming a job later does not silently weaken protection.
> The check only appears in the search box after the workflow has run at least
> once, so complete step 1 first.

### Or via `gh`

```bash
gh api -X PUT repos/railsdead526-afk/VeloraAi/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=CI passed' \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -f 'enforce_admins=true' \
  -f 'restrictions=' \
  -F 'allow_force_pushes=false' \
  -F 'allow_deletions=false'
```

### Also: make the repository private

**Settings → General → Danger Zone → Change repository visibility → Private.**

The repository is public and now carries a proprietary `LICENSE`. Leaving
commercial billing and security logic public serves no purpose and complicates
investor diligence.

---

## 3. Schedule the maintenance job

**This is revenue-critical.** `scripts/run_maintenance.py` expires lapsed
subscriptions, downgrades users past their grace window, purges expired tokens,
and refreshes subscription metrics. If it never runs, every paid plan silently
becomes permanent — the exact bug this release fixed.

The job is idempotent and finishes in well under a second on a small dataset,
so running it more often than necessary is harmless.

### Railway (matches the committed config)

Railway runs cron as a **separate service** that starts, works, and exits. A web
server never exits, so it cannot double as the cron target.

1. In your Railway project: **New → GitHub Repo →** select `VeloraAi`.
2. Name the service `maintenance`.
3. **Settings → Config-as-code →** set the path to `railway.maintenance.toml`.
4. **Variables →** copy every variable from the web service, then add:
   ```
   RUN_MIGRATIONS=false
   ```
   The web service owns migrations. Without this flag the cron would run
   `alembic upgrade head` hourly and could race a deploy.
5. **Settings → Cron Schedule** should already read `0 * * * *` from the config
   file. Set it manually if not.
6. Deploy.

Constraints worth knowing: schedules are UTC, the minimum interval is five
minutes, timing can drift by a few minutes, and if a run is still active the
next one is skipped rather than queued.

### A plain server (VM, VPS, Docker host)

```bash
crontab -e
```

```cron
0 * * * * cd /srv/veloraai && /srv/veloraai/.venv/bin/python -m scripts.run_maintenance >> /var/log/velora-maintenance.log 2>&1
```

With Docker:

```cron
0 * * * * docker run --rm --env-file /srv/veloraai/.env -e RUN_MIGRATIONS=false veloraai:latest python -m scripts.run_maintenance >> /var/log/velora-maintenance.log 2>&1
```

### Kubernetes

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: velora-maintenance
spec:
  schedule: "0 * * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: maintenance
              image: veloraai:1.0.0
              command: ["python", "-m", "scripts.run_maintenance"]
              env:
                - name: RUN_MIGRATIONS
                  value: "false"
              envFrom:
                - secretRef:
                    name: velora-secrets
```

### Verify

Run it once by hand first:

```bash
python -m scripts.run_maintenance
```

Expected output:

```json
{
  "event": "maintenance_completed",
  "subscriptions": {
    "marked_past_due": 0,
    "expired": 0,
    "canceled_at_period_end": 0,
    "reminders_sent": 0
  },
  "purged": { "revoked_access_tokens": 0, "refresh_tokens": 0, ... },
  "subscription_counts": {}
}
```

Exit code 0 means success. Then confirm it fires on schedule by checking the
platform logs after the next hour boundary.

### Alert on it

A cron job that fails silently is worse than no cron job, because you believe
you are covered. Add the alert from `docs/runbook.md` §8:

> **Maintenance stalled** — no successful run in 3 hours — SEV2

The simplest implementation is a dead-man's switch (Healthchecks.io, Better
Stack, Cronitor): append a ping to the end of the command and let the monitor
alert when the ping stops arriving.

```bash
python -m scripts.run_maintenance && curl -fsS -m 10 https://hc-ping.com/<uuid>
```

---

## 4. Before the first production deploy

Beyond the three tasks above, production will refuse to boot without these.
That refusal is deliberate — see `Settings.validate()` in `app/core/config.py`.

```bash
python -m scripts.generate_keys
```

Set on the platform, never in the repository:

| Variable | Note |
| --- | --- |
| `APP_ENV=production` | switches on every production gate |
| `SECRET_KEY` | ≥ 32 chars; rotating it logs everyone out |
| `CREDENTIAL_ENCRYPTION_KEYS` | **back this up separately from the database** |
| `DATABASE_URL` | PostgreSQL with pgvector |
| `DATABASE_SCHEMA` | must not be `public` |
| `RATE_LIMIT_STORAGE_URI` | `redis://...`, not `memory://` |
| `CORS_ORIGINS` | https origins, no `*` |
| `TRUSTED_HOSTS` | your API hostnames, no `*` |
| `FRONTEND_BASE_URL` | https; used in verification and reset links |
| `REQUIRE_EMAIL_VERIFICATION=true` | enforced in production |
| `METRICS_TOKEN` | guards `/api/v1/metrics` |
| `ALLOW_ENV_TOOL_CREDENTIALS=false` | must stay false; it breaks tenant isolation |
| `AI_PROVIDER` + key | `mock` is refused |
| `MIDTRANS_*`, `PRO_PRICE_IDR`, `MAX_PRICE_IDR` | prices must be > 0 |
| `VAT_PERCENT` | `12` for Indonesian PPN, if registered as PKP |

> **`CREDENTIAL_ENCRYPTION_KEYS` is not recoverable.** It lives only in your
> secret store. A database restore without it leaves every user's connected
> integration permanently undecryptable. Keep a copy in a password manager or
> KMS with the same retention as your backups. See `docs/runbook.md` §5.

Also still required before charging the public: an email transport wired into
`app/services/notification_service.set_email_sender` (verification and reset
links are currently only logged), and the legal items in
`docs/legal/compliance-checklist.md`.
