"""Session start, turn start and stop: snapshots, diffs, statement promotion.

A session is one chat; Kiro keeps its id across many replies. A turn is one reply:
it starts when the person sends a prompt (`on_turn_start`) and ends when the agent
stops (`on_stop`). The stop compares the project with the snapshot taken at the
start of the turn, so what a person changed between two replies is not blamed on
the agent. That change is recorded on its own, as "between turns".
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from papertrail import ledger, verifier, watch, witness
from papertrail.ignore import RULE_NAME as IGNORE_RULE
from papertrail import statement as statement_mod
from papertrail.outcome import NO_STATEMENT, last_overall, undeclared_from_diff
from papertrail.statement import AGENT_KEYS, parse


def on_start(payload: dict, root: Path, home: Path) -> dict:
    """Take a snapshot and append a witness/start entry. Return the entry."""
    session_id: str = payload.get("session_id", "unknown")
    ledger_path = root / ".papertrail" / "ledger.jsonl"

    snap = witness.snapshot(root)
    return ledger.append(ledger_path, session_id, "witness",
                         {"event": "start", "snapshot": snap, "ignore": IGNORE_RULE})


_SNAPSHOT_EVENTS = ("start", "turn", "stop")


def _latest_turn(session_entries: list[dict]) -> dict | None:
    """The newest witness/turn record of the session, or None."""
    found = None
    for e in session_entries:
        if e["kind"] == "witness" and e["data"].get("event") == "turn":
            found = e
    return found


def on_turn_start(payload: dict, root: Path, home: Path) -> dict:
    """
    The person has sent a prompt. Take a snapshot and append a witness/turn record.
    If the session already has a snapshot and the project differs from it, also append
    a witness/between_turns record: what changed since then, outside the agent.

    The compared-from snapshot is the latest one in the session. When that is the start
    of a turn that never stopped (interrupted, or a prompt Kiro sent itself) the record
    says `unfinished`, because some of those changes may be the agent's.

    The text of the prompt is never read. Returns the witness/turn record.
    """
    session_id: str = payload.get("session_id", "unknown")
    ledger_path = root / ".papertrail" / "ledger.jsonl"
    snap = witness.snapshot(root)
    earlier = None
    for e in ledger.read(ledger_path):
        if (
            e["session_id"] == session_id
            and e["kind"] == "witness"
            and e["data"].get("event") in _SNAPSHOT_EVENTS
            and "snapshot" in e["data"]
        ):
            earlier = e
    turn_entry = ledger.append(ledger_path, session_id, "witness", {
        "event": "turn", "snapshot": snap, "ignore": IGNORE_RULE,
    })
    if earlier is not None:
        diff = witness.diff(witness.without_ignored(earlier["data"]["snapshot"], root), snap)
        if any(diff.values()):
            event = earlier["data"]["event"]
            between = {
                "event":        "between_turns",
                "diff":         diff,
                "baseline":     f"{event}:{earlier['seq']}",
                "witness_seq":  turn_entry["seq"],
                "evidence_seq": [earlier["seq"], turn_entry["seq"]],
                "unfinished":   event == "turn",
            }
            setup_files = watch.changed_files(diff)
            if setup_files:  # the hooks, the statement rule or the MCP settings changed
                between["setup_changed"] = setup_files
            ledger.append(ledger_path, session_id, "witness", between)
    return turn_entry


def on_stop(payload: dict, root: Path, home: Path) -> dict:
    """
    Determine diff baseline, compute diff, append witness/stop entry, and
    optionally promote statement.json.  Return the witness/stop entry.

    If no statement was promoted (none was written, or it was unusable) and the
    witness saw changes, also record a NO_STATEMENT overall verdict.
    """
    session_id: str = payload.get("session_id", "unknown")
    ledger_path = root / ".papertrail" / "ledger.jsonl"

    snap_new = witness.snapshot(root)
    entries = ledger.read(ledger_path)

    # --- 1. Determine diff baseline ---
    # Inside the current turn (everything from its start on): the stop a statement was
    # written at, else the snapshot at the start of the turn. A session with no turn
    # start (the turn hook is not installed, or did not fire) works as it always did:
    # the stop a statement points at, else the session start.
    session_entries = [e for e in entries if e["session_id"] == session_id]
    turn_entry = _latest_turn(session_entries)
    scope = (
        [e for e in session_entries if e["seq"] >= turn_entry["seq"]]
        if turn_entry is not None
        else session_entries
    )
    witness_seqs_from_stmts = [
        e["data"]["witness_seq"]
        for e in scope
        if e["kind"] == "statement" and "witness_seq" in e.get("data", {})
    ]
    baseline_snap = None
    baseline_label = "none"
    if witness_seqs_from_stmts:
        ref_seq = max(witness_seqs_from_stmts)
        for e in scope:
            if e["seq"] == ref_seq and e["kind"] == "witness":
                baseline_snap = e["data"]["snapshot"]
                baseline_label = f"prev_stop_seq:{ref_seq}"
                break
    elif turn_entry is not None:
        baseline_snap = turn_entry["data"]["snapshot"]
        baseline_label = f"turn:{turn_entry['seq']}"
    else:
        for e in session_entries:
            if e["kind"] == "witness" and e["data"].get("event") == "start":
                baseline_snap = e["data"]["snapshot"]
                baseline_label = "start"
                break
    # --- 2. Compute diff ---
    if baseline_snap is not None:
        # The baseline is read through today's rule too: an older snapshot, or one taken
        # before .gitignore changed, must not report skipped files as deleted.
        diff = witness.diff(witness.without_ignored(baseline_snap, root), snap_new)
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
            "ignore":   IGNORE_RULE,
        },
    )
    witness_seq = stop_entry["seq"]

    # --- 3b. The recording setup changed during this turn: say so on its own line,
    # whether or not the agent declared it. The statement's verdict is not touched.
    setup_files = watch.changed_files(diff)
    if setup_files:
        ledger.append(ledger_path, session_id, "witness", {
            "event":        "setup_changed",
            "files":        setup_files,
            "diff":         watch.setup_changes(diff),
            "baseline":     baseline_label,
            "witness_seq":  witness_seq,
            "evidence_seq": [witness_seq],
        })

    # --- 4. Promote statement.json if present and valid ---
    promoted = False
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
            promoted_data = {
                **raw,
                "session_id":  session_id,
                "ts":          datetime.now(timezone.utc).isoformat(),
                "witness_seq": witness_seq,
            }
            ledger.append(ledger_path, session_id, "statement", promoted_data)

            stmts_dir = root / ".papertrail" / "statements"
            stmts_dir.mkdir(exist_ok=True)
            n = sum(1 for _ in stmts_dir.glob(f"{session_id}-*.json")) + 1
            out = stmts_dir / f"{session_id}-{n}.json"
            out.write_text(json.dumps(promoted_data, indent=2), encoding="utf-8")
            stmt_path.unlink()
            promoted = True
            _check_statement(ledger_path, session_id, out)

    # --- 5. Changes but no statement: say so ---
    if not promoted:
        _record_no_statement(ledger_path, session_id, stop_entry, diff, scope)

    return stop_entry


def _check_statement(ledger_path: Path, session_id: str, statement_file: Path) -> None:
    """
    Run the verifier on the statement just promoted, so its verdicts are in the
    record without anyone running `verify`. The verifier records each statement
    once (it recognises its own overall verdict), so `verify` later adds nothing.
    Never raises: a failure becomes an error record.
    """
    try:
        stmt = statement_mod.parse(statement_file)
        verifier.verify(stmt, ledger.read(ledger_path), session_id, ledger_path=ledger_path)
    except Exception as exc:  # the hook must never disturb the agent
        try:
            ledger.append(ledger_path, session_id, "error", {
                "error":  f"the statement could not be checked: {type(exc).__name__}: {exc}",
                "source": "session.py auto-check",
            })
        except Exception:
            pass


def _record_no_statement(
    ledger_path: Path,
    session_id: str,
    stop_entry: dict,
    diff: dict,
    entries: list[dict],
) -> dict | None:
    """
    Append a NO_STATEMENT overall verdict listing the witness diff as undeclared.

    Nothing is recorded when nothing changed (or there was no baseline), or when
    the turn's latest overall verdict is already this same NO_STATEMENT.
    `entries` are the session's records of the current turn, as on_stop read them
    before it appended anything. The same change in a later turn is a new fact, so
    it is not compared with an earlier turn. The records on_stop appends itself are
    never overall verdicts, so the list is still exact.
    """
    undeclared = undeclared_from_diff(diff)
    if not undeclared:
        return None
    last = last_overall(entries, session_id)
    if (
        last is not None
        and last["data"].get("verdict") == NO_STATEMENT
        and last["data"].get("undeclared") == undeclared
    ):
        return None
    return ledger.append(ledger_path, session_id, "verdict", {
        "kind_detail":  "statement_overall",
        "verdict":      NO_STATEMENT,
        "evidence_seq": [stop_entry["seq"]],
        "witness_seq":  stop_entry["seq"],
        "undeclared":   undeclared,
    })
