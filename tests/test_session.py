"""Tests for papertrail.session — Task 4."""

import json
from pathlib import Path

import pytest

from papertrail import ledger
from papertrail.session import on_start, on_stop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lp(root: Path) -> Path:
    return root / ".papertrail" / "ledger.jsonl"


def _entries(root: Path) -> list[dict]:
    return ledger.read(_lp(root))


def _last(root: Path) -> dict:
    es = _entries(root)
    assert es
    return es[-1]


def _by_kind(root: Path, kind: str) -> list[dict]:
    return [e for e in _entries(root) if e["kind"] == kind]


_SESSION = "sess-test"


def _base_payload(session_id: str = _SESSION) -> dict:
    return {"session_id": session_id}


def _write_statement(root: Path, extra: dict | None = None) -> None:
    stmt = {
        "summary": "Did some work.",
        "files_read": [],
        "files_created": [],
        "files_modified": [],
        "files_deleted": [],
    }
    if extra:
        stmt.update(extra)
    p = root / ".papertrail" / "statement.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(stmt), encoding="utf-8")


# ---------------------------------------------------------------------------
# AC3.4b — on_stop after on_start appends witness/stop with diff keys
# ---------------------------------------------------------------------------

def test_on_stop_after_on_start_has_diff(tmp_path):
    """AC3.4b: on_stop after on_start appends witness/stop with created/deleted/modified."""
    on_start(_base_payload(), tmp_path, Path.home())
    # Create a file between start and stop so the diff is non-trivial.
    (tmp_path / "new_file.txt").write_text("hello", encoding="utf-8")

    stop = on_stop(_base_payload(), tmp_path, Path.home())

    assert stop["kind"] == "witness"
    assert stop["data"]["event"] == "stop"
    diff = stop["data"]["diff"]
    assert "created" in diff
    assert "deleted" in diff
    assert "modified" in diff
    assert "new_file.txt" in diff["created"]


# ---------------------------------------------------------------------------
# AC3.4c — on_stop with no prior start → baseline="none", empty diff
# ---------------------------------------------------------------------------

def test_on_stop_no_prior_start(tmp_path):
    """AC3.4c: on_stop with no prior start → baseline='none', empty diff."""
    stop = on_stop(_base_payload(), tmp_path, Path.home())

    assert stop["data"]["baseline"] == "none"
    assert stop["data"]["diff"] == {"created": [], "deleted": [], "modified": []}


# ---------------------------------------------------------------------------
# AC3.4d — second on_stop diffs from previous stop's snapshot, not start
# ---------------------------------------------------------------------------

def test_second_stop_diffs_from_previous_stop(tmp_path):
    """AC3.4d: second on_stop diffs from that stop's snapshot, not the start snapshot."""
    on_start(_base_payload(), tmp_path, Path.home())
    _write_statement(tmp_path)
    on_stop(_base_payload(), tmp_path, Path.home())

    # Add a new file; this should appear in the second stop's diff.
    (tmp_path / "after_first_stop.txt").write_text("x", encoding="utf-8")
    _write_statement(tmp_path)
    stop2 = on_stop(_base_payload(), tmp_path, Path.home())

    # The second stop's baseline should reference the first stop, not start.
    assert stop2["data"]["baseline"].startswith("prev_stop_seq:")
    # The new file must be in the second diff.
    assert "after_first_stop.txt" in stop2["data"]["diff"]["created"]


# ---------------------------------------------------------------------------
# AC4.2a — valid statement.json is promoted and statement.json deleted
# ---------------------------------------------------------------------------

def test_valid_statement_promoted(tmp_path):
    """AC4.2a: after on_stop with valid statement.json, <session_id>-1.json exists and statement.json is gone."""
    on_start(_base_payload(), tmp_path, Path.home())
    _write_statement(tmp_path)
    on_stop(_base_payload(), tmp_path, Path.home())

    stmt_path = tmp_path / ".papertrail" / "statement.json"
    assert not stmt_path.exists(), "statement.json was not deleted after promotion"

    promoted = tmp_path / ".papertrail" / "statements" / f"{_SESSION}-1.json"
    assert promoted.exists(), f"Promoted file not found: {promoted}"

    data = json.loads(promoted.read_text(encoding="utf-8"))
    for key in ("summary", "files_read", "files_created", "files_modified",
                "files_deleted", "session_id", "ts", "witness_seq"):
        assert key in data, f"Missing key in promoted file: {key}"


# ---------------------------------------------------------------------------
# AC4.2b — ledger contains a statement entry with matching session_id and summary
# ---------------------------------------------------------------------------

def test_statement_entry_in_ledger(tmp_path):
    """AC4.2b: ledger contains a statement entry with matching session_id and summary."""
    on_start(_base_payload(), tmp_path, Path.home())
    _write_statement(tmp_path, {"summary": "Specific summary."})
    on_stop(_base_payload(), tmp_path, Path.home())

    stmts = _by_kind(tmp_path, "statement")
    assert len(stmts) == 1
    assert stmts[0]["session_id"] == _SESSION
    assert stmts[0]["data"]["summary"] == "Specific summary."


