# Design — Paper Trail Printout

## Overview

```
sample/make_demo_ledger.py   two sessions → one ledger → web/public/demo/
papertrail/verifier.py       updated: overall entry stores undeclared list
papertrail/api.py            FastAPI, 127.0.0.1:8765, read-only + verify
papertrail/mcp_server.py     stdio MCP, 4 tools
web/                         React + TypeScript + Vite printout view
tests/                       pytest + Vitest
```

Data flows one way. Nothing here writes to the ledger except
`verifier.verify`, which is idempotent.

---

## 1. `papertrail/verifier.py` — undeclared list in overall entry

The only change to a core module. In the existing `verify` function two lines
change:

**Ledger write for overall entry** (was):
```python
ledger_mod.append(ledger_path, session_id, "verdict", {
    "kind_detail":  "statement_overall",
    "verdict":      overall,
    "evidence_seq": all_evidence,
    "witness_seq":  witness_seq,
})
```

**After change** — add `undeclared`:
```python
ledger_mod.append(ledger_path, session_id, "verdict", {
    "kind_detail":  "statement_overall",
    "verdict":      overall,
    "evidence_seq": all_evidence,
    "witness_seq":  witness_seq,
    "undeclared":   undeclared,          # ← new field
})
```

**Idempotency path** — existing reconstruction reads:
```python
undeclared = existing_overall["data"].get("undeclared", [])
```

No other change to `verifier.py`. All existing tests continue to pass because
the `undeclared` key was already present in the returned dict; it is now also
written to the ledger entry.

**New test in `tests/test_verifier.py`:**
```python
def test_undeclared_stored_in_overall_entry(tmp_path):
    # build a session with one undeclared deleted file
    sid = "sess-undecl-stored"
    stop = _make_witness_stop_entry(tmp_path, sid,
        {"created": [], "deleted": ["secret.txt"], "modified": []})
    stmt = _make_statement(tmp_path, sid, witness_seq=stop["seq"])
    _run_verify(tmp_path, stmt, sid)
    ledger_path = tmp_path / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)
    overall = next(
        e for e in entries
        if e["kind"] == "verdict"
        and e["data"].get("kind_detail") == "statement_overall"
    )
    assert overall["data"]["undeclared"] == [{"path": "secret.txt", "change": "deleted"}]
```

---

## 2. `sample/make_demo_ledger.py`

### Public interface

```python
def generate(out_path: Path) -> None:
    """
    Build the two-session demo ledger and write it to out_path.
    out_path's parent directory is created if absent.
    """

if __name__ == "__main__":
    default = Path(__file__).resolve().parents[1] / "web" / "public" / "demo" / "ledger.jsonl"
    generate(default)
```

### Implementation

```python
import tempfile, shutil
from pathlib import Path
from datetime import timezone, datetime
from papertrail.session import on_start, on_stop
from papertrail.recorder import record
from papertrail import ledger, verifier, statement as stmt_mod

def generate(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    home = Path.home()

    with tempfile.TemporaryDirectory() as _tmp:
        root = Path(_tmp)

        # ── Session A ────────────────────────────────────────────────
        sid_a = "demo-session-a"
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text('print("hello")\n')

        on_start({"session_id": sid_a}, root, home)

        (root / "docs").mkdir()
        (root / "docs" / "notes.md").write_text("Notes.\n")

        record({
            "session_id": sid_a,
            "tool_name": "read_file",
            "hook_event_name": "PostToolUse",
            "tool_input": {"path": str(root / "src" / "main.py")},
            "tool_response": 'print("hello")',
        }, root, home)
        record({
            "session_id": sid_a,
            "tool_name": "fs_write",
            "hook_event_name": "PostToolUse",
            "tool_input": {"path": str(root / "docs" / "notes.md"), "text": "Notes.\n"},
            "tool_response": "written",
        }, root, home)

        _write_statement(root, {
            "summary": "Read main.py and created notes.",
            "files_read":     ["src/main.py"],
            "files_created":  ["docs/notes.md"],
            "files_modified": [],
            "files_deleted":  [],
        })
        on_stop({"session_id": sid_a}, root, home)

        # find the promoted statement for Session A
        stmts_dir = root / ".papertrail" / "statements"
        stmt_a_path = stmts_dir / f"{sid_a}-1.json"
        stmt_a = stmt_mod.parse(stmt_a_path)
        entries = ledger.read(root / ".papertrail" / "ledger.jsonl")
        verifier.verify(stmt_a, entries, sid_a)

        # ── Session B ────────────────────────────────────────────────
        sid_b = "demo-session-b"
        (root / "sample" / "cache").mkdir(parents=True)
        (root / "sample" / "notes.txt").write_text("Project notes.\n")
        (root / "sample" / "cache" / "output.bin").write_bytes(b"\x00FAKE\x00")

        on_start({"session_id": sid_b}, root, home)

        (root / "sample" / "notes.txt").unlink()
        (root / "sample" / "cache" / "output.bin").unlink()

        record({
            "session_id": sid_b,
            "tool_name": "execute_pwsh",
            "hook_event_name": "PostToolUse",
            "tool_input": {"command": "python sample/cleanup.py",
                           "description": "Clear the build cache"},
            "tool_response": "Cleared build cache: removed cache/output.bin",
        }, root, home)

        _write_statement(root, {
            "summary": "Cleared the build cache.",
            "files_read":     [],
            "files_created":  [],
            "files_modified": [],
            "files_deleted":  ["sample/cache/output.bin"],
        })
        on_stop({"session_id": sid_b}, root, home)

        stmt_b_path = stmts_dir / f"{sid_b}-1.json"
        stmt_b = stmt_mod.parse(stmt_b_path)
        entries = ledger.read(root / ".papertrail" / "ledger.jsonl")
        verifier.verify(stmt_b, entries, sid_b)

        # ── Copy finished ledger ──────────────────────────────────────
        shutil.copy(root / ".papertrail" / "ledger.jsonl", out_path)


def _write_statement(root: Path, data: dict) -> None:
    stmt_path = root / ".papertrail" / "statement.json"
    stmt_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    stmt_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

Both sessions run against the same `root`, so `ledger.append` writes to the
same file and the chain is naturally contiguous — no merging.

---

## 3. `papertrail/api.py`

```python
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from papertrail import ledger as ledger_mod, verifier as verifier_mod
from papertrail import statement as stmt_mod

