"""The web client's document statuses must match the ones the backend emits.

This drift was real and silent. The panel polled while a document was in
``pending``, ``processing`` or ``indexing``. The backend only ever emits
``queued``, ``processing``, ``ready`` and ``failed`` - so two of the three names
were fiction, and ``queued``, the state every new document starts in, was
missing. A freshly uploaded document therefore sat on "queued" in the UI
forever, even though indexing had finished server side.

Nothing failed when that happened: no exception, no log line, no test. Hence
this contract test, which parses the TypeScript rather than trusting a comment.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.document import DOCUMENT_STATUSES, PENDING_DOCUMENT_STATUSES

WEB_DOCUMENTS_TS = Path(__file__).resolve().parents[1] / "web" / "lib" / "documents.ts"


def _parse_set(source: str, name: str) -> set[str]:
    """Read `export const <name>: ReadonlySet<string> = new Set([...])`."""
    match = re.search(
        rf"export const {name}:\s*ReadonlySet<string>\s*=\s*new Set\(\[(.*?)\]\)",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"{name} not found in {WEB_DOCUMENTS_TS.name}")

    body = match.group(1)
    constants = dict(re.findall(r"export const (\w+) = '([^']+)'", source))
    values: set[str] = set()
    for raw in (part.strip() for part in body.split(",")):
        if not raw:
            continue
        literal = re.fullmatch(r"'([^']+)'", raw)
        if literal:
            values.add(literal.group(1))
        elif raw in constants:
            values.add(constants[raw])
        else:
            raise AssertionError(f"unrecognised entry {raw!r} in {name}")
    return values


@pytest.fixture(scope="module")
def source() -> str:
    assert WEB_DOCUMENTS_TS.exists(), f"missing {WEB_DOCUMENTS_TS}"
    return WEB_DOCUMENTS_TS.read_text(encoding="utf-8")


def test_status_vocabulary_matches(source):
    assert _parse_set(source, "DOCUMENT_STATUSES") == set(DOCUMENT_STATUSES)


def test_pending_statuses_match(source):
    assert _parse_set(source, "PENDING_DOCUMENT_STATUSES") == set(PENDING_DOCUMENT_STATUSES)


def test_pending_is_a_subset_of_all_statuses():
    assert PENDING_DOCUMENT_STATUSES <= DOCUMENT_STATUSES


def test_backend_only_writes_known_statuses():
    """Catches a new status added in a service but not in the shared vocabulary."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    written: set[str] = set()
    for path in (app_dir / "services").glob("rag*.py"):
        text = path.read_text(encoding="utf-8")
        # `<obj>.status = "x"` covers document.status and failed.status.
        # `"status": "x"` covers the bulk update in the claim step.
        # A bare `status="x"` is excluded: that is record_embedding_usage,
        # which has its own unrelated vocabulary.
        written |= set(re.findall(r'\.status\s*=\s*"([a-z_]+)"', text))
        written |= set(re.findall(r'"status":\s*"([a-z_]+)"', text))

    assert written, "the scan found no status writes at all; the patterns are wrong"
    unknown = written - set(DOCUMENT_STATUSES)
    assert unknown == set(), f"services write statuses the vocabulary does not know: {unknown}"
