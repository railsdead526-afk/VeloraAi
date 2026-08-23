"""Column types shared by the models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """A timestamp that is always timezone-aware in Python, on every dialect.

    PostgreSQL round-trips `timestamptz` as an aware datetime. SQLite has no
    timezone type and hands back a naive one, so the same column behaves
    differently depending on where the code runs. Comparing a naive value to
    `datetime.now(UTC)` raises TypeError, which means the divergence surfaces
    as a crash rather than a wrong answer.

    Three services had each grown their own private `_as_aware()` helper to
    patch this at the call site. That is a rule every future reader has to
    remember, and forgetting it is a runtime error. Fixing it once at the
    column boundary removes the rule entirely.

    Writes are strict: a naive datetime is rejected rather than assumed to be
    UTC, because guessing an offset silently stores the wrong instant.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "Refusing to store a naive datetime. Use datetime.now(UTC), or attach "
                "the correct tzinfo: an assumed offset stores the wrong instant."
            )
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        # SQLite loses the offset; everything is stored as UTC, so restore it.
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
