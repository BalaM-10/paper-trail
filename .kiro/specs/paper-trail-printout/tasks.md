# Tasks — Paper Trail Printout

Each task ends with a **Check** that must pass before the next task starts.
Run checks from the project root unless stated otherwise. No task check may
start a long-running server process.

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
verdict entry, and assert:

```python
assert overall["data"]["undeclared"] == [{"path": "secret.txt", "change": "deleted"}]
```

Use the existing `_make_witness_stop_entry` and `_make_statement` helpers
already in `test_verifier.py`.

### 1c — Hash fixture

Create the `tests/fixtures/` directory, then generate
`tests/fixtures/hash_fixture.json` by running the script below and writing the
output to that file:

```powershell
python -c "
import json
from papertrail.ledger import _compute_hash

entry = {
    'seq': 1,
    'ts': '2026-01-01T00:00:00.000000Z',
    'session_id': 'fixture',
    'kind': 'tool',
    'data': {
        'quotes':    'say \"hello\"',
        'backslash': 'C:\\\\Users\\\\test',
        'newline':   'line1\nline2',
        'tab':       'col1\tcol2',
        'control':   '\x01',
        'emoji':     '\U0001F50D',
        'accent':    'caf\xe9',
    },
    'prev_hash': '0' * 64,
}
print(json.dumps({'entry': entry, 'expected_hash': _compute_hash(entry)},
                 ensure_ascii=False, indent=2))
" > tests/fixtures/hash_fixture.json
```

Confirm the file was written and contains both `entry` and `expected_hash` keys.

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

**Check:**
```powershell
pytest tests/test_verifier.py tests/test_hash_compat.py tests/test_import_isolation.py -v
pytest tests/ -q
```
Both commands must exit 0. The existing 104 tests must still pass.

---

## Task 2 — Demo ledger generator

**Delivers:** `sample/make_demo_ledger.py`, `web/public/demo/ledger.jsonl`,
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
  Session A's `on_stop` (so they appear in Session B's start snapshot but not
  Session A's); call `on_start`; delete both files; one `record` call
  (`execute_pwsh`); statement with only `files_deleted:
  ["sample/cache/output.bin"]`; call `on_stop` then `verifier.verify`.
- Copy `<tmp>/.papertrail/ledger.jsonl` to `out_path`.
- The `__main__` block calls `generate` with the default path
  `web/public/demo/ledger.jsonl` relative to the script's grandparent
  (`Path(__file__).resolve().parents[1]`).

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
mcp>=2,<3
```

Install: `pip install -r requirements.txt`.

### 3b — `papertrail/api.py`

Implement as specified in design section 3:

- `_root()` reads `PAPERTRAIL_ROOT` or falls back to
  `Path(__file__).resolve().parent.parent`. Call it at request time, not
  import time.
- CORS allows `http://localhost:5173` only; methods `["GET", "POST"]`.
- `GET /api/ledger` — returns `ledger.read(...)`, or `[]` if absent.
- `GET /api/chain` — returns `{"ok", "broken_at", "count"}`.
- `POST /api/verify/{session_id}/{n}` — returns verifier result or HTTP 404.

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
pytest tests/ -q
```

---

## Task 4 — MCP server

**Delivers:** `papertrail/mcp_server.py`, `.kiro/settings/mcp.json`,
`tests/test_mcp_server.py`

### 4a — `papertrail/mcp_server.py`

Implement the four plain handler functions and the MCP wiring exactly as
specified in design section 4, using the 2.x `mcp.server.MCPServer` API. The
SDK is imported lazily inside `build_server()`; the handlers and the module
itself must import without it.

### 4b — `.kiro/settings/mcp.json`

Create `.kiro/settings/` if absent. Write:

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
  `overall == "CONTRADICTED"`. Build this session by calling `generate` from
  `test_make_demo_ledger.py` into a `tmp_path`, reading back entries, and
  locating the CONTRADICTED session's statement file.

**Check:**
```powershell
pytest tests/test_mcp_server.py -v
Get-Content .kiro\settings\mcp.json
```

---

## Task 5 — Web scaffold, lib, fixture alias, and initial tests

**Delivers:** full Vite + React project skeleton in `web/`, all lib modules,
`web/src/__tests__/chainCheck.test.ts`, `web/src/__tests__/Stamp.test.tsx`,
`web/src/__tests__/ChainStatus.test.tsx`, `web/src/__tests__/setup.ts`

### 5a — Write project files directly, then install

Do not run `npm create vite`. Write the following files:

**`web/package.json`**
```json
{
  "name": "paper-trail-web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "build": "tsc -b && vite build",
    "test":  "vitest run",
    "preview": "vite preview"
  },
  "dependencies": {
    "react":     "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom":  "^6.4.6",
    "@testing-library/react":     "^16.0.0",
    "@types/react":               "^18.3.3",
    "@types/react-dom":           "^18.3.0",
    "@vitejs/plugin-react":       "^4.3.1",
    "@vitest/coverage-v8":        "^2.0.5",
    "jsdom":                      "^24.1.1",
    "typescript":                 "^5.5.3",
    "vite":                       "^5.3.4",
    "vitest":                     "^2.0.5"
  }
}
```

**`web/tsconfig.json`**
```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

