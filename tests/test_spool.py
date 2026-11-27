"""Tests for papertrail/spool.py and `python -m papertrail print`."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from papertrail import ledger, spool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((PROJECT_ROOT / "tests" / "fixtures" / "sentences.json").read_text(encoding="utf-8"))
DEMO = PROJECT_ROOT / "web" / "public" / "demo" / "ledger.jsonl"


def _project(tmp_path: Path) -> Path:
    """A project folder holding a copy of the demo record (four sessions)."""
    (tmp_path / ".papertrail").mkdir()
    shutil.copyfile(DEMO, tmp_path / ".papertrail" / "ledger.jsonl")
    return tmp_path


def _lines(text: str) -> list[str]:
    return text.split("\n")[:-1]


# ---------------------------------------------------------------------------
# Contract shared with the screen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", FIXTURE["sentences"], ids=lambda c: c["name"])
def test_sentences_match_the_shared_fixture(case):
    entry = {"seq": 1, "session_id": "s", **case["entry"]}
    assert spool.entry_text(entry) == case["text"]


@pytest.mark.parametrize("case", FIXTURE["verdictWords"], ids=lambda c: c["verdict"])
def test_verdict_words(case):
    assert spool.verdict_word(case["verdict"]) == case["word"]


@pytest.mark.parametrize("case", FIXTURE["fingerprints"], ids=lambda c: c["name"])
def test_fingerprint_line(case):
    assert spool.fingerprint_line(case["entries"]) == case["text"]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def test_no_line_is_longer_than_80_columns(tmp_path):
    root = _project(tmp_path)
    for sid in ("demo-session-a", "demo-session-b", "demo-session-c"):
        for line in _lines(spool.render_session(root, sid)):
            assert len(line) <= 80


def test_long_paths_and_long_session_ids_still_fit():
    long_path = "dir/" * 50 + "file.txt"
    sid = "s" * 150
    entries = [
        {"seq": 1, "session_id": sid, "kind": "tool", "hash": "a" * 64,
         "data": {"tool_name": "fs_write", "tool_input": {"path": long_path}}},
    ]
    text = spool.render(entries, sid, (True, None))
    assert all(len(line) <= 80 for line in _lines(text))
    assert long_path.replace("/", "") in text.replace("\n", "").replace(" ", "").replace("/", "")


def test_header_lines(tmp_path):
    root = _project(tmp_path)
    lines = _lines(spool.render_session(root, "demo-session-b"))
    assert lines[0] == "PAPER TRAIL - evidence report"
    assert lines[1] == "Session: demo-session-b"
    assert lines[2].startswith("Statement: ")
    assert lines[3] == "Paper intact"
    assert lines[4] == "-" * 80


def test_line_numbers_match_the_record_and_bangs_come_before_the_overall_line(tmp_path):
    root = _project(tmp_path)
    text = spool.render_session(root, "demo-session-b")
    body = [l for l in _lines(text) if re.match(r"^\s*(\d+|!)  \S", l)]
    numbers = [l.split()[0] for l in body]
    assert numbers[0] == "9"
    assert "!" in numbers
    assert numbers.index("!") == len(numbers) - 2
    assert numbers[-1] == "14"
    assert numbers[: numbers.index("!")] == [str(n) for n in range(9, 14)]


def test_session_b_prints_the_expected_sentences(tmp_path):
    root = _project(tmp_path)
    text = spool.render_session(root, "demo-session-b")
    assert "12  Agent stated: Cleared the build cache." in text
    assert "SUPPORTED: Agent said it deleted sample/cache/output.bin." in text
    assert "!  Witness saw sample/notes.txt deleted. The agent never mentioned it." in text
    assert "Overall: the statement does not match the evidence. (CONTRADICTED)" in text


def test_session_c_has_no_statement(tmp_path):
    root = _project(tmp_path)
    text = spool.render_session(root, "demo-session-c")
    assert "Statement: none written" in text
    assert "Overall: the agent changed files and said nothing. (NO STATEMENT)" in text
    assert "NO_STATEMENT" not in text
    assert "The agent never mentioned it." in text


def test_last_line_is_the_final_fingerprint_and_count(tmp_path):
    root = _project(tmp_path)
    entries = ledger.read(root / ".papertrail" / "ledger.jsonl")
    assert len(entries) == 34
    for sid in ("demo-session-a", "demo-session-c"):
        last = _lines(spool.render_session(root, sid))[-1]
        assert last == f"{entries[-1]['hash']} (34 lines)"


def test_a_tampered_record_shows_where_the_paper_tore(tmp_path):
    root = _project(tmp_path)
    path = root / ".papertrail" / "ledger.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    rows[1]["data"]["tool_input"]["command"] = "something else"
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    ok, at = ledger.verify_chain(path)
    assert not ok
    text = spool.render_session(root, "demo-session-a")
    assert f"Paper torn at line {at}" in text
    assert "Paper intact" not in text


def test_the_number_column_widens_for_big_line_numbers():
    sid = "s"
    entries = [
        {"seq": 1000 + i, "session_id": sid, "kind": "tool", "hash": "b" * 64,
         "data": {"tool_name": "read_file", "tool_input": {"path": f"f{i}.py"}}}
        for i in range(3)
    ]
    text = spool.render(entries, sid, (True, None))
    assert "1000  Agent read f0.py." in text
    assert "1002  Agent read f2.py." in text
    assert all(len(l) <= 80 for l in _lines(text))


def test_a_non_ascii_path_is_kept():
    sid = "s"
    entries = [
        {"seq": 1, "session_id": sid, "kind": "tool", "hash": "c" * 64,
         "data": {"tool_name": "fs_write", "tool_input": {"path": "docs/caf\u00e9-\u65e5\u672c.md"}}},
    ]
    assert "Agent wrote docs/caf\u00e9-\u65e5\u672c.md." in spool.render(entries, sid, (True, None))


# ---------------------------------------------------------------------------
# Writing the file
# ---------------------------------------------------------------------------

def test_write_makes_the_spool_file(tmp_path):
    root = _project(tmp_path)
    before = (root / ".papertrail" / "ledger.jsonl").read_bytes()
    path = spool.write(root, "demo-session-b")
    assert path == root / ".papertrail" / "spool" / "demo-session-b.txt"
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert raw.decode("utf-8") == spool.render_session(root, "demo-session-b")
    assert (root / ".papertrail" / "ledger.jsonl").read_bytes() == before


def test_write_overwrites(tmp_path):
    root = _project(tmp_path)
    path = spool.write(root, "demo-session-a")
    path.write_text("old", encoding="utf-8")
    spool.write(root, "demo-session-a")
    assert path.read_text(encoding="utf-8").startswith("PAPER TRAIL")


@pytest.mark.parametrize("bad", ["nope", "../evil", "a/b", "", "..", "x\\y"])
def test_unknown_or_unsafe_ids_raise_and_write_nothing(tmp_path, bad):
    root = _project(tmp_path)
    with pytest.raises(LookupError):
        spool.write(root, bad)
    assert not (root / ".papertrail" / "spool").exists()
    assert not (root / "evil.txt").exists()


def test_the_text_has_no_absolute_paths_or_machine_names(tmp_path):
    root = _project(tmp_path)
    text = spool.render_session(root, "demo-session-b")
    assert str(root) not in text
    assert not re.search(r"[A-Za-z]:\\|/Users/|/home/", text)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def _cli(args: list[str], root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PAPERTRAIL_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, "-m", "papertrail", *args],
        capture_output=True, text=True, env=env, cwd=str(PROJECT_ROOT),
    )


def test_cli_print_writes_the_file(tmp_path):
    root = _project(tmp_path)
    r = _cli(["print", "demo-session-c"], root)
    assert r.returncode == 0
    assert r.stdout.strip() == "Wrote .papertrail/spool/demo-session-c.txt"
    assert (root / ".papertrail" / "spool" / "demo-session-c.txt").is_file()


@pytest.mark.parametrize("bad", ["nope", "../evil"])
def test_cli_print_unknown_or_unsafe_id_fails(tmp_path, bad):
    root = _project(tmp_path)
    r = _cli(["print", bad], root)
    assert r.returncode == 1
    assert not (root / ".papertrail" / "spool").exists()


def test_cli_print_without_arguments_shows_usage(tmp_path):
    root = _project(tmp_path)
    r = _cli(["print"], root)
    assert r.returncode == 1
    assert "Usage: python -m papertrail print <session_id>" in r.stderr


# ---------------------------------------------------------------------------
# One roll per turn (paper-trail-turns R2.8, R2.9)
# ---------------------------------------------------------------------------

def test_a_session_with_two_turns_prints_two_reports_separated_by_a_tear_line(tmp_path):
    root = _project(tmp_path)
    lines = _lines(spool.render_session(root, "demo-session-d"))
    assert lines.count("PAPER TRAIL - evidence report") == 2
    assert lines.count(spool.TEAR) == 1
    first, second = "\n".join(lines).split(spool.TEAR + "\n")
    assert "Turn: 1 of 2\nStatement: Wrote the plan.\nPaper intact" in first
    assert "Turn: 2 of 2\nStatement: Cleared two drafts.\nPaper intact" in second
    assert "Session: demo-session-d" in first and "Session: demo-session-d" in second
    assert all(len(line) <= 80 for line in lines)


def test_each_roll_has_its_own_lines_with_the_real_line_numbers(tmp_path):
    root = _project(tmp_path)
    text = spool.render_session(root, "demo-session-d")
    first, second = text.split(spool.TEAR + "\n")

    def numbers(block):
        return [int(m.group(1)) for m in re.finditer(r"^\s*(\d+)  \S", block, re.M)]

    assert numbers(first) == list(range(20, 27))
    assert numbers(second) == list(range(27, 35))
    assert " 28  Between turns, outside the agent: deleted drafts/old-a.txt," in second  # wraps at 80 columns
    assert "Between turns, outside the agent: deleted drafts/old-a.txt, drafts/old-b.txt." in " ".join(second.split())
    assert "Between turns" not in first
    assert "!" not in re.findall(r"^\s*(!)  ", text, re.M)  # nothing of the agent's was left out


def test_the_between_turns_line_is_plain_and_has_no_verdict_word(tmp_path):
    root = _project(tmp_path)
    second = spool.render_session(root, "demo-session-d").split(spool.TEAR + "\n")[1]
    (line,) = [l for l in _lines(second) if "Between turns" in l]
    assert not re.search(r"SUPPORTED|CONTRADICTED|UNVERIFIED|NO STATEMENT", line)


def test_only_the_last_line_is_the_fingerprint_of_the_whole_record(tmp_path):
    root = _project(tmp_path)
    text = spool.render_session(root, "demo-session-d")
    entries = ledger.read(root / ".papertrail" / "ledger.jsonl")
    assert text.count("Fingerprint of the record:") == 1
    assert _lines(text)[-1] == f"{entries[-1]['hash']} (34 lines)"


def test_a_session_with_one_roll_prints_as_it_always_did(tmp_path):
    root = _project(tmp_path)
    text = spool.render_session(root, "demo-session-b")
    assert "Turn:" not in text and spool.TEAR not in text
    assert text.count("PAPER TRAIL - evidence report") == 1


def test_a_torn_record_says_so_in_every_roll(tmp_path):
    root = _project(tmp_path)
    path = root / ".papertrail" / "ledger.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    rows[21]["data"]["tool_input"]["path"] = "drafts/other.md"
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    text = spool.render_session(root, "demo-session-d")
    assert text.count("Paper torn at line") == 2
    assert "Paper intact" not in text