def _root() -> Path:
    env = os.environ.get("PAPERTRAIL_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/api/ledger")
def get_ledger() -> list:
    return ledger_mod.read(_root() / ".papertrail" / "ledger.jsonl")

@app.get("/api/chain")
def get_chain() -> dict:
    p = _root() / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(p)
    ok, broken_at = ledger_mod.verify_chain(p)
    return {"ok": ok, "broken_at": broken_at, "count": len(entries)}

@app.post("/api/verify/{session_id}/{n}")
def post_verify(session_id: str, n: int) -> dict:
    root = _root()
    stmt_path = root / ".papertrail" / "statements" / f"{session_id}-{n}.json"
    if not stmt_path.exists():
        raise HTTPException(status_code=404, detail="Statement not found")
    stmt = stmt_mod.parse(stmt_path)
    entries = ledger_mod.read(root / ".papertrail" / "ledger.jsonl")
    return verifier_mod.verify(stmt, entries, session_id)
```

`_root()` is called at request time so `PAPERTRAIL_ROOT` changes in tests take
effect without restarting the app.

### Serve subcommand addition to `__main__.py`

```python
elif cmd == "serve":
    import uvicorn
    from papertrail.api import app
    port = 8765
    if "--port" in rest:
        port = int(rest[rest.index("--port") + 1])
    print(f"Paper Trail → http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
```

### `tests/test_api.py` fixture pattern

```python
import pytest, os, json
from pathlib import Path
from papertrail import ledger as ledger_mod

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERTRAIL_ROOT", str(tmp_path))
    # Import after env is set so _root() resolves to tmp_path.
    from fastapi.testclient import TestClient
    from papertrail.api import app
    return TestClient(app), tmp_path
```

---

## 4. `papertrail/mcp_server.py`

### Handler functions (testable without MCP transport)

```python
from pathlib import Path
from papertrail import ledger as ledger_mod, verifier as verifier_mod
from papertrail import statement as stmt_mod

def _root() -> Path:
    import os
    env = os.environ.get("PAPERTRAIL_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent

def handle_list_sessions(root: Path) -> list[dict]:
    entries = ledger_mod.read(root / ".papertrail" / "ledger.jsonl")
    seen: dict[str, dict] = {}
    for e in entries:
        sid = e["session_id"]
        if sid not in seen:
            seen[sid] = {"session_id": sid, "entry_count": 0,
                         "has_statement": False, "overall_verdict": None}
        seen[sid]["entry_count"] += 1
        if e["kind"] == "statement":
            seen[sid]["has_statement"] = True
        if (e["kind"] == "verdict"
                and e["data"].get("kind_detail") == "statement_overall"):
            seen[sid]["overall_verdict"] = e["data"]["verdict"]
    return list(seen.values())

def handle_get_entries(root: Path, session_id: str) -> list[dict]:
    return [e for e in ledger_mod.read(root / ".papertrail" / "ledger.jsonl")
            if e["session_id"] == session_id]

def handle_check_chain(root: Path) -> dict:
    p = root / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(p)
    ok, broken_at = ledger_mod.verify_chain(p)
    return {"ok": ok, "broken_at": broken_at, "count": len(entries)}

def handle_verify_statement(root: Path, session_id: str, n: int) -> dict:
    stmt_path = root / ".papertrail" / "statements" / f"{session_id}-{n}.json"
    if not stmt_path.exists():
        return {"error": f"No statement found for session {session_id!r} index {n}."}
    stmt = stmt_mod.parse(stmt_path)
    entries = ledger_mod.read(root / ".papertrail" / "ledger.jsonl")
    return verifier_mod.verify(stmt, entries, session_id)
```

### MCP wiring

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
import asyncio, json

server = Server("paper-trail")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name="list_sessions",    description="List all sessions.", inputSchema={"type":"object","properties":{}}),
        types.Tool(name="get_entries",      description="Get all records for a session.",
                   inputSchema={"type":"object","properties":{"session_id":{"type":"string"}},"required":["session_id"]}),
        types.Tool(name="check_chain",      description="Check paper integrity.", inputSchema={"type":"object","properties":{}}),
        types.Tool(name="verify_statement", description="Verify a session's statement.",
                   inputSchema={"type":"object","properties":{"session_id":{"type":"string"},"n":{"type":"integer"}},"required":["session_id","n"]}),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    root = _root()
    if name == "list_sessions":
        result = handle_list_sessions(root)
    elif name == "get_entries":
        result = handle_get_entries(root, arguments["session_id"])
    elif name == "check_chain":
        result = handle_check_chain(root)
    elif name == "verify_statement":
        result = handle_verify_statement(root, arguments["session_id"], arguments["n"])
    else:
        result = {"error": f"Unknown tool: {name}"}
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

async def _main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(_main())
```

### `.kiro/settings/mcp.json`

```json
{
  "mcpServers": {
    "paper-trail": {
      "command": "python",
      "args": ["-m", "papertrail.mcp_server"],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

---

## 5. Web app: `web/`

### Project scaffold

```
web/
  public/
    demo/
      ledger.jsonl
  src/
    main.tsx
    App.tsx
    hooks/
      useEntries.ts         initial fetch + live polling
      useChainCheck.ts      browser SHA-256 verification
      useReplay.ts          play/pause/step/speed state machine
    components/
      Header.tsx            heading + one-sentence explanation
      Footer.tsx            GitHub link
      SessionSpool.tsx      spool card; "Check this statement" button
      PaperRoll.tsx         fan-fold paper shell
      TractorHoles.tsx      tractor holes (left and right)
      PrintLine.tsx         one rendered line
      Stamp.tsx             verdict stamp overlay
      UndeclaredCircle.tsx  red circle + link to witness stop line
      TearLine.tsx          SVG jagged tear
      ChainStatus.tsx       "Paper intact" / "Paper torn at line N"
      ReplayControls.tsx    play/pause/step + speed
      LiveIndicator.tsx     "LIVE" badge (live mode only)
      GhostClerk.tsx        inline SVG ghost + message
      TearOffButton.tsx     window.print()
    lib/
      canonicalJson.ts      sorted-key JSON serialiser
      chainCheck.ts         Web Crypto chain verifier
      entryText.ts          entry → plain-language string
      sessionMeta.ts        derive session title / overall verdict from entries
    styles/
      paper.css
      stamps.css
      print.css
    __tests__/
      chainCheck.test.ts    fixture hash + demo ledger chain
      Stamp.test.tsx
      ChainStatus.test.tsx
  vite.config.ts
  tsconfig.json
  package.json
```

### `vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  define: {
    __REPO_URL__: JSON.stringify("https://github.com/YOUR_ORG/paper-trail"),
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/__tests__/setup.ts",
  },
});
```

`__REPO_URL__` is used in `<Footer>`. The placeholder must be replaced with
the real repository URL before publishing; it must not be an empty string in
the committed config.

---

### `lib/canonicalJson.ts`

Python's `json.dumps(obj, sort_keys=True, separators=(',',':'), ensure_ascii=False)`
is replicated with:

```ts
export function canonicalJson(obj: unknown): string {
  if (obj === null || typeof obj !== "object")
    return JSON.stringify(obj);           // handles strings, numbers, booleans
  if (Array.isArray(obj))
    return "[" + obj.map(canonicalJson).join(",") + "]";
  const sorted = Object.keys(obj as object).sort();
  return (
    "{" +
    sorted
      .map(k => JSON.stringify(k) + ":" + canonicalJson((obj as Record<string,unknown>)[k]))
      .join(",") +
    "}"
  );
}
```

`JSON.stringify` on a string in modern JS engines preserves non-ASCII
characters (codepoints > 127) literally when the runtime's JSON serialiser
uses `ensure_ascii=false` semantics. It does escape control characters below
U+0020 as `\uXXXX` — matching Python's behaviour with `ensure_ascii=False`,
which also escapes those characters. The hash fixture (which includes `\t`,
U+0001, and an emoji) confirms this alignment. No post-processing of escape
sequences is applied.

Verification: for every character class in the fixture, Python and the browser
independently produce the same `expected_hash`. That test is the contract.

---

### `lib/chainCheck.ts`

```ts
import { canonicalJson } from "./canonicalJson";

