import sys, json, os
from pathlib import Path

_env_root = os.environ.get("PAPERTRAIL_ROOT")
root = Path(_env_root) if _env_root else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from papertrail import ledger
from papertrail.recorder import record

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
