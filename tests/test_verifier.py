"""Tests for papertrail/verifier.py."""

import os
import json
from pathlib import Path

import pytest

from papertrail import ledger as ledger_mod
from papertrail.session import on_start, on_stop
from papertrail.verifier import verify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_statement(
    tmp_path: Path,
    session_id: str = "sess-test",
    summary: str = "Test statement.",
    files_read: list | None = None,
    files_created: list | None = None,
    files_modified: list | None = None,
    files_deleted: list | None = None,
    witness_seq: int = 1,
) -> dict:
    return {
        "summary":        summary,
        "files_read":     files_read     or [],
        "files_created":  files_created  or [],
        "files_modified": files_modified or [],
        "files_deleted":  files_deleted  or [],
        "session_id":     session_id,
        "ts":             "2026-01-01T00:00:00+00:00",
        "witness_seq":    witness_seq,
    }


def _make_witness_stop_entry(
    tmp_path: Path,
    session_id: str,
    diff: dict,
    baseline: str = "start",
) -> dict:
    """Append a fake witness/stop entry and return it."""
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    return ledger_mod.append(ledger_path, session_id, "witness", {
        "event":    "stop",
        "snapshot": {},
        "diff":     diff,
        "baseline": baseline,
    })


def _run_verify(tmp_path: Path, stmt: dict, session_id: str) -> dict:
    """Run verify() with PAPERTRAIL_ROOT pointing at tmp_path."""
    old_env = os.environ.get("PAPERTRAIL_ROOT")
    os.environ["PAPERTRAIL_ROOT"] = str(tmp_path)
    try:
        ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
        entries = ledger_mod.read(ledger_path)
        return verify(stmt, entries, session_id)
    finally:
        if old_env is None:
            os.environ.pop("PAPERTRAIL_ROOT", None)
        else:
            os.environ["PAPERTRAIL_ROOT"] = old_env


# ---------------------------------------------------------------------------
# AC5.1a — files_created in diff → SUPPORTED, cites witness_seq
# ---------------------------------------------------------------------------

def test_files_created_in_diff_supported(tmp_path):
    sid = "sess-5-1a"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": ["src/foo.py"], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_created=["src/foo.py"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    v = result["verdicts"][0]
    assert v["verdict"] == "SUPPORTED"
    assert stop["seq"] in v["evidence_seq"]


# ---------------------------------------------------------------------------
# AC5.1b — files_created absent from diff, not excluded → CONTRADICTED
# ---------------------------------------------------------------------------

def test_files_created_absent_contradicted(tmp_path):
    sid = "sess-5-1b"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": [], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_created=["src/missing.py"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    v = result["verdicts"][0]
    assert v["verdict"] == "CONTRADICTED"


# ---------------------------------------------------------------------------
# AC5.1c — files_created inside excluded dir → UNVERIFIED, empty seq
# ---------------------------------------------------------------------------

def test_files_created_excluded_unverified(tmp_path):
    sid = "sess-5-1c"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": [], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_created=["node_modules/pkg/index.js"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    v = result["verdicts"][0]
    assert v["verdict"] == "UNVERIFIED"
    assert v["evidence_seq"] == []


# ---------------------------------------------------------------------------
# AC5.1d — files_deleted in diff → SUPPORTED
# ---------------------------------------------------------------------------

def test_files_deleted_in_diff_supported(tmp_path):
    sid = "sess-5-1d"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": [], "deleted": ["old.txt"], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_deleted=["old.txt"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    v = result["verdicts"][0]
    assert v["verdict"] == "SUPPORTED"


# ---------------------------------------------------------------------------
# AC5.1e — files_deleted absent from diff, not excluded → CONTRADICTED
# ---------------------------------------------------------------------------

def test_files_deleted_absent_contradicted(tmp_path):
    sid = "sess-5-1e"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": [], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_deleted=["ghost.txt"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    v = result["verdicts"][0]
    assert v["verdict"] == "CONTRADICTED"


# ---------------------------------------------------------------------------
# AC5.1f — files_read confirmed by tool entry → SUPPORTED
# ---------------------------------------------------------------------------

def test_files_read_with_tool_entry_supported(tmp_path):
    sid = "sess-5-1f"
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    # Append a tool entry that records a read.
    ledger_mod.append(ledger_path, sid, "tool", {
        "tool_name": "fs_read",
        "hook_event_name": "PostToolUse",
        "tool_input": {"path": "README.md"},
        "tool_response": "",
    })
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": [], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_read=["README.md"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    v = result["verdicts"][0]
    assert v["verdict"] == "SUPPORTED"


