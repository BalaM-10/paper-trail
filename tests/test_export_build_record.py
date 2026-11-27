"""Tests for sample/export_build_record.py (AC2.1a to AC2.1f)."""

import hashlib
import json
from pathlib import Path

import pytest

from papertrail import ledger
from sample import export_build_record as export_mod
from sample.export_build_record import export, identity_terms, main, scan

TERMS = {"alice": "the user name", "box-7": "the machine name"}


def _record(tmp_path: Path, rows: list[tuple[str, str, dict]]) -> Path:
    """A real, chained ledger from (session, kind, data) rows."""
    path = tmp_path / "source" / "ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    for session, kind, data in rows:
        ledger.append(path, session, kind, data)
    return path


CLEAN = [
    ("s1", "witness", {"event": "start", "snapshot": {"a.txt": {"size": 1, "sha256": "ab"}}}),
    ("s1", "tool", {"tool_name": "read_file", "tool_input": {"path": "src/main.py"}}),
    ("s1", "tool", {"tool_name": "execute_pwsh", "tool_input": {"command": "python -m pytest tests/ -q"}}),
    ("s1", "statement", {"summary": "Read a file."}),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# AC2.1a, AC2.1e: a clean record is copied unchanged
# ---------------------------------------------------------------------------

def test_a_clean_record_is_copied_byte_for_byte(tmp_path):
    source = _record(tmp_path, CLEAN)
    dest = tmp_path / "web" / "demo" / "build-ledger.jsonl"
    before = source.read_bytes()
    assert export(source, dest, TERMS) == ([], [])
    assert dest.read_bytes() == before
    assert _sha(dest) == _sha(source)
    assert ledger.verify_chain(dest) == (True, None)
    assert source.read_bytes() == before
    assert not list(dest.parent.glob("*.tmp"))


def test_running_it_twice_gives_the_same_file(tmp_path):
    source = _record(tmp_path, CLEAN)
    dest = tmp_path / "out" / "b.jsonl"
    export(source, dest, TERMS)
    first = dest.read_bytes()
    assert export(source, dest, TERMS) == ([], [])
    assert dest.read_bytes() == first


def test_it_works_with_windows_line_endings(tmp_path):
    source = _record(tmp_path, CLEAN)
    crlf = source.read_bytes().replace(b"\n", b"\r\n")
    source.write_bytes(crlf)
    dest = tmp_path / "b.jsonl"
    assert export(source, dest, TERMS) == ([], [])
    assert dest.read_bytes() == crlf


# ---------------------------------------------------------------------------
# AC2.1b: what it refuses
# ---------------------------------------------------------------------------

LEAKS = [
    ("a drive path", {"tool_input": {"command": "cd C:\\Program Files\\Thing"}}, "data.tool_input.command"),
    ("a drive path", {"tool_input": {"path": "d:/work/notes.txt"}}, "data.tool_input.path"),
    ("a drive path", {"cwd": "c:\\\\Work\\\\x"}, "data.cwd"),
    ("a network path", {"tool_input": {"path": "\\\\fileserver\\share\\x.txt"}}, "data.tool_input.path"),
    ("a path under a user or system folder", {"tool_input": {"path": "/Users/bob/x.txt"}}, "data.tool_input.path"),
    ("a path under a user or system folder", {"tool_input": {"command": "ls /home/bob"}}, "data.tool_input.command"),
    ("a path under a user or system folder", {"tool_input": {"command": "cat /var/log/syslog"}}, "data.tool_input.command"),
    ("a path under a user or system folder", {"tool_input": {"command": "rm -rf /tmp/x"}}, "data.tool_input.command"),
    ("a path under a user or system folder", {"x": ["ok", "/private/etc/hosts"]}, "data.x[1]"),
    ("the user name", {"tool_input": {"command": "echo Alice was here"}}, "data.tool_input.command"),
    ("the machine name", {"tool_response": "host BOX-7 answered"}, "data.tool_response"),
    ("the user name", {"nested": {"deep": [{"k": "hello alice"}]}}, "data.nested.deep[0].k"),
    ("the user name", {"alice": "a key, not a value"}, "data.alice (name)"),
]


@pytest.mark.parametrize("what,data,field", LEAKS, ids=[f"{w}-{f}" for w, _, f in LEAKS])
def test_it_refuses_and_names_the_line_the_field_and_the_kind(tmp_path, what, data, field):
    source = _record(tmp_path, [*CLEAN, ("s2", "tool", data)])
    dest = tmp_path / "out" / "b.jsonl"
    problems, findings = export(source, dest, TERMS)
    assert problems == []
    hit = [f for f in findings if f.what == what and f.field == field]
    assert hit, findings
    assert hit[0].line == len(CLEAN) + 1
    assert hit[0].kind == "tool"
    assert hit[0].seq == len(CLEAN) + 1
    assert hit[0].text
    assert not dest.exists()
    assert not dest.parent.exists()


def test_every_finding_on_every_line_is_listed(tmp_path):
    rows = [
        *CLEAN,
        ("s2", "tool", {"tool_input": {"command": "cd C:\\x"}}),
        ("s2", "tool", {"tool_input": {"command": "fine"}}),
        ("s2", "error", {"error": "alice at BOX-7", "raw": "{\"cwd\": \"/home/alice\"}"}),
    ]
    source = _record(tmp_path, rows)
    _, findings = export(source, tmp_path / "b.jsonl", TERMS)
    assert [f.line for f in findings] == [5, 7, 7, 7, 7]
    assert {f.what for f in findings if f.line == 7} == {
        "the user name",
        "the machine name",
        "a path under a user or system folder",
    }


def test_the_same_thing_twice_in_one_field_is_reported_once(tmp_path):
    source = _record(tmp_path, [*CLEAN, ("s", "tool", {"c": "C:\\a and D:\\b and /home/x and /home/y"})])
    _, findings = export(source, tmp_path / "b.jsonl", TERMS)
    assert sorted(f.what for f in findings) == [
        "a drive path",
        "a path under a user or system folder",
    ]


# ---------------------------------------------------------------------------
# AC2.1f: ordinary text is not a path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "see https://example.org/a/b and http://localhost:5173/x",
        "file:///./web/node_modules/x.js",
        "ratio a:b and key: value and c: and x:y",
        "src/Users/readme.md and docs/home/index.md",
        "Created: a.md. Changed: b.py.",
        "12:30:45 and 8:00",
        "ssh://git@github.com/x/y.git",
    ],
)
def test_ordinary_text_is_not_mistaken_for_a_path(tmp_path, text):
    source = _record(tmp_path, [*CLEAN, ("s", "tool", {"text": text})])
    assert export(source, tmp_path / "b.jsonl", TERMS) == ([], [])