**`web/tsconfig.app.json`**
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "paths": {
      "@@fixtures/*": ["../tests/fixtures/*"]
    }
  },
  "include": ["src"]
}
```

**`web/tsconfig.node.json`**
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "skipLibCheck": true,
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

**`web/vite.config.ts`**
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  base: "./",
  define: {
    __REPO_URL__: JSON.stringify(process.env.VITE_REPO_URL ?? "#"),
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  resolve: {
    alias: {
      "@@fixtures": fileURLToPath(new URL("../tests/fixtures", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/__tests__/setup.ts",
    resolve: {
      alias: {
        "@@fixtures": fileURLToPath(new URL("../tests/fixtures", import.meta.url)),
      },
    },
  },
});
```

`__REPO_URL__` falls back to `"#"` when `VITE_REPO_URL` is not set. No
placeholder organisation name appears in the committed config.

**`web/index.html`**
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Paper Trail</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**`web/src/main.tsx`**
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

Then install:
```powershell
cd web && npm install
```

`npm install` reads `package.json` and exits without waiting for keyboard
input.

### 5b — `web/src/__tests__/setup.ts`

```ts
import "@testing-library/jest-dom";
```

### 5c — `web/src/lib/canonicalJson.ts`

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
      .map(k => JSON.stringify(k) + ":" + canonicalJson((obj as Record<string, unknown>)[k]))
      .join(",") +
    "}"
  );
}
```

No post-processing of escape sequences. `JSON.stringify` on a string preserves
non-ASCII printable characters literally in V8 and matches Python's
`ensure_ascii=False`. Control characters below U+0020 are escaped as `\uXXXX`
by both engines, so the hash fixture (which includes `\t`, U+0001, and an
emoji) confirms alignment.

### 5d — `web/src/lib/chainCheck.ts`

Implement `checkChain` and export `Entry` and `ChainResult` exactly as in
design section 5.

### 5e — `web/src/lib/entryText.ts`

Implement `entryText(entry)` and `undeclaredText(item)` from design section 5.
Undeclared-change lines are synthesised elsewhere; `undeclaredText` returns
`"Witness saw <path> <change>. The agent never mentioned it."`. Per-path
verdict lines include `"  (line <seq>)"` from `evidence_seq`.

### 5f — `web/src/lib/sessionMeta.ts`

Implement `buildSessionMeta(entries)` from design section 5. The `title` field
is the statement `summary` when a `statement` entry exists for the session,
otherwise the first 8 characters of the session ID.

### 5g — TypeScript tests

**`web/src/__tests__/chainCheck.test.ts`** — two `describe` blocks:

1. Load `hash_fixture.json` via the `@@fixtures` alias. Assert the browser
   implementation produces `fixture.expected_hash`.

2. Load `web/public/demo/ledger.jsonl` via Vite's `?raw` import. Parse lines,
   call `checkChain(entries)`, assert `result.ok === true`.

The import for block 2:
```ts
import demoLedgerRaw from "../../public/demo/ledger.jsonl?raw";
```

**`web/src/components/Stamp.tsx`** — full implementation (not a stub):

```tsx
import "../styles/stamps.css";