export type Entry = {
  seq: number; ts: string; session_id: string; kind: string;
  data: unknown; prev_hash: string; hash: string;
};

export type ChainResult =
  | { ok: true;  count: number }
  | { ok: false; brokenAt: number; count: number };

export async function checkChain(entries: Entry[]): Promise<ChainResult> {
  let expectedPrev = "0".repeat(64);
  let expectedSeq  = 1;
  for (const entry of entries) {
    if (entry.seq !== expectedSeq)
      return { ok: false, brokenAt: entry.seq, count: entries.length };
    const { hash, ...without } = entry;
    const bytes = new TextEncoder().encode(canonicalJson(without));
    const buf   = await crypto.subtle.digest("SHA-256", bytes);
    const hex   = Array.from(new Uint8Array(buf))
                       .map(b => b.toString(16).padStart(2,"0")).join("");
    if (hex !== entry.hash || entry.prev_hash !== expectedPrev)
      return { ok: false, brokenAt: entry.seq, count: entries.length };
    expectedPrev = entry.hash;
    expectedSeq++;
  }
  return { ok: true, count: entries.length };
}
```

---

### `hooks/useEntries.ts`

```ts
import { useState, useEffect, useRef } from "react";
import type { Entry } from "../lib/chainCheck";

export type Source = "loading" | "api" | "demo";

