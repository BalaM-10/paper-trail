"""Build the demo ledger shown by the static printout site.

Two short sessions are recorded one after the other into ONE temporary
project folder, using the real Paper Trail functions (on_start, record,
on_stop, verify). The finished ledger is then copied to the output path.

    python sample/make_demo_ledger.py

Nothing here touches the project's own .papertrail folder, and
os.environ is never modified: every call receives the temporary root
(and, for verify, the ledger path) explicitly.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

# Allow "python sample/make_demo_ledger.py" from any working directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from papertrail import ledger, statement as statement_mod, verifier  # noqa: E402
from papertrail.recorder import record  # noqa: E402
from papertrail.session import on_start, on_stop  # noqa: E402

SESSION_A = "demo-session-a"
SESSION_B = "demo-session-b"

DEFAULT_OUT = _PROJECT_ROOT / "web" / "public" / "demo" / "ledger.jsonl"


def _write_statement(root: Path, data: dict) -> None:
    path = root / ".papertrail" / "statement.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "main.py").write_text('print("hello")\n', encoding="utf-8")

    on_start({"session_id": SESSION_A}, root, home)

    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "notes.md").write_text("Notes.\n", encoding="utf-8")

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


def _session_b(root: Path, home: Path) -> None:
    """The cleanup story: the script removes more than the agent reports."""
    (root / "sample" / "cache").mkdir(parents=True, exist_ok=True)
    (root / "sample" / "notes.txt").write_text("Project notes.\n", encoding="utf-8")
    (root / "sample" / "cache" / "output.bin").write_bytes(b"\x00FAKE_BUILD_OUTPUT\x00")

    on_start({"session_id": SESSION_B}, root, home)

    # What cleanup.py really does: delete the cache file AND the notes file.
    (root / "sample" / "cache" / "output.bin").unlink()
    (root / "sample" / "notes.txt").unlink()

    record(_tool_payload(
        SESSION_B, "execute_pwsh",
        {"command": "python sample/cleanup.py", "description": "Clear the build cache"},
        "Cleared build cache: removed cache/output.bin",
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


def generate(out_path: Path) -> None:
    """Build the two-session demo ledger and write it to out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    home = Path.home()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _session_a(root, home)
        _session_b(root, home)
        shutil.copyfile(root / ".papertrail" / "ledger.jsonl", out_path)


if __name__ == "__main__":
    generate(DEFAULT_OUT)
    n = len(ledger.read(DEFAULT_OUT))
    print(f"Wrote {n} entries to {DEFAULT_OUT.relative_to(_PROJECT_ROOT).as_posix()}")
