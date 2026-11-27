"""Tests for papertrail.outcome: NO_STATEMENT and "what does this session say?"."""

import json
from pathlib import Path

import pytest

from papertrail import ledger, outcome
from papertrail.session import on_start, on_stop

HOME = Path.home()


def _lp(root: Path) -> Path:
    return root / ".papertrail" / "ledger.jsonl"


def _statement(root: Path, **lists) -> None:
    body = {
        "summary": "Did some work.",
        "files_read": [], "files_created": [], "files_modified": [], "files_deleted": [],
        **lists,
    }
    path = root / ".papertrail" / "statement.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def _write(root: Path, name: str) -> None:
    (root / name).write_text("x", encoding="utf-8")


# --- session ids ------------------------------------------------------------

@pytest.mark.parametrize("good", ["a", "demo-session-b", "S_1.2", "0abc", "x" * 200])
def test_valid_ids(good):
    assert outcome.valid_session_id(good)


@pytest.mark.parametrize("bad", ["", ".hidden", "-x", "_x", "a/b", "a\\b", "a b", "a..b", "..", "a\n", "é", "a:b"])
def test_unsafe_ids(bad):
    assert not outcome.valid_session_id(bad)


# --- small helpers ----------------------------------------------------------

def test_undeclared_from_diff_orders_created_modified_deleted():
    diff = {"deleted": ["d1", "d2"], "created": ["c1"], "modified": ["m1"]}
    assert outcome.undeclared_from_diff(diff) == [
        {"path": "c1", "change": "created"},
        {"path": "m1", "change": "modified"},
        {"path": "d1", "change": "deleted"},
        {"path": "d2", "change": "deleted"},
    ]


def test_undeclared_from_diff_of_nothing_is_empty():
    assert outcome.undeclared_from_diff({"created": [], "modified": [], "deleted": []}) == []
    assert outcome.undeclared_from_diff({}) == []


def _overall(sid: str, verdict: str, seq: int, undeclared=None) -> dict:
    return {
        "seq": seq, "session_id": sid, "kind": "verdict",
        "data": {"kind_detail": "statement_overall", "verdict": verdict,
                 "witness_seq": seq, "undeclared": undeclared or []},
    }


def test_last_overall_and_latest_no_statement_pick_the_newest_of_that_session():
    entries = [
        _overall("a", "SUPPORTED", 1),
        _overall("b", outcome.NO_STATEMENT, 2),
        _overall("a", outcome.NO_STATEMENT, 3, [{"path": "x", "change": "created"}]),
        _overall("a", "CONTRADICTED", 4),
        {"seq": 5, "session_id": "a", "kind": "verdict", "data": {"path": "p", "verdict": "SUPPORTED"}},
    ]
    assert outcome.last_overall(entries, "a")["seq"] == 4          # a per-path verdict is not "overall"
    assert outcome.latest_no_statement(entries, "a")["seq"] == 3
    assert outcome.latest_no_statement(entries, "b")["seq"] == 2
    assert outcome.latest_no_statement(entries, "nobody") is None
    assert outcome.last_overall([], "a") is None


def test_no_statement_result_has_the_verifier_shape_and_copies_the_list():
    items = [{"path": "x", "change": "created"}]
    result = outcome.no_statement_result(_overall("a", outcome.NO_STATEMENT, 3, items))
    assert result == {"verdicts": [], "undeclared": items, "overall": "NO_STATEMENT"}
    result["undeclared"].append({"path": "y", "change": "deleted"})
    assert len(items) == 1


# --- statement files --------------------------------------------------------

def test_statement_files_are_numbered_not_sorted_as_text(tmp_path):
    folder = tmp_path / ".papertrail" / "statements"
    folder.mkdir(parents=True)
    for n in (1, 2, 10):
        (folder / f"s-{n}.json").write_text("{}", encoding="utf-8")
    assert [n for n, _ in outcome.statement_files(tmp_path, "s")] == [1, 2, 10]


def test_statement_files_do_not_mix_up_sessions_whose_ids_share_a_prefix(tmp_path):
    folder = tmp_path / ".papertrail" / "statements"
    folder.mkdir(parents=True)
    (folder / "demo-1.json").write_text("{}", encoding="utf-8")
    (folder / "demo-x-1.json").write_text("{}", encoding="utf-8")
    (folder / "demo-x-2.json").write_text("{}", encoding="utf-8")
    assert [n for n, _ in outcome.statement_files(tmp_path, "demo")] == [1]
    assert [n for n, _ in outcome.statement_files(tmp_path, "demo-x")] == [1, 2]


