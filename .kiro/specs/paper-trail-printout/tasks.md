# Tasks — Paper Trail Printout

Each task ends with a **Check** that must pass before the next task starts.
Run checks from the project root unless stated otherwise.

---

## Task 1 — Verifier change and hash fixture

**Delivers:** updated `papertrail/verifier.py`, new test in
`tests/test_verifier.py`, `tests/fixtures/hash_fixture.json`,
`tests/test_hash_compat.py`, `tests/test_import_isolation.py`

### 1a — Add `undeclared` to the overall verdict entry

In `papertrail/verifier.py`, find the `ledger_mod.append` call that writes the
overall verdict entry and add `"undeclared": undeclared` to its `data` dict:

```python
ledger_mod.append(ledger_path, session_id, "verdict", {
    "kind_detail":  "statement_overall",
    "verdict":      overall,
    "evidence_seq": all_evidence,
    "witness_seq":  witness_seq,
    "undeclared":   undeclared,
})
```

In the idempotency reconstruction path, read the stored list back:

```python
undeclared = existing_overall["data"].get("undeclared", [])
```

No other change to `verifier.py`.

### 1b — New test in `tests/test_verifier.py`

Add `test_undeclared_stored_in_overall_entry`: build a session with one
undeclared deleted file, call `_run_verify`, read the ledger, find the overall
verdict entry, and assert `overall["data"]["undeclared"] == [{"path":
"secret.txt", "change": "deleted"}]`. (Use the existing `_make_witness_stop_entry`
and `_make_statement` helpers already in `test_verifier.py`.)

### 1c — Hash fixture

Create `tests/fixtures/` directory and generate `tests/fixtures/hash_fixture.json`
by running this script once and committing the output:

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
print(json.dumps(
    {"entry": entry, "expected_hash": _compute_hash(entry)},
    ensure_ascii=False, indent=2,
))
```

The printed JSON is the fixture file. It has two top-level keys: `entry` (the
entry dict without a `hash` field) and `expected_hash` (the hex string).

### 1d — `tests/test_hash_compat.py`

```python
import json
from pathlib import Path
from papertrail.ledger import _compute_hash

FIXTURE = Path(__file__).parent / "fixtures" / "hash_fixture.json"

def test_python_hash_matches_fixture():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert _compute_hash(data["entry"]) == data["expected_hash"]
```

### 1e — `tests/test_import_isolation.py`

```python
import subprocess, sys

FORBIDDEN = ["fastapi", "uvicorn", "httpx", "mcp"]
CORE = [
    "papertrail.ledger",
    "papertrail.witness",
    "papertrail.session",
    "papertrail.recorder",
]

