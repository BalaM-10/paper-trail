"""Turns: what changes between two replies is not the agent's (paper-trail-turns R1)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from papertrail import ledger
from papertrail.session import on_start, on_stop, on_turn_start

ROOT = Path(__file__).resolve().parents[1]
SID = "sess-turns"
PAYLOAD = {"session_id": SID}


def _lp(root: Path) -> Path:
    return root / ".papertrail" / "ledger.jsonl"


def _entries(root: Path) -> list[dict]:
    return ledger.read(_lp(root))


def _witness(root: Path, event: str) -> list[dict]:
    return [e for e in _entries(root) if e["kind"] == "witness" and e["data"].get("event") == event]


def _overalls(root: Path) -> list[dict]:
    return [
        e for e in _entries(root)
        if e["kind"] == "verdict" and e["data"].get("kind_detail") == "statement_overall"
    ]


def _write_statement(root: Path, **lists) -> None:
    stmt = {"summary": "Did some work.", "files_read": [], "files_created": [], "files_modified": [],
            "files_deleted": [], **lists}
    path = root / ".papertrail" / "statement.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stmt), encoding="utf-8")


def _put(root: Path, *names: str) -> None:
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(name, encoding="utf-8")


def _remove(root: Path, *names: str) -> None:
    for name in names:
        (root / name).unlink()


# ---------------------------------------------------------------------------
# AC1.7: the case that was reported
# ---------------------------------------------------------------------------

def _two_turns(root: Path, with_turn_hook: bool) -> None:
    """A person deletes two files between two replies; the agent then deletes two others and says so."""
    _put(root, "keep.txt", "person-1.txt", "person-2.txt", "agent-1.txt", "agent-2.txt")
    on_start(PAYLOAD, root, Path.home())
    if with_turn_hook:
        on_turn_start(PAYLOAD, root, Path.home())
    _put(root, "made.txt")
    _write_statement(root, files_created=["made.txt"])
    on_stop(PAYLOAD, root, Path.home())

    _remove(root, "person-1.txt", "person-2.txt")  # the person, between the replies
    if with_turn_hook:
        on_turn_start(PAYLOAD, root, Path.home())
    _remove(root, "agent-1.txt", "agent-2.txt")  # the agent
    _write_statement(root, files_deleted=["agent-1.txt", "agent-2.txt"])
    on_stop(PAYLOAD, root, Path.home())


def test_what_the_person_deleted_between_turns_is_not_blamed_on_the_agent(tmp_path):
    _two_turns(tmp_path, with_turn_hook=True)
    first, second = _overalls(tmp_path)
    assert first["data"]["verdict"] == "SUPPORTED"
    assert second["data"]["verdict"] == "SUPPORTED"
    assert second["data"]["undeclared"] == []
    stop = _witness(tmp_path, "stop")[-1]
    assert stop["data"]["diff"]["deleted"] == ["agent-1.txt", "agent-2.txt"]
    assert stop["data"]["baseline"].startswith("turn:")
    # the two files the person deleted are on record, as their own neutral entry
    (between,) = _witness(tmp_path, "between_turns")
    assert between["data"]["diff"] == {"created": [], "modified": [], "deleted": ["person-1.txt", "person-2.txt"]}
    assert between["data"]["unfinished"] is False
    assert ledger.verify_chain(_lp(tmp_path)) == (True, None)


def test_control_without_the_turn_hook_the_same_steps_blame_the_agent(tmp_path):
    """Today's behaviour, which this spec fixes: the stop compares with the previous stop."""
    _two_turns(tmp_path, with_turn_hook=False)
    second = _overalls(tmp_path)[-1]
    assert second["data"]["verdict"] == "CONTRADICTED"
    assert second["data"]["undeclared"] == [
        {"path": "person-1.txt", "change": "deleted"},
        {"path": "person-2.txt", "change": "deleted"},
    ]
    assert not _witness(tmp_path, "between_turns")


def test_the_between_turns_record_points_at_the_lines_it_compares(tmp_path):
    _two_turns(tmp_path, with_turn_hook=True)
    (between,) = _witness(tmp_path, "between_turns")
    stops = _witness(tmp_path, "stop")
    turns = _witness(tmp_path, "turn")
    assert between["data"]["baseline"] == f"stop:{stops[0]['seq']}"
    assert between["data"]["witness_seq"] == turns[1]["seq"]
    assert between["data"]["evidence_seq"] == [stops[0]["seq"], turns[1]["seq"]]
    assert between["seq"] == turns[1]["seq"] + 1  # the turn record first, then what changed before it