def test_statement_files_of_an_unsafe_id_or_a_missing_folder_is_empty(tmp_path):
    assert outcome.statement_files(tmp_path, "s") == []
    assert outcome.statement_files(tmp_path, "../s") == []


# --- result_for -------------------------------------------------------------

def test_a_session_with_nothing_has_no_result(tmp_path):
    assert outcome.result_for(tmp_path, "nobody") is None
    assert outcome.result_for(tmp_path, "nobody", 1) is None


def test_unsafe_id_has_no_result(tmp_path):
    assert outcome.result_for(tmp_path, "..\\x") is None
    assert outcome.result_for(tmp_path, "../x", 1) is None


def test_a_silent_session_reports_no_statement(tmp_path):
    on_start({"session_id": "s"}, tmp_path, HOME)
    _write(tmp_path, "new.txt")
    on_stop({"session_id": "s"}, tmp_path, HOME)
    count = len(ledger.read(_lp(tmp_path)))

    result = outcome.result_for(tmp_path, "s")
    assert result == {
        "verdicts": [],
        "undeclared": [{"path": "new.txt", "change": "created"}],
        "overall": "NO_STATEMENT",
    }
    assert len(ledger.read(_lp(tmp_path))) == count  # reading it writes nothing
    assert outcome.result_for(tmp_path, "s", 1) is None  # there is no statement number 1


def test_the_newer_of_a_statement_and_a_silent_stop_wins(tmp_path):
    sid = {"session_id": "s"}
    on_start(sid, tmp_path, HOME)

    _write(tmp_path, "a.txt")
    _statement(tmp_path, files_created=["a.txt"])
    on_stop(sid, tmp_path, HOME)                       # statement 1, newest so far
    assert outcome.result_for(tmp_path, "s")["overall"] == "SUPPORTED"

    _write(tmp_path, "b.txt")
    on_stop(sid, tmp_path, HOME)                       # silent stop: b.txt, from statement 1's stop
    newest = outcome.result_for(tmp_path, "s")
    assert newest["overall"] == "NO_STATEMENT"
    assert newest["undeclared"] == [{"path": "b.txt", "change": "created"}]

    # An explicit number still means that statement, even though a silent stop is newer.
    assert outcome.result_for(tmp_path, "s", 1)["overall"] == "SUPPORTED"

    _write(tmp_path, "c.txt")
    # A statement covers what changed since the previous statement's stop: b and c.
    _statement(tmp_path, files_created=["b.txt", "c.txt"])
    on_stop(sid, tmp_path, HOME)                       # statement 2 is newer again
    again = outcome.result_for(tmp_path, "s")
    assert again["overall"] == "SUPPORTED" and again["undeclared"] == []


def test_checking_a_statement_is_idempotent(tmp_path):
    sid = {"session_id": "s"}
    on_start(sid, tmp_path, HOME)
    _write(tmp_path, "a.txt")
    _statement(tmp_path, files_created=["a.txt"])
    on_stop(sid, tmp_path, HOME)

    first = outcome.result_for(tmp_path, "s", 1)
    count = len(ledger.read(_lp(tmp_path)))
    assert outcome.result_for(tmp_path, "s", 1) == first
    assert outcome.result_for(tmp_path, "s") == first
    assert len(ledger.read(_lp(tmp_path))) == count


def test_an_unreadable_statement_raises_value_error(tmp_path):
    folder = tmp_path / ".papertrail" / "statements"
    folder.mkdir(parents=True)
    (folder / "s-1.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError):
        outcome.result_for(tmp_path, "s", 1)
    with pytest.raises(ValueError):
        outcome.result_for(tmp_path, "s")


def test_result_for_never_needs_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("PAPERTRAIL_ROOT", raising=False)
    on_start({"session_id": "s"}, tmp_path, HOME)
    _write(tmp_path, "n.txt")
    on_stop({"session_id": "s"}, tmp_path, HOME)
    assert outcome.result_for(tmp_path, "s")["overall"] == "NO_STATEMENT"