# ---------------------------------------------------------------------------
# AC2.1d: other refusals
# ---------------------------------------------------------------------------

def test_a_missing_source(tmp_path):
    dest = tmp_path / "b.jsonl"
    problems, findings = export(tmp_path / "nope.jsonl", dest, TERMS)
    assert problems and "missing" in problems[0] and findings == []
    assert not dest.exists()


def test_an_empty_source(tmp_path):
    source = tmp_path / "ledger.jsonl"
    source.write_text("\n\n", encoding="utf-8")
    problems, _ = export(source, tmp_path / "b.jsonl", TERMS)
    assert problems and "empty" in problems[0]


@pytest.mark.parametrize("bad", ["not json at all\n", "[1, 2]\n", '{"seq": 1}\n'])
def test_a_source_that_is_not_records(tmp_path, bad):
    source = tmp_path / "ledger.jsonl"
    source.write_text(bad, encoding="utf-8")
    problems, _ = export(source, tmp_path / "b.jsonl", TERMS)
    assert problems and "Line 1 is not a record" in problems[0]
    assert not (tmp_path / "b.jsonl").exists()


def test_a_torn_record_is_refused_and_says_where(tmp_path):
    source = _record(tmp_path, CLEAN)
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    rows[1]["data"]["tool_input"]["path"] = "src/other.py"
    source.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    problems, findings = export(source, tmp_path / "b.jsonl", TERMS)
    assert problems and "torn at line 2" in problems[0]
    assert findings == []
    assert not (tmp_path / "b.jsonl").exists()