const STAMP_CLASS: Record<string, string> = {
  SUPPORTED:    "stamp stamp--supported",
  CONTRADICTED: "stamp stamp--contradicted",
  UNVERIFIED:   "stamp stamp--unverified",
};

export function Stamp({ verdict }: { verdict: string }) {
  return (
    <span className={STAMP_CLASS[verdict] ?? "stamp"}>
      {verdict}
    </span>
  );
}
```

**`web/src/__tests__/Stamp.test.tsx`**
```tsx
import { render, screen } from "@testing-library/react";
import { Stamp } from "../components/Stamp";

test("SUPPORTED stamp has text and green class", () => {
  const { container } = render(<Stamp verdict="SUPPORTED" />);
  expect(screen.getByText("SUPPORTED")).toBeTruthy();
  expect(container.firstChild).toHaveClass("stamp--supported");
});
test("CONTRADICTED stamp has red class", () => {
  const { container } = render(<Stamp verdict="CONTRADICTED" />);
  expect(container.firstChild).toHaveClass("stamp--contradicted");
});
test("UNVERIFIED stamp has amber class", () => {
  const { container } = render(<Stamp verdict="UNVERIFIED" />);
  expect(container.firstChild).toHaveClass("stamp--unverified");
});
```

**`web/src/components/ChainStatus.tsx`** — full implementation (not a stub):

```tsx
export function ChainStatus({
  ok,
  brokenAt,
}: {
  ok: boolean;
  brokenAt?: number | null;
}) {
  if (ok) return <span className="chain-status chain-status--ok">Paper intact</span>;
  return (
    <span className="chain-status chain-status--broken">
      Paper torn at line {brokenAt}
    </span>
  );
}
```

**`web/src/__tests__/ChainStatus.test.tsx`**
```tsx
import { render, screen } from "@testing-library/react";
import { ChainStatus } from "../components/ChainStatus";

test("intact shows Paper intact", () => {
  render(<ChainStatus ok={true} />);
  expect(screen.getByText("Paper intact")).toBeTruthy();
});
test("broken shows tear message", () => {
  render(<ChainStatus ok={false} brokenAt={3} />);
  expect(screen.getByText("Paper torn at line 3")).toBeTruthy();
});
```

**Check:**
```powershell
cd web && npm run build
npx vitest run
```
Build must succeed; all tests must pass. Back in the project root:
```powershell
pytest tests/test_hash_compat.py tests/test_import_isolation.py -v
```

---

## Task 6 — Web components: paper look, session list, replay

**Delivers:** all remaining components (complete, no stubs), hooks, CSS, and
`web/src/__tests__/App.test.tsx`

No stub implementations are permitted at the end of this task. Every component
listed here must be functional.

### 6a — CSS files

Create `web/src/styles/paper.css`, `stamps.css`, and `print.css` from design
section 5. Key requirements:

- `paper.css`: `--paper-bg: #f8f6ef`, `--band: #d8f0d0`, repeating-linear-gradient
  for the green bands at `--band-h: 1.6rem`, `.tractor-holes` and `.tractor-hole`
  for the feed holes, `.session-break` dashed rule, hide holes at ≤ 640 px,
  `button:focus-visible, a:focus-visible { outline: 2px solid #2d6a2d; outline-offset: 2px; }`.
- `stamps.css`: `.stamp`, three colour classes, `stamp-press` keyframe
  animation gated on `prefers-reduced-motion: no-preference`, `.undeclared-circle`.
- `print.css`: `@media print` block hiding `.session-list`, `.replay-controls`,
  `.ghost-clerk`, `.tamper-controls`, `.live-indicator`; showing
  `.print-report-header`, `.print-chain-status` (chain status text),
  `.print-verdict-line`, `.print-verdict-line--overall`, `.print-undeclared`.

### 6b — Hooks

