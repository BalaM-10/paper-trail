"""Tests for sample/run_cases.py: seven cases, the README table, and no contact with the project record."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from sample import run_cases

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _fingerprint_of_project_record() -> str | None:
    path = ROOT / ".papertrail" / "ledger.jsonl"
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def test_there_are_seven_cases_named_a_to_g():
    assert [c.letter for c in run_cases.CASES] == list("abcdefg")


@pytest.mark.parametrize("case", run_cases.CASES, ids=lambda c: c.letter)
def test_every_case_gives_the_expected_result(case):
    result = run_cases.run_case(case)
    assert result.actual == result.expected, result.story
    assert result.passed


def test_the_expected_results_say_what_each_case_is_about():
    expected = {c.letter: c.expected for c in run_cases.CASES}
    assert expected["a"] == "SUPPORTED"
    assert expected["b"].startswith("CONTRADICTED") and "undeclared" in expected["b"]
    assert expected["c"].startswith("CONTRADICTED") and "contradicted claim" in expected["c"]
    assert expected["d"].startswith("NO_STATEMENT")
    assert "between turns" in expected["e"] and expected["e"].startswith("SUPPORTED")
    assert expected["f"].startswith("Paper torn")
    assert "setup changed" in expected["g"]


def test_running_the_cases_never_touches_the_project_record_or_the_environment():
    before = (_fingerprint_of_project_record(), dict(os.environ))
    run_cases.run_all()
    assert (_fingerprint_of_project_record(), dict(os.environ)) == before


def test_the_script_prints_expected_actual_and_pass_for_each_case(capsys):
    assert run_cases.main([]) == 0
    out = capsys.readouterr().out
    assert out.count("expected:") == 7 and out.count("actual:") == 7
    assert out.count("result:   PASS") == 7
    assert "7 of 7 cases passed." in out


def test_the_exit_status_is_one_when_a_case_fails(monkeypatch, capsys):
    bad = run_cases.Case("z", "Broken", "x", "SUPPORTED", lambda root, sid: "CONTRADICTED")
    monkeypatch.setattr(run_cases, "CASES", (bad,))
    assert run_cases.main([]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_the_table_has_a_row_per_case_and_no_path_of_this_machine():
    table = run_cases.table(run_cases.run_all())
    assert len(table.splitlines()) == 2 + 7
    assert str(Path.home()) not in table and "Temp" not in table


def test_the_readme_table_is_up_to_date():
    """If this fails, run: python sample/run_cases.py --write-readme"""
    text = README.read_bytes().decode("utf-8")
    block = run_cases.readme_block(text)
    assert block is not None, "README.md must hold the two marker comments"
    assert block == run_cases.table(run_cases.run_all())


def test_a_stale_readme_table_is_noticed(tmp_path):
    text = README.read_bytes().decode("utf-8")
    stale = text.replace("| pass |", "| FAIL |", 1)
    assert run_cases.readme_block(stale) != run_cases.table(run_cases.run_all())


def test_the_readme_markers_come_once_each_in_order():
    text = README.read_text(encoding="utf-8")
    assert text.count(run_cases.START_MARK) == 1 and text.count(run_cases.END_MARK) == 1
    assert text.index(run_cases.START_MARK) < text.index(run_cases.END_MARK)


def test_update_readme_rewrites_only_between_the_markers(tmp_path):
    copy = tmp_path / "README.md"
    copy.write_bytes(b"top\n" + run_cases.START_MARK.encode() + b"\nold\n" + run_cases.END_MARK.encode() + b"\nbottom\n")
    assert run_cases.update_readme(run_cases.run_all(), copy) is True
    text = copy.read_bytes().decode("utf-8")
    assert text.startswith("top\n") and text.endswith("\nbottom\n") and "old" not in text
    assert run_cases.update_readme(run_cases.run_all(), copy) is False  # a second time changes nothing
    assert not copy.read_bytes().startswith(b"\xef\xbb\xbf")


def test_the_cases_leave_no_temporary_folder_behind():
    import tempfile
    seen: list[str] = []
    real = tempfile.TemporaryDirectory

    class Spy(real):  # type: ignore[misc, valid-type]
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            seen.append(self.name)

    run_cases.tempfile.TemporaryDirectory = Spy
    try:
        run_cases.run_all()
    finally:
        run_cases.tempfile.TemporaryDirectory = real
    assert len(seen) == 7 and not any(Path(p).exists() for p in seen)