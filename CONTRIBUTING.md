# Contributing to VeloraAi

VeloraAi is proprietary software. Contributions are accepted only from people
authorised by the copyright holder.

## Intellectual property

By submitting a contribution you assign all right, title, and interest in that
contribution to the copyright holder, and you confirm that:

1. the work is yours, or you have the right to submit it;
2. it is not encumbered by any third-party licence or employment agreement;
3. it contains no code copied from a source with an incompatible licence.

Every commit must be signed off (Developer Certificate of Origin):

```bash
git commit -s -m "feat: your change"
```

## Branching

- `main` is protected. It must always be green.
- Work on short-lived branches: `feat/...`, `fix/...`, `chore/...`, `docs/...`.
- Never force-push to `main`.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat(billing): expire subscriptions past their period end
fix(auth): reject refresh tokens after rotation
chore(deps): upgrade pypdf to 6.15.0
docs(runbook): add restore drill procedure
```

## Definition of done

A pull request is mergeable only when all of the following hold:

- [ ] CI is fully green (tests, migrations, lint, types, audit, frontend).
- [ ] New behaviour has tests. Bug fixes have a regression test.
- [ ] Coverage does not decrease below the enforced floor.
- [ ] Any schema change ships with an Alembic migration **and** a working
      `downgrade()`.
- [ ] Any new configuration key is added to `.env.example` and validated in
      `app/core/config.py`.
- [ ] Security-relevant changes are noted in the PR description.
- [ ] `CHANGELOG.md` is updated for user-visible changes.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python -m scripts.generate_keys      # fills SECRET_KEY and CREDENTIAL_ENCRYPTION_KEYS
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd web && npm ci && npm run dev
```

## Before pushing

```bash
ruff check app tests
ruff format --check app tests
mypy app
pytest -q --cov=app --cov-fail-under=70
pip-audit -r requirements.txt --strict
```

## Reviews

At least one approving review from a `CODEOWNERS` entry is required. Changes to
`app/core/`, `app/services/billing_service.py`, `app/services/credential_service.py`,
`app/tools/`, or `alembic/` require explicit security review.

## Reporting security issues

Do not use pull requests or issues. See `SECURITY.md`.