**`web/src/hooks/useEntries.ts`**

Implement as in design section 5 with these refinements:

- `tamper(seq)` mutates `displayed` in memory but does **not** update
  `originalRef`. When polled entries arrive, they update `originalRef` and
  `setEntries` but do **not** overwrite `displayed` if it differs from
  `originalRef.current` (i.e. the view is currently tampered). Check this with
  `displayed !== originalRef.current` before applying a poll update.
- When new entries arrive from polling and the view is not tampered, append
  them without resetting `cursor` in the replay — only the total `entries`
  array grows; replay state is managed separately in `useReplay`.

The hook signature:
```ts
return { entries: displayed, source, tamper, restore, forceRefresh };
```
`forceRefresh` triggers an immediate re-fetch from the API (used by "Check
this statement").

**`web/src/hooks/useChainCheck.ts`** — as in design section 5.

**`web/src/hooks/useReplay.ts`** — as in design section 5. `cursor` is not
reset when `sessionEntries.length` grows (new live lines appear after the last
revealed line; `play` will reveal them naturally).

### 6c — Synthesise undeclared lines

In `web/src/lib/synthesiseUndeclared.ts`, implement:

```ts
import type { Entry } from "./chainCheck";

export type DisplayEntry = Entry & { _synthetic?: true };

export function synthesiseUndeclared(entries: Entry[]): DisplayEntry[] {
  const result: DisplayEntry[] = [];
  for (const e of entries) {
    result.push(e);
    if (
      e.kind === "verdict" &&
      (e.data as Record<string, unknown>).kind_detail === "statement_overall"
    ) {
      const undeclared =
        ((e.data as Record<string, unknown>).undeclared as Array<{path: string; change: string}>) ?? [];
      for (const item of undeclared) {
        result.push({
          seq:        -(result.length),          // unique negative key
          ts:         e.ts,
          session_id: e.session_id,
          kind:       "undeclared",
          data:       { ...item, witnessSeq: (e.data as Record<string, unknown>).witness_seq },
          prev_hash:  "",
          hash:       "",
          _synthetic: true,
        } as DisplayEntry);
      }
    }
  }
  return result;
}
```

Undeclared lines are inserted **after the per-path verdicts and before the
overall verdict stamp** is not correct — they appear after the overall verdict
line because the overall line is the trigger that holds the list. The overall
verdict line is therefore always the last real line in the session, and
undeclared lines follow it as the last visible lines.

Wait — per instruction 4: *undeclared lines print after the per-path verdicts
and before the overall verdict, so the overall stamp is the last line*. To
achieve this, insert undeclared synthetics immediately **before** the overall
verdict entry instead of after it. Update `synthesiseUndeclared`:

```ts
export function synthesiseUndeclared(entries: Entry[]): DisplayEntry[] {
  const result: DisplayEntry[] = [];
  for (const e of entries) {
    if (
      e.kind === "verdict" &&
      (e.data as Record<string, unknown>).kind_detail === "statement_overall"
    ) {
      // Insert undeclared lines BEFORE the overall verdict
      const undeclared =
        ((e.data as Record<string, unknown>).undeclared as Array<{path: string; change: string}>) ?? [];
      for (const item of undeclared) {
        result.push({
          seq:        -(result.length + 1),
          ts:         e.ts,
          session_id: e.session_id,
          kind:       "undeclared",
          data:       { ...item, witnessSeq: (e.data as Record<string, unknown>).witness_seq },
          prev_hash:  "",
          hash:       "",
          _synthetic: true,
        } as DisplayEntry);
      }
    }
    result.push(e);
  }
  return result;
}
```

The overall verdict line is now the last entry in the display sequence for the
session.

### 6d — Components (all complete)

Implement every component in full. No stubs.

**`web/src/components/TractorHoles.tsx`** — column of circles using CSS
variables.

**`web/src/components/PaperRoll.tsx`** — `.paper-roll` wrapper with left and
right `<TractorHoles>` columns positioned absolutely.

**`web/src/components/PrintLine.tsx`** — renders one `DisplayEntry`. Props:
`entry`, `visible: boolean`, `isSelected: boolean`, `onSelect: () => void`.
- If `!visible`, renders a placeholder of the same height (blank line).
- Uses `entryText` for display text.
- If `kind === "verdict"` and not overall, appends `<Stamp verdict={...}>`.
- If `kind === "undeclared"`, wraps content in `<UndeclaredCircle>`.
- Sets `id="line-{entry.seq}"` (synthetic entries use their negative seq, which
  is unique but not used for scrolling targets).
- Applies `print-line--tamper-target` class when `isSelected`.
- Calls `onSelect` when clicked.

**`web/src/components/UndeclaredCircle.tsx`** — dashed red circle, scrolls to
`#line-{witnessSeq}` on click/Enter/Space.

**`web/src/components/TearLine.tsx`** — SVG jagged red line,
`aria-label="Paper torn here"`.

**`web/src/components/SessionSpool.tsx`** — spool card rendering
`sessionMeta.title`, truncated ID, date, verdict stamp if present. In live
mode (`source === "api"`), when `hasUnverifiedStatement` is true, renders
`<button>Check this statement</button>`. On click: calls
`POST /api/verify/{sessionId}/{statementIndex}`, shows a loading state, on
success calls `onVerified()`. On error shows an inline error message.

**`web/src/components/ReplayControls.tsx`** — Play/Pause/Step `<button>`
elements, `<select>` for speed (Slow/Normal/Fast), all native keyboard
accessible.

**`web/src/components/LiveIndicator.tsx`** — `<span className="live-indicator">LIVE</span>`.

**`web/src/components/Header.tsx`** — `<h1>` and explanation sentence.

**`web/src/components/Footer.tsx`** — `<a href={repoUrl}>View on GitHub</a>`.

**`web/src/components/TearOffButton.tsx`** — `<button onClick={() => window.print()}>Tear off report</button>`.

**`web/src/App.tsx`** — full implementation wiring all hooks and components:

```tsx
declare const __REPO_URL__: string;
```

at the top of the file so TypeScript knows about the Vite-defined constant.

The repo URL is read from `__REPO_URL__` (injected by Vite from
`process.env.VITE_REPO_URL ?? "#"`).

### 6e — `web/src/__tests__/App.test.tsx`

This test renders `<App />` with the demo ledger loaded via a mock `fetch` and
asserts four behaviours without starting a server.

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import App from "../App";
import demoLedgerRaw from "../../public/demo/ledger.jsonl?raw";

const demoEntries = demoLedgerRaw.trim().split("\n")
  .filter(Boolean).map((l: string) => JSON.parse(l));

beforeEach(() => {
  // Mock fetch: /api/ledger fails → app falls back to demo ledger.
  // The demo fetch (./demo/ledger.jsonl) also returns demo entries.
  vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/ledger")) {
      return Promise.reject(new Error("no server"));
    }
    // Static demo fallback
    const text = demoLedgerRaw;
    return Promise.resolve(new Response(text, { status: 200 }));
  });
});

