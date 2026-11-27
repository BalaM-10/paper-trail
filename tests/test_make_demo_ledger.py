"""Tests for sample/make_demo_ledger.py (structure and verdicts only)."""

import os
from pathlib import Path

import pytest

from papertrail import ledger as ledger_mod
from sample.make_demo_ledger import SESSION_A, SESSION_B, generate

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def demo(tmp_path):
    out = tmp_path / "ledger.jsonl"
    generate(out_path=out)
    return out, ledger_mod.read(out)


def _overall(entries, sid):
    return next(
        e for e in entries
        if e["session_id"] == sid
        and e["kind"] == "verdict"
        and e["data"].get("kind_detail") == "statement_overall"
    )


def test_chain_is_intact(demo):
    out, _ = demo
    assert ledger_mod.verify_chain(out) == (True, None)


def test_two_sessions_each_with_required_kinds(demo):
    _, entries = demo
    sids = list(dict.fromkeys(e["session_id"] for e in entries))
    assert sids == [SESSION_A, SESSION_B]
    for sid in sids:
        kinds = {e["kind"] for e in entries if e["session_id"] == sid}
        assert kinds >= {"witness", "tool", "statement", "verdict"}


def test_overall_verdicts(demo):
    _, entries = demo
    assert _overall(entries, SESSION_A)["data"]["verdict"] == "SUPPORTED"
    assert _overall(entries, SESSION_B)["data"]["verdict"] == "CONTRADICTED"


def test_session_a_read_claim_is_supported_by_a_tool_entry(demo):
    _, entries = demo
    tools = [e for e in entries if e["session_id"] == SESSION_A and e["kind"] == "tool"]
    assert any(e["data"]["tool_name"] == "read_file" for e in tools)
    read_verdict = next(
        e for e in entries
        if e["session_id"] == SESSION_A
        and e["kind"] == "verdict"
        and e["data"].get("claim") == "files_read"
    )
    assert read_verdict["data"]["verdict"] == "SUPPORTED"


def test_session_b_undeclared_notes_file(demo):
    _, entries = demo
    undeclared = _overall(entries, SESSION_B)["data"]["undeclared"]
    assert {"path": "sample/notes.txt", "change": "deleted"} in undeclared


def test_overall_verdict_is_last_entry_of_each_session(demo):
    _, entries = demo
    for sid in (SESSION_A, SESSION_B):
        session = [e for e in entries if e["session_id"] == sid]
        assert session[-1]["kind"] == "verdict"
        assert session[-1]["data"].get("kind_detail") == "statement_overall"


def test_no_absolute_paths_or_machine_names(demo):
    out, _ = demo
    raw = out.read_text(encoding="utf-8")
    assert ":\\" not in raw and ":/" not in raw
    assert Path.home().name.lower() not in raw.lower()
    for name in (os.environ.get("USERNAME"), os.environ.get("COMPUTERNAME")):
        if name:
            assert name.lower() not in raw.lower()


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
        assert SESSION_A not in sids and SESSION_B not in sids
    else:
        assert before is None
