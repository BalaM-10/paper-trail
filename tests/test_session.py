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


# ===========================================================================
# NO_STATEMENT: the agent changed files and wrote no statement (R2.1)
# ===========================================================================

import time

from papertrail.outcome import NO_STATEMENT


def _make(root: Path, name: str, text: str = "x") -> None:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _overall(root: Path) -> list[dict]:
    return [
        e for e in _entries(root)
        if e["kind"] == "verdict" and e["data"].get("kind_detail") == "statement_overall"
    ]


def test_ac2_1a_changes_and_no_statement_record_a_verdict_after_the_stop(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    _make(tmp_path, "new.txt")
    stop = on_stop(_base_payload(), tmp_path, Path.home())

    entries = _entries(tmp_path)
    assert [e["kind"] for e in entries[-2:]] == ["witness", "verdict"]
    verdict = entries[-1]
    assert verdict["seq"] == stop["seq"] + 1
    assert verdict["session_id"] == _SESSION
    assert verdict["data"] == {
        "kind_detail": "statement_overall",
        "verdict": NO_STATEMENT,
        "evidence_seq": [stop["seq"]],
        "witness_seq": stop["seq"],
        "undeclared": [{"path": "new.txt", "change": "created"}],
    }
    assert ledger.verify_chain(_lp(tmp_path)) == (True, None)


def test_ac2_1a_lists_every_change_created_then_modified_then_deleted(tmp_path):
    _make(tmp_path, "keep.txt", "old")
    _make(tmp_path, "gone.txt")
    on_start(_base_payload(), tmp_path, Path.home())
    _make(tmp_path, "keep.txt", "new and different")
    (tmp_path / "gone.txt").unlink()
    _make(tmp_path, "fresh.txt")
    on_stop(_base_payload(), tmp_path, Path.home())

    assert _overall(tmp_path)[-1]["data"]["undeclared"] == [
        {"path": "fresh.txt", "change": "created"},
        {"path": "keep.txt", "change": "modified"},
        {"path": "gone.txt", "change": "deleted"},
    ]


def test_ac2_1b_no_changes_means_no_verdict(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    before = len(_entries(tmp_path))
    on_stop(_base_payload(), tmp_path, Path.home())
    assert len(_entries(tmp_path)) == before + 1  # only the witness/stop record
    assert _overall(tmp_path) == []


def test_ac2_1c_a_promoted_statement_means_no_no_statement(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    _make(tmp_path, "new.txt")
    _write_statement(tmp_path, {"files_created": ["new.txt"]})
    on_stop(_base_payload(), tmp_path, Path.home())
    # witness, the statement, and the statement's own checked verdicts (never NO_STATEMENT)
    assert [e["kind"] for e in _entries(tmp_path)][-4:] == ["witness", "statement", "verdict", "verdict"]
    assert [o["data"]["verdict"] for o in _overall(tmp_path)] == ["SUPPORTED"]


def test_ac2_1d_no_start_snapshot_means_no_baseline_and_no_verdict(tmp_path):
    _make(tmp_path, "new.txt")
    stop = on_stop(_base_payload(), tmp_path, Path.home())
    assert stop["data"]["baseline"] == "none"
    assert _overall(tmp_path) == []


def test_ac2_1e_an_unusable_statement_counts_as_none(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    _make(tmp_path, "new.txt")
    bad = tmp_path / ".papertrail" / "statement.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(json.dumps({"summary": "Only a summary."}), encoding="utf-8")

    stop = on_stop(_base_payload(), tmp_path, Path.home())

    kinds = [e["kind"] for e in _entries(tmp_path)]
    assert kinds[-3:] == ["witness", "error", "verdict"]       # error first, then the verdict
    assert (tmp_path / ".papertrail" / "rejected" / f"statement-{stop['seq']}.json").exists()
    assert not bad.exists()
    assert _by_kind(tmp_path, "statement") == []
    assert _overall(tmp_path)[-1]["data"]["verdict"] == NO_STATEMENT


def test_ac2_1f_the_same_changes_are_not_recorded_twice_but_new_ones_are(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    _make(tmp_path, "a.txt")
    on_stop(_base_payload(), tmp_path, Path.home())
    on_stop(_base_payload(), tmp_path, Path.home())   # nothing new happened
    on_stop(_base_payload(), tmp_path, Path.home())
    assert len(_overall(tmp_path)) == 1

    _make(tmp_path, "b.txt")                          # something new did
    on_stop(_base_payload(), tmp_path, Path.home())
    verdicts = _overall(tmp_path)
    assert len(verdicts) == 2
    assert verdicts[1]["data"]["undeclared"] == [
        {"path": "a.txt", "change": "created"},       # the baseline has not moved on
        {"path": "b.txt", "change": "created"},
    ]


def test_ac2_1f_another_sessions_verdict_does_not_count_as_a_repeat(tmp_path):
    on_start(_base_payload("one"), tmp_path, Path.home())
    on_start(_base_payload("two"), tmp_path, Path.home())
    _make(tmp_path, "a.txt")
    on_stop(_base_payload("one"), tmp_path, Path.home())
    on_stop(_base_payload("two"), tmp_path, Path.home())
    sessions = [e["session_id"] for e in _overall(tmp_path)]
    assert sessions == ["one", "two"]


def test_ac2_1g_changes_are_measured_from_the_last_promoted_statement(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    _make(tmp_path, "a.txt")
    _write_statement(tmp_path, {"files_created": ["a.txt"]})
    stop1 = on_stop(_base_payload(), tmp_path, Path.home())

    _make(tmp_path, "b.txt")
    stop2 = on_stop(_base_payload(), tmp_path, Path.home())

    assert stop2["data"]["baseline"] == f"prev_stop_seq:{stop1['seq']}"
    assert _overall(tmp_path)[-1]["data"]["undeclared"] == [{"path": "b.txt", "change": "created"}]


def test_ac2_1i_the_record_holds_no_contents_and_no_absolute_paths(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    _make(tmp_path, "secret.txt", "TOP-SECRET-CONTENTS-12345")
    on_stop(_base_payload(), tmp_path, Path.home())
    raw = _lp(tmp_path).read_text(encoding="utf-8")
    assert "TOP-SECRET-CONTENTS-12345" not in raw
    assert str(tmp_path) not in raw and tmp_path.as_posix() not in raw
    assert "secret.txt" in raw  # the path is there, relative


def test_ac2_1h_the_stop_is_still_quick(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    for i in range(20):
        _make(tmp_path, f"f{i}.txt")
    started = time.perf_counter()
    on_stop(_base_payload(), tmp_path, Path.home())
    assert time.perf_counter() - started < 1.0


def test_the_hook_script_records_it_too_and_exits_zero(tmp_path):
    import os
    import subprocess
    import sys

    project = Path(__file__).resolve().parents[1]
    hook = project / ".kiro" / "hooks" / "witness.py"
    env = {**os.environ, "PAPERTRAIL_ROOT": str(tmp_path)}
    payload = json.dumps({"session_id": "via-hook"})

    def run(event: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(hook), event], input=payload,
            capture_output=True, text=True, env=env, cwd=str(project), timeout=30,
        )

    assert run("start").returncode == 0
    _make(tmp_path, "made-by-the-agent.txt")
    assert run("stop").returncode == 0

    last = ledger.read(_lp(tmp_path))[-1]
    assert last["kind"] == "verdict"
    assert last["data"]["verdict"] == NO_STATEMENT
    assert last["data"]["undeclared"] == [{"path": "made-by-the-agent.txt", "change": "created"}]


# ---------------------------------------------------------------------------
# A promoted statement is checked at once (paper-trail-clean-record R2)
# ---------------------------------------------------------------------------

def _verdicts(root: Path) -> list[dict]:
    return _by_kind(root, "verdict")


def _overalls(root: Path) -> list[dict]:
    return [e for e in _verdicts(root) if e["data"].get("kind_detail") == "statement_overall"]


def test_ac2_1a_the_verdicts_are_recorded_by_the_stop_hook_itself(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    _write_statement(tmp_path, {"files_created": ["a.txt"]})
    stop = on_stop(_base_payload(), tmp_path, Path.home())

    kinds = [e["kind"] for e in _entries(tmp_path)]
    assert kinds == ["witness", "witness", "statement", "verdict", "verdict"]
    per_claim, overall = _verdicts(tmp_path)
    assert (per_claim["data"]["path"], per_claim["data"]["verdict"]) == ("a.txt", "SUPPORTED")
    assert overall["data"]["kind_detail"] == "statement_overall"
    assert overall["data"]["verdict"] == "SUPPORTED"
    assert overall["data"]["witness_seq"] == stop["seq"]


def test_ac2_1b_a_contradiction_and_an_undeclared_change_are_recorded(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    _write_statement(tmp_path, {"files_created": ["a.txt", "ghost.txt"]})
    on_stop(_base_payload(), tmp_path, Path.home())
    by_path = {v["data"]["path"]: v["data"]["verdict"] for v in _verdicts(tmp_path) if "path" in v["data"]}
    assert by_path == {"a.txt": "SUPPORTED", "ghost.txt": "CONTRADICTED"}
    (overall,) = _overalls(tmp_path)
    assert overall["data"]["verdict"] == "CONTRADICTED"
    assert overall["data"]["undeclared"] == [{"path": "b.txt", "change": "created"}]


def test_ac2_2_verify_later_adds_nothing(tmp_path, monkeypatch):
    from papertrail import outcome
    from papertrail.__main__ import main

    on_start(_base_payload(), tmp_path, Path.home())
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    _write_statement(tmp_path, {"files_created": ["a.txt"]})
    on_stop(_base_payload(), tmp_path, Path.home())
    before = _lp(tmp_path).read_bytes()

    monkeypatch.setenv("PAPERTRAIL_ROOT", str(tmp_path))
    assert outcome.result_for(tmp_path, _SESSION)["overall"] == "SUPPORTED"
    assert outcome.result_for(tmp_path, _SESSION, 1)["overall"] == "SUPPORTED"
    assert main(["verify", _SESSION]) == 0
    assert main(["verify", _SESSION, "1"]) == 0
    assert _lp(tmp_path).read_bytes() == before
    assert ledger.verify_chain(_lp(tmp_path)) == (True, None)


def test_ac2_3_each_statement_in_a_session_is_checked_once(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    _write_statement(tmp_path, {"files_created": ["a.txt"]})
    on_stop(_base_payload(), tmp_path, Path.home())
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    _write_statement(tmp_path, {"files_created": ["b.txt"]})
    on_stop(_base_payload(), tmp_path, Path.home())
    overalls = _overalls(tmp_path)
    assert [o["data"]["verdict"] for o in overalls] == ["SUPPORTED", "SUPPORTED"]
    assert len({o["data"]["witness_seq"] for o in overalls}) == 2
    assert len([v for v in _verdicts(tmp_path) if "path" in v["data"]]) == 2


def test_ac2_4_a_rejected_statement_is_not_checked(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / ".papertrail" / "statement.json").write_text('{"summary": "only this"}', encoding="utf-8")
    on_stop(_base_payload(), tmp_path, Path.home())
    verdicts = _verdicts(tmp_path)
    assert [v["data"]["verdict"] for v in verdicts] == ["NO_STATEMENT"]  # the old rule, unchanged
    assert not _by_kind(tmp_path, "statement")


def test_ac2_5_a_statement_that_cannot_be_checked_is_still_promoted_and_nothing_raises(tmp_path):
    on_start(_base_payload(), tmp_path, Path.home())
    # an absolute path is not allowed by the statement parser, so the check fails
    _write_statement(tmp_path, {"files_read": ["/home/someone/x.txt"]})
    on_stop(_base_payload(), tmp_path, Path.home())  # must not raise
    assert len(_by_kind(tmp_path, "statement")) == 1
    (error,) = _by_kind(tmp_path, "error")
    assert error["data"]["source"] == "session.py auto-check"
    assert "could not be checked" in error["data"]["error"]
    assert not _verdicts(tmp_path)
    assert ledger.verify_chain(_lp(tmp_path)) == (True, None)


def test_ac2_5_a_failure_inside_the_verifier_is_an_error_record_too(tmp_path, monkeypatch):
    from papertrail import session

    def boom(*args, **kwargs):
        raise RuntimeError("verifier broke")

    monkeypatch.setattr(session.verifier, "verify", boom)
    on_start(_base_payload(), tmp_path, Path.home())
    _write_statement(tmp_path)
    on_stop(_base_payload(), tmp_path, Path.home())
    assert len(_by_kind(tmp_path, "statement")) == 1
    assert "verifier broke" in _by_kind(tmp_path, "error")[0]["data"]["error"]


def test_ac2_6_the_stop_with_a_statement_and_20_files_is_still_quick(tmp_path):
    import time

    on_start(_base_payload(), tmp_path, Path.home())
    names = []
    for i in range(20):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
        names.append(f"f{i}.txt")
    _write_statement(tmp_path, {"files_created": names})
    started = time.perf_counter()
    on_stop(_base_payload(), tmp_path, Path.home())
    assert time.perf_counter() - started < 1.0
    assert _overalls(tmp_path)[0]["data"]["verdict"] == "SUPPORTED"


def test_the_hook_script_checks_the_statement_and_exits_zero(tmp_path):
    import os
    import subprocess
    import sys

    project = Path(__file__).resolve().parents[1]
    hook = project / ".kiro" / "hooks" / "witness.py"
    env = {**os.environ, "PAPERTRAIL_ROOT": str(tmp_path)}
    payload = json.dumps({"session_id": "via-hook-2"})

    def run(event: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(hook), event], input=payload, capture_output=True,
                              text=True, env=env, cwd=str(project), timeout=30)

    assert run("start").returncode == 0
    (tmp_path / "made.txt").write_text("m", encoding="utf-8")
    _write_statement(tmp_path, {"files_created": ["made.txt"]})
    assert run("stop").returncode == 0
    assert _overalls(tmp_path)[-1]["data"]["verdict"] == "SUPPORTED"