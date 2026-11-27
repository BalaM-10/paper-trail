"""What a session's record says about it: a checked statement, or NO_STATEMENT.

NO_STATEMENT is the verdict for a session in which the agent changed files and
wrote no statement. The stop hook records it (see session.py) in the same shape
as a verifier's overall verdict, so anything that reads overall verdicts
already understands it.

Standard library only: session.py imports this module and runs as a hook.
"""

import re
from pathlib import Path

from papertrail import ledger, statement as statement_mod, verifier

NO_STATEMENT = "NO_STATEMENT"

# Session ids become part of a file name, so accept a conservative alphabet.
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def valid_session_id(session_id: str) -> bool:
    """True if the id is safe to use in a file name."""
    return bool(_SESSION_ID_RE.fullmatch(session_id)) and ".." not in session_id


def undeclared_from_diff(diff: dict) -> list[dict]:
    """The witness diff as undeclared changes: created, then modified, then deleted."""
    return [
        {"path": path, "change": change}
        for change in ("created", "modified", "deleted")
        for path in diff.get(change, [])
    ]


def is_overall(entry: dict) -> bool:
    return entry["kind"] == "verdict" and entry["data"].get("kind_detail") == "statement_overall"


def last_overall(entries: list[dict], session_id: str) -> dict | None:
    """The newest overall verdict record of the session, or None."""
    found = None
    for e in entries:
        if e["session_id"] == session_id and is_overall(e):
            found = e
    return found


def latest_no_statement(entries: list[dict], session_id: str) -> dict | None:
    """The newest NO_STATEMENT verdict record of the session, or None."""
    found = None
    for e in entries:
        if (
            e["session_id"] == session_id
            and is_overall(e)
            and e["data"].get("verdict") == NO_STATEMENT
        ):
            found = e
    return found


def no_statement_result(entry: dict) -> dict:
    """A NO_STATEMENT record in the shape `verifier.verify` returns."""
    return {
        "verdicts": [],
        "undeclared": list(entry["data"].get("undeclared", [])),
        "overall": NO_STATEMENT,
    }


def statement_files(root: Path, session_id: str) -> list[tuple[int, Path]]:
    """The session's promoted statement files as (number, path), lowest number first."""
    folder = root / ".papertrail" / "statements"
    found: list[tuple[int, Path]] = []
    if not valid_session_id(session_id) or not folder.is_dir():
        return found
    for path in folder.glob(f"{session_id}-*.json"):
        number = path.stem[len(session_id) + 1:]
        # "x-1" belongs to session "x"; "x-y-1" belongs to session "x-y", not "x".
        if number.isdigit() and path.stem == f"{session_id}-{number}":
            found.append((int(number), path))
    return sorted(found)


def result_for(root: Path, session_id: str, n: int | None = None) -> dict | None:
    """
    What the record says about a session, as {"verdicts", "undeclared", "overall"}.

    n given:   statement number n, checked now (verifier records its verdicts
               once, as always). None if that statement file does not exist.
    n omitted: whichever is newer, the highest-numbered statement or the latest
               NO_STATEMENT verdict. None if the session has neither.

    A statement that cannot be read raises ValueError. An unsafe id gives None.
    """
    if not valid_session_id(session_id):
        return None
    ledger_path = root / ".papertrail" / "ledger.jsonl"
    entries = ledger.read(ledger_path)

    if n is not None:
        path = root / ".papertrail" / "statements" / f"{session_id}-{n}.json"
        if not path.exists():
            return None
        stmt = statement_mod.parse(path)
        return verifier.verify(stmt, entries, session_id, ledger_path=ledger_path)

    files = statement_files(root, session_id)
    stmt = statement_mod.parse(files[-1][1]) if files else None
    silent = latest_no_statement(entries, session_id)
    if stmt is None and silent is None:
        return None
    if stmt is not None and (silent is None or silent["data"]["witness_seq"] < stmt["witness_seq"]):
        return verifier.verify(stmt, entries, session_id, ledger_path=ledger_path)
    return no_statement_result(silent)
