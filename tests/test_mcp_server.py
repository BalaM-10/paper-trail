"""Tests for papertrail/mcp_server.py.

Handlers are called directly with tmp_path as the root. One smoke test drives
the real stdio protocol against a short-lived subprocess that exits when its
stdin closes. The project's own .papertrail folder is never used.
"""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from papertrail import ledger as ledger_mod
from papertrail.mcp_server import (
    handle_check_chain,
    handle_get_entries,
    handle_list_sessions,
    handle_verify_statement,
)
from papertrail import spool
from papertrail.mcp_server import handle_print_session
from sample.make_demo_ledger import SESSION_A, SESSION_B, SESSION_C, generate

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _lp(root: Path) -> Path:
    return root / ".papertrail" / "ledger.jsonl"


@pytest.fixture
def demo_root(tmp_path) -> Path:
    """A project root holding the generated demo ledger and its statements."""
    generate(out_path=_lp(tmp_path))
    stmts = tmp_path / ".papertrail" / "statements"
    stmts.mkdir(parents=True, exist_ok=True)
    for e in ledger_mod.read(_lp(tmp_path)):
        if e["kind"] == "statement":
            (stmts / f"{e['session_id']}-1.json").write_text(
                json.dumps(e["data"]), encoding="utf-8"
            )
    return tmp_path


def _seed_unverified(root: Path, sid: str = "sess-mcp") -> None:
    lp = _lp(root)
    ledger_mod.append(lp, sid, "witness", {"event": "start", "snapshot": {}})
    stop = ledger_mod.append(lp, sid, "witness", {
        "event": "stop", "snapshot": {},
        "diff": {"created": [], "deleted": ["a.txt", "b.txt"], "modified": []},
        "baseline": "start",
    })
    stmt = {
        "summary": "Removed a.", "files_read": [], "files_created": [],
        "files_modified": [], "files_deleted": ["a.txt"],
        "session_id": sid, "ts": "2026-01-01T00:00:00+00:00",
        "witness_seq": stop["seq"],
    }
    d = root / ".papertrail" / "statements"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}-1.json").write_text(json.dumps(stmt), encoding="utf-8")


# --- list_sessions ---------------------------------------------------------

def test_list_sessions_empty(tmp_path):
    assert handle_list_sessions(tmp_path) == []


def test_list_sessions_two_sessions_counts(tmp_path):
    lp = _lp(tmp_path)
    ledger_mod.append(lp, "sess-a", "tool", {})
    ledger_mod.append(lp, "sess-b", "tool", {})
    ledger_mod.append(lp, "sess-a", "tool", {})
    result = handle_list_sessions(tmp_path)
    assert [(s["session_id"], s["entry_count"]) for s in result] == [("sess-a", 2), ("sess-b", 1)]
    assert all(s["has_statement"] is False and s["overall_verdict"] is None for s in result)


def test_list_sessions_reports_statement_and_verdict(demo_root):
    by_id = {s["session_id"]: s for s in handle_list_sessions(demo_root)}
    assert by_id[SESSION_A]["overall_verdict"] == "SUPPORTED"
    assert by_id[SESSION_B]["overall_verdict"] == "CONTRADICTED"
    assert by_id[SESSION_A]["has_statement"] and by_id[SESSION_B]["has_statement"]
    # The agent that changed files and said nothing: a verdict, but no statement.
    assert by_id[SESSION_C]["overall_verdict"] == "NO_STATEMENT"
    assert by_id[SESSION_C]["has_statement"] is False


# --- get_entries -----------------------------------------------------------

def test_get_entries_filters_by_session_in_order(demo_root):
    entries = handle_get_entries(demo_root, SESSION_B)
    assert entries and all(e["session_id"] == SESSION_B for e in entries)
    assert [e["seq"] for e in entries] == sorted(e["seq"] for e in entries)


def test_get_entries_unknown_session_is_empty(demo_root):
    assert handle_get_entries(demo_root, "nobody") == []


# --- check_chain -----------------------------------------------------------

def test_check_chain_ok(demo_root):
    result = handle_check_chain(demo_root)
    assert result["ok"] is True and result["broken_at"] is None
    assert result["count"] == len(ledger_mod.read(_lp(demo_root)))


def test_check_chain_empty(tmp_path):
    assert handle_check_chain(tmp_path) == {"ok": True, "broken_at": None, "count": 0}


