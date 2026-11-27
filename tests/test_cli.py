"""Tests for papertrail/__main__.py CLI and hook scripts."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from papertrail import ledger as ledger_mod

# Root of the project (parent of this file's directory)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env(tmp_path: Path) -> dict:
    return {"PAPERTRAIL_ROOT": str(tmp_path), **os.environ}


def _cli(args: list[str], tmp_path: Path, input_data: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "papertrail"] + args,
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=str(PROJECT_ROOT),
        input=input_data,
    )


def _build_session(tmp_path: Path, session_id: str) -> dict:
    """
    Build a minimal ledger with a witness/stop entry and a promoted statement.
    Returns the statement dict.
    """
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"

    # witness/start
    ledger_mod.append(ledger_path, session_id, "witness", {
        "event": "start",
        "snapshot": {"sample/cache/output.bin": {"size": 20, "sha256": "aaa"}},
    })

    # tool entry for a file read
    ledger_mod.append(ledger_path, session_id, "tool", {
        "tool_name": "fs_read",
        "hook_event_name": "PostToolUse",
        "tool_input": {"path": "sample/src/main.py"},
        "tool_response": "",
    })

    # witness/stop — notes.txt deleted (undeclared), output.bin deleted (declared)
    stop = ledger_mod.append(ledger_path, session_id, "witness", {
        "event": "stop",
        "snapshot": {},
        "diff": {
            "created": [],
            "deleted": ["sample/cache/output.bin", "sample/notes.txt"],
            "modified": [],
        },
        "baseline": "start",
    })
    witness_seq = stop["seq"]

    # Promoted statement
    stmt = {
        "summary":        "Cleared build cache.",
        "files_read":     ["sample/src/main.py"],
        "files_created":  [],
        "files_modified": [],
        "files_deleted":  ["sample/cache/output.bin"],
        "session_id":     session_id,
        "ts":             "2026-01-01T00:00:00+00:00",
        "witness_seq":    witness_seq,
    }
    stmts_dir = tmp_path / ".papertrail" / "statements"
    stmts_dir.mkdir(parents=True, exist_ok=True)
    (stmts_dir / f"{session_id}-1.json").write_text(json.dumps(stmt, indent=2), encoding="utf-8")

    ledger_mod.append(ledger_path, session_id, "statement", stmt)

    return stmt


# ---------------------------------------------------------------------------
# AC7.1a — valid session ID → verdicts in stdout
# ---------------------------------------------------------------------------

def test_verify_valid_session(tmp_path):
    sid = "sess-cli-7-1a"
    _build_session(tmp_path, sid)
    result = _cli(["verify", sid], tmp_path)
    assert result.returncode == 0
    # At least one verdict line.
    assert "SUPPORTED" in result.stdout or "CONTRADICTED" in result.stdout or "UNVERIFIED" in result.stdout


# ---------------------------------------------------------------------------
# AC7.1b — undeclared changes appear as UNDECLARED
# ---------------------------------------------------------------------------

def test_verify_undeclared_in_output(tmp_path):
    sid = "sess-cli-7-1b"
    _build_session(tmp_path, sid)
    result = _cli(["verify", sid], tmp_path)
    assert result.returncode == 0
    assert "UNDECLARED" in result.stdout
    assert "sample/notes.txt" in result.stdout


# ---------------------------------------------------------------------------
# AC7.1c — last non-blank line is OVERALL: <verdict>
# ---------------------------------------------------------------------------

def test_verify_last_line_overall(tmp_path):
    sid = "sess-cli-7-1c"
    _build_session(tmp_path, sid)
    result = _cli(["verify", sid], tmp_path)
    non_blank = [l for l in result.stdout.splitlines() if l.strip()]
    assert non_blank, "expected some output"
    assert non_blank[-1].startswith("OVERALL:")


# ---------------------------------------------------------------------------
# AC7.1d — unknown session ID → non-zero exit, error message
# ---------------------------------------------------------------------------

def test_verify_unknown_session(tmp_path):
    result = _cli(["verify", "no-such-session-xyz"], tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "no statement found" in combined.lower() or "error" in combined.lower()


# ---------------------------------------------------------------------------
# AC7.1e — verify <session_id> 1 loads -1.json even when -2.json exists
# ---------------------------------------------------------------------------

def test_verify_specific_index(tmp_path):
    sid = "sess-cli-7-1e"
    _build_session(tmp_path, sid)

    # Create a second statement file with a different summary.
    stmt2 = {
        "summary":        "Second statement.",
        "files_read":     [],
        "files_created":  [],
        "files_modified": [],
        "files_deleted":  [],
        "session_id":     sid,
        "ts":             "2026-01-02T00:00:00+00:00",
        "witness_seq":    99,
    }
    stmts_dir = tmp_path / ".papertrail" / "statements"
    (stmts_dir / f"{sid}-2.json").write_text(json.dumps(stmt2, indent=2), encoding="utf-8")

    # Asking for index 1 should reference output.bin, not the second statement.
    result = _cli(["verify", sid, "1"], tmp_path)
    assert result.returncode == 0
    assert "sample/cache/output.bin" in result.stdout


# ---------------------------------------------------------------------------
# AC7.2a — valid chain → Chain OK (<n> entries), exit 0
# ---------------------------------------------------------------------------

def test_check_chain_valid(tmp_path):
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    for i in range(5):
        ledger_mod.append(ledger_path, "s", "tool", {"i": i})
    result = _cli(["check-chain"], tmp_path)
    assert result.returncode == 0
    assert "Chain OK" in result.stdout
    assert "5" in result.stdout


# ---------------------------------------------------------------------------
# AC7.2b — broken chain → Chain BROKEN at seq <n>, exit 1
# ---------------------------------------------------------------------------

def test_check_chain_broken(tmp_path):
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    e1 = ledger_mod.append(ledger_path, "s", "tool", {"i": 1})
    e2 = ledger_mod.append(ledger_path, "s", "tool", {"i": 2})

    # Corrupt the second entry.
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    entry["data"]["i"] = 999  # mutate data, hash becomes wrong
    lines[1] = json.dumps(entry, separators=(",", ":"))
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = _cli(["check-chain"], tmp_path)
    assert result.returncode == 1
    assert "BROKEN" in result.stdout
    assert "2" in result.stdout


# ---------------------------------------------------------------------------
# AC7.2c — absent ledger → No ledger found, exit 0
# ---------------------------------------------------------------------------

def test_check_chain_no_ledger(tmp_path):
    result = _cli(["check-chain"], tmp_path)
    assert result.returncode == 0
    assert "No ledger found" in result.stdout


# ---------------------------------------------------------------------------
# AC1.4a–c — concurrent lock test: two processes each append 50 entries
# ---------------------------------------------------------------------------

def _append_many(tmp_path: Path, n: int) -> None:
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    for i in range(n):
        ledger_mod.append(ledger_path, "concurrent", "tool", {"i": i})


def test_concurrent_append(tmp_path):
    n = 50
    t1 = threading.Thread(target=_append_many, args=(tmp_path, n))
    t2 = threading.Thread(target=_append_many, args=(tmp_path, n))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    ok, broken = ledger_mod.verify_chain(ledger_path)
    assert ok, f"chain broken at seq {broken}"
    entries = ledger_mod.read(ledger_path)
    assert len(entries) == 100


# ---------------------------------------------------------------------------
# Hook script: record.py with valid payload → kind="tool", relative path
# ---------------------------------------------------------------------------

def test_hook_record_valid_payload(tmp_path):
    # Use a path under tmp_path so the recorder can normalise it to relative form.
    abs_path = str(tmp_path / "src" / "foo.py")
    payload = json.dumps({
        "session_id": "hook-test",
        "tool_name": "fs_write",
        "hook_event_name": "PostToolUse",
        "tool_input": {"path": abs_path, "text": "hi"},
        "tool_response": "ok",
    })
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / ".kiro" / "hooks" / "record.py")],
        input=payload,
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)
    assert entries[-1]["kind"] == "tool"
    # Path must be relative (no drive letter, no absolute indicator).
    path_val = entries[-1]["data"]["tool_input"].get("path", "")
    assert not os.path.isabs(str(path_val))


# ---------------------------------------------------------------------------
# Hook script: record.py with empty stdin → kind="error", exit 0
# ---------------------------------------------------------------------------

def test_hook_record_empty_stdin(tmp_path):
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / ".kiro" / "hooks" / "record.py")],
        input="",
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)
    assert entries[-1]["kind"] == "error"


# ---------------------------------------------------------------------------
# Hook script: witness.py start → kind="witness", data.event="start"
# ---------------------------------------------------------------------------

def test_hook_witness_start(tmp_path):
    payload = json.dumps({"session_id": "hook-wtest"})
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / ".kiro" / "hooks" / "witness.py"), "start"],
        input=payload,
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)
    last = entries[-1]
    assert last["kind"] == "witness"
    assert last["data"]["event"] == "start"


# ---------------------------------------------------------------------------
# Hook script: witness.py stop after start → kind="witness", event="stop", diff present
# ---------------------------------------------------------------------------

def test_hook_witness_stop_after_start(tmp_path):
    payload = json.dumps({"session_id": "hook-wtest2"})

    # start
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / ".kiro" / "hooks" / "witness.py"), "start"],
        input=payload,
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=str(PROJECT_ROOT),
    )

    # stop
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / ".kiro" / "hooks" / "witness.py"), "stop"],
        input=payload,
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)
    last = entries[-1]
    assert last["kind"] == "witness"
    assert last["data"]["event"] == "stop"
    assert "diff" in last["data"]
    diff = last["data"]["diff"]
    assert "created" in diff
    assert "deleted" in diff
    assert "modified" in diff


# ===========================================================================
# NO_STATEMENT through the CLI (R2.2)
# ===========================================================================

from papertrail.session import on_start, on_stop


def _touch(root: Path, name: str) -> None:
    (root / name).write_text("x", encoding="utf-8")


def _statement(root: Path, **lists) -> None:
    body = {
        "summary": "Made a file.",
        "files_read": [], "files_created": [], "files_modified": [], "files_deleted": [],
        **lists,
    }
    path = root / ".papertrail" / "statement.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def _silent_session(root: Path, sid: str, *names: str) -> None:
    on_start({"session_id": sid}, root, Path.home())
    for name in names:
        _touch(root, name)
    on_stop({"session_id": sid}, root, Path.home())


def test_verify_a_silent_session_prints_the_changes_and_no_statement(tmp_path):
    _silent_session(tmp_path, "quiet", "b.txt", "a.txt")
    before = (tmp_path / ".papertrail" / "ledger.jsonl").read_bytes()

    result = _cli(["verify", "quiet"], tmp_path)

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].split() == ["UNDECLARED", "created", "a.txt"]
    assert lines[1].split() == ["UNDECLARED", "created", "b.txt"]
    assert lines[-1] == "OVERALL: NO_STATEMENT"
    assert lines[-2] == ""                      # a blank line before OVERALL, as always
    # Asking is reading: the record is exactly as it was.
    assert (tmp_path / ".papertrail" / "ledger.jsonl").read_bytes() == before


def test_verify_a_silent_session_by_number_needs_a_statement_file(tmp_path):
    _silent_session(tmp_path, "quiet", "a.txt")
    result = _cli(["verify", "quiet", "1"], tmp_path)
    assert result.returncode == 1
    assert "no statement found" in (result.stdout + result.stderr).lower()


def test_verify_shows_whichever_is_newer_and_a_number_always_means_that_statement(tmp_path):
    sid = {"session_id": "mixed"}
    on_start(sid, tmp_path, Path.home())
    _touch(tmp_path, "a.txt")
    _statement(tmp_path, files_created=["a.txt"])
    on_stop(sid, tmp_path, Path.home())          # statement 1
    _touch(tmp_path, "b.txt")
    on_stop(sid, tmp_path, Path.home())          # a silent stop, newer than statement 1

    newest = _cli(["verify", "mixed"], tmp_path)
    assert newest.stdout.splitlines()[-1] == "OVERALL: NO_STATEMENT"
    assert "b.txt" in newest.stdout and "a.txt" not in newest.stdout

    numbered = _cli(["verify", "mixed", "1"], tmp_path)
    assert numbered.stdout.splitlines()[-1] == "OVERALL: SUPPORTED"

    _touch(tmp_path, "c.txt")
    _statement(tmp_path, files_created=["b.txt", "c.txt"])
    on_stop(sid, tmp_path, Path.home())          # statement 2 is newest again
    assert _cli(["verify", "mixed"], tmp_path).stdout.splitlines()[-1] == "OVERALL: SUPPORTED"


def test_verify_an_unknown_session_is_still_an_error(tmp_path):
    _silent_session(tmp_path, "quiet", "a.txt")
    result = _cli(["verify", "somebody-else"], tmp_path)
    assert result.returncode == 1
    assert "no statement found" in (result.stdout + result.stderr).lower()


def test_verify_refuses_an_unsafe_session_id(tmp_path):
    result = _cli(["verify", "..\\..\\x"], tmp_path)
    assert result.returncode == 1


def test_a_corrupt_statement_is_reported_not_a_traceback(tmp_path):
    folder = tmp_path / ".papertrail" / "statements"
    folder.mkdir(parents=True)
    (folder / "bad-1.json").write_text("{ nope", encoding="utf-8")
    result = _cli(["verify", "bad"], tmp_path)
    assert result.returncode == 1
    assert "could not parse" in result.stdout.lower()
    assert "Traceback" not in result.stderr


def test_usage_lists_print(tmp_path):
    result = _cli([], tmp_path)
    assert result.returncode == 1
    assert "print" in result.stderr