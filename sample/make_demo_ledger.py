"""Build the demo ledger shown by the static printout site.

Three short sessions are recorded one after the other into ONE temporary
project folder, using the real Paper Trail functions (on_start, record,
on_stop, verify). The finished ledger is then copied to the output path.

    python sample/make_demo_ledger.py

  A  an honest agent: reads a file, creates a file, says so
  B  the cleanup story: the real sample/cleanup.py is run, and its pattern is
     too broad, so a file the agent never mentioned goes too
  C  an agent that changes two files and stops without writing a statement
  D  two turns in one session: between them a person deletes two files; in the
     second turn the agent deletes two others and says so. The turn hook keeps
     the person's two files out of the agent's verdict
  E  the agent edits one of the recording hooks while it works and says so; the
     statement is honest, and the printout still prints the loud line "RECORDING
     SETUP CHANGED DURING THIS TURN"

Nothing here touches the project's own .papertrail folder, and os.environ is
never modified: every call receives the temporary root (and, for verify, the
ledger path) explicitly.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Allow "python sample/make_demo_ledger.py" from any working directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from papertrail import ledger, statement as statement_mod, verifier  # noqa: E402
from papertrail.recorder import record  # noqa: E402
from papertrail.session import on_start, on_stop, on_turn_start  # noqa: E402
from sample.reset import restore  # noqa: E402

SESSION_A = "demo-session-a"
SESSION_B = "demo-session-b"
SESSION_C = "demo-session-c"
SESSION_D = "demo-session-d"
SESSION_E = "demo-session-e"

SAMPLE_DIR = _PROJECT_ROOT / "sample"
DEFAULT_OUT = _PROJECT_ROOT / "web" / "public" / "demo" / "ledger.jsonl"

_GREETING_OLD = 'print("Hello from sample project")'
_GREETING_NEW = 'print("Hello from the sample project")'
_HELPERS = 'def greeting(name: str) -> str:\n    return f"Hello, {name}"\n'


def _write_text(path: Path, text: str) -> None:
    """Write with a fixed newline so the file is the same on every system."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_statement(root: Path, data: dict) -> None:
    _write_text(root / ".papertrail" / "statement.json", json.dumps(data, indent=2))


def _tool_payload(session_id: str, tool_name: str, tool_input: dict, response: str) -> dict:
    return {
        "session_id": session_id,
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": response,
    }


def _verify_latest(root: Path, session_id: str) -> dict:
    """Verify the session's first promoted statement into the temp ledger."""
    ledger_path = root / ".papertrail" / "ledger.jsonl"
    stmt = statement_mod.parse(root / ".papertrail" / "statements" / f"{session_id}-1.json")
    entries = ledger.read(ledger_path)
    return verifier.verify(stmt, entries, session_id, ledger_path=ledger_path)


def _session_a(root: Path, home: Path) -> None:
    """Honest agent: reads one file, creates one file, says so."""
    _write_text(root / "src" / "main.py", 'print("hello")\n')

    on_start({"session_id": SESSION_A}, root, home)

    _write_text(root / "docs" / "notes.md", "Notes.\n")

    record(_tool_payload(
        SESSION_A, "read_file",
        {"path": str(root / "src" / "main.py")},
        'print("hello")',
    ), root, home)
    record(_tool_payload(
        SESSION_A, "fs_write",
        {"path": str(root / "docs" / "notes.md"), "text": "Notes.\n"},
        "written",
    ), root, home)

    _write_statement(root, {
        "summary": "Read main.py and wrote a notes file.",
        "files_read": ["src/main.py"],
        "files_created": ["docs/notes.md"],
        "files_modified": [],
        "files_deleted": [],
    })
    on_stop({"session_id": SESSION_A}, root, home)
    _verify_latest(root, SESSION_A)


def _run_cleanup(root: Path) -> str:
    """Run the project's real cleanup script and return what it printed."""
    result = subprocess.run(
        [sys.executable, str(root / "sample" / "cleanup.py")],
        cwd=root, capture_output=True, text=True, check=True, timeout=30,
    )
    return result.stdout.strip()


def _session_b(root: Path, home: Path) -> None:
    """The cleanup story: the script's pattern is too broad and the agent never notices."""
    sample = root / "sample"
    restore(sample)  # cache/output.bin and notes.txt, exactly as sample/reset.py makes them
    _write_text(sample / "cleanup.py", (SAMPLE_DIR / "cleanup.py").read_text(encoding="utf-8"))

    on_start({"session_id": SESSION_B}, root, home)

    # The real script runs; what it deletes is whatever its pattern matches.
    printed = _run_cleanup(root)

    record(_tool_payload(
        SESSION_B, "execute_pwsh",
        {"command": "python sample/cleanup.py", "description": "Clear the build cache"},
        printed,
    ), root, home)

    _write_statement(root, {
        "summary": "Cleared the build cache.",
        "files_read": [],
        "files_created": [],
        "files_modified": [],
        "files_deleted": ["sample/cache/output.bin"],
    })
    on_stop({"session_id": SESSION_B}, root, home)
    _verify_latest(root, SESSION_B)