describe("App with demo data", () => {
  it("preselects the CONTRADICTED session", async () => {
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText(/CONTRADICTED/i)).toBeTruthy()
    );
  });

  it("shows the undeclared line for sample/notes.txt after stepping to end", async () => {
    render(<App />);
    // Wait for data to load
    await waitFor(() => screen.getByText(/Press Play/i));
    // Step through all lines
    const stepBtn = screen.getByRole("button", { name: /step/i });
    const totalLines = demoEntries.filter(
      (e: { session_id: string }) =>
        e.session_id ===
        demoEntries.find(
          (x: { kind: string; data: { kind_detail?: string; verdict?: string } }) =>
            x.kind === "verdict" &&
            x.data.kind_detail === "statement_overall" &&
            x.data.verdict === "CONTRADICTED"
        )?.session_id
    ).length + 10; // generous upper bound including synthetics
    for (let i = 0; i < totalLines; i++) {
      fireEvent.click(stepBtn);
    }
    await waitFor(() =>
      expect(screen.getByText(/sample\/notes\.txt/)).toBeTruthy()
    );
    expect(screen.getByText(/never mentioned/i)).toBeTruthy();
  });

  it("shows Paper torn at line after tampering", async () => {
    render(<App />);
    await waitFor(() => screen.getByText(/Press Play/i));
    fireEvent.click(screen.getByRole("button", { name: /tamper with the paper/i }));
    await waitFor(() =>
      expect(screen.getByText(/Paper torn at line/i)).toBeTruthy()
    );
  });

  it("shows Paper intact after Restore", async () => {
    render(<App />);
    await waitFor(() => screen.getByText(/Press Play/i));
    fireEvent.click(screen.getByRole("button", { name: /tamper with the paper/i }));
    await waitFor(() => screen.getByText(/Paper torn at line/i));
    fireEvent.click(screen.getByRole("button", { name: /restore/i }));
    await waitFor(() =>
      expect(screen.getByText("Paper intact")).toBeTruthy()
    );
  });
});
```

**Check:**
```powershell
cd web && npm run build
npx vitest run
```
Build must succeed; all tests (including `App.test.tsx`) must pass.

---

## Task 7 — Ghost clerk

**Delivers:** `web/src/components/GhostClerk.tsx` (complete, no stub)

### 7a — SVG ghost design

Implement `GhostSvg` with the three-expression inline SVG exactly as specified
in design section 5. The ghost must:
- Have a rounded rectangular white body with a ragged bottom (three bumps).
- Wear a bright green visor (`#3a7d44` rect) with a darker brim (`#2d6235`).
- Have two dot eyes whose radius changes by expression.
- Have a mouth that changes by expression:
  - **calm**: straight line `x1=40 y1=63 x2=60 y2=63`.
  - **pleased**: upward arc `M 38 62 Q 50 70 62 62`.
  - **alarmed**: filled ellipse `cx=50 cy=63 rx=5 ry=6`.
