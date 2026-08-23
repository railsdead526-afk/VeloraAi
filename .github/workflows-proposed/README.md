# One-line fix needed in `.github/workflows/ci.yml`

Making the repository private broke the `Security scanning` job. gitleaks lists
the commits on a pull request so it can scan only the diff, and on a private
repository the default `GITHUB_TOKEN` cannot read that endpoint:

```
GET /repos/railsdead526-afk/VeloraAi/pulls/35/commits
403 Resource not accessible by integration
```

Nothing is wrong with the code. The token simply needs one more read scope.

## The change

At the top of `.github/workflows/ci.yml`:

```yaml
permissions:
  contents: read
  pull-requests: read   # <- add this line
```

`ci.yml` in this directory is the corrected file, if copying is easier than
editing.

## Why this file is here rather than applied

The automation preparing this branch does not hold GitHub's `workflows`
permission, so it cannot push changes under `.github/workflows/`. Your own
credentials can. See `docs/deployment.md` §1 for the three ways to apply it.

Delete this directory once the change is in.
