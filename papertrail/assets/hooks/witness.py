"""Kiro hook: the witness takes a snapshot. Run as `witness.py start`, `witness.py turn`
or `witness.py stop`. Never raises, and prints nothing: Kiro adds a hook's output to the
agent's context, and a UserPromptSubmit hook that exits with 2 would block the prompt."""
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
    from papertrail import ledger, session
except Exception as exc:
    _note_and_exit("witness.py", exc)

# event on the command line -> the function in papertrail/session.py that handles it
HANDLERS = {"start": "on_start", "turn": "on_turn_start", "stop": "on_stop"}


def _save_payload(event: str, payload: dict, root: Path) -> None:
    """Write the payload once to .papertrail/payloads/session-<event>.json (to see what Kiro sends)."""
    payloads_dir = root / ".papertrail" / "payloads"
    payloads_dir.mkdir(parents=True, exist_ok=True)
    dest = payloads_dir / f"session-{event}.json"
    if not dest.exists():
        saved = dict(payload)
        if "prompt" in saved:  # what the person typed is never kept
            saved["prompt"] = f"<not kept: {len(str(saved['prompt']))} characters>"
        dest.write_text(json.dumps(saved, indent=2), encoding="utf-8")


event = sys.argv[1] if len(sys.argv) > 1 else ""
raw = ""
payload = {}
try:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    if event not in HANDLERS:
        raise ValueError(f"unknown event {event!r}; use start, turn or stop")
    _save_payload(event, payload, root)
    getattr(session, HANDLERS[event])(payload, root, Path.home())
except Exception as exc:
    try:
        ledger_path = root / ".papertrail" / "ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger.append(ledger_path, payload.get("session_id", "unknown") if isinstance(payload, dict) else "unknown",
                      "error", {"error": str(exc), "source": f"witness.py {event}"})
    except Exception:
        pass
sys.exit(0)