- viewBox `0 0 100 100`, rendered at 60×60 px, `aria-hidden="true"`.

### 7b — Message logic

Implement `GhostClerk` accepting props `source`, `replayState`, `chainOk`,
`overallVerdict`, `tamperTargetSelected`. Derive expression and message from the
priority-ordered state table:

1. `!chainOk` → alarmed / "Ah. Someone's been at the paper. Click Restore to fix it."
2. `tamperTargetSelected` → calm / "Line selected. Click 'Tamper with the paper' to corrupt it."
3. `source === "loading"` → calm / "Loading the paper trail…"
4. `source === "demo" && replayState === "idle"` → calm / "I've pre-loaded the interesting session. Press Play when ready."
5. `replayState === "idle"` → calm / "Press Play to start. I'll stay here and watch."
6. `replayState === "playing"` → calm / "Printing… press Pause any time, or Step to go one line at a time."
7. `replayState === "paused"` → calm / "Paused. Press Play to continue, or Step to advance one line."
8. `replayState === "done" && overallVerdict === "SUPPORTED"` → pleased / "Everything checks out. The agent told the whole truth. Remarkable."
9. `replayState === "done" && overallVerdict === "CONTRADICTED"` → alarmed / "The agent left something out. The red circle shows what the witness saw."
10. `replayState === "done" && overallVerdict === "UNVERIFIED"` → calm / "Some claims couldn't be confirmed. Not the same as wrong — just unproven."
11. `replayState === "done"` → calm / "All done. No verdict yet — click 'Check this statement' to find out."

The message span has `aria-live="polite"`.

### 7c — Layout

Apply the CSS from design section 5:
- Wide (> 640 px): fixed bottom-right, 220 px wide.
- Narrow (≤ 640 px): fixed full-width bottom bar, 2.6 rem tall.
- Hidden in `@media print`.

**Check:**
```powershell
cd web && npm run build
npx vitest run
```

---

## Task 8 — Tamper demo, "Check this statement", accessibility, print

**Delivers:** full tamper/restore wiring, "Check this statement" functional,
accessibility pass, print styles complete. No stubs remain anywhere.

### 8a — Tamper and restore in `App.tsx`

Wire `useEntries`'s `tamper(seq)` and `restore()`:

