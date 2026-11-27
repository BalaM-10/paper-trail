"""Tests for papertrail/api.py and the serve subcommand.

Every test points PAPERTRAIL_ROOT at tmp_path, so the project's own
.papertrail folder is never read or written. No server is started.
"""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from papertrail import ledger as ledger_mod
from papertrail.api import ALLOWED_ORIGIN, app


@pytest.fixture
def root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("PAPERTRAIL_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def client(root) -> TestClient:
    return TestClient(app)


def _ledger_path(root: Path) -> Path:
    return root / ".papertrail" / "ledger.jsonl"


def _seed_session(root: Path, sid: str = "sess-api") -> dict:
    """A witness/stop that deleted two files and a statement that names one."""
    lp = _ledger_path(root)
    ledger_mod.append(lp, sid, "witness", {"event": "start", "snapshot": {}})
    stop = ledger_mod.append(lp, sid, "witness", {
        "event": "stop",
        "snapshot": {},
        "diff": {"created": [], "deleted": ["a.txt", "b.txt"], "modified": []},
        "baseline": "start",
    })
    stmt = {
        "summary": "Removed a.",
        "files_read": [], "files_created": [], "files_modified": [],
        "files_deleted": ["a.txt"],
        "session_id": sid,
        "ts": "2026-01-01T00:00:00+00:00",
        "witness_seq": stop["seq"],
    }
    stmts = root / ".papertrail" / "statements"
    stmts.mkdir(parents=True, exist_ok=True)
    (stmts / f"{sid}-1.json").write_text(json.dumps(stmt), encoding="utf-8")
    return stmt


# --- GET /api/ledger -------------------------------------------------------

def test_ledger_returns_entries_in_order(client, root):
    lp = _ledger_path(root)
    for i in range(3):
        ledger_mod.append(lp, "s", "tool", {"i": i})
    resp = client.get("/api/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert [e["seq"] for e in body] == [1, 2, 3]
    assert [e["data"]["i"] for e in body] == [0, 1, 2]


def test_ledger_empty_when_absent(client):
    resp = client.get("/api/ledger")
    assert resp.status_code == 200
    assert resp.json() == []


def test_ledger_with_10000_records_is_fast(client, root):
    lp = _ledger_path(root)
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "w", encoding="utf-8") as f:
        for i in range(1, 10_001):
            f.write(json.dumps({
                "seq": i, "ts": "t", "session_id": "s", "kind": "tool",
                "data": {"i": i}, "prev_hash": "p", "hash": "h",
            }) + "\n")
    start = time.perf_counter()
    resp = client.get("/api/ledger")
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert len(resp.json()) == 10_000
    assert elapsed < 2.0


# --- GET /api/chain --------------------------------------------------------

def test_chain_ok(client, root):
    lp = _ledger_path(root)
    for i in range(4):
        ledger_mod.append(lp, "s", "tool", {"i": i})
    assert client.get("/api/chain").json() == {"ok": True, "broken_at": None, "count": 4}


def test_chain_broken_reports_seq(client, root):
    lp = _ledger_path(root)
    for i in range(4):
        ledger_mod.append(lp, "s", "tool", {"i": i})
    lines = lp.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[2])          # seq 3
    entry["data"]["i"] = 999
    lines[2] = json.dumps(entry, separators=(",", ":"))
    lp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert client.get("/api/chain").json() == {"ok": False, "broken_at": 3, "count": 4}


def test_chain_empty_ledger_is_ok(client):
    assert client.get("/api/chain").json() == {"ok": True, "broken_at": None, "count": 0}


# --- POST /api/verify ------------------------------------------------------

def test_verify_returns_result_and_stores_undeclared(client, root):
    _seed_session(root)
    resp = client.post("/api/verify/sess-api/1")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"verdicts", "undeclared", "overall"}
    assert body["overall"] == "CONTRADICTED"
    assert body["undeclared"] == [{"path": "b.txt", "change": "deleted"}]

    stored = [
        e for e in ledger_mod.read(_ledger_path(root))
        if e["kind"] == "verdict" and e["data"].get("kind_detail") == "statement_overall"
    ]
    assert len(stored) == 1
    assert stored[0]["data"]["undeclared"] == [{"path": "b.txt", "change": "deleted"}]


def test_verify_is_idempotent(client, root):
    _seed_session(root)
    first = client.post("/api/verify/sess-api/1").json()
    count = len(ledger_mod.read(_ledger_path(root)))
    second = client.post("/api/verify/sess-api/1").json()
    assert second == first
    assert len(ledger_mod.read(_ledger_path(root))) == count


def test_verify_missing_statement_is_404(client):
    assert client.post("/api/verify/no-such-session/1").status_code == 404


def test_verify_wrong_index_is_404(client, root):
    _seed_session(root)
    assert client.post("/api/verify/sess-api/2").status_code == 404


@pytest.mark.parametrize("bad_id", ["..%5Csecret", "%2e%2e", "a%5Cb", ".hidden", "a..b"])
def test_verify_rejects_unsafe_session_ids(client, root, bad_id):
    _seed_session(root)
    assert client.post(f"/api/verify/{bad_id}/1").status_code == 404


def test_verify_unreadable_statement_is_422(client, root):
    stmts = root / ".papertrail" / "statements"
    stmts.mkdir(parents=True)
    (stmts / "broken-1.json").write_text("{ not json", encoding="utf-8")
    assert client.post("/api/verify/broken/1").status_code == 422