def test_no_heavy_imports():
    for mod in CORE:
        result = subprocess.run(
            [sys.executable, "-c",
             f"import {mod}; import sys; "
             f"bad = [m for m in {FORBIDDEN!r} if m in sys.modules]; "
             f"assert not bad, bad"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, \
            f"Importing {mod} pulled in forbidden packages:\n{result.stderr}"
```

**Check:** `pytest tests/test_verifier.py tests/test_hash_compat.py tests/test_import_isolation.py -v` exits 0. The existing 104 tests must still pass: `pytest tests/ -q`.

---

## Task 2 — Demo ledger generator

**Delivers:** `sample/make_demo_ledger.py`, `web/public/demo/` directory,
`tests/test_make_demo_ledger.py`

### 2a — `sample/make_demo_ledger.py`

Implement `generate(out_path: Path)` and the `__main__` block exactly as
specified in design section 2. Key points:

- One `tempfile.TemporaryDirectory` for both sessions.
- Pass `root=Path(_tmp)` and `home=Path.home()` to every `on_start`, `on_stop`,
  `record`, and `verifier.verify` call. Never set `PAPERTRAIL_ROOT`.
- Session A: create `src/main.py` before `on_start`; create `docs/notes.md`
  after; two `record` calls (`read_file` then `fs_write`); statement with
  `files_read` and `files_created`; call `on_stop` then `verifier.verify`.
- Session B: create `sample/notes.txt` and `sample/cache/output.bin` after
  Session A's `on_stop`; call `on_start`; delete both files; one `record`
  call (`execute_pwsh`); statement with only `files_deleted:
  ["sample/cache/output.bin"]`; call `on_stop` then `verifier.verify`.
- Copy `<tmp>/.papertrail/ledger.jsonl` to `out_path`.
- The `__main__` block calls `generate` with the default path
  `web/public/demo/ledger.jsonl` relative to the script's grandparent.

Create `web/public/demo/` and run `python sample/make_demo_ledger.py` to
populate the file.

### 2b — `tests/test_make_demo_ledger.py`

```python
import json
from pathlib import Path
from papertrail import ledger as ledger_mod
from sample.make_demo_ledger import generate

def test_generator_structure(tmp_path):
    out = tmp_path / "ledger.jsonl"
    generate(out_path=out)
    entries = ledger_mod.read(out)

    # chain intact
    ok, broken = ledger_mod.verify_chain(out)
    assert ok, f"chain broken at seq {broken}"

    # two sessions, each with required entry kinds
    sids = list(dict.fromkeys(e["session_id"] for e in entries))
    assert len(sids) == 2
    for sid in sids:
        kinds = {e["kind"] for e in entries if e["session_id"] == sid}
        assert kinds >= {"witness", "tool", "statement", "verdict"}

    # overall verdicts
    overall = {
        e["session_id"]: e["data"]["verdict"]
        for e in entries
        if e["kind"] == "verdict"
        and e["data"].get("kind_detail") == "statement_overall"
    }
    assert set(overall.values()) == {"SUPPORTED", "CONTRADICTED"}

    # undeclared in CONTRADICTED session
    contradicted_sid = next(s for s, v in overall.items() if v == "CONTRADICTED")
    overall_entry = next(
        e for e in entries
        if e["session_id"] == contradicted_sid
        and e["kind"] == "verdict"
        and e["data"].get("kind_detail") == "statement_overall"
    )
    paths = [u["path"] for u in overall_entry["data"]["undeclared"]]
    assert "sample/notes.txt" in paths

    # no absolute paths
    raw = out.read_text(encoding="utf-8")
    assert ":\\" not in raw and ":/" not in raw
```

**Check:**
```powershell
pytest tests/test_make_demo_ledger.py -v
```
Then confirm `web/public/demo/ledger.jsonl` exists and contains two sessions:
```powershell
python -c "
import json
lines = open('web/public/demo/ledger.jsonl').readlines()
sids = list(dict.fromkeys(json.loads(l)['session_id'] for l in lines))
print(f'{len(lines)} entries, sessions: {sids}')
"
```

---

## Task 3 — Local API and serve subcommand

**Delivers:** `papertrail/api.py`, updated `papertrail/__main__.py`,
`tests/test_api.py`, updated `requirements.txt`

### 3a — `requirements.txt`

Add these lines (keeping existing `pytest` and `hypothesis`):

```
fastapi
uvicorn[standard]
httpx
mcp
```

Install: `pip install -r requirements.txt`.

### 3b — `papertrail/api.py`

Implement as specified in design section 3. The app must:

- Import `FastAPI`, `CORSMiddleware`, and `HTTPException` from `fastapi` and
  `fastapi.middleware.cors`.
- Define `_root()` using `PAPERTRAIL_ROOT` or `Path(__file__).resolve().parent.parent`.
- Register CORS for `http://localhost:5173` only, methods `["GET", "POST"]`.
- Implement the three endpoints: `GET /api/ledger`, `GET /api/chain`,
  `POST /api/verify/{session_id}/{n}`.
- `_root()` is called at request time (not at import time) so test fixtures
  that set `PAPERTRAIL_ROOT` take effect without restarting.

### 3c — Add `serve` to `papertrail/__main__.py`

Add an `elif cmd == "serve":` branch:

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

### 3d — `tests/test_api.py`

Use the fixture pattern from design section 3. Cover:

- `GET /api/ledger` with entries present (returns list) and absent (returns `[]`).
- `GET /api/chain` with valid chain (`ok: true`) and broken chain (`ok: false`,
  `broken_at` set to the right seq).
- `POST /api/verify/{session_id}/{n}` success (returns dict with `overall`).
- `POST /api/verify/{session_id}/{n}` with missing statement file (returns 404).

For the verify test, pre-build a minimal ledger with a witness stop entry and
a promoted statement file in `tmp_path / ".papertrail" / "statements"`.

**Check:**
```powershell
pytest tests/test_api.py -v
```
Also run `pytest tests/ -q` to confirm no regressions.

---

## Task 4 — MCP server

**Delivers:** `papertrail/mcp_server.py`, `.kiro/settings/mcp.json`,
`tests/test_mcp_server.py`

### 4a — `papertrail/mcp_server.py`

Implement the four plain handler functions and the MCP wiring exactly as
specified in design section 4:

- `handle_list_sessions(root)` — builds per-session summary from ledger entries.
- `handle_get_entries(root, session_id)` — filters entries by session.
- `handle_check_chain(root)` — calls `ledger.verify_chain`.
- `handle_verify_statement(root, session_id, n)` — calls `verifier.verify` or
  returns `{"error": ...}`.
- MCP server wiring via `mcp.server.Server` and `stdio_server`.
- `__main__` block runs `asyncio.run(_main())`.

The four handler functions must not import `mcp`; only the wiring code at
module level and `_main` import from `mcp`.

### 4b — `.kiro/settings/mcp.json`

Create the directory `.kiro/settings/` if absent and write:

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

No absolute paths, no machine-specific values.

### 4c — `tests/test_mcp_server.py`

Call handler functions directly with `tmp_path` as root. Cover:

- `handle_list_sessions` on empty ledger returns `[]`.
- `handle_list_sessions` with two sessions returns two items with correct
  `entry_count`, `has_statement`, `overall_verdict`.
- `handle_get_entries` returns only entries for the given session; unknown
  session returns `[]`.
- `handle_check_chain` returns `{"ok": True, "broken_at": None, "count": N}`
  on a valid ledger.
- `handle_verify_statement` for the demo CONTRADICTED session returns
  `overall == "CONTRADICTED"`. Build this session using the same helper from
  `test_make_demo_ledger.py` (import `generate`, write to `tmp_path`, read
  back).

**Check:**
```powershell
pytest tests/test_mcp_server.py -v
```
Also confirm `.kiro/settings/mcp.json` exists:
```powershell
Get-Content .kiro\settings\mcp.json
```

---

## Task 5 — Web scaffold, lib, and Python-side tests

**Delivers:** Vite + React project in `web/`, `lib/canonicalJson.ts`,
`lib/chainCheck.ts`, `lib/entryText.ts`, `lib/sessionMeta.ts`,
`web/src/__tests__/chainCheck.test.ts`, `web/src/__tests__/Stamp.test.tsx`,
`web/src/__tests__/ChainStatus.test.tsx`

### 5a — Scaffold the web project

From the project root:

```powershell
cd web
npm create vite@latest . -- --template react-ts
npm install
npm install --save-dev vitest @vitest/coverage-v8 @testing-library/react @testing-library/jest-dom jsdom
```

Replace the generated `vite.config.ts` with the config from design section 5:

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

Create `web/src/__tests__/setup.ts`:

```ts
import "@testing-library/jest-dom";
```

Add a `tsconfig.json` path alias so the fixture is importable from TypeScript
tests. In `tsconfig.json` (or `tsconfig.app.json`) add under `compilerOptions`:

```json
"paths": {
  "@@fixtures/*": ["../../tests/fixtures/*"]
}
```

And in `vite.config.ts` under the `test` block:

```ts
resolve: {
  alias: {
    "@@fixtures": new URL("../../tests/fixtures", import.meta.url).pathname,
  },
},
```

Add a `"test"` script to `web/package.json`:

```json
"test": "vitest run"
```

### 5b — `web/src/lib/canonicalJson.ts`

Implement as in design section 5, using `JSON.stringify` for strings and keys
with no post-processing of escape sequences:

```ts
export function canonicalJson(obj: unknown): string {
  if (obj === null || typeof obj !== "object")
    return JSON.stringify(obj);
  if (Array.isArray(obj))
    return "[" + obj.map(canonicalJson).join(",") + "]";
  const keys = Object.keys(obj as object).sort();
  return (
    "{" +
    keys
      .map(k => JSON.stringify(k) + ":" + canonicalJson((obj as Record<string,unknown>)[k]))
      .join(",") +
    "}"
  );
}
```

### 5c — `web/src/lib/chainCheck.ts`

Implement `checkChain` as in design section 5. Export the `Entry` and
`ChainResult` types.

### 5d — `web/src/lib/entryText.ts`

Implement `entryText(entry)` and `undeclaredText(item)` exactly as in design
section 5. The tool-verb map must cover `read_file`, `fs_write`, `str_replace`,
and `execute_pwsh`; anything else falls back to `"Agent used a tool: <name>."`.
Per-path verdict lines must include the evidence seq reference:
`"<path>: <VERDICT>  (line <seq>)"`.

### 5e — `web/src/lib/sessionMeta.ts`

Implement `buildSessionMeta(entries)` as in design section 5.

### 5f — TypeScript tests

**`web/src/__tests__/chainCheck.test.ts`**

Two `describe` blocks:

1. Load `hash_fixture.json` via the `@@fixtures` alias. Compute canonical JSON
   of `fixture.entry`, SHA-256 it with Web Crypto, compare to
   `fixture.expected_hash`.

2. Load `web/public/demo/ledger.jsonl` via the `?raw` Vite import. Parse lines,
   call `checkChain(entries)`, assert `result.ok === true`.

**`web/src/__tests__/Stamp.test.tsx`**

Create `web/src/components/Stamp.tsx` (a minimal stub if the full component
isn't ready yet — it only needs to render `<span className={...}>{verdict}</span>`).
Test:
- SUPPORTED → text "SUPPORTED", class contains `stamp--supported`.
- CONTRADICTED → class contains `stamp--contradicted`.
- UNVERIFIED → class contains `stamp--unverified`.

**`web/src/__tests__/ChainStatus.test.tsx`**

Create `web/src/components/ChainStatus.tsx` stub.
Test:
- `<ChainStatus ok={true} />` → text "Paper intact".
- `<ChainStatus ok={false} brokenAt={3} />` → text "Paper torn at line 3".

**Check:**
```powershell
cd web && npx vitest run
```
All tests pass. Back in the project root:
```powershell
pytest tests/test_hash_compat.py tests/test_import_isolation.py -v
```

---

## Task 6 — Web components: paper look, session list, replay

**Delivers:** `PaperRoll.tsx`, `TractorHoles.tsx`, `SessionSpool.tsx`,
`PrintLine.tsx`, `UndeclaredCircle.tsx`, `TearLine.tsx`, `ReplayControls.tsx`,
`LiveIndicator.tsx`, `Header.tsx`, `Footer.tsx`, hooks `useEntries.ts`,
`useChainCheck.ts`, `useReplay.ts`, CSS files

### 6a — CSS files

Create `web/src/styles/paper.css`, `stamps.css`, and `print.css` from the
design. Key points:
- `paper.css`: `--paper-bg: #f8f6ef`, `--band: #d8f0d0`, repeating-linear-gradient
  for the green bands, tractor holes via `.tractor-holes` and `.tractor-hole`,
  `.session-break` dashed rule, responsive hide of holes at ≤ 640 px.
- `stamps.css`: `.stamp`, `.stamp--supported` (`#2d6a2d`),
  `.stamp--contradicted` (`#8b1a1a`), `.stamp--unverified` (`#7a5c00`),
  `stamp-press` animation gated on `prefers-reduced-motion: no-preference`.
- `print.css`: `@media print` block hiding `.session-list`, `.replay-controls`,
  `.ghost-clerk`, `.tamper-controls`, `.live-indicator`; showing
  `.print-report-header`, `.print-chain-status`, verdict lines, undeclared
  lines.

### 6b — Hooks

**`web/src/hooks/useEntries.ts`**  
Implement as in design section 5. The hook:
- Attempts `fetch("/api/ledger")` on mount; on success sets `source: "api"`.
- On failure fetches `"./demo/ledger.jsonl"` and sets `source: "demo"`.
- In live mode, `setInterval` polls every 2000 ms; clears on unmount.
- Exposes `entries` (displayed, possibly tampered), `source`, `tamper(seq)`,
  `restore()`.
- Maintains `originalRef` as the untampered copy.

**`web/src/hooks/useChainCheck.ts`**  
Calls `checkChain(entries)` in a `useEffect` whenever `entries` changes.

**`web/src/hooks/useReplay.ts`**  
State machine: `idle | playing | paused | done`. Exposes `state`, `cursor`,
`speed`, `setSpeed`, `step`, `play`, `pause`, `reset`.

### 6c — Components

Create the following, all importing from `../lib/entryText` or `../styles/`
as needed. Stub-level implementations are acceptable at this stage as long as
they render without errors and satisfy the CSS class contracts the tests check.

- **`Stamp.tsx`** — full implementation with correct CSS classes and stamp
  animation.
- **`ChainStatus.tsx`** — "Paper intact" / "Paper torn at line N".
- **`TearLine.tsx`** — SVG jagged red line with `aria-label="Paper torn here"`.
- **`UndeclaredCircle.tsx`** — dashed red border, click scrolls to
  `#line-{witnessSeq}`.
- **`TractorHoles.tsx`** — renders N holes using `--hole-size` and `--hole-gap`.
- **`PaperRoll.tsx`** — wraps content in `.paper-roll` with left and right
  `<TractorHoles>`.
- **`PrintLine.tsx`** — renders one entry. Accepts `entry`, `visible`,
  `isSelected`, `onSelect`. When `kind === "verdict"` and not overall, renders
  `<Stamp>` inline. When `kind === "undeclared"` (synthetic), wraps in
  `<UndeclaredCircle witnessSeq={...}>`. Line gets `id="line-{entry.seq}"`.
- **`SessionSpool.tsx`** — spool card: title (from `sessionMeta.title`),
  truncated session ID, date from first entry's `ts`, verdict stamp if present,
  "Check this statement" button (live mode only, `hasUnverifiedStatement`
  true), click handler.
- **`ReplayControls.tsx`** — Play/Pause/Step buttons, speed selector (Slow /
  Normal / Fast), all keyboard accessible.
- **`LiveIndicator.tsx`** — small `<span className="live-indicator">LIVE</span>`.
- **`Header.tsx`** — `<h1>Paper Trail: what did the agent really do?</h1>`
  followed by the one-sentence explanation.
- **`Footer.tsx`** — `<a href={repoUrl}>View on GitHub</a>`.

### 6d — Synthesise undeclared lines

In a helper `synthesiseUndeclared(entries: Entry[]): DisplayEntry[]`, find the
overall verdict entry for the session, extract its `data.undeclared` list, and
insert a synthetic entry `{kind: "undeclared", seq: -1, data: {path, change, witnessSeq}}` immediately after the overall verdict entry. `witnessSeq` is taken
from the overall verdict entry's `data.witness_seq`.

**Check:**
```powershell
cd web && npm run dev
```
Open `http://localhost:5173` in a browser. Without the API running, the demo
ledger should load, the CONTRADICTED session should be preselected, and the
paper should render with green bands and tractor holes. The page must not throw
a JavaScript error. Close the dev server.

---

## Task 7 — Ghost clerk

**Delivers:** `web/src/components/GhostClerk.tsx`

### 7a — SVG ghost design

Implement the `GhostSvg` sub-component as specified in design section 5
(component `<GhostClerk>`). The ghost:
- Is an original design: rounded rectangular white body, ragged bottom with
  three bumps, two dot eyes, a green visor (rect + darker rect for brim), and
  a mouth that varies by expression.
- Has three expressions: `calm` (straight mouth), `pleased` (upward arc),
  `alarmed` (small open ellipse).
- viewBox is `0 0 100 100`, rendered at 60×60 px.
- Has `aria-hidden="true"`.

### 7b — Message logic

Implement `GhostClerk` as a component that accepts `source`, `replay` state,
`chainResult`, and `overallVerdict`, and derives the message string and
expression from the state table in the design. Use the exact messages from
the table:

| Condition | Expression | Message |
|---|---|---|
| `source === "loading"` | calm | "Loading the paper trail…" |
| `source === "demo"` and no session yet | calm | "I've pre-loaded the interesting session. Press Play when ready." |
| session selected, `state === "idle"` | calm | "Press Play to start. I'll stay here and watch." |
| `state === "playing"` | calm | "Printing… press Pause any time, or Step to go one line at a time." |
| `state === "paused"` | calm | "Paused. Press Play to continue, or Step to advance one line." |
| `state === "done"`, no verdict | calm | "All done. No verdict yet — click 'Check this statement' to find out." |
| `state === "done"`, SUPPORTED | pleased | "Everything checks out. The agent told the whole truth. Remarkable." |
| `state === "done"`, CONTRADICTED | alarmed | "The agent left something out. The red circle shows what the witness saw." |
| `state === "done"`, UNVERIFIED | calm | "Some claims couldn't be confirmed. Not the same as wrong — just unproven." |
| chain torn | alarmed | "Ah. Someone's been at the paper. Click Restore to fix it." |
| tamper target selected | calm | "Line selected. Click 'Tamper with the paper' to corrupt it." |

### 7c — Layout

Apply the CSS from the design:
- Wide (> 640 px): `position: fixed; bottom: 1rem; right: 1rem; width: 220px`.
- Narrow (≤ 640 px): full-width bottom bar, `height: 2.6rem`, `white-space: nowrap`.
- Hidden in print.

**Check:**
```powershell
cd web && npm run dev
```
Open the page. The ghost should be visible in the bottom-right corner with a
calm expression and the first-load message. No console errors.

---

## Task 8 — Tamper demo, "Check this statement", accessibility, print

**Delivers:** tamper/restore wiring in `App.tsx`, "Check this statement" in
`SessionSpool.tsx`, print styles complete, accessibility pass

### 8a — Tamper and restore in `App.tsx`

Wire `useEntries`'s `tamper(seq)` and `restore()` to:
- A click handler on `<PrintLine>` that sets `tamperTarget` state.
- The "Tamper with the paper" button: calls `tamper(tamperTarget)` if set,
  otherwise finds the first `execute_pwsh` entry in the current session and
  calls `tamper` with its seq.
- The "Restore" button: calls `restore()` and clears `tamperTarget`.

Both buttons must be rendered as `<button>` elements with the exact text
specified in AC4.13c ("Tamper with the paper") and an accessible label for
Restore.

Selected lines get a CSS class `print-line--tamper-target` for highlighting
(subtle yellow background).

### 8b — "Check this statement" in `SessionSpool.tsx`

When `source === "api"` and the session's `hasUnverifiedStatement` is true,
render a `<button>Check this statement</button>`. On click:
1. Call `POST /api/verify/{session_id}/{statementIndex}`.
2. On success, trigger an immediate re-fetch of entries from the API (call a
   callback passed in as `onVerified`).
3. Show a spinner or disabled state while the request is in flight.
4. On error, show a brief inline error message.

### 8c — Accessibility pass

Ensure all interactive elements (`<SessionSpool>`, Play, Pause, Step, speed
selector, Tamper, Restore, Tear off, "Check this statement") are:
- `<button>` or `<a>` elements (no `div` with `onClick` as the sole affordance).
- Have visible `:focus-visible` outlines (add to `paper.css`: 
  `button:focus-visible, a:focus-visible { outline: 2px solid #2d6a2d; outline-offset: 2px; }`).
- Activatable with Enter and Space (native for `<button>`).

Add `aria-label` to icon-only buttons. Add `aria-live="polite"` to the ghost
clerk message span.

### 8d — Print stylesheet complete

Verify `print.css` hides all non-report elements and that `<PrintLine>` for
verdict entries renders the evidence-line reference in parentheses (this is
already in `entryText.ts`; confirm it appears). The chain status must appear
in the print output via a `.print-chain-status` element rendered by `App.tsx`
outside the hidden controls.

**Check:**
```powershell
cd web && npm run dev
```
Manually verify:
1. Click "Tamper with the paper" on the demo session — "Paper torn at line N"
   appears and a tear graphic is visible at that line.
2. Click "Restore" — "Paper intact" returns and the tear disappears.
3. No console errors or accessibility warnings in the browser's DevTools.
4. `npx vitest run` still passes.

---

## Task 9 — Full integration and final checks

**Delivers:** all tests green, `web/public/demo/ledger.jsonl` committed,
`requirements.txt` updated

### 9a — Regenerate demo ledger

Run `python sample/make_demo_ledger.py` from the project root to ensure
`web/public/demo/ledger.jsonl` reflects the current verifier output (which now
stores `undeclared` in the overall entry). Confirm the file is non-empty and
the demo chain test in Vitest passes.

### 9b — Full Python test suite

```powershell
pytest tests/ -v --tb=short
```

All tests must pass, including:
- `test_verifier.py` (new `test_undeclared_stored_in_overall_entry`).
- `test_make_demo_ledger.py`.
- `test_api.py`.
- `test_mcp_server.py`.
- `test_hash_compat.py`.
- `test_import_isolation.py`.
- All 104 pre-existing tests.

### 9c — Full TypeScript test suite

```powershell
cd web && npx vitest run
```

All tests must pass, including:
- `chainCheck.test.ts` (fixture hash + demo ledger chain intact).
- `Stamp.test.tsx`.
- `ChainStatus.test.tsx`.

### 9d — Static build smoke test

```powershell
cd web && npm run build
```

Build must complete with no errors. Open `web/dist/index.html` in a browser
(via a local file server or `npx serve dist`). Confirm:
- The demo data loads from `./demo/ledger.jsonl`.
- Both sessions appear as spools.
- The CONTRADICTED session is preselected.
- The ghost clerk is visible and shows the first-load message.
- "Paper intact" is shown.

**Check (final):**
```powershell
pytest tests/ -q
cd web && npx vitest run
```
Both commands exit 0 with no failures.
