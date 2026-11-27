"""MCP server (stdio) so the Kiro agent can query its own paper trail.

Run by Kiro through .kiro/settings/mcp.json:

    python -m papertrail.mcp_server

The handle_* functions hold all the logic and use only the standard library plus
papertrail itself. The MCP SDK is imported lazily inside build_server(), so the
handlers can be tested without it.

stdout carries the protocol, so nothing in this module may print to it.
"""

import os
from pathlib import Path

from papertrail import ledger as ledger_mod
from papertrail import outcome, spool


def _root() -> Path:
    env = os.environ.get("PAPERTRAIL_ROOT")
    return Path(env) if env else Path.cwd()  # the project, not the install folder


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
        if outcome.is_overall(e):
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


def handle_verify_statement(root: Path, session_id: str, n: int | None = None) -> dict:
    """
    Check statement number n, or (no number) report whichever is newer: the
    latest statement or a NO_STATEMENT verdict. Returns {"error": ...} if the
    session has neither, or the statement cannot be read.
    """
    try:
        result = outcome.result_for(root, session_id, n)
    except ValueError as exc:  # includes json.JSONDecodeError
        return {"error": f"The statement could not be read: {exc}"}
    if result is None:
        where = f" (number {n})" if n is not None else ""
        return {"error": f"No statement found for session {session_id!r}{where}."}
    return result


def handle_print_session(root: Path, session_id: str) -> str:
    """The print-ready text of one session: exactly what `papertrail print` writes."""
    try:
        return spool.render_session(root, session_id)
    except LookupError as exc:
        return f"Error: {exc}."


# ---------------------------------------------------------------------------
# MCP wiring
# ---------------------------------------------------------------------------

def build_server():
    """Create the MCP server with its five tools. Imports the SDK lazily."""
    from mcp.server import MCPServer

    server = MCPServer("paper-trail")

    @server.tool()
    def list_sessions() -> list[dict]:
        """List every recorded session with its record count, whether it has a
        statement, and its overall verdict (or null if not yet checked). A
        session where the agent changed files and wrote no statement has the
        verdict NO_STATEMENT."""
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
    def verify_statement(session_id: str, n: int | None = None) -> dict:
        """Check statement number n of a session against what the witness saw
        and what the records show. Without n, report the newest outcome: the
        latest statement checked, or NO_STATEMENT. Returns a verdict per line,
        anything the statement left out, and an overall verdict."""
        return handle_verify_statement(_root(), session_id, n)

    @server.tool()
    def print_session(session_id: str) -> str:
        """Get a print-ready text of one session: plain text, 80 columns, with
        line numbers, the verdicts, and a fingerprint of the whole record on the
        last line."""
        return handle_print_session(_root(), session_id)

    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