def test_check_chain_reports_break(tmp_path):
    lp = _lp(tmp_path)
    for i in range(3):
        ledger_mod.append(lp, "s", "tool", {"i": i})
    lines = lp.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    entry["data"]["i"] = 99
    lines[1] = json.dumps(entry, separators=(",", ":"))
    lp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert handle_check_chain(tmp_path) == {"ok": False, "broken_at": 2, "count": 3}


# --- verify_statement ------------------------------------------------------

def test_verify_statement_demo_contradicted_session(demo_root):
    result = handle_verify_statement(demo_root, SESSION_B, 1)
    assert result["overall"] == "CONTRADICTED"
    assert {"path": "sample/notes.txt", "change": "deleted"} in result["undeclared"]


def test_verify_statement_demo_supported_session(demo_root):
    assert handle_verify_statement(demo_root, SESSION_A, 1)["overall"] == "SUPPORTED"


def test_verify_statement_computes_and_stores_verdicts(tmp_path):
    _seed_unverified(tmp_path)
    result = handle_verify_statement(tmp_path, "sess-mcp", 1)
    assert set(result) == {"verdicts", "undeclared", "overall"}
    assert result["overall"] == "CONTRADICTED"
    stored = [e for e in ledger_mod.read(_lp(tmp_path))
              if e["kind"] == "verdict" and e["data"].get("kind_detail") == "statement_overall"]
    assert len(stored) == 1


def test_verify_statement_is_idempotent(tmp_path):
    _seed_unverified(tmp_path)
    first = handle_verify_statement(tmp_path, "sess-mcp", 1)
    count = len(ledger_mod.read(_lp(tmp_path)))
    assert handle_verify_statement(tmp_path, "sess-mcp", 1) == first
    assert len(ledger_mod.read(_lp(tmp_path))) == count


@pytest.mark.parametrize("sid", ["nobody", "..\\x", "../x", ".hidden", "a..b", ""])
def test_verify_statement_missing_or_unsafe_returns_error(tmp_path, sid):
    result = handle_verify_statement(tmp_path, sid, 1)
    assert set(result) == {"error"} and result["error"]


def test_verify_statement_wrong_number_returns_error(tmp_path):
    _seed_unverified(tmp_path)
    assert "error" in handle_verify_statement(tmp_path, "sess-mcp", 7)


def test_verify_statement_unreadable_returns_error(tmp_path):
    d = tmp_path / ".papertrail" / "statements"
    d.mkdir(parents=True)
    (d / "bad-1.json").write_text("{ nope", encoding="utf-8")
    assert "error" in handle_verify_statement(tmp_path, "bad", 1)


# --- import hygiene --------------------------------------------------------

def test_importing_module_does_not_load_the_sdk():
    code = "import papertrail.mcp_server, sys; assert 'mcp' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# --- real stdio protocol ---------------------------------------------------

def _reader(stream, q: "queue.Queue[str]") -> None:
    for line in iter(stream.readline, ""):
        q.put(line)


def test_stdio_protocol_end_to_end(demo_root):
    env = {**os.environ, "PAPERTRAIL_ROOT": str(demo_root)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "papertrail.mcp_server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env=env, cwd=str(PROJECT_ROOT),
    )
    out: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, out), daemon=True).start()

    def send(obj: dict) -> None:
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def recv() -> dict:
        return json.loads(out.get(timeout=20))   # every line on stdout is protocol JSON

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"}}})
        assert recv()["result"]["serverInfo"]["name"] == "paper-trail"
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in recv()["result"]["tools"]}
        assert names == {
            "list_sessions", "get_entries", "check_chain", "verify_statement", "print_session",
        }

        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "verify_statement",
            "arguments": {"session_id": SESSION_B, "n": 1}}})
        reply = recv()["result"]
        assert reply["isError"] is False
        payload = json.loads(reply["content"][0]["text"])
        assert payload["overall"] == "CONTRADICTED"

        # n is optional: with none, the session that said nothing reports NO_STATEMENT.
        send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "verify_statement", "arguments": {"session_id": SESSION_C}}})
        quiet = json.loads(recv()["result"]["content"][0]["text"])
        assert quiet["overall"] == "NO_STATEMENT"

        send({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
            "name": "print_session", "arguments": {"session_id": SESSION_B}}})
        printed = recv()["result"]
        assert printed["isError"] is False
        assert "".join(c["text"] for c in printed["content"]) == handle_print_session(demo_root, SESSION_B)
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    assert proc.returncode == 0


# --- workspace registration (AC5.2) ----------------------------------------

