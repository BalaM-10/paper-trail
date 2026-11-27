"""Tests for papertrail/rolls.py (paper-trail-turns R2.1 to R2.4)."""

import json
from pathlib import Path

import pytest

from papertrail import rolls

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "rolls.json").read_text(encoding="utf-8"))
DEMO = ROOT / "web" / "public" / "demo" / "ledger.jsonl"


def _records(case: dict) -> list[dict]:
    return [{"ts": "2026-03-04T10:00:00Z", "prev_hash": "", "hash": "", **e} for e in case["entries"]]


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: c["name"])
def test_the_shared_fixture(case):
    got = [
        {
            "sessionId": r.session_id,
            "number": r.number,
            "count": r.count,
            "turnStart": r.turn_start,
            "seqs": [e["seq"] for e in r.entries],
            "title": r.title,
            "overall": r.overall,
            "statementNumber": r.statement_number,
            "hasUnverifiedStatement": r.has_unverified_statement,
        }
        for r in rolls.split(_records(case))
    ]
    assert got == case["rolls"]


def test_the_date_is_the_date_of_the_first_record():
    (roll,) = rolls.split([{"seq": 1, "session_id": "s", "kind": "tool", "data": {}, "ts": "2026-03-04T23:59:59Z"}])
    assert roll.date == "2026-03-04"
    assert (roll.first_seq, roll.last_seq) == (1, 1)


def test_every_record_is_in_exactly_one_roll_and_in_order():
    for case in FIXTURE["cases"]:
        records = _records(case)
        seqs = [e["seq"] for r in rolls.split(records) for e in r.entries]
        assert sorted(seqs) == sorted(e["seq"] for e in records)
        assert len(seqs) == len(set(seqs))
        for r in rolls.split(records):
            assert [e["seq"] for e in r.entries] == sorted(e["seq"] for e in r.entries)


def test_nothing_is_renumbered():
    records = _records(FIXTURE["cases"][3])
    originals = {e["seq"]: e for e in records}
    for r in rolls.split(records):
        for e in r.entries:
            assert e is originals[e["seq"]]  # the real record, not a copy with a new line number


def test_an_empty_record_has_no_rolls():
    assert rolls.split([]) == []
    assert rolls.split_session([]) == []


def test_the_demo_record_has_the_turn_session():
    entries = [json.loads(line) for line in DEMO.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_session = {}
    for r in rolls.split(entries):
        by_session.setdefault(r.session_id, []).append(r)
    assert [len(v) for v in by_session.values()] == [1, 1, 1, 2, 1]
    d1, d2 = by_session["demo-session-d"]
    assert (d1.number, d2.number, d2.count) == (1, 2, 2)
    assert d1.overall == d2.overall == "SUPPORTED"
    assert [e["data"].get("event") for e in d2.entries if e["kind"] == "witness"] == ["turn", "between_turns", "stop"]