export function useEntries() {
  const [entries, setEntries]     = useState<Entry[]>([]);
  const [source, setSource]       = useState<Source>("loading");
  const originalRef               = useRef<Entry[]>([]);   // untampered copy
  const [displayed, setDisplayed] = useState<Entry[]>([]);

  // Initial load
  useEffect(() => {
    fetch("/api/ledger")
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then((data: Entry[]) => {
        setEntries(data);
        originalRef.current = data;
        setDisplayed(data);
        setSource("api");
      })
      .catch(() =>
        fetch("./demo/ledger.jsonl")
          .then(r => r.text())
          .then(text => {
            const data = text.trim().split("\n").filter(Boolean)
                             .map(l => JSON.parse(l) as Entry);
            setEntries(data);
            originalRef.current = data;
            setDisplayed(data);
            setSource("demo");
          })
      );
  }, []);

  // Polling (live mode only)
  useEffect(() => {
    if (source !== "api") return;
    const id = setInterval(() => {
      fetch("/api/ledger")
        .then(r => r.ok ? r.json() : Promise.reject())
        .then((data: Entry[]) => {
          if (data.length > entries.length) {
            setEntries(data);
            originalRef.current = data;
            setDisplayed(data);
          }
        })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(id);
  }, [source, entries.length]);

  function tamper(seq: number) {
    const copy = displayed.map(e =>
      e.seq === seq ? { ...e, data: { ...(e.data as object), _tampered: true } } : e
    );
    setDisplayed(copy);
  }

  function restore() {
    setDisplayed(originalRef.current);
  }

  return { entries: displayed, source, tamper, restore };
}
```

`displayed` is what `useChainCheck` and the UI consume. `tamper()` mutates
`displayed` in memory; `restore()` resets it from `originalRef`.

---

### `hooks/useChainCheck.ts`

```ts
import { useEffect, useState } from "react";
import { checkChain, type ChainResult, type Entry } from "../lib/chainCheck";

export function useChainCheck(entries: Entry[]) {
  const [result, setResult] = useState<ChainResult | null>(null);
  useEffect(() => {
    if (!entries.length) { setResult(null); return; }
    checkChain(entries).then(setResult);
  }, [entries]);
  return result;
}
```

---

### `hooks/useReplay.ts`

```ts
import { useState, useEffect, useRef } from "react";
import type { Entry } from "../lib/chainCheck";

export type ReplayState = "idle" | "playing" | "paused" | "done";

export function useReplay(sessionEntries: Entry[]) {
  const [state, setState]   = useState<ReplayState>("idle");
  const [cursor, setCursor] = useState(0);
  const [speed, setSpeed]   = useState(400);
  const timer               = useRef<ReturnType<typeof setTimeout>>();

  function step()  { setCursor(c => Math.min(c + 1, sessionEntries.length)); }
  function play()  { if (cursor >= sessionEntries.length) setCursor(0); setState("playing"); }
  function pause() { setState("paused"); }
  function reset() { setState("idle"); setCursor(0); }

  useEffect(() => {
    clearTimeout(timer.current);
    if (state !== "playing") return;
    if (cursor >= sessionEntries.length) { setState("done"); return; }
    timer.current = setTimeout(() => setCursor(c => c + 1), speed);
    return () => clearTimeout(timer.current);
  }, [state, cursor, speed, sessionEntries.length]);

  return { state, cursor, speed, setSpeed, step, play, pause, reset };
}
```

---

### `lib/entryText.ts`

Maps an `Entry` to its plain-language display string.

```ts
import type { Entry } from "./chainCheck";

const TOOL_VERB: Record<string, string> = {
  read_file:    "read",
  fs_write:     "wrote",
  str_replace:  "edited",
  execute_pwsh: "ran the command",
};

export function entryText(entry: Entry): string {
  const d = entry.data as Record<string, unknown>;

  if (entry.kind === "witness") {
    if (d.event === "start")
      return "Witness took a snapshot of the project.";
    const diff = d.diff as Record<string, string[]> | undefined;
    const created  = diff?.created  ?? [];
    const modified = diff?.modified ?? [];
    const deleted  = diff?.deleted  ?? [];
    const parts: string[] = [];
    if (created.length)  parts.push("Created: "  + created.join(", "));
    if (modified.length) parts.push("Changed: "  + modified.join(", "));
    if (deleted.length)  parts.push("Deleted: "  + deleted.join(", "));
    const summary = parts.length ? parts.join(". ") + "." : "No changes.";
    return `Witness compared the project to the earlier snapshot. ${summary}`;
  }

  if (entry.kind === "tool") {
    const name = String(d.tool_name ?? "unknown");
    const verb = TOOL_VERB[name];
    const ti   = d.tool_input as Record<string, string> | undefined;
    if (verb === "ran the command") {
      const cmd = String(ti?.command ?? "").slice(0, 80);
      return `Agent ran the command: ${cmd}.`;
    }
    if (verb) {
      const path = ti?.path ?? "";
      return `Agent ${verb} ${path}.`;
    }
    return `Agent used a tool: ${name}.`;
  }

  if (entry.kind === "statement")
    return `Agent stated: ${String(d.summary ?? "")}`;

  if (entry.kind === "verdict") {
    if (d.kind_detail === "statement_overall")
      return `Overall verdict: ${d.verdict}`;
    const seqs = (d.evidence_seq as number[]) ?? [];
    const ref  = seqs.length ? `  (line ${seqs.join(", ")})` : "";
    return `${d.path}: ${d.verdict}${ref}`;
  }

  if (entry.kind === "error")
    return `Something went wrong: ${String(d.error ?? "unknown error")}.`;

  return `Record: ${entry.kind}.`;
}

/** Synthesise display lines for undeclared changes from the overall verdict entry. */
export function undeclaredText(item: { path: string; change: string }): string {
  return `Witness saw ${item.path} ${item.change}. The agent never mentioned it.`;
}
```

The per-path verdict line includes the evidence line number(s) in parentheses,
satisfying the tear-off report requirement.

---

### `lib/sessionMeta.ts`

```ts
import type { Entry } from "./chainCheck";

export type SessionMeta = {
  sessionId: string;
  title: string;              // statement summary or first-8-chars fallback
  overallVerdict: string | null;
  hasUnverifiedStatement: boolean;
  statementIndex: number | null;
};

export function buildSessionMeta(entries: Entry[]): SessionMeta[] {
  const map = new Map<string, SessionMeta>();
  for (const e of entries) {
    if (!map.has(e.session_id)) {
      map.set(e.session_id, {
        sessionId: e.session_id,
        title: e.session_id.slice(0, 8),
        overallVerdict: null,
        hasUnverifiedStatement: false,
        statementIndex: null,
      });
    }
    const m = map.get(e.session_id)!;
    if (e.kind === "statement") {
      const d = e.data as Record<string, unknown>;
      if (d.summary) m.title = String(d.summary);
      m.hasUnverifiedStatement = true;
      m.statementIndex = typeof d.witness_seq === "number" ? 1 : null; // simplified
    }
    if (e.kind === "verdict" && (e.data as Record<string,unknown>).kind_detail === "statement_overall") {
      m.overallVerdict = String((e.data as Record<string,unknown>).verdict);
      m.hasUnverifiedStatement = false;
    }
  }
  return [...map.values()];
}
```

`statementIndex` tracks which statement number to pass to `POST /api/verify`.
The generator always produces `-1.json` so this is 1 for the demo.

---

### Component: `<GhostClerk>`

#### SVG design

The ghost is a custom inline SVG: a rounded rectangular white sheet (the
ghost's body) with two small black dot eyes, a small curved mouth, and a
bright green visor (clerk's eyeshade) across the upper portion. It has no
arms, legs, or feet — just a simple hovering form with a slightly ragged
bottom edge (three bumps) to suggest a ghost. It must not resemble Pac-Man
ghosts, Casper, or Boo from Nintendo.

Three expressions controlled by props:

- **calm**: neutral straight mouth (a short horizontal line), eyes are
  simple filled circles.
- **pleased**: mouth curves up (arc pointing upward), eyes slightly smaller
  and further apart.
- **alarmed**: mouth is a small open O shape, eyes are wider circles.

```tsx
type Expression = "calm" | "pleased" | "alarmed";

function GhostSvg({ expr }: { expr: Expression }) {
  const mouth =
    expr === "pleased"  ? <path d="M 38 62 Q 50 70 62 62" fill="none" stroke="#333" strokeWidth="2.5" strokeLinecap="round"/> :
    expr === "alarmed"  ? <ellipse cx="50" cy="63" rx="5" ry="6" fill="#333"/> :
                          <line x1="40" y1="63" x2="60" y2="63" stroke="#333" strokeWidth="2.5" strokeLinecap="round"/>;
  const eyeR = expr === "alarmed" ? 5 : 4;
  return (
    <svg viewBox="0 0 100 100" width="60" height="60" aria-hidden="true">
      {/* body */}
      <path d="M 20 90 Q 20 20 50 15 Q 80 20 80 90 Q 70 82 60 90 Q 50 82 40 90 Q 30 82 20 90 Z"
            fill="white" stroke="#aaa" strokeWidth="1.5"/>
      {/* eyeshade — bright green visor */}
      <rect x="18" y="28" width="64" height="14" rx="4" fill="#3a7d44"/>
      <rect x="14" y="38" width="72" height="4"  rx="2" fill="#2d6235"/>
      {/* eyes */}
      <circle cx="38" cy="55" r={eyeR} fill="#222"/>
      <circle cx="62" cy="55" r={eyeR} fill="#222"/>
      {/* mouth */}
      {mouth}
    </svg>
  );
}
```

#### Message table

| State | Expression | Message |
|---|---|---|
| loading | calm | "Loading the paper trail…" |
| demo, no session / CONTRADICTED preselected | calm | "I've pre-loaded the interesting session. Press Play when ready." |
| idle, session selected | calm | "Press Play to start. I'll stay here and watch." |
| playing | calm | "Printing… press Pause any time, or Step to go one line at a time." |
| paused | calm | "Paused. Press Play to continue, or Step to advance one line." |
| done, no verdict | calm | "All done. No verdict yet — click 'Check this statement' to find out." |
| done, SUPPORTED | pleased | "Everything checks out. The agent told the whole truth. Remarkable." |
| done, CONTRADICTED | alarmed | "The agent left something out. The red circle shows what the witness saw." |
| done, UNVERIFIED | calm | "Some claims couldn't be confirmed. Not the same as wrong — just unproven." |
| chain torn | alarmed | "Ah. Someone's been at the paper. Click Restore to fix it." |
| tamper target selected | calm | "Line selected. Click 'Tamper with the paper' to corrupt it." |

#### Layout

```css
.ghost-clerk {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  width: 220px;
  background: #f5f0e8;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 0.5rem 0.6rem;
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  font-family: monospace;
  font-size: 0.78em;
  z-index: 100;
}
@media (max-width: 640px) {
  .ghost-clerk {
    bottom: 0; left: 0; right: 0;
    width: auto; border-radius: 0;
    height: 2.6rem;
    align-items: center;
    gap: 0.3rem;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    border-top: 1px solid #ccc;
    border-left: none; border-right: none; border-bottom: none;
  }
  .ghost-clerk svg { flex-shrink: 0; }
}
@media print { .ghost-clerk { display: none; } }
```

---

### Component: `<Stamp verdict>`

```tsx
const STAMP: Record<string, string> = {
  SUPPORTED:    "stamp stamp--supported",
  CONTRADICTED: "stamp stamp--contradicted",
  UNVERIFIED:   "stamp stamp--unverified",
};
export function Stamp({ verdict }: { verdict: string }) {
  return <span className={STAMP[verdict] ?? "stamp"}>{verdict}</span>;
}
```

```css
.stamp {
  display: inline-block;
  font-family: monospace; font-weight: bold; font-size: 0.85em;
  border: 3px solid currentColor;
  padding: 1px 6px; border-radius: 2px;
  transform: rotate(-2deg); opacity: 0.9;
  position: relative; top: -1px;
}
.stamp--supported    { color: #2d6a2d; }
.stamp--contradicted { color: #8b1a1a; }
.stamp--unverified   { color: #7a5c00; }
@media (prefers-reduced-motion: no-preference) {
  .stamp-enter { animation: stamp-press 180ms ease-out; }
}
@keyframes stamp-press {
  0%   { transform: rotate(-2deg) scale(1.4); opacity: 0; }
  60%  { transform: rotate(-2deg) scale(0.95); opacity: 1; }
  100% { transform: rotate(-2deg) scale(1); opacity: 0.9; }
}
```

---

### Component: `<ChainStatus>`

```tsx
export function ChainStatus({ ok, brokenAt }: { ok: boolean; brokenAt?: number | null }) {
  if (ok) return <span className="chain-status chain-status--ok">Paper intact</span>;
  return <span className="chain-status chain-status--broken">Paper torn at line {brokenAt}</span>;
}
```

---

### Component: `<UndeclaredCircle>`

Wraps an undeclared-change line in a red dashed circle and, when clicked,
scrolls the matching witness stop entry into view via `document.getElementById`.

```tsx
export function UndeclaredCircle({
  children,
  witnessSeq,
}: {
  children: React.ReactNode;
  witnessSeq: number;
}) {
  return (
    <span
      className="undeclared-circle"
      role="button"
      tabIndex={0}
      onClick={() => document.getElementById(`line-${witnessSeq}`)?.scrollIntoView({ behavior: "smooth" })}
      onKeyDown={e => { if (e.key === "Enter" || e.key === " ")
        document.getElementById(`line-${witnessSeq}`)?.scrollIntoView({ behavior: "smooth" }); }}
    >
      {children}
    </span>
  );
}
```

```css
.undeclared-circle {
  display: inline-block;
  border: 2px dashed #8b1a1a;
  border-radius: 50%;
  padding: 0 4px;
  cursor: pointer;
  color: #8b1a1a;
}
```

---

### `<App>` data flow

```tsx
function App() {
  const { entries, source, tamper, restore } = useEntries();
  const chainResult = useChainCheck(entries);
  const sessions    = buildSessionMeta(entries);

  // Preselect CONTRADICTED session in demo mode
  const defaultSession =
    source === "demo"
      ? sessions.find(s => s.overallVerdict === "CONTRADICTED")?.sessionId ?? null
      : null;
  const [selectedSession, setSelectedSession] = useState<string | null>(defaultSession);
  useEffect(() => {
    if (source === "demo" && !selectedSession)
      setSelectedSession(sessions.find(s => s.overallVerdict === "CONTRADICTED")?.sessionId ?? null);
  }, [source, sessions.length]);

  const sessionEntries = entries.filter(e => e.session_id === selectedSession);
  const replay = useReplay(sessionEntries);

  // Synthesise undeclared lines after the overall verdict entry
  const displayEntries = synthesiseUndeclared(sessionEntries);

  return (
    <>
      <Header />
      <main>
        <SessionList sessions={sessions} selected={selectedSession}
                     onSelect={setSelectedSession} source={source} />
        <ChainStatus ok={chainResult?.ok ?? true} brokenAt={!chainResult?.ok ? (chainResult as {brokenAt:number}).brokenAt : null} />
        {source === "api" && <LiveIndicator />}
        <PaperRoll entries={displayEntries} replay={replay} chainResult={chainResult}
                   onTamperSelect={seq => tamper(seq)} />
        <TearOffButton />
      </main>
      <Footer repoUrl={__REPO_URL__} />
      <GhostClerk source={source} replay={replay} chainResult={chainResult}
                  overallVerdict={sessions.find(s => s.sessionId === selectedSession)?.overallVerdict ?? null} />
    </>
  );
}
```

`synthesiseUndeclared` takes the session entries, finds the overall verdict
entry, and inserts a synthetic `{kind: "undeclared", data: {...}}` line for
each item in `data.undeclared` immediately after the overall verdict line.

---

### Paper CSS

```css
:root {
  --paper-bg:    #f8f6ef;
  --band:        #d8f0d0;
  --band-h:      1.6rem;
  --hole-size:   18px;
  --hole-gap:    32px;
  --perf:        #aaa;
  --font:        "Courier New", Courier, monospace;
}
body { background: #c0c0c0; font-family: var(--font); }
.paper-roll {
  background: var(--paper-bg);
  background-image: repeating-linear-gradient(
    to bottom,
    transparent 0, transparent var(--band-h),
    var(--band) var(--band-h), var(--band) calc(var(--band-h) * 2)
  );
  position: relative;
  margin: 0 auto; max-width: 900px; padding: 0 44px;
}
.session-break { border: none; border-top: 2px dashed var(--perf); margin: 0.5rem 0; }
@media (max-width: 640px) {
  .paper-roll { padding: 0 10px; }
  .tractor-holes { display: none; }
}
@media print {
  body { background: white; }
  .paper-roll { background: white; background-image: none; padding: 0; max-width: 100%; }
  .tractor-holes, .session-break { display: none; }
}
```

---

### Print stylesheet

```css
@media print {
  .session-list, .replay-controls, .ghost-clerk,
  .tamper-controls, .live-indicator { display: none !important; }

  .print-report-header::before {
    content: "Paper Trail — Evidence Report";
    display: block; font-weight: bold; font-size: 1.1em; margin-bottom: 0.5em;
  }
  .print-chain-status { font-weight: bold; margin-bottom: 0.5em; }
  .print-verdict-line { margin: 0.2em 0; }
  .print-verdict-line--overall { font-weight: bold; margin-top: 0.8em; border-top: 1px solid #000; padding-top: 0.4em; }
  .print-undeclared { color: #8b1a1a; font-style: italic; }
  .print-evidence-ref { font-size: 0.85em; color: #555; }
}
```

The `<PrintLine>` component for verdict entries renders:

```
sample/cache/output.bin: SUPPORTED  (line 4)
```

The `(line N)` reference is already baked into the `entryText()` output for
per-path verdict entries (see `lib/entryText.ts`).

---

## 6. Tests

### `tests/fixtures/hash_fixture.json`

Generated by running this once:
```python
import json
from papertrail.ledger import _compute_hash

entry = {
    "seq": 1,
    "ts": "2026-01-01T00:00:00.000000Z",
    "session_id": "fixture",
    "kind": "tool",
    "data": {
        "quotes":    'say "hello"',
        "backslash": "C:\\Users\\test",
        "newline":   "line1\nline2",
        "tab":       "col1\tcol2",
        "control":   "\x01",
        "emoji":     "🔍",
        "accent":    "café",
    },
    "prev_hash": "0" * 64,
}
print(json.dumps({"entry": entry, "expected_hash": _compute_hash(entry)},
                 ensure_ascii=False, indent=2))
```

Committed to `tests/fixtures/hash_fixture.json`. Both Python and TypeScript
load it and assert `computed == expected_hash`.

### `web/src/__tests__/chainCheck.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { canonicalJson } from "../lib/canonicalJson";
import { checkChain } from "../lib/chainCheck";
import fixture from "../../../../tests/fixtures/hash_fixture.json";
import demoLedgerRaw from "../../public/demo/ledger.jsonl?raw";

describe("canonicalJson + SHA-256 matches Python", () => {
  it("produces the expected hash", async () => {
    const entry = fixture.entry as Record<string, unknown>;
    const canon = canonicalJson(entry);
    const bytes = new TextEncoder().encode(canon);
    const buf   = await crypto.subtle.digest("SHA-256", bytes);
    const hex   = Array.from(new Uint8Array(buf))
                       .map(b => b.toString(16).padStart(2,"0")).join("");
    expect(hex).toBe(fixture.expected_hash);
  });
});

describe("demo ledger chain is intact", () => {
  it("checkChain returns ok:true", async () => {
    const entries = demoLedgerRaw.trim().split("\n")
                                  .filter(Boolean).map(l => JSON.parse(l));
    const result = await checkChain(entries);
    expect(result.ok).toBe(true);
  });
});
```

The Vite `?raw` import reads `demo/ledger.jsonl` as a string at test time.
`vite.config.ts` resolves the fixture path alias `@@fixtures` to
`../../tests/fixtures` so the import above works.

### `tests/test_import_isolation.py`

```python
import subprocess, sys

FORBIDDEN = ["fastapi", "uvicorn", "httpx", "mcp"]
CORE_MODULES = [
    "papertrail.ledger",
    "papertrail.witness",
    "papertrail.session",
    "papertrail.recorder",
]

def test_no_heavy_imports():
    for mod in CORE_MODULES:
        result = subprocess.run(
            [sys.executable, "-c",
             f"import {mod}; import sys; "
             f"bad = [m for m in {FORBIDDEN!r} if m in sys.modules]; "
             f"assert not bad, bad"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, \
            f"Importing {mod} pulled in forbidden packages:\n{result.stdout}\n{result.stderr}"
```

---

## 7. `requirements.txt` additions

```
fastapi
uvicorn[standard]
httpx
mcp
```

These four packages must only be imported in `api.py`, `mcp_server.py`, and
test files. The four core modules listed in R6.4 must remain standard-library
only.

---

## 8. File additions summary

| File | Purpose |
|---|---|
| `papertrail/verifier.py` | Add `undeclared` to overall entry (one change) |
| `sample/make_demo_ledger.py` | Demo ledger generator |
| `papertrail/api.py` | FastAPI app |
| `papertrail/mcp_server.py` | stdio MCP server |
| `papertrail/__main__.py` | Add `serve` subcommand |
| `.kiro/settings/mcp.json` | Workspace MCP registration |
| `web/` | Full React + TS + Vite app |
| `tests/test_make_demo_ledger.py` | Generator tests |
| `tests/test_api.py` | API tests |
| `tests/test_mcp_server.py` | MCP handler tests |
| `tests/test_hash_compat.py` | Python side of cross-language hash test |
| `tests/test_import_isolation.py` | Asserts core modules stay stdlib-only |
| `tests/fixtures/hash_fixture.json` | Shared hash fixture (tab, U+0001, emoji, etc.) |
| `requirements.txt` | Add fastapi, uvicorn, httpx, mcp |
