"""Tests for sample/make_demo_ledger.py (structure and verdicts, not byte-for-byte)."""

import copy
import json
import os
from pathlib import Path

import pytest

from papertrail import ledger as ledger_mod
from sample.make_demo_ledger import SESSION_A, SESSION_B, SESSION_C, SESSION_D, generate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMITTED = PROJECT_ROOT / "web" / "public" / "demo" / "ledger.jsonl"


@pytest.fixture
def demo(tmp_path):
    out = tmp_path / "ledger.jsonl"
    generate(out_path=out)
    return out, ledger_mod.read(out)


def _session(entries, sid):
    return [e for e in entries if e["session_id"] == sid]


def _overall(entries, sid):
    return next(
        e for e in entries
        if e["session_id"] == sid
        and e["kind"] == "verdict"
        and e["data"].get("kind_detail") == "statement_overall"
    )


def _stop(entries, sid):
    return next(
        e for e in _session(entries, sid)
        if e["kind"] == "witness" and e["data"]["event"] == "stop"
    )


def _shape(entries):
    """What the demo says, without what differs by machine: file snapshots, promotion times, hashes."""
    shaped = []
    for e in entries:
        data = copy.deepcopy(e["data"])
        data.pop("snapshot", None)
        if e["kind"] == "statement":
            data.pop("ts", None)
        shaped.append((e["seq"], e["session_id"], e["kind"], data))
    return shaped


# --- structure ----------------------------------------------------------------

def test_chain_is_intact(demo):
    out, _ = demo
    assert ledger_mod.verify_chain(out) == (True, None)


def test_four_sessions_in_order(demo):
    _, entries = demo
    assert list(dict.fromkeys(e["session_id"] for e in entries)) == [SESSION_A, SESSION_B, SESSION_C, SESSION_D]


def test_sessions_a_and_b_have_every_kind_of_record(demo):
    _, entries = demo
    for sid in (SESSION_A, SESSION_B):
        kinds = {e["kind"] for e in _session(entries, sid)}
        assert kinds >= {"witness", "tool", "statement", "verdict"}


def test_overall_verdicts(demo):
    _, entries = demo
    assert _overall(entries, SESSION_A)["data"]["verdict"] == "SUPPORTED"
    assert _overall(entries, SESSION_B)["data"]["verdict"] == "CONTRADICTED"
    assert _overall(entries, SESSION_C)["data"]["verdict"] == "NO_STATEMENT"
    assert [e["data"]["verdict"] for e in _session(entries, SESSION_D) if e["data"].get("kind_detail") == "statement_overall"] == ["SUPPORTED", "SUPPORTED"]


def test_the_overall_verdict_is_the_last_record_of_each_session(demo):
    _, entries = demo
    for sid in (SESSION_A, SESSION_B, SESSION_C, SESSION_D):
        last = _session(entries, sid)[-1]
        assert last["kind"] == "verdict"
        assert last["data"].get("kind_detail") == "statement_overall"


# --- session A ----------------------------------------------------------------

def test_session_a_read_claim_is_supported_by_a_tool_entry(demo):
    _, entries = demo
    tools = [e for e in _session(entries, SESSION_A) if e["kind"] == "tool"]
    assert any(e["data"]["tool_name"] == "read_file" for e in tools)
    read_verdict = next(
        e for e in _session(entries, SESSION_A)
        if e["kind"] == "verdict" and e["data"].get("claim") == "files_read"
    )
    assert read_verdict["data"]["verdict"] == "SUPPORTED"


# --- session D: two turns, and a person in between -------------------------------

def _turns(entries):
    return [e for e in _session(entries, SESSION_D) if e["kind"] == "witness" and e["data"]["event"] == "turn"]


def test_session_d_has_two_turns_and_one_between_turns_record(demo):
    _, entries = demo
    assert len(_turns(entries)) == 2
    (between,) = [e for e in _session(entries, SESSION_D) if e["data"].get("event") == "between_turns"]
    assert between["data"]["diff"] == {
        "created": [], "modified": [], "deleted": ["drafts/old-a.txt", "drafts/old-b.txt"],
    }
    assert between["data"]["unfinished"] is False
    assert between["seq"] == _turns(entries)[1]["seq"] + 1


def test_session_d_second_turn_is_supported_with_nothing_undeclared(demo):
    _, entries = demo
    overalls = [e for e in _session(entries, SESSION_D) if e["data"].get("kind_detail") == "statement_overall"]
    assert [o["data"]["verdict"] for o in overalls] == ["SUPPORTED", "SUPPORTED"]
    assert overalls[1]["data"]["undeclared"] == []
    stops = [e for e in _session(entries, SESSION_D) if e["data"].get("event") == "stop"]
    assert stops[1]["data"]["diff"]["deleted"] == ["drafts/draft-1.txt", "drafts/draft-2.txt"]
    assert stops[1]["data"]["baseline"] == f"turn:{_turns(entries)[1]['seq']}"


def test_session_d_each_turn_has_its_own_statement(demo):
    _, entries = demo
    summaries = [e["data"]["summary"] for e in _session(entries, SESSION_D) if e["kind"] == "statement"]
    assert summaries == ["Wrote the plan.", "Cleared two drafts."]

