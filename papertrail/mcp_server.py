"""MCP server (stdio) so the Kiro agent can query its own paper trail.

Run by Kiro through .kiro/settings/mcp.json:

    python -m papertrail.mcp_server

The four handle_* functions hold all the logic and use only the standard
library plus papertrail itself. The MCP SDK is imported lazily inside
build_server(), so the handlers can be tested without it.

stdout carries the protocol, so nothing in this module may print to it.
"""

import os
import re
from pathlib import Path

from papertrail import ledger as ledger_mod
from papertrail import statement as statement_mod
from papertrail import verifier as verifier_mod

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _root() -> Path:
    env = os.environ.get("PAPERTRAIL_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def _ledger_path(root: Path) -> Path:
    return root / ".papertrail" / "ledger.jsonl"


# ---------------------------------------------------------------------------
# Handlers (plain functions, directly testable)
# ---------------------------------------------------------------------------

def handle_list_sessions(root: Path) -> list[dict]:
    """One summary per session, in the order sessions first appear."""
    sessions: dict[str, dict] = {}
    for e in ledger_mod.read(_ledger_path(root)):
        s = sessions.setdefault(e["session_id"], {
            "session_id": e["session_id"],
            "entry_count": 0,
            "has_statement": False,
            "overall_verdict": None,
        })
        s["entry_count"] += 1
        if e["kind"] == "statement":
            s["has_statement"] = True
        if e["kind"] == "verdict" and e["data"].get("kind_detail") == "statement_overall":
            s["overall_verdict"] = e["data"]["verdict"]
    return list(sessions.values())


def handle_get_entries(root: Path, session_id: str) -> list[dict]:
    """Every record of one session, in order. Empty for an unknown session."""
    return [e for e in ledger_mod.read(_ledger_path(root)) if e["session_id"] == session_id]


def handle_check_chain(root: Path) -> dict:
    """Whether the whole record is intact, and where it breaks if not."""
    path = _ledger_path(root)
    entries = ledger_mod.read(path)
    ok, broken_at = ledger_mod.verify_chain(path)
    return {"ok": ok, "broken_at": broken_at, "count": len(entries)}


def handle_verify_statement(root: Path, session_id: str, n: int) -> dict:
    """Check a promoted statement. Returns {"error": ...} if it can't be found."""
    missing = {"error": f"No statement found for session {session_id!r} (number {n})."}
    if not _SESSION_ID_RE.match(session_id) or ".." in session_id:
        return missing
    stmt_path = root / ".papertrail" / "statements" / f"{session_id}-{n}.json"
    if not stmt_path.exists():
        return missing
    try:
        stmt = statement_mod.parse(stmt_path)
    except ValueError as exc:   # includes json.JSONDecodeError
        return {"error": f"The statement could not be read: {exc}"}
    ledger_path = _ledger_path(root)
    entries = ledger_mod.read(ledger_path)
    return verifier_mod.verify(stmt, entries, session_id, ledger_path=ledger_path)


# ---------------------------------------------------------------------------
# MCP wiring
# ---------------------------------------------------------------------------

def build_server():
    """Create the MCP server with its four tools. Imports the SDK lazily."""
    from mcp.server import MCPServer

    server = MCPServer("paper-trail")

    @server.tool()
    def list_sessions() -> list[dict]:
        """List every recorded session with its record count, whether it has a
        statement, and its overall verdict (or null if not yet checked)."""
        return handle_list_sessions(_root())

    @server.tool()
    def get_entries(session_id: str) -> list[dict]:
        """Get every record of one session, in the order it was written."""
        return handle_get_entries(_root(), session_id)

    @server.tool()
    def check_chain() -> dict:
        """Check that the whole record is intact. Reports where it breaks if not."""
        return handle_check_chain(_root())

    @server.tool()
    def verify_statement(session_id: str, n: int = 1) -> dict:
        """Check statement number n of a session against what the witness saw
        and what the records show. Returns a verdict per line, anything the
        statement left out, and an overall verdict."""
        return handle_verify_statement(_root(), session_id, n)

    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