# ---------------------------------------------------------------------------
# AC4.2c — on_stop with no statement.json runs fine, only witness/stop appended
# ---------------------------------------------------------------------------

def test_on_stop_no_statement_no_error(tmp_path):
    """AC4.2c: on_stop with no statement.json runs without error, only witness/stop added."""
    on_start(_base_payload(), tmp_path, Path.home())
    stop = on_stop(_base_payload(), tmp_path, Path.home())

    assert stop["kind"] == "witness"
    assert stop["data"]["event"] == "stop"
    assert _by_kind(tmp_path, "statement") == []
    assert _by_kind(tmp_path, "error") == []


# ---------------------------------------------------------------------------
# AC4.2d — second promotion creates <session_id>-2.json; both files distinct
# ---------------------------------------------------------------------------

def test_second_promotion_creates_numbered_file(tmp_path):
    """AC4.2d: second promotion creates <session_id>-2.json; both files distinct."""
    on_start(_base_payload(), tmp_path, Path.home())

    _write_statement(tmp_path, {"summary": "First stop."})
    on_stop(_base_payload(), tmp_path, Path.home())

    _write_statement(tmp_path, {"summary": "Second stop."})
    on_stop(_base_payload(), tmp_path, Path.home())

    f1 = tmp_path / ".papertrail" / "statements" / f"{_SESSION}-1.json"
    f2 = tmp_path / ".papertrail" / "statements" / f"{_SESSION}-2.json"
    assert f1.exists() and f2.exists()
    d1 = json.loads(f1.read_text(encoding="utf-8"))
    d2 = json.loads(f2.read_text(encoding="utf-8"))
    assert d1["summary"] != d2["summary"]


# ---------------------------------------------------------------------------
# AC4.2e — second stop's diff baseline is the first promoting stop's snapshot
# ---------------------------------------------------------------------------

def test_second_stop_baseline_is_first_promoting_stop(tmp_path):
    """AC4.2e: second stop's diff baseline is the first promoting stop's snapshot."""
    on_start(_base_payload(), tmp_path, Path.home())
    _write_statement(tmp_path)
    stop1 = on_stop(_base_payload(), tmp_path, Path.home())

    _write_statement(tmp_path)
    stop2 = on_stop(_base_payload(), tmp_path, Path.home())

    # Second stop's baseline must reference stop1's seq.
    expected_label = f"prev_stop_seq:{stop1['seq']}"
    assert stop2["data"]["baseline"] == expected_label


# ---------------------------------------------------------------------------
# AC4.2f — stop without statement does not advance baseline
# ---------------------------------------------------------------------------

def test_stop_without_statement_does_not_advance_baseline(tmp_path):
    """AC4.2f: a stop without a statement does not advance the baseline for the next stop."""
    on_start(_base_payload(), tmp_path, Path.home())
    _write_statement(tmp_path)
    stop1 = on_stop(_base_payload(), tmp_path, Path.home())

    # Second stop — no statement.
    stop2 = on_stop(_base_payload(), tmp_path, Path.home())

    # Third stop — no statement again. Its baseline must still reference stop1
    # (the last promoting stop), not stop2.
    _write_statement(tmp_path)
    stop3 = on_stop(_base_payload(), tmp_path, Path.home())

    expected = f"prev_stop_seq:{stop1['seq']}"
    assert stop3["data"]["baseline"] == expected


# ---------------------------------------------------------------------------
# AC4.2g — witness_seq in promoted file equals stop entry's seq
# ---------------------------------------------------------------------------

def test_witness_seq_in_promoted_file_matches_stop_seq(tmp_path):
    """AC4.2g: witness_seq in the promoted file equals the stop entry's seq."""
    on_start(_base_payload(), tmp_path, Path.home())
    _write_statement(tmp_path)
    stop = on_stop(_base_payload(), tmp_path, Path.home())

    promoted = tmp_path / ".papertrail" / "statements" / f"{_SESSION}-1.json"
    data = json.loads(promoted.read_text(encoding="utf-8"))
    assert data["witness_seq"] == stop["seq"]


# ---------------------------------------------------------------------------
# AC4.2h — later no-statement stop does not alter existing statement files
# ---------------------------------------------------------------------------

def test_later_no_statement_stop_does_not_alter_existing_files(tmp_path):
    """AC4.2h: a later no-statement stop does not alter existing statement files."""
    on_start(_base_payload(), tmp_path, Path.home())
    _write_statement(tmp_path, {"summary": "Original."})
    on_stop(_base_payload(), tmp_path, Path.home())

    promoted = tmp_path / ".papertrail" / "statements" / f"{_SESSION}-1.json"
    original_content = promoted.read_text(encoding="utf-8")
    original_mtime = promoted.stat().st_mtime

    # Second stop without a statement.
    on_stop(_base_payload(), tmp_path, Path.home())

    assert promoted.read_text(encoding="utf-8") == original_content
    assert promoted.stat().st_mtime == original_mtime