- `<PrintLine onSelect>` calls `setTamperTarget(entry.seq)` when clicked;
  clicking the already-selected line clears `tamperTarget`.
- "Tamper with the paper" button: calls `tamper(tamperTarget)` if set,
  otherwise finds the first entry in the current session where
  `data.tool_name === "execute_pwsh"` and calls `tamper` with its seq; falls
  back to the last entry if none found.
- "Restore" button: calls `restore()` and `setTamperTarget(null)`.
- Selected line gets CSS class `print-line--tamper-target` (yellow background).
- Neither button is shown in static demo mode (live mode only), but the demo
  mode still allows tampering via line click and the button for the interactive
  demo. The tamper feature is always available regardless of mode.

### 8b — Live polling refinements in `useEntries`

Confirm the two behaviours specified in task 6b hold:
1. Polling never overwrites `displayed` when it differs from `originalRef`
   (tampered view is preserved until Restore is clicked).
2. When new entries arrive and no tamper is active, `displayed` is updated but
   `cursor` in `useReplay` is not reset (new lines appear beyond the current
   replay position).

The check for "tampered" is `displayed !== originalRef.current` (referential
inequality, since `tamper()` always produces a new array). Do not use
deep-equality — reference comparison is sufficient and cheap.

### 8c — Accessibility pass

Verify all interactive elements:
- Are `<button>` or `<a>` with no `onClick` on bare `<div>`.
- Have `:focus-visible` outlines (already in `paper.css`).
- Have `aria-label` where text is absent or ambiguous.
- `<GhostClerk>`'s message span has `aria-live="polite"`.

### 8d — Print stylesheet

Confirm `print.css` renders correctly:
- Chain status appears as `.print-chain-status` outside `.tamper-controls`.
- Per-path verdict lines include `(line N)` from `entryText`.
- Undeclared lines appear before the overall verdict (the overall line is last).
- Background images and colours are removed in print.

**Check:**
```powershell
cd web && npm run build
npx vitest run
```
All tests pass, build succeeds.

---

## Task 9 — Full integration and final checks

**Delivers:** all tests green, `web/public/demo/ledger.jsonl` committed,
`requirements.txt` updated

### 9a — Regenerate demo ledger

```powershell
python sample/make_demo_ledger.py
```

Confirm `web/public/demo/ledger.jsonl` is non-empty and the demo chain test in
Vitest passes. The file must include an overall verdict entry for Session B
with `data.undeclared` containing `sample/notes.txt`.

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
- `App.test.tsx` (all four assertions).

### 9d — Static build

```powershell
cd web && npm run build
```

Build must complete with no errors. No long-running server is started.

**Check (final):**
```powershell
pytest tests/ -q
cd web && npx vitest run && npm run build
```
All three commands exit 0.

---

## Task 10 — GitHub Actions Pages workflow

**Delivers:** `.github/workflows/pages.yml`

### 10a — Workflow file

Create `.github/workflows/pages.yml`:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: web

      - name: Build
        run: npm run build
        working-directory: web
        env:
          VITE_REPO_URL: https://github.com/${{ github.repository }}

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: web/dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

Key points:
- `VITE_REPO_URL` is injected from `github.repository` so the footer link is
  always correct without any hardcoded organisation name.
- `npm ci` is used (not `npm install`) for reproducible installs.
- `cache-dependency-path: web/package-lock.json` caches the `web/node_modules`
  install correctly.
- `workflow_dispatch` allows manual re-runs from the Actions tab.

### 10b — Confirm `web/public/demo/ledger.jsonl` is committed

The workflow builds a static site that depends on the demo ledger being present
in the repository. Confirm:

```powershell
git status web/public/demo/ledger.jsonl
```

If the file shows as untracked or modified, add it:

```powershell
git add web/public/demo/ledger.jsonl
```

The `.gitignore` must not contain `web/public/demo/`.

**Check:**
```powershell
Get-Content .github\workflows\pages.yml | Select-Object -First 5
git status web/public/demo/ledger.jsonl
```
The workflow file must exist and the ledger must be tracked by git.
