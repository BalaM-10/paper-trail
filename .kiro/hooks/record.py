"""Kiro hook: record one tool call (or file delete) in the ledger. Never raises."""
import json
import os
import sys
from pathlib import Path

# <project>/.kiro/hooks/<this file>. Only the standard library is used until the
# import below, so a project without Paper Trail installed is never disturbed.
_project = Path(__file__).resolve().parents[2]
root = Path(os.environ.get("PAPERTRAIL_ROOT") or _project)


def _note_and_exit(source: str, exc: BaseException) -> None:
    """One line in .papertrail/hook-errors.txt (no paths), then exit 0."""
    try:
        folder = root / ".papertrail"
        folder.mkdir(parents=True, exist_ok=True)
        what = getattr(exc, "name", None) or ""
        line = f"{source}: cannot import papertrail ({type(exc).__name__}: {what})"
        with open(folder / "hook-errors.txt", "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
    except Exception:
        pass
    sys.exit(0)


if (_project / "papertrail").is_dir():  # this repository: use the folder beside .kiro
    sys.path.insert(0, str(_project))
try:
    from papertrail import ledger
    from papertrail.recorder import record
except Exception as exc:
    _note_and_exit("record.py", exc)

raw = ""
payload = {}
try:
    raw = sys.stdin.read()
    payload = json.loads(raw)
    record(payload, root, Path.home())
except Exception as exc:
    ledger_path = root / ".papertrail" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.append(ledger_path, payload.get("session_id", "unknown"),
                  "error", {"error": str(exc), "raw": raw[:500]})
sys.exit(0)