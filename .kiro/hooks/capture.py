import sys, json, os
from pathlib import Path

root = Path(__file__).resolve().parents[2]
payloads_dir = root / ".papertrail" / "payloads"
payloads_dir.mkdir(parents=True, exist_ok=True)

event = sys.argv[1] if len(sys.argv) > 1 else "unknown"
dest = payloads_dir / f"session-{event}.json"

try:
    raw = sys.stdin.read()
    # Write once: do not overwrite an existing capture.
    if not dest.exists():
        dest.write_text(raw, encoding="utf-8")
except Exception as exc:
    (payloads_dir / f"capture-error-{event}.txt").write_text(str(exc))