def test_verify_never_writes_outside_tmp_root(client, root):
    project_ledger = Path(__file__).resolve().parents[1] / ".papertrail" / "ledger.jsonl"
    before = project_ledger.read_text(encoding="utf-8") if project_ledger.exists() else ""
    _seed_session(root, "sess-isolation-check")
    client.post("/api/verify/sess-isolation-check/1")
    after = project_ledger.read_text(encoding="utf-8") if project_ledger.exists() else ""
    assert "sess-isolation-check" not in after.replace(before, "", 1)


# --- CORS and surface area -------------------------------------------------

def test_cors_allows_only_the_dev_origin(client):
    ok = client.get("/api/ledger", headers={"Origin": ALLOWED_ORIGIN})
    assert ok.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN

    other = client.get("/api/ledger", headers={"Origin": "http://evil.example"})
    assert other.headers.get("access-control-allow-origin") is None
    assert "*" not in ok.headers.get("access-control-allow-origin", "")


def test_only_documented_routes_exist():
    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }
    assert routes == {
        ("GET", "/api/ledger"),
        ("GET", "/api/chain"),
        ("POST", "/api/verify/{session_id}/{n}"),
        ("POST", "/api/verify/{session_id}"),
    }


def test_ledger_rejects_writes(client):
    assert client.post("/api/ledger", json={}).status_code == 405
    assert client.put("/api/ledger", json={}).status_code == 405
    assert client.delete("/api/ledger").status_code == 405


# --- serve subcommand (uvicorn.run is replaced; nothing is started) --------

@pytest.fixture
def fake_uvicorn(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr("uvicorn.run", lambda application, **kw: calls.append(kw))
    return calls


def test_serve_defaults_to_loopback_8765(fake_uvicorn, capsys):
    from papertrail.__main__ import main
    assert main(["serve"]) == 0
    assert fake_uvicorn == [{"host": "127.0.0.1", "port": 8765, "log_level": "warning"}]
    assert "http://127.0.0.1:8765" in capsys.readouterr().out


def test_serve_port_option(fake_uvicorn):
    from papertrail.__main__ import main
    assert main(["serve", "--port", "9000"]) == 0
    assert fake_uvicorn[0]["port"] == 9000
    assert fake_uvicorn[0]["host"] == "127.0.0.1"


@pytest.mark.parametrize("args", [["serve", "--port"], ["serve", "--port", "abc"]])
def test_serve_bad_port_exits_1_without_starting(fake_uvicorn, args, capsys):
    from papertrail.__main__ import main
    assert main(args) == 1
    assert fake_uvicorn == []
    assert "--port" in capsys.readouterr().err


# --- NO_STATEMENT (R2.2) -----------------------------------------------------

from papertrail.session import on_start, on_stop


def _silent_session(root: Path, sid: str, *names: str) -> None:
    on_start({"session_id": sid}, root, Path.home())
    for name in names:
        (root / name).write_text("x", encoding="utf-8")
    on_stop({"session_id": sid}, root, Path.home())


def test_ledger_carries_the_no_statement_verdict_like_any_other(client, root):
    _silent_session(root, "quiet", "a.txt")
    body = client.get("/api/ledger").json()
    verdict = body[-1]
    assert verdict["kind"] == "verdict"
    assert verdict["data"]["verdict"] == "NO_STATEMENT"
    assert verdict["data"]["undeclared"] == [{"path": "a.txt", "change": "created"}]
    assert client.get("/api/chain").json()["ok"] is True


def test_verify_latest_reports_a_silent_session(client, root):
    _silent_session(root, "quiet", "b.txt", "a.txt")
    before = len(ledger_mod.read(_ledger_path(root)))
    resp = client.post("/api/verify/quiet")
    assert resp.status_code == 200
    assert resp.json() == {
        "verdicts": [],
        "undeclared": [{"path": "a.txt", "change": "created"}, {"path": "b.txt", "change": "created"}],
        "overall": "NO_STATEMENT",
    }
    assert len(ledger_mod.read(_ledger_path(root))) == before  # nothing was written


def test_verify_latest_checks_the_newest_statement_when_there_is_one(client, root):
    _seed_session(root)
    resp = client.post("/api/verify/sess-api")
    assert resp.status_code == 200
    assert set(resp.json()) == {"verdicts", "undeclared", "overall"}
    assert resp.json()["overall"] == "CONTRADICTED"


def test_the_numbered_route_still_needs_a_statement_file(client, root):
    _silent_session(root, "quiet", "a.txt")
    assert client.post("/api/verify/quiet/1").status_code == 404


def test_verify_latest_for_nobody_is_404(client):
    assert client.post("/api/verify/nobody").status_code == 404


@pytest.mark.parametrize("bad_id", ["..%5Csecret", "%2e%2e", ".hidden", "a..b"])
def test_verify_latest_refuses_unsafe_ids(client, root, bad_id):
    _silent_session(root, "quiet", "a.txt")
    assert client.post(f"/api/verify/{bad_id}").status_code == 404


def test_verify_latest_with_an_unreadable_statement_is_422(client, root):
    folder = root / ".papertrail" / "statements"
    folder.mkdir(parents=True)
    (folder / "broken-1.json").write_text("{ not json", encoding="utf-8")
    assert client.post("/api/verify/broken").status_code == 422