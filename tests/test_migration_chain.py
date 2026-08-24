"""Structural checks on the migration chain.

These exist because the SQLite test job cannot catch everything the PostgreSQL
job does. Alembic stores the current revision in `alembic_version.version_num`,
a VARCHAR(32). SQLite ignores declared string lengths, so an over-long revision
id passes every local test and only fails when the PostgreSQL job runs
`alembic upgrade head` - which is exactly what happened with
`0017_subscription_reminder_marker` at 33 characters.
"""

from __future__ import annotations

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

#: alembic_version.version_num is VARCHAR(32) unless explicitly widened.
MAX_REVISION_LENGTH = 32


@pytest.fixture(scope="module")
def script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config("alembic.ini"))


@pytest.fixture(scope="module")
def revisions(script) -> list:
    return list(script.walk_revisions())


def test_revision_ids_fit_the_version_column(revisions):
    too_long = {
        revision.revision: len(revision.revision)
        for revision in revisions
        if len(revision.revision) > MAX_REVISION_LENGTH
    }
    assert too_long == {}, (
        f"revision ids longer than {MAX_REVISION_LENGTH} characters will not fit "
        f"alembic_version.version_num on PostgreSQL: {too_long}"
    )


def test_there_is_exactly_one_head(script):
    heads = script.get_heads()
    assert len(heads) == 1, f"the migration history has branched: {heads}"


def test_every_revision_is_reachable_from_the_head(script, revisions):
    walked = {revision.revision for revision in revisions}
    all_known = {revision.revision for revision in script.get_revisions("heads")}
    assert all_known <= walked


def test_no_duplicate_revision_ids(revisions):
    ids = [revision.revision for revision in revisions]
    assert len(ids) == len(set(ids))


def test_every_revision_defines_a_downgrade(revisions):
    """A migration that cannot be undone turns a bad deploy into an outage."""
    missing = []
    for revision in revisions:
        module = revision.module
        downgrade = getattr(module, "downgrade", None)
        if downgrade is None:
            missing.append(revision.revision)
            continue
        source = revision.path
        with open(source, encoding="utf-8") as handle:
            body = handle.read()
        marker = body.split("def downgrade(")[-1]
        if "pass" in marker and "op." not in marker:
            missing.append(revision.revision)
    assert missing == [], f"revisions without a real downgrade: {missing}"