def _session_c(root: Path, home: Path) -> None:
    """An agent that changes two files and stops without a statement."""
    src = root / "sample" / "src"
    main_text = (SAMPLE_DIR / "src" / "main.py").read_text(encoding="utf-8")
    assert _GREETING_OLD in main_text, "sample/src/main.py changed; update the demo edit"
    _write_text(src / "main.py", main_text)

    on_start({"session_id": SESSION_C}, root, home)

    _write_text(src / "main.py", main_text.replace(_GREETING_OLD, _GREETING_NEW))
    _write_text(src / "helpers.py", _HELPERS)

    record(_tool_payload(
        SESSION_C, "str_replace",
        {"path": str(src / "main.py"), "old_str": _GREETING_OLD, "new_str": _GREETING_NEW},
        "edited",
    ), root, home)
    record(_tool_payload(
        SESSION_C, "fs_write",
        {"path": str(src / "helpers.py"), "text": _HELPERS},
        "written",
    ), root, home)

    # No statement. The stop hook sees the changes and says so.
    on_stop({"session_id": SESSION_C}, root, home)


def _session_d(root: Path, home: Path) -> None:
    """Two turns. A person tidies up between them; the agent only answers for its own work."""
    drafts = root / "drafts"
    for name in ("old-a.txt", "old-b.txt", "draft-1.txt", "draft-2.txt"):
        _write_text(drafts / name, f"{name}\n")
    on_start({"session_id": SESSION_D}, root, home)

    # Turn 1: the agent writes a plan and says so.
    on_turn_start({"session_id": SESSION_D}, root, home)
    _write_text(drafts / "plan.md", "Plan.\n")
    record(_tool_payload(
        SESSION_D, "fs_write",
        {"path": str(drafts / "plan.md"), "text": "Plan.\n"},
        "written",
    ), root, home)
    _write_statement(root, {
        "summary": "Wrote the plan.",
        "files_read": [],
        "files_created": ["drafts/plan.md"],
        "files_modified": [],
        "files_deleted": [],
    })
    on_stop({"session_id": SESSION_D}, root, home)

    # Between the turns a person deletes two files. The agent is not involved.
    (drafts / "old-a.txt").unlink()
    (drafts / "old-b.txt").unlink()

    # Turn 2: the agent deletes two other files and says so.
    on_turn_start({"session_id": SESSION_D}, root, home)
    (drafts / "draft-1.txt").unlink()
    (drafts / "draft-2.txt").unlink()
    record(_tool_payload(
        SESSION_D, "execute_pwsh",
        {"command": "Remove-Item drafts/draft-1.txt, drafts/draft-2.txt", "description": "Clear two drafts"},
        "",
    ), root, home)
    _write_statement(root, {
        "summary": "Cleared two drafts.",
        "files_read": [],
        "files_created": [],
        "files_modified": [],
        "files_deleted": ["drafts/draft-1.txt", "drafts/draft-2.txt"],
    })
    on_stop({"session_id": SESSION_D}, root, home)


def _session_e(root: Path, home: Path) -> None:
    """An honest agent that also edits a recording hook. The record is marked, whatever it says."""
    hook = root / ".kiro" / "hooks" / "record.py"
    _write_text(hook, "# stand-in for the recording hook\n")
    on_start({"session_id": SESSION_E}, root, home)
    on_turn_start({"session_id": SESSION_E}, root, home)
    _write_text(hook, "# stand-in for the recording hook\n# edited by the agent\n")
    _write_text(root / "docs" / "setup-notes.md", "Setup notes.\n")
    record(_tool_payload(
        SESSION_E, "fs_write",
        {"path": str(hook), "text": "# stand-in for the recording hook\n# edited by the agent\n"},
        "written",
    ), root, home)
    record(_tool_payload(
        SESSION_E, "fs_write",
        {"path": str(root / "docs" / "setup-notes.md"), "text": "Setup notes.\n"},
        "written",
    ), root, home)
    _write_statement(root, {
        "summary": "Edited the record hook and wrote setup notes.",
        "files_read": [],
        "files_created": ["docs/setup-notes.md"],
        "files_modified": [".kiro/hooks/record.py"],
        "files_deleted": [],
    })
    on_stop({"session_id": SESSION_E}, root, home)


def generate(out_path: Path) -> None:
    """Build the five-session demo ledger and write it to out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    home = Path.home()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _session_a(root, home)
        _session_b(root, home)
        _session_c(root, home)
        _session_d(root, home)
        _session_e(root, home)
        shutil.copyfile(root / ".papertrail" / "ledger.jsonl", out_path)


if __name__ == "__main__":
    generate(DEFAULT_OUT)
    n = len(ledger.read(DEFAULT_OUT))
    print(f"Wrote {n} entries to {DEFAULT_OUT.relative_to(_PROJECT_ROOT).as_posix()}")
