"""Local, read-only API for the Paper Trail printout.

Started with:  python -m papertrail serve

Binds to 127.0.0.1 only. The one endpoint with a side effect is
POST /api/verify, which appends verdict records through verifier.verify.
"""

import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from papertrail import ledger as ledger_mod
from papertrail import statement as statement_mod
from papertrail import verifier as verifier_mod

# Only the local Vite dev page may call the API from a browser. The built
# site is static and makes no API calls unless the API happens to be running.
ALLOWED_ORIGIN = "http://localhost:5173"

# Session ids become part of a file name, so accept a conservative alphabet.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _root() -> Path:
    """Project root. Read at request time so tests can redirect it."""
    env = os.environ.get("PAPERTRAIL_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def _ledger_path(root: Path) -> Path:
    return root / ".papertrail" / "ledger.jsonl"


def _statement_path(root: Path, session_id: str, n: int) -> Path | None:
    """Path to a promoted statement, or None if the id is not acceptable."""
    if not _SESSION_ID_RE.match(session_id) or ".." in session_id:
        return None
    return root / ".papertrail" / "statements" / f"{session_id}-{n}.json"


# No docs pages or schema route: the three endpoints below are the whole surface.
app = FastAPI(title="Paper Trail", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/ledger")
def get_ledger() -> list:
    """Every record, in the order it was written. Empty list if none yet."""
    return ledger_mod.read(_ledger_path(_root()))


@app.get("/api/chain")
def get_chain() -> dict:
    """Whether the record is intact, and where it breaks if not."""
    path = _ledger_path(_root())
    entries = ledger_mod.read(path)
    ok, broken_at = ledger_mod.verify_chain(path)
    return {"ok": ok, "broken_at": broken_at, "count": len(entries)}


@app.post("/api/verify/{session_id}/{n}")
def post_verify(session_id: str, n: int) -> dict:
    """Check one promoted statement against the witness and the records."""
    root = _root()
    stmt_path = _statement_path(root, session_id, n)
    if stmt_path is None or not stmt_path.exists():
        raise HTTPException(status_code=404, detail="Statement not found")
    try:
        stmt = statement_mod.parse(stmt_path)
    except ValueError as exc:   # includes json.JSONDecodeError
        raise HTTPException(status_code=422, detail=f"Statement unreadable: {exc}")
    ledger_path = _ledger_path(root)
    entries = ledger_mod.read(ledger_path)
    return verifier_mod.verify(stmt, entries, session_id, ledger_path=ledger_path)