def test_nothing_changed_between_turns_records_nothing_extra(tmp_path):
    _put(tmp_path, "a.txt")
    on_start(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    on_stop(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    assert not _witness(tmp_path, "between_turns")
    assert len(_witness(tmp_path, "turn")) == 2


# ---------------------------------------------------------------------------
# AC1.4: where the comparison starts
# ---------------------------------------------------------------------------

def test_a_change_between_the_session_start_and_the_first_prompt_is_between_turns(tmp_path):
    _put(tmp_path, "a.txt", "b.txt")
    on_start(PAYLOAD, tmp_path, Path.home())
    _remove(tmp_path, "a.txt")
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    (between,) = _witness(tmp_path, "between_turns")
    assert between["data"]["baseline"].startswith("start:")
    assert between["data"]["diff"]["deleted"] == ["a.txt"]
    assert between["data"]["unfinished"] is False


def test_the_first_prompt_with_no_earlier_snapshot_has_no_between_turns_record(tmp_path):
    """SessionStart did not fire (it does not, on some builds): the turn start is the baseline."""
    _put(tmp_path, "a.txt")
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    assert not _witness(tmp_path, "between_turns")
    _put(tmp_path, "new.txt")
    _write_statement(tmp_path, files_created=["new.txt"])
    on_stop(PAYLOAD, tmp_path, Path.home())
    assert _overalls(tmp_path)[-1]["data"]["verdict"] == "SUPPORTED"  # there is a diff to check against
    assert _witness(tmp_path, "stop")[-1]["data"]["baseline"].startswith("turn:")


def test_a_turn_that_never_stopped_is_flagged_not_blamed_on_the_person(tmp_path):
    _put(tmp_path, "a.txt", "b.txt")
    on_start(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    _remove(tmp_path, "a.txt")  # whoever did this, there was no stop to say
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    (between,) = _witness(tmp_path, "between_turns")
    assert between["data"]["unfinished"] is True
    assert between["data"]["baseline"].startswith("turn:")


# ---------------------------------------------------------------------------
# AC1.5, AC1.6: the stop, the verdicts and NO_STATEMENT
# ---------------------------------------------------------------------------

def test_between_turns_changes_never_reach_a_no_statement_list(tmp_path):
    _put(tmp_path, "person.txt")
    on_start(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    on_stop(PAYLOAD, tmp_path, Path.home())
    _remove(tmp_path, "person.txt")
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    _put(tmp_path, "agent.txt")  # the agent changes a file and writes no statement
    on_stop(PAYLOAD, tmp_path, Path.home())
    (verdict,) = _overalls(tmp_path)
    assert verdict["data"]["verdict"] == "NO_STATEMENT"
    assert verdict["data"]["undeclared"] == [{"path": "agent.txt", "change": "created"}]


def test_a_turn_where_only_the_person_changed_files_is_not_a_no_statement(tmp_path):
    _put(tmp_path, "person.txt")
    on_start(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    on_stop(PAYLOAD, tmp_path, Path.home())
    _remove(tmp_path, "person.txt")
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    on_stop(PAYLOAD, tmp_path, Path.home())  # the agent only answered
    assert _overalls(tmp_path) == []


def test_the_same_change_in_two_turns_is_reported_in_both(tmp_path):
    """NO_STATEMENT compares with its own turn only, so a repeat in a later turn is not hidden."""
    on_start(PAYLOAD, tmp_path, Path.home())
    for _ in range(2):
        on_turn_start(PAYLOAD, tmp_path, Path.home())
        _put(tmp_path, "same.txt")
        on_stop(PAYLOAD, tmp_path, Path.home())
        _remove(tmp_path, "same.txt")  # the person tidies up
    verdicts = _overalls(tmp_path)
    assert [v["data"]["verdict"] for v in verdicts] == ["NO_STATEMENT", "NO_STATEMENT"]
    assert all(v["data"]["undeclared"] == [{"path": "same.txt", "change": "created"}] for v in verdicts)


def test_a_second_stop_in_one_turn_does_not_count_declared_work_again(tmp_path):
    on_start(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    _put(tmp_path, "a.txt")
    _write_statement(tmp_path, files_created=["a.txt"])
    on_stop(PAYLOAD, tmp_path, Path.home())
    on_stop(PAYLOAD, tmp_path, Path.home())  # Kiro stopped twice, with no new work
    assert [v["data"]["verdict"] for v in _overalls(tmp_path)] == ["SUPPORTED"]
    assert _witness(tmp_path, "stop")[-1]["data"]["baseline"].startswith("prev_stop_seq:")


def test_a_session_with_no_turn_start_works_as_it_always_did(tmp_path):
    _put(tmp_path, "a.txt")
    on_start(PAYLOAD, tmp_path, Path.home())
    _put(tmp_path, "b.txt")
    _write_statement(tmp_path, files_created=["b.txt"])
    on_stop(PAYLOAD, tmp_path, Path.home())
    assert _witness(tmp_path, "stop")[0]["data"]["baseline"] == "start"
    assert _overalls(tmp_path)[0]["data"]["verdict"] == "SUPPORTED"


def test_other_sessions_turns_are_not_mixed_in(tmp_path):
    other = {"session_id": "another-chat"}
    _put(tmp_path, "a.txt")
    on_start(PAYLOAD, tmp_path, Path.home())
    on_start(other, tmp_path, Path.home())
    on_turn_start(other, tmp_path, Path.home())
    _put(tmp_path, "b.txt")
    _write_statement(tmp_path, files_created=["b.txt"])
    on_stop(PAYLOAD, tmp_path, Path.home())  # PAYLOAD has no turn: it compares with its own start
    assert _witness(tmp_path, "stop")[-1]["data"]["baseline"] == "start"


# ---------------------------------------------------------------------------
# AC1.9: reads count for their own turn
# ---------------------------------------------------------------------------

def _tool_read(root: Path, path: str) -> None:
    ledger.append(_lp(root), SID, "tool", {"tool_name": "read_file", "tool_input": {"path": path}})


def test_a_read_in_an_earlier_turn_is_not_evidence_for_this_turn(tmp_path):
    _put(tmp_path, "x.py")
    on_start(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    _tool_read(tmp_path, "x.py")
    _write_statement(tmp_path, files_read=["x.py"])
    on_stop(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    _write_statement(tmp_path, files_read=["x.py"])  # claims a read it did not make in this turn
    on_stop(PAYLOAD, tmp_path, Path.home())
    first, second = _overalls(tmp_path)
    assert first["data"]["verdict"] == "SUPPORTED"
    assert second["data"]["verdict"] == "UNVERIFIED"


def test_a_read_in_this_turn_still_counts_and_cites_its_real_line(tmp_path):
    _put(tmp_path, "x.py")
    on_start(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    on_stop(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    _tool_read(tmp_path, "x.py")
    read_line = _entries(tmp_path)[-1]["seq"]
    _write_statement(tmp_path, files_read=["x.py"])
    on_stop(PAYLOAD, tmp_path, Path.home())
    per_claim = [e for e in _entries(tmp_path) if e["kind"] == "verdict" and e["data"].get("claim") == "files_read"]
    assert per_claim[-1]["data"]["evidence_seq"] == [read_line]
    assert _overalls(tmp_path)[-1]["data"]["verdict"] == "SUPPORTED"


# ---------------------------------------------------------------------------
# AC1.2, AC1.10: the hook script, the way Kiro runs it
# ---------------------------------------------------------------------------

HOOK = ROOT / ".kiro" / "hooks" / "witness.py"


def _run(root: Path, event: str, payload) -> subprocess.CompletedProcess:
    env = {**os.environ, "PAPERTRAIL_ROOT": str(root)}
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), event], input=stdin, capture_output=True, text=True,
                          env=env, cwd=str(ROOT), timeout=60)


def test_the_turn_hook_script_records_prints_nothing_and_exits_zero(tmp_path):
    _put(tmp_path, "a.txt")
    done = _run(tmp_path, "turn", {"session_id": SID, "hook_event_name": "UserPromptSubmit",
                                   "cwd": str(tmp_path), "prompt": "please read C:\\secret\\plan.txt for me"})
    assert done.returncode == 0
    assert done.stdout == "" and done.stderr == ""  # anything printed would reach the agent
    (turn,) = _witness(tmp_path, "turn")
    assert set(turn["data"]["snapshot"]) == {"a.txt"}
    # the prompt is stored nowhere
    everything = "".join(p.read_text(encoding="utf-8", errors="replace") for p in (tmp_path / ".papertrail").rglob("*") if p.is_file())
    assert "secret" not in everything and "please read" not in everything
    saved = json.loads((tmp_path / ".papertrail" / "payloads" / "session-turn.json").read_text(encoding="utf-8"))
    assert saved["prompt"].startswith("<not kept: ") and saved["session_id"] == SID


def test_the_hook_scripts_run_start_turn_and_stop_in_order(tmp_path):
    _put(tmp_path, "a.txt")
    assert _run(tmp_path, "start", PAYLOAD).returncode == 0
    assert _run(tmp_path, "turn", PAYLOAD).returncode == 0
    _put(tmp_path, "b.txt")
    assert _run(tmp_path, "stop", PAYLOAD).returncode == 0
    events = [e["data"]["event"] for e in _entries(tmp_path) if e["kind"] == "witness"]
    assert events == ["start", "turn", "stop"]
    assert _overalls(tmp_path)[-1]["data"]["verdict"] == "NO_STATEMENT"


def test_the_reported_case_through_the_hook_scripts(tmp_path):
    _put(tmp_path, "keep.txt", "person-1.txt", "person-2.txt", "agent-1.txt", "agent-2.txt")
    _run(tmp_path, "start", PAYLOAD)
    _run(tmp_path, "turn", PAYLOAD)
    _write_statement(tmp_path)
    _run(tmp_path, "stop", PAYLOAD)
    _remove(tmp_path, "person-1.txt", "person-2.txt")
    _run(tmp_path, "turn", PAYLOAD)
    _remove(tmp_path, "agent-1.txt", "agent-2.txt")
    _write_statement(tmp_path, files_deleted=["agent-1.txt", "agent-2.txt"])
    _run(tmp_path, "stop", PAYLOAD)
    assert _overalls(tmp_path)[-1]["data"]["verdict"] == "SUPPORTED"
    assert _overalls(tmp_path)[-1]["data"]["undeclared"] == []
    assert _witness(tmp_path, "between_turns")[0]["data"]["diff"]["deleted"] == ["person-1.txt", "person-2.txt"]


@pytest.mark.parametrize("event,stdin", [
    ("turn", "this is not json"),
    ("turn", ""),
    ("turn", "[1, 2]"),
    ("sleep", "{}"),
    ("", "{}"),
])
def test_the_hook_never_fails_and_never_prints(tmp_path, event, stdin):
    done = _run(tmp_path, event, stdin)
    assert done.returncode == 0
    assert done.stdout == ""


def test_an_unknown_event_is_an_error_record_not_a_stop(tmp_path):
    _put(tmp_path, "a.txt")
    assert _run(tmp_path, "sleep", PAYLOAD).returncode == 0
    entries = _entries(tmp_path)
    assert [e["kind"] for e in entries] == ["error"]
    assert "unknown event" in entries[0]["data"]["error"]
    assert not (tmp_path / ".papertrail" / "payloads").exists()


def test_the_turn_start_is_quick_with_20_changed_files(tmp_path):
    on_start(PAYLOAD, tmp_path, Path.home())
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    on_stop(PAYLOAD, tmp_path, Path.home())
    for i in range(20):
        _put(tmp_path, f"f{i}.txt")
    started = time.perf_counter()
    on_turn_start(PAYLOAD, tmp_path, Path.home())
    assert time.perf_counter() - started < 1.0
    assert len(_witness(tmp_path, "between_turns")[0]["data"]["diff"]["created"]) == 20


def test_the_record_with_turns_holds_no_path_or_name(tmp_path):
    from sample import export_build_record as export_mod

    _two_turns(tmp_path, with_turn_hook=True)
    lines = _lp(tmp_path).read_text(encoding="utf-8").splitlines()
    assert export_mod.scan(lines, {"someone-else": "the user name"}) == []
