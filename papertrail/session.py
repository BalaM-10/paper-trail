"""Session start/stop logic: snapshot, diff, statement promotion."""

import json
from datetime import datetime, timezone
from pathlib import Path

from papertrail import ledger, witness
from papertrail.statement import AGENT_KEYS, parse


def on_start(payload: dict, root: Path, home: Path) -> dict:
    """Take a snapshot and append a witness/start entry. Return the entry."""
    session_id: str = payload.get("session_id", "unknown")
    ledger_path = root / ".papertrail" / "ledger.jsonl"

    snap = witness.snapshot(root)
    return ledger.append(ledger_path, session_id, "witness",
                         {"event": "start", "snapshot": snap})


def on_stop(payload: dict, root: Path, home: Path) -> dict:
    """
    Determine diff baseline, compute diff, append witness/stop entry, and
    optionally promote statement.json.  Return the witness/stop entry.
    """
    session_id: str = payload.get("session_id", "unknown")
    ledger_path = root / ".papertrail" / "ledger.jsonl"

    snap_new = witness.snapshot(root)
    entries = ledger.read(ledger_path)

    # --- 1. Determine diff baseline from statement entries, not by position ---
    session_entries = [e for e in entries if e["session_id"] == session_id]

    witness_seqs_from_stmts = [
        e["data"]["witness_seq"]
        for e in session_entries
        if e["kind"] == "statement" and "witness_seq" in e.get("data", {})
    ]

    baseline_snap = None
    baseline_label = "none"

    if witness_seqs_from_stmts:
        ref_seq = max(witness_seqs_from_stmts)
        for e in session_entries:
            if e["seq"] == ref_seq and e["kind"] == "witness":
                baseline_snap = e["data"]["snapshot"]
                baseline_label = f"prev_stop_seq:{ref_seq}"
                break
    else:
        for e in session_entries:
            if e["kind"] == "witness" and e["data"].get("event") == "start":
                baseline_snap = e["data"]["snapshot"]
                baseline_label = "start"
                break

    # --- 2. Compute diff ---
    if baseline_snap is not None:
        diff = witness.diff(baseline_snap, snap_new)
    else:
        diff = {"created": [], "deleted": [], "modified": []}

    # --- 3. Append witness/stop entry ---
    stop_entry = ledger.append(
        ledger_path, session_id, "witness",
        {
            "event":    "stop",
            "snapshot": snap_new,
            "diff":     diff,
            "baseline": baseline_label,
        },
    )
    witness_seq = stop_entry["seq"]

    # --- 4. Promote statement.json if present and valid ---
    stmt_path = root / ".papertrail" / "statement.json"
    if stmt_path.exists():
        raw_text = stmt_path.read_text(encoding="utf-8")
        try:
            raw = json.loads(raw_text)
            missing = AGENT_KEYS - raw.keys()
            if missing:
                raise ValueError(f"missing keys: {missing}")
        except (json.JSONDecodeError, ValueError) as exc:
            ledger.append(ledger_path, session_id, "error", {
                "error":  f"invalid statement.json: {exc}",
                "source": "session.py on_stop",
            })
            rejected = root / ".papertrail" / "rejected"
            rejected.mkdir(exist_ok=True)
            stmt_path.rename(rejected / f"statement-{witness_seq}.json")
        else:
            promoted = {
                **raw,
                "session_id":  session_id,
                "ts":          datetime.now(timezone.utc).isoformat(),
                "witness_seq": witness_seq,
            }
            ledger.append(ledger_path, session_id, "statement", promoted)

            stmts_dir = root / ".papertrail" / "statements"
            stmts_dir.mkdir(exist_ok=True)
            n = sum(1 for _ in stmts_dir.glob(f"{session_id}-*.json")) + 1
            out = stmts_dir / f"{session_id}-{n}.json"
            out.write_text(json.dumps(promoted, indent=2), encoding="utf-8")
            stmt_path.unlink()

    return stop_entry
