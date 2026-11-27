"""Local, read-only API for the Paper Trail printout.

Started with:  python -m papertrail serve

Binds to 127.0.0.1 only. The endpoints with a side effect are the two
POST /api/verify routes, which append verdict records through verifier.verify
(once; asking again returns the same answer).
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from papertrail import ledger as ledger_mod
from papertrail import outcome

# Only the local Vite dev page may call the API from a browser. The built site is
# static and makes no API calls unless the API happens to be running.
ALLOWED_ORIGIN = "http://localhost:5173"


def _root() -> Path:
    """Project root. Read at request time so tests can redirect it."""
    env = os.environ.get("PAPERTRAIL_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def _ledger_path(root: Path) -> Path:
    return root / ".papertrail" / "ledger.jsonl"


# No docs pages or schema route: the routes below are the whole surface.
app = FastAPI(title="Paper Trail", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _result(session_id: str, n: int | None) -> dict:
    try:
        result = outcome.result_for(_root(), session_id, n)
    except ValueError as exc:  # includes json.JSONDecodeError
        raise HTTPException(status_code=422, detail=f"Statement unreadable: {exc}")
    if result is None:
        raise HTTPException(status_code=404, detail="Statement not found")
    return result


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
    return _result(session_id, n)


@app.post("/api/verify/{session_id}")
def post_verify_latest(session_id: str) -> dict:
    """
    What the record says about a session now: its newest statement checked, or
    the NO_STATEMENT verdict if the agent changed files and said nothing later.
    """
    return _result(session_id, None)
