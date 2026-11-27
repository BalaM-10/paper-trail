"""Seven cases anyone can run to see what Paper Trail does.

    python sample/run_cases.py                  # run them and print the results
    python sample/run_cases.py --write-readme   # also update the table in README.md

Each case is played in its own temporary folder with the real Paper Trail
functions (on_start, on_turn_start, on_stop). Nothing here touches the project's
own .papertrail folder, and os.environ is never changed: every call receives the
temporary folder explicitly. The temporary folder is removed afterwards.

For each case the script prints what should happen (expected), what did happen
(actual) and PASS or FAIL. The exit code is 0 only when every case passes.
"""
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Allow "python sample/run_cases.py" from any working directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from papertrail import ledger  # noqa: E402
from papertrail.outcome import is_overall  # noqa: E402
from papertrail.session import on_start, on_stop, on_turn_start  # noqa: E402

README = _PROJECT_ROOT / "README.md"
START_MARK = "<!-- cases:start -->"
END_MARK = "<!-- cases:end -->"
HOOK = ".kiro/hooks/record.py"


@dataclass(frozen=True)
class Case:
    letter: str
    name: str
    story: str
    expected: str
    play: Callable[[Path, str], str]  # (temporary folder, session id) -> what happened


@dataclass(frozen=True)
class Result:
    letter: str
    name: str
    story: str
    expected: str
    actual: str

    @property
    def passed(self) -> bool:
        return self.actual == self.expected


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _put(root: Path, name: str, text: str | None = None) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name if text is None else text, encoding="utf-8", newline="\n")


def _statement(root: Path, summary: str, **lists: list[str]) -> None:
    data = {"summary": summary, "files_read": [], "files_created": [], "files_modified": [],
            "files_deleted": [], **lists}
    _put(root, ".papertrail/statement.json", json.dumps(data))


def _ledger_path(root: Path) -> Path:
    return root / ".papertrail" / "ledger.jsonl"


def _entries(root: Path, sid: str) -> list[dict]:
    return [e for e in ledger.read(_ledger_path(root)) if e["session_id"] == sid]


def _outcome(root: Path, sid: str) -> str:
    """What the record says about the session's latest statement, in one short line."""
    entries = _entries(root, sid)
    overalls = [e for e in entries if is_overall(e)]
    if not overalls:
        return "no verdict"
    last = overalls[-1]["data"]
    parts = [str(last["verdict"])]
    wrong = [
        e["data"]["path"] for e in entries
        if e["kind"] == "verdict" and e["data"].get("witness_seq") == last["witness_seq"]
        and e["data"].get("verdict") == "CONTRADICTED" and "path" in e["data"]
    ]
    if wrong:
        parts.append("contradicted claim: " + ", ".join(sorted(wrong)))
    undeclared = [u["path"] for u in last.get("undeclared", [])]
    if undeclared:
        parts.append("undeclared: " + ", ".join(sorted(undeclared)))
    return "; ".join(parts)


def _between(root: Path, sid: str) -> list[str]:
    files: list[str] = []
    for e in _entries(root, sid):
        if e["kind"] == "witness" and e["data"].get("event") == "between_turns":
            diff = e["data"].get("diff", {})
            files += [p for key in ("created", "modified", "deleted") for p in diff.get(key, [])]
    return sorted(files)


def _setup_files(root: Path, sid: str) -> list[str]:
    files: list[str] = []
    for e in _entries(root, sid):
        if e["kind"] == "witness" and e["data"].get("event") == "setup_changed":
            files += e["data"].get("files", [])
    return sorted(files)


# ---------------------------------------------------------------------------
# The cases
# ---------------------------------------------------------------------------

def _a_honest(root: Path, sid: str) -> str:
    _put(root, "keep.txt")
    on_start({"session_id": sid}, root, root / "home")
    _put(root, "report.txt")
    _statement(root, "Wrote the report.", files_created=["report.txt"])
    on_stop({"session_id": sid}, root, root / "home")
    return _outcome(root, sid)


def _b_undeclared(root: Path, sid: str) -> str:
    _put(root, "keep.txt")
    on_start({"session_id": sid}, root, root / "home")
    _put(root, "report.txt")
    _put(root, "extra.txt")
    _statement(root, "Wrote the report.", files_created=["report.txt"])
    on_stop({"session_id": sid}, root, root / "home")
    return _outcome(root, sid)


def _c_false_claim(root: Path, sid: str) -> str:
    _put(root, "keep.txt")
    on_start({"session_id": sid}, root, root / "home")
    _put(root, "report.txt")
    _statement(root, "Wrote the report and a summary.", files_created=["report.txt", "ghost.txt"])
    on_stop({"session_id": sid}, root, root / "home")
    return _outcome(root, sid)


def _d_no_statement(root: Path, sid: str) -> str:
    _put(root, "keep.txt")
    on_start({"session_id": sid}, root, root / "home")
    _put(root, "changed.txt")
    on_stop({"session_id": sid}, root, root / "home")
    return _outcome(root, sid)


def _e_person_between_turns(root: Path, sid: str) -> str:
    _put(root, "person.txt", "before")
    on_start({"session_id": sid}, root, root / "home")
    on_turn_start({"session_id": sid}, root, root / "home")
    _put(root, "first.txt")
    _statement(root, "Wrote the first file.", files_created=["first.txt"])
    on_stop({"session_id": sid}, root, root / "home")
    _put(root, "person.txt", "after")  # a person edits a file between the replies
    on_turn_start({"session_id": sid}, root, root / "home")
    _put(root, "second.txt")
    _statement(root, "Wrote the second file.", files_created=["second.txt"])
    on_stop({"session_id": sid}, root, root / "home")
    between = _between(root, sid)
    return _outcome(root, sid) + ("; between turns: " + ", ".join(between) if between else "")


