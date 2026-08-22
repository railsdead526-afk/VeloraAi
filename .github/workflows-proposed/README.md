# Proposed CI pipeline — requires one manual step

`ci.yml` in this directory is the hardened pipeline for release 1.0.0. It could
not be committed to `.github/workflows/` directly: the GitHub App used for this
session does not hold the `workflows` permission, so any push that creates or
updates a workflow file is rejected by GitHub.

## Apply it

```bash
git mv .github/workflows-proposed/ci.yml .github/workflows/ci.yml
rmdir .github/workflows-proposed 2>/dev/null || true
git commit -m "ci: apply hardened pipeline"
git push
```

Do this from a normal local checkout, or edit the file through the GitHub web UI.
Both routes, with verification steps, are written out in
[`docs/deployment.md`](../../docs/deployment.md) §1.

## Why it matters

**The workflow currently in `.github/workflows/ci.yml` is stale and will fail
on this branch.** It installs `requirements.txt` and runs `pytest`, but test and
lint tooling moved to `requirements-dev.txt` in this release. Until the file
above is applied, CI cannot pass.

## What the new pipeline adds

| Job | Purpose |
| --- | --- |
| `lint` | `ruff check`, `ruff format --check`, `mypy` |
| `tests` | pytest with an enforced 72% coverage floor, coverage artifact |
| `migrations` | PostgreSQL upgrade, **full `downgrade base` reversibility**, drift report |
| `security` | `pip-audit` on both requirement sets, bandit rules, gitleaks secret scan |
| `sandbox-service` | isolated execution service suite |
| `frontend` | `npm audit`, `tsc --noEmit`, lint, build |
| `docker` | image build plus Trivy scan, failing on HIGH/CRITICAL |
| `ci-passed` | single aggregate gate to require in branch protection |

## Then enable branch protection

Settings → Branches → add a rule for `main`:

- Require a pull request before merging (1 approval)
- Require status checks to pass → select **`CI passed`**
- Require branches to be up to date before merging
- Require conversation resolution
- Do not allow force pushes or deletions
- Include administrators

Without this, a red commit can land on `main` again — which is exactly how the
two failing tests fixed in this release got there.