# ---------------------------------------------------------------------------
# AC5.1g — files_read with no tool entry → UNVERIFIED
# ---------------------------------------------------------------------------

def test_files_read_no_tool_entry_unverified(tmp_path):
    sid = "sess-5-1g"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": [], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_read=["some/file.py"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    v = result["verdicts"][0]
    assert v["verdict"] == "UNVERIFIED"
    assert v["evidence_seq"] == []


# ---------------------------------------------------------------------------
# AC5.1i — back-slash path matches forward-slash diff path
# ---------------------------------------------------------------------------

def test_backslash_path_matches(tmp_path):
    sid = "sess-5-1i"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": ["src/foo.py"], "deleted": [], "modified": []})
    # Statement uses back-slash (Windows path).
    stmt = _make_statement(tmp_path, sid, files_created=["src\\foo.py"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    v = result["verdicts"][0]
    assert v["verdict"] == "SUPPORTED"


# ---------------------------------------------------------------------------
# AC5.1j — case-different path matches on Windows
# ---------------------------------------------------------------------------

def test_case_different_path_matches(tmp_path):
    sid = "sess-5-1j"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": ["Src/Foo.py"], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_created=["src/foo.py"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    v = result["verdicts"][0]
    # On Windows: SUPPORTED; on other platforms: CONTRADICTED (case sensitive).
    import sys
    if sys.platform == "win32":
        assert v["verdict"] == "SUPPORTED"
    else:
        assert v["verdict"] in ("SUPPORTED", "CONTRADICTED")


# ---------------------------------------------------------------------------
# AC5.2a–c — undeclared deleted/created/modified
# ---------------------------------------------------------------------------

def test_undeclared_deleted(tmp_path):
    sid = "sess-5-2a"
    stop = _make_witness_stop_entry(tmp_path, sid, {
        "created": [], "deleted": ["secret.txt"], "modified": [],
    })
    stmt = _make_statement(tmp_path, sid, witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    assert any(u["path"] == "secret.txt" and u["change"] == "deleted" for u in result["undeclared"])


def test_undeclared_created(tmp_path):
    sid = "sess-5-2b"
    stop = _make_witness_stop_entry(tmp_path, sid, {
        "created": ["new_file.py"], "deleted": [], "modified": [],
    })
    stmt = _make_statement(tmp_path, sid, witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    assert any(u["path"] == "new_file.py" and u["change"] == "created" for u in result["undeclared"])


def test_undeclared_modified(tmp_path):
    sid = "sess-5-2c"
    stop = _make_witness_stop_entry(tmp_path, sid, {
        "created": [], "deleted": [], "modified": ["config.json"],
    })
    stmt = _make_statement(tmp_path, sid, witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    assert any(u["path"] == "config.json" and u["change"] == "modified" for u in result["undeclared"])


# ---------------------------------------------------------------------------
# AC5.3a–d — overall verdict all four cases
# ---------------------------------------------------------------------------

def test_overall_supported(tmp_path):
    sid = "sess-5-3a"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": ["a.py"], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_created=["a.py"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    assert result["overall"] == "SUPPORTED"


def test_overall_contradicted_by_verdict(tmp_path):
    sid = "sess-5-3b"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": [], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_created=["a.py"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    assert result["overall"] == "CONTRADICTED"


def test_overall_contradicted_by_undeclared(tmp_path):
    sid = "sess-5-3c"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": ["hidden.py"], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    assert result["overall"] == "CONTRADICTED"


def test_overall_unverified(tmp_path):
    sid = "sess-5-3d"
    # No witness stop entry — baseline="none" → UNVERIFIED (no contradictions,
    # but not all SUPPORTED since the claim cannot be checked).
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    # Append a witness entry with baseline="none" at seq 1.
    stop = ledger_mod.append(ledger_path, sid, "witness", {
        "event": "stop", "snapshot": {}, "diff": {}, "baseline": "none",
    })
    stmt = _make_statement(tmp_path, sid, files_created=["a.py"], witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    assert result["overall"] == "UNVERIFIED"


# ---------------------------------------------------------------------------
# AC5.4d — overall entry has data.kind_detail == "statement_overall"
# ---------------------------------------------------------------------------

def test_overall_entry_kind_detail(tmp_path):
    sid = "sess-5-4d"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": ["x.py"], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_created=["x.py"], witness_seq=stop["seq"])
    _run_verify(tmp_path, stmt, sid)
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)
    overall_entries = [
        e for e in entries
        if e["kind"] == "verdict"
        and e["data"].get("kind_detail") == "statement_overall"
    ]
    assert len(overall_entries) == 1


# ---------------------------------------------------------------------------
# Idempotency: second verify call returns same result, no new ledger entries
# ---------------------------------------------------------------------------

def test_idempotency(tmp_path):
    sid = "sess-idempotent"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": ["a.py"], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_created=["a.py"], witness_seq=stop["seq"])

    result1 = _run_verify(tmp_path, stmt, sid)
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    count_after_first = len(ledger_mod.read(ledger_path))

    result2 = _run_verify(tmp_path, stmt, sid)
    count_after_second = len(ledger_mod.read(ledger_path))

    assert result1["overall"] == result2["overall"]
    assert result1["verdicts"] == result2["verdicts"]
    assert count_after_first == count_after_second


# ---------------------------------------------------------------------------
# baseline == "none": all non-read claims UNVERIFIED, undeclared empty
# ---------------------------------------------------------------------------

def test_baseline_none_unverified(tmp_path):
    sid = "sess-baseline-none"
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    stop = ledger_mod.append(ledger_path, sid, "witness", {
        "event": "stop", "snapshot": {}, "diff": {}, "baseline": "none",
    })
    stmt = _make_statement(tmp_path, sid,
                           files_created=["a.py"], files_deleted=["b.txt"],
                           witness_seq=stop["seq"])
    result = _run_verify(tmp_path, stmt, sid)
    for v in result["verdicts"]:
        if v["claim"] != "files_read":
            assert v["verdict"] == "UNVERIFIED"
    assert result["undeclared"] == []


# ---------------------------------------------------------------------------
# Every per-path verdict entry has witness_seq in data
# ---------------------------------------------------------------------------

def test_per_path_verdict_has_witness_seq(tmp_path):
    sid = "sess-wseq"
    stop = _make_witness_stop_entry(tmp_path, sid, {"created": ["z.py"], "deleted": [], "modified": []})
    stmt = _make_statement(tmp_path, sid, files_created=["z.py"], witness_seq=stop["seq"])
    _run_verify(tmp_path, stmt, sid)
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)
    per_path = [
        e for e in entries
        if e["kind"] == "verdict"
        and e["data"].get("kind_detail") != "statement_overall"
        and "path" in e["data"]
    ]
    assert per_path, "expected per-path verdict entries"
    for e in per_path:
        assert "witness_seq" in e["data"]


# ---------------------------------------------------------------------------
# Undeclared changes are stored on the overall verdict entry
# ---------------------------------------------------------------------------

def test_undeclared_stored_in_overall_entry(tmp_path):
    sid = "sess-undecl-stored"
    stop = _make_witness_stop_entry(
        tmp_path, sid, {"created": [], "deleted": ["secret.txt"], "modified": []}
    )
    stmt = _make_statement(tmp_path, sid, witness_seq=stop["seq"])
    _run_verify(tmp_path, stmt, sid)
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)
    overall = next(
        e for e in entries
        if e["kind"] == "verdict"
        and e["data"].get("kind_detail") == "statement_overall"
    )
    assert overall["data"]["undeclared"] == [{"path": "secret.txt", "change": "deleted"}]


def test_undeclared_idempotent_round_trip(tmp_path):
    sid = "sess-undecl-idem"
    stop = _make_witness_stop_entry(
        tmp_path, sid, {"created": [], "deleted": ["secret.txt"], "modified": []}
    )
    stmt = _make_statement(tmp_path, sid, witness_seq=stop["seq"])
    first = _run_verify(tmp_path, stmt, sid)
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    count = len(ledger_mod.read(ledger_path))
    second = _run_verify(tmp_path, stmt, sid)
    assert second["undeclared"] == first["undeclared"] == [{"path": "secret.txt", "change": "deleted"}]
    assert len(ledger_mod.read(ledger_path)) == count


def test_explicit_ledger_path_ignores_environment(tmp_path, monkeypatch):
    """verify(ledger_path=...) writes there even when PAPERTRAIL_ROOT is unset."""
    monkeypatch.delenv("PAPERTRAIL_ROOT", raising=False)
    sid = "sess-explicit-path"
    stop = _make_witness_stop_entry(
        tmp_path, sid, {"created": ["a.py"], "deleted": [], "modified": []}
    )
    stmt = _make_statement(tmp_path, sid, files_created=["a.py"], witness_seq=stop["seq"])
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)
    result = verify(stmt, entries, sid, ledger_path=ledger_path)
    assert result["overall"] == "SUPPORTED"
    kinds = [e["kind"] for e in ledger_mod.read(ledger_path)]
    assert kinds.count("verdict") == 2   # one per-path + one overall