def test_workspace_mcp_registration():
    path = PROJECT_ROOT / ".kiro" / "settings" / "mcp.json"
    assert path.exists(), "create .kiro/settings/mcp.json (see tasks.md Task 4b)"
    config = json.loads(path.read_text(encoding="utf-8"))
    entry = config["mcpServers"]["paper-trail"]
    assert entry["command"] == "python"
    assert entry["args"] == ["-m", "papertrail.mcp_server"]
    assert entry.get("disabled", False) is False
    raw = path.read_text(encoding="utf-8")
    assert ":\\" not in raw and ":/" not in raw and "/Users/" not in raw


# --- NO_STATEMENT and print_session (R2.2, R3.2) ----------------------------------

def test_verify_statement_without_a_number_reports_a_silent_session(demo_root):
    before = _lp(demo_root).read_bytes()
    result = handle_verify_statement(demo_root, SESSION_C)
    assert result == {
        "verdicts": [],
        "undeclared": [
            {"path": "sample/src/helpers.py", "change": "created"},
            {"path": "sample/src/main.py", "change": "modified"},
        ],
        "overall": "NO_STATEMENT",
    }
    assert _lp(demo_root).read_bytes() == before  # reading wrote nothing


def test_verify_statement_with_a_number_still_needs_that_statement(demo_root):
    assert "error" in handle_verify_statement(demo_root, SESSION_C, 1)


def test_verify_statement_without_a_number_checks_the_newest_statement(demo_root):
    assert handle_verify_statement(demo_root, SESSION_B)["overall"] == "CONTRADICTED"
    assert handle_verify_statement(demo_root, SESSION_A)["overall"] == "SUPPORTED"


def test_print_session_returns_the_text_the_command_would_write(demo_root):
    text = handle_print_session(demo_root, SESSION_B)
    assert text == spool.render_session(demo_root, SESSION_B)
    assert text.splitlines()[-1].endswith("lines)")
    assert not (demo_root / ".papertrail" / "spool").exists()  # the tool writes nothing


def test_print_session_describes_a_silent_session(demo_root):
    text = handle_print_session(demo_root, SESSION_C)
    assert "Statement: none written" in text
    assert "Overall: the agent changed files and said nothing. (NO STATEMENT)" in text.replace("\n      ", " ")


@pytest.mark.parametrize("sid", ["nobody", "", "..\\x", "../x", ".hidden", "a..b"])
def test_print_session_errors_are_one_plain_line(demo_root, sid):
    text = handle_print_session(demo_root, sid)
    assert text.startswith("Error: ")
    assert "\n" not in text.rstrip("\n")


# --- one roll per turn (paper-trail-turns R2.7) ----------------------------

def test_list_sessions_has_one_item_per_turn(demo_root):
    items = handle_list_sessions(demo_root)
    d = [s for s in items if s["session_id"] == "demo-session-d"]
    assert [(s["turn"], s["turns"], s["title"], s["overall_verdict"], s["has_statement"]) for s in d] == [
        (1, 2, "Wrote the plan.", "SUPPORTED", True),
        (2, 2, "Cleared two drafts.", "SUPPORTED", True),
    ]
    assert [s["entry_count"] for s in d] == [7, 8]
    assert [(s["session_id"], s["turn"], s["turns"]) for s in items if s["session_id"] != "demo-session-d"] == [
        (SESSION_A, 1, 1), (SESSION_B, 1, 1), (SESSION_C, 1, 1),
    ]
    assert [s["title"] for s in items if s["session_id"] == SESSION_C] == ["No statement written"]


def test_get_entries_can_return_one_turn_with_its_real_line_numbers(demo_root):
    whole = handle_get_entries(demo_root, "demo-session-d")
    second = handle_get_entries(demo_root, "demo-session-d", 2)
    assert [e["seq"] for e in second] == list(range(27, 35))
    assert [e["seq"] for e in handle_get_entries(demo_root, "demo-session-d", 1)] == list(range(20, 27))
    assert second == [e for e in whole if e["seq"] >= 27]
    assert handle_get_entries(demo_root, "demo-session-d", 3) == []
    assert handle_get_entries(demo_root, "demo-session-d", 0) == []
    assert handle_get_entries(demo_root, "nope", 1) == []


def test_print_session_has_a_report_per_turn(demo_root):
    text = handle_print_session(demo_root, "demo-session-d")
    assert "Turn: 1 of 2" in text and "Turn: 2 of 2" in text