def _f_record_edited(root: Path, sid: str) -> str:
    _put(root, "secret.txt")
    on_start({"session_id": sid}, root, root / "home")
    (root / "secret.txt").unlink()
    _statement(root, "Cleared a cache.", files_deleted=["secret.txt"])
    on_stop({"session_id": sid}, root, root / "home")
    # Afterwards someone edits the record: the stop line no longer lists the deletion.
    path = _ledger_path(root)
    lines = path.read_text(encoding="utf-8").split("\n")
    edited = []
    for line in lines:
        if line.strip():
            entry = json.loads(line)
            if entry["kind"] == "witness" and entry["data"].get("event") == "stop":
                entry["data"]["diff"]["deleted"] = []
            line = json.dumps(entry, separators=(",", ":"))
        edited.append(line)
    path.write_text("\n".join(edited), encoding="utf-8", newline="\n")
    ok, broken_at = ledger.verify_chain(path)
    return "Paper intact" if ok else f"Paper torn at line {broken_at}"


def _g_setup_changed(root: Path, sid: str) -> str:
    _put(root, HOOK, "# stand-in for the recording hook\n")
    on_start({"session_id": sid}, root, root / "home")
    on_turn_start({"session_id": sid}, root, root / "home")
    _put(root, HOOK, "# stand-in for the recording hook\n# changed\n")
    _statement(root, "Changed the record hook.", files_modified=[HOOK])
    on_stop({"session_id": sid}, root, root / "home")
    setup = _setup_files(root, sid)
    return _outcome(root, sid) + ("; setup changed: " + ", ".join(setup) if setup else "")


CASES: tuple[Case, ...] = (
    Case("a", "Honest agent",
         "The agent writes one file and says so.",
         "SUPPORTED", _a_honest),
    Case("b", "Change it did not declare",
         "The agent writes two files and mentions one.",
         "CONTRADICTED; undeclared: extra.txt", _b_undeclared),
    Case("c", "Claim that did not happen",
         "The agent says it wrote a file that was never written.",
         "CONTRADICTED; contradicted claim: ghost.txt", _c_false_claim),
    Case("d", "No statement",
         "The agent changes a file and writes no statement.",
         "NO_STATEMENT; undeclared: changed.txt", _d_no_statement),
    Case("e", "Person changes a file between turns",
         "Between two replies a person edits a file. The second turn is judged on the agent's own work.",
         "SUPPORTED; between turns: person.txt", _e_person_between_turns),
    Case("f", "Record edited afterwards",
         "After the run, someone edits the record to hide a deletion.",
         "Paper torn at line 2", _f_record_edited),
    Case("g", "Recording setup changed mid-turn",
         "The agent edits a recording hook and says so. The record is marked either way.",
         f"SUPPORTED; setup changed: {HOOK}", _g_setup_changed),
)


# ---------------------------------------------------------------------------
# Running, printing, README
# ---------------------------------------------------------------------------

def run_case(case: Case) -> Result:
    """Play one case in its own temporary folder. Never touches the project's record."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        actual = case.play(Path(tmp), f"case-{case.letter}")
    return Result(case.letter, case.name, case.story, case.expected, actual)


def run_all() -> list[Result]:
    return [run_case(case) for case in CASES]


def table(results: list[Result]) -> str:
    """The results as a Markdown table (no dates, no paths of this machine)."""
    rows = [
        "| Case | What happens | Expected | Actual | Result |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        rows.append(
            f"| {r.letter}) {r.name} | {r.story} | {_cell(r.expected)} | {_cell(r.actual)} | "
            f"{'pass' if r.passed else 'FAIL'} |"
        )
    return "\n".join(rows)


def _cell(text: str) -> str:
    return "`" + text.replace("|", "\\|") + "`"


def readme_block(text: str) -> str | None:
    """The text between the two marker comments, or None if the markers are not there."""
    if START_MARK not in text or END_MARK not in text:
        return None
    start = text.index(START_MARK) + len(START_MARK)
    end = text.index(END_MARK)
    return text[start:end].strip("\n")


def update_readme(results: list[Result], path: Path = README) -> bool:
    """Replace the table between the markers. Returns True if the file changed."""
    text = path.read_bytes().decode("utf-8")
    start = text.index(START_MARK) + len(START_MARK)
    end = text.index(END_MARK)
    new = text[:start] + "\n" + table(results) + "\n" + text[end:]
    if new == text:
        return False
    path.write_bytes(new.encode("utf-8"))
    return True


def main(argv: list[str]) -> int:
    results = run_all()
    for r in results:
        print(f"Case {r.letter}) {r.name}")
        print(f"  expected: {r.expected}")
        print(f"  actual:   {r.actual}")
        print(f"  result:   {'PASS' if r.passed else 'FAIL'}")
    failed = [r for r in results if not r.passed]
    print(f"{len(results) - len(failed)} of {len(results)} cases passed.")
    if "--write-readme" in argv:
        changed = update_readme(results)
        print("README.md table updated." if changed else "README.md table already up to date.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