def test_an_existing_destination_is_left_as_it_was_on_refusal(tmp_path):
    source = _record(tmp_path, [*CLEAN, ("s", "tool", {"c": "C:\\x"})])
    dest = tmp_path / "b.jsonl"
    dest.write_text("older published record\n", encoding="utf-8")
    export(source, dest, TERMS)
    assert dest.read_text(encoding="utf-8") == "older published record\n"


def test_the_source_is_never_changed(tmp_path):
    source = _record(tmp_path, [*CLEAN, ("s", "tool", {"c": "C:\\x"})])
    before = source.read_bytes()
    export(source, tmp_path / "b.jsonl", TERMS)
    assert source.read_bytes() == before


# ---------------------------------------------------------------------------
# AC2.1c: the command line
# ---------------------------------------------------------------------------

def test_the_command_refuses_with_a_list_and_status_1(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(export_mod, "identity_terms", lambda: TERMS)
    source = _record(tmp_path, [*CLEAN, ("s2", "tool", {"tool_input": {"command": "cd C:\\Program Files"}})])
    dest = tmp_path / "out" / "b.jsonl"
    code = main(["--source", str(source), "--dest", str(dest)])
    out = capsys.readouterr().out
    assert code == 1
    assert "Nothing was copied." in out
    assert "line 5 (tool) data.tool_input.command: a drive path" in out
    assert "1 finding in total" in out
    assert not dest.exists()


def test_the_command_succeeds_and_prints_the_fingerprint(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(export_mod, "identity_terms", lambda: TERMS)
    source = _record(tmp_path, CLEAN)
    dest = tmp_path / "out" / "b.jsonl"
    assert main(["--source", str(source), "--dest", str(dest)]) == 0
    out = capsys.readouterr().out
    last = ledger.read(dest)[-1]["hash"]
    assert f"Copied {len(CLEAN)} lines to b.jsonl." in out
    assert f"Fingerprint of the record: {last}" in out


def test_the_command_refuses_to_copy_a_file_onto_itself(tmp_path, capsys):
    source = _record(tmp_path, CLEAN)
    assert main(["--source", str(source), "--dest", str(source)]) == 1
    assert "same file" in capsys.readouterr().out


def test_the_command_reports_a_missing_source(tmp_path, capsys):
    assert main(["--source", str(tmp_path / "x.jsonl"), "--dest", str(tmp_path / "y.jsonl")]) == 1
    assert "missing" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# the names it looks for
# ---------------------------------------------------------------------------

def test_identity_terms_are_lower_case_and_long_enough(monkeypatch):
    monkeypatch.setattr(export_mod.getpass, "getuser", lambda: "Alice")
    monkeypatch.setattr(export_mod.socket, "gethostname", lambda: "BOX-7.example.org")
    monkeypatch.setenv("USERNAME", "ab")
    monkeypatch.setenv("COMPUTERNAME", "BOX-7")
    terms = identity_terms()
    assert terms["alice"] == "the user name"
    assert terms["box-7.example.org"] == "the machine name"
    assert terms["box-7"] == "the machine name"
    assert "ab" not in terms
    assert all(t == t.lower() and len(t) >= 3 for t in terms)


def test_scan_without_any_names_still_finds_paths():
    line = json.dumps({"seq": 1, "kind": "tool", "data": {"p": "C:\\x"}})
    assert [f.what for f in scan([line], {})] == ["a drive path"]
