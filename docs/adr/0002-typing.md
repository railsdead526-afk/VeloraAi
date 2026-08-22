# ADR 0002: Incremental static typing

Status: Accepted
Date: 2026-08-22

## Context

The codebase had no type checking. Adding `mypy` across the whole application
produced ~150 errors, almost all of a single shape:

```
error: Incompatible types in assignment
       (expression has type "datetime", variable has type "Column[datetime]")
```

These come from SQLAlchemy's legacy `Column(...)` declarative style, where an
attribute's static type is `Column[T]` rather than `T`. They are not real bugs,
and suppressing them wholesale would leave a type checker that proves nothing.

## Decision

Enforce `mypy` in CI, but scope it explicitly (`files` in `pyproject.toml`) to
the surfaces where a type error is most likely to cost money or leak data:
`app/core`, `app/schemas`, `app/crud/user.py`, the auth/billing/credential
services, the credential context, and `scripts/`.

Models reachable from that scope (`user`, `auth`, `integration`, `billing`) were
migrated to SQLAlchemy 2.0 `Mapped[...]` / `mapped_column(...)`, which removes
the error class at the source rather than suppressing it.

## Consequences

The checked surface is genuinely clean, with no blanket ignores. The unchecked
surface is explicit and visible in one place, so the gap cannot be mistaken for
coverage.

## Update, 2026-08-22

The remaining legacy models (`conversation`, `message`, `ai_usage`,
`ai_request_reservation`, `audit_log`, `document`, `embedding_usage`,
`tool_confirmation`) have been migrated, so **the entire model layer is now
type checked**, along with `app/crud`, the billing/quota/audit/export services,
and the tool registry. Scope went from 32 to 52 files.

The migration paid for itself immediately. `ToolRegistry.list()` shadows the
builtin `list` inside the class body, so its own `-> list[ToolDefinition]`
annotations resolved to the *method* rather than the type. Every reader,
including the previous author, had been misreading those signatures. mypy
caught it the moment the module entered scope.

Still outside the checked set: `app/api/`, `app/services/ai_*`, and the tool
provider modules. They are added as they are annotated; the `files` list only
ever grows.