# --- session B: the real script -------------------------------------------------

def test_session_b_records_what_the_real_script_printed(demo):
    _, entries = demo
    command = next(e for e in _session(entries, SESSION_B) if e["kind"] == "tool")
    assert command["data"]["tool_input"]["command"] == "python sample/cleanup.py"
    assert command["data"]["tool_response"] == "Cleared build cache: removed cache/output.bin"
    assert "notes" not in command["data"]["tool_response"]  # the printed line only mentions the cache


def test_session_b_diff_is_what_the_script_did_to_its_starting_files(demo):
    _, entries = demo
    start = next(
        e for e in _session(entries, SESSION_B)
        if e["kind"] == "witness" and e["data"]["event"] == "start"
    )
    # The real script was in the project, and so were the files it was about to remove.
    assert {"sample/cleanup.py", "sample/cache/output.bin", "sample/notes.txt"} <= set(start["data"]["snapshot"])
    assert _stop(entries, SESSION_B)["data"]["diff"] == {
        "created": [],
        "modified": [],
        "deleted": ["sample/cache/output.bin", "sample/notes.txt"],
    }


def test_session_b_undeclared_notes_file(demo):
    _, entries = demo
    undeclared = _overall(entries, SESSION_B)["data"]["undeclared"]
    assert undeclared == [{"path": "sample/notes.txt", "change": "deleted"}]


# --- session C: no statement --------------------------------------------------------

def test_session_c_has_no_statement_at_all(demo):
    _, entries = demo
    kinds = [e["kind"] for e in _session(entries, SESSION_C)]
    assert "statement" not in kinds
    assert kinds == ["witness", "tool", "tool", "witness", "verdict"]


def test_session_c_changed_two_files_and_the_verdict_lists_them_created_first(demo):
    _, entries = demo
    assert _stop(entries, SESSION_C)["data"]["diff"] == {
        "created": ["sample/src/helpers.py"],
        "modified": ["sample/src/main.py"],
        "deleted": [],
    }
    verdict = _overall(entries, SESSION_C)
    assert verdict["data"]["undeclared"] == [
        {"path": "sample/src/helpers.py", "change": "created"},
        {"path": "sample/src/main.py", "change": "modified"},
    ]
    stop = _stop(entries, SESSION_C)
    assert verdict["seq"] == stop["seq"] + 1
    assert verdict["data"]["witness_seq"] == stop["seq"]
    tools = [e["data"]["tool_name"] for e in _session(entries, SESSION_C) if e["kind"] == "tool"]
    assert tools == ["str_replace", "fs_write"]


# --- the rules every record follows ------------------------------------------------------

def test_no_absolute_paths_or_machine_names(demo):
    out, _ = demo
    raw = out.read_text(encoding="utf-8")
    assert ":\\" not in raw and ":/" not in raw
    assert Path.home().name.lower() not in raw.lower()
    for name in (os.environ.get("USERNAME"), os.environ.get("COMPUTERNAME")):
        if name:
            assert name.lower() not in raw.lower()


def test_no_file_contents_are_recorded(demo):
    out, _ = demo
    raw = out.read_text(encoding="utf-8")
    for contents in ("def greeting", "Hello from the sample project", "Project notes", "FAKE_BUILD_OUTPUT"):
        assert contents not in raw, contents


def test_generate_does_not_touch_environment_or_project_ledger(tmp_path):
    project_ledger = PROJECT_ROOT / ".papertrail" / "ledger.jsonl"
    before = project_ledger.read_bytes() if project_ledger.exists() else None
    env_before = dict(os.environ)

    generate(out_path=tmp_path / "ledger.jsonl")

    assert dict(os.environ) == env_before
    # Hooks may append unrelated tool records while the suite runs, so only
    # require that no entry of a demo session reached the project ledger.
    if project_ledger.exists():
        sids = {e["session_id"] for e in ledger_mod.read(project_ledger)}
        assert not sids & {SESSION_A, SESSION_B, SESSION_C}
    else:
        assert before is None


def test_two_runs_say_the_same_thing(tmp_path):
    generate(out_path=tmp_path / "one.jsonl")
    generate(out_path=tmp_path / "two.jsonl")
    assert _shape(ledger_mod.read(tmp_path / "one.jsonl")) == _shape(ledger_mod.read(tmp_path / "two.jsonl"))


# --- the committed demo -----------------------------------------------------------------

def test_the_committed_demo_ledger_is_current(tmp_path):
    """If this fails, run: python sample/make_demo_ledger.py"""
    assert COMMITTED.exists()
    assert ledger_mod.verify_chain(COMMITTED) == (True, None)
    generate(out_path=tmp_path / "fresh.jsonl")
    assert _shape(ledger_mod.read(COMMITTED)) == _shape(ledger_mod.read(tmp_path / "fresh.jsonl"))


def test_the_committed_demo_ledger_is_utf8_without_a_byte_order_mark():
    assert not COMMITTED.read_bytes().startswith(b"\xef\xbb\xbf")
    json.loads(COMMITTED.read_text(encoding="utf-8").splitlines()[0])
