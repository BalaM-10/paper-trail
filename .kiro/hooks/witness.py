import sys, json, os
from pathlib import Path

_env_root = os.environ.get("PAPERTRAIL_ROOT")
root = Path(_env_root) if _env_root else Path(__file__).resolve().parents[2]
_pkg_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_pkg_root))
from papertrail import ledger
from papertrail.session import on_start, on_stop


def _save_payload(event: str, payload: dict, root: Path) -> None:
    """Write raw JSON once to .papertrail/payloads/session-<event>.json."""
    payloads_dir = root / ".papertrail" / "payloads"
    payloads_dir.mkdir(parents=True, exist_ok=True)
    dest = payloads_dir / f"session-{event}.json"
    if not dest.exists():
        dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")


raw = ""
payload = {}
try:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    _save_payload(sys.argv[1], payload, root)
    if sys.argv[1] == "start":
        on_start(payload, root, Path.home())
    else:
        on_stop(payload, root, Path.home())
except Exception as exc:
    ledger_path = root / ".papertrail" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.append(ledger_path, payload.get("session_id", "unknown"),
                  "error", {"error": str(exc), "source": f"witness.py {sys.argv[1]}"})
sys.exit(0)
