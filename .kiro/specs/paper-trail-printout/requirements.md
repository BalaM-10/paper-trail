# Requirements — Paper Trail Printout

## Scope

Demo ledger generator, local read-only API, web printout view, MCP server,
and their tests. The core modules `ledger.py`, `witness.py`, `statement.py`,
`recorder.py`, and `session.py` are complete and must not be changed.
One permitted change: `papertrail/verifier.py` must be updated so the overall
verdict ledger entry stores the undeclared-changes list (R2). All other
additions go into new files.

---

## R1 — Demo ledger generator

### R1.1 Generator script

`sample/make_demo_ledger.py` builds a self-contained demo ledger by calling
the real `papertrail` functions—`on_start`, `record`, `on_stop`, `verify`—in
a single temporary directory, then copies the finished ledger to
`web/public/demo/ledger.jsonl`. It never writes to the project's own
`.papertrail/`.

The generator records exactly two sessions into the same temporary root (and
therefore the same `ledger.jsonl`) using different session IDs, one after the
other. No merging, no re-sequencing, no re-numbering. The `PAPERTRAIL_ROOT`
environment variable is never set by the generator; every call passes
`root=tmp_root` and `home=Path.home()` explicitly.

**Session A — honest agent (overall verdict SUPPORTED)**

Start state: `src/main.py` exists in the temp root.

1. `on_start` — real `witness.snapshot` records `src/main.py`.
2. Create `docs/notes.md` on disk.
3. `record` with a `read_file` payload (`path`: `src/main.py`).
4. `record` with an `fs_write` payload (`path`: `docs/notes.md`).
5. Statement: `files_read: ["src/main.py"], files_created: ["docs/notes.md"]`.
6. `on_stop` — diff shows `docs/notes.md` created.
7. `verify` — read SUPPORTED (tool entry exists), created SUPPORTED (in diff).
   Overall: SUPPORTED.

**Session B — cleanup story (overall verdict CONTRADICTED)**

Start state: `sample/notes.txt` and `sample/cache/output.bin` are created on
disk after Session A's `on_stop`, so they appear in Session B's start snapshot
but not Session A's.

1. `on_start` — real snapshot records both files.
2. Delete both files from disk.
3. `record` with an `execute_pwsh` payload (command `python sample/cleanup.py`).
4. Statement: `files_deleted: ["sample/cache/output.bin"]` only.
5. `on_stop` — diff shows both files deleted.
6. `verify` — `output.bin` SUPPORTED, `notes.txt` undeclared → overall
   CONTRADICTED.

The generator creates real files so `witness.snapshot` runs against the real
filesystem — no hand-built snapshot dicts. All paths in the generated ledger
are relative and neutral because `ledger.append`'s `_sanitise_data` replaces
the temp root with `"."`.

**Acceptance criteria**

- AC1.1a: Running `python sample/make_demo_ledger.py` exits 0 and writes
  `web/public/demo/ledger.jsonl`.
- AC1.1b: The file contains entries for both sessions; each session has at
  least a `witness` start entry, one or more `tool` entries, a `witness` stop
  entry, a `statement` entry, and one or more `verdict` entries.
- AC1.1c: The last `verdict` entry for Session A has `data.verdict =
  "SUPPORTED"` and `data.kind_detail = "statement_overall"`.
- AC1.1d: The last `verdict` entry for Session B has `data.verdict =
  "CONTRADICTED"` and `data.kind_detail = "statement_overall"`.
- AC1.1e: No entry contains an absolute path, a drive letter, a user name, or
  a machine name.
- AC1.1f: `verify_chain` on the generated ledger returns `(True, None)`.
- AC1.1g: The overall verdict entry for Session B has `data.undeclared`
  containing at least `{"path": "sample/notes.txt", "change": "deleted"}`.

### R1.2 Generator test

`tests/test_make_demo_ledger.py` calls the generator as a function (not as a
subprocess). The generator exposes `generate(out_path: Path)` which accepts an
explicit output path so tests redirect to `tmp_path / "ledger.jsonl"` and
never touch `web/public/demo/` or the project's `.papertrail/`. Tests check
structure and overall verdicts; they do not assert byte-for-byte snapshot
contents.

**Acceptance criteria**

- AC1.2a: Tests call `generate(out_path=tmp_path / "ledger.jsonl")` and assert
  all AC1.1 conditions.
- AC1.2b: No test writes to the project's own `.papertrail/` or `web/`.

---

## R2 — Verifier change (one permitted core modification)

### R2.1 Undeclared changes in the overall verdict entry

`papertrail/verifier.py` is updated so the overall `verdict` ledger entry's
`data` includes `"undeclared": [{"path": str, "change": str}]`. The function
signature and return value are unchanged; only the ledger write for the overall
entry gains the extra field.

Idempotency is preserved: when reconstructing from an existing overall entry,
`undeclared` is read from `existing_overall["data"].get("undeclared", [])`.

**Acceptance criteria**

- AC2.1a: After `verify` runs, the overall `verdict` entry in the ledger has
  `data.undeclared` as a list of `{"path", "change"}` dicts (may be empty).
- AC2.1b: For Session B of the demo, `data.undeclared` contains
  `{"path": "sample/notes.txt", "change": "deleted"}`.
- AC2.1c: A second call to `verify` with the same statement returns the same
  `undeclared` list and appends no new ledger entries.
- AC2.1d: `tests/test_verifier.py` has at least one test asserting
  `data.undeclared` on the overall entry matches the expected list.

---

## R3 — Local API

### R3.1 Endpoints

`papertrail/api.py` is a FastAPI application started by
`python -m papertrail serve`. It binds to `127.0.0.1:8765` by default.

The root is `PAPERTRAIL_ROOT` when set, otherwise the parent of the
`papertrail/` package directory.

| Method | Path | Description |
|---|---|---|
| GET | `/api/ledger` | Returns all entries as a JSON array, in append order. |
| GET | `/api/chain` | Returns `{"ok": bool, "broken_at": int\|null, "count": int}`. |
| POST | `/api/verify/{session_id}/{n}` | Runs `verifier.verify` for `<session_id>-<n>.json`. Returns the result dict or HTTP 404 if the file is absent. |

The API binds to `127.0.0.1` only. CORS allows only `http://localhost:5173`
(Vite dev server). The Vite dev server proxies `/api` to port 8765 so the app
makes no cross-origin requests in production.

**Acceptance criteria**

- AC3.1a: `GET /api/ledger` returns HTTP 200 and all entries in order.
- AC3.1b: `GET /api/ledger` returns `[]` when the ledger is absent.
- AC3.1c: `GET /api/chain` returns `{"ok": true, "broken_at": null, "count": N}`
  on a valid chain.
- AC3.1d: `GET /api/chain` returns `{"ok": false, "broken_at": N, "count": M}`
  when broken.
- AC3.1e: `POST /api/verify/{session_id}/{n}` returns HTTP 200 and a dict with
  `verdicts`, `undeclared`, and `overall` on success.
- AC3.1f: `POST /api/verify/{session_id}/{n}` returns HTTP 404 when the
  statement file is absent.
- AC3.1g: No write endpoint exists other than `POST /api/verify`, whose only
  side effect is appending verdict entries via `verifier.verify`.
- AC3.1h: `Access-Control-Allow-Origin` is set to `http://localhost:5173`
  only. No wildcard.

### R3.2 Serve subcommand

**Acceptance criteria**

- AC3.2a: `python -m papertrail serve` starts on `127.0.0.1:8765` and prints
  a startup message.
- AC3.2b: `python -m papertrail serve --port 9000` starts on port 9000.

### R3.3 API tests

`tests/test_api.py` uses FastAPI's `TestClient`. Every test sets
`PAPERTRAIL_ROOT` to a `tmp_path`.

**Acceptance criteria**

- AC3.3a: Tests cover all three endpoints with both the success and error/empty
  cases.
- AC3.3b: The `POST /api/verify` test asserts the returned `overall` field.
- AC3.3c: `pytest tests/test_api.py` exits 0.

---

## R4 — Web printout view

### R4.1 Data loading and live mode

The web app tries `/api/ledger` first. On failure it falls back to
`./demo/ledger.jsonl` (relative URL, works from any static base). In live mode
(API reachable) the app polls `/api/ledger` every 2 seconds; new entries are
appended to the display and a "LIVE" indicator is shown. In static demo mode
there is no polling and no indicator.

**Acceptance criteria**

- AC4.1a: When the API returns 200, the app displays entries from the API.
- AC4.1b: When the API is unreachable, the app falls back to
  `./demo/ledger.jsonl` without showing an error page.
- AC4.1c: The built site works as a static demo with no backend.
- AC4.1d: `vite.config.ts` sets `base: "./"` and the demo fetch uses a
  relative URL.
- AC4.1e: In live mode, polling occurs every 2 seconds; new entries are
  appended and "LIVE" is visible.
- AC4.1f: In static demo mode there is no polling and no "LIVE" indicator.

### R4.2 "Check this statement" button (live mode only)

In live mode, a session spool whose statement has not yet been verified shows a
"Check this statement" button. Clicking it calls `POST /api/verify/{id}/{n}`,
then reloads entries from the API so the verdict stamps appear on the paper.
In static demo mode all verdicts are already in the demo ledger; the button is
not shown.

**Acceptance criteria**

- AC4.2a: In live mode, a spool with a `statement` entry and no
  `statement_overall` verdict entry shows "Check this statement".
- AC4.2b: Clicking the button calls `POST /api/verify/{session_id}/{n}` and,
  on success, refreshes entries from the API.
- AC4.2c: After the refresh, verdict stamps appear on the paper.
- AC4.2d: The button is never shown in static demo mode.

### R4.3 First-load page chrome

**Acceptance criteria**

- AC4.3a: The page has a one-line heading "Paper Trail: what did the agent
  really do?" visible above the session list.
- AC4.3b: Immediately below the heading is one sentence of plain-language
  explanation (e.g. "Pick a session below and press Play to see the full record
  of what the agent did — and what the witness saw.").
- AC4.3c: In static demo mode, the CONTRADICTED session (Session B) is
  preselected when the page loads. Its entries are shown in the replay view and
  the ghost clerk's opening message invites the user to press Play.
- AC4.3d: Each spool is titled with the statement summary from the promoted
  statement entry. If no statement entry exists for the session, the title
  falls back to the first 8 characters of the session ID.
- AC4.3e: A footer links to the GitHub repository. The link text is "View on
  GitHub". The URL is `https://github.com/` followed by the actual repository
  path (set as a Vite `define` constant `__REPO_URL__` in `vite.config.ts`
  with a placeholder that the implementer fills in; it must not be an empty
  string in the committed config).

### R4.4 Paper look

**Acceptance criteria**

- AC4.4a: Off-white background; alternating pale-green horizontal bands at a
  natural line height.
- AC4.4b: Tractor-feed holes down both edges, visually distinguishable from
  content.
- AC4.4c: A perforation line between sessions.
- AC4.4d: All content in a monospace font.
- AC4.4e: Responsive: tractor holes hidden at phone widths; no horizontal
  scrolling at 375 px.

### R4.5 Session list

**Acceptance criteria**

- AC4.5a: Every distinct `session_id` appears as a spool.
- AC4.5b: Spools with an overall verdict show it as a stamp.
- AC4.5c: Each spool's title is the statement summary (AC4.3d fallback applies).
- AC4.5d: Clicking a spool loads its entries in the replay view.

### R4.6 Replay

Each entry renders in plain language using tool-name verbs and named file
lists (see design). The table below maps entry kinds to display text:

| `kind` | Display text |
|---|---|
| `witness` start | "Witness took a snapshot of the project." |
| `witness` stop | "Witness compared the project to the earlier snapshot. Created: … Changed: … Deleted: …" (file names listed; groups omitted when empty) |
| `tool` `read_file` | "Agent read \<path\>." |
| `tool` `fs_write` | "Agent wrote \<path\>." |
| `tool` `str_replace` | "Agent edited \<path\>." |
| `tool` `execute_pwsh` | "Agent ran the command: \<command truncated to 80 chars\>." |
| `tool` other | "Agent used a tool: \<tool\_name\>." |
| `statement` | "Agent stated: \<summary\>." |
| `verdict` per-path | "\<path\>: \<VERDICT\>  (line \<seq\>)" |
| `verdict` overall | "Overall verdict: \<VERDICT\>" |
| `undeclared` (synthetic) | "Witness saw \<path\> \<change\>. The agent never mentioned it." |
| `error` | "Something went wrong: \<message\>." |

Undeclared-change lines are synthesised from the `undeclared` list of the
overall verdict entry and inserted immediately after the overall verdict line.

**Acceptance criteria**

- AC4.6a: Replay starts hidden; first line position is marked.
- AC4.6b: Play reveals lines one at a time. Speeds: Slow 1 s, Normal 400 ms,
  Fast 100 ms per line.
- AC4.6c: Pause stops; Step advances one line.
- AC4.6d: Playing a fully-replayed session replays from the start.
- AC4.6e: Tool entries use the verb mapping above.
- AC4.6f: Witness stop lines name the files grouped by created/changed/deleted;
  groups with no files are omitted.
- AC4.6g: Undeclared-change lines are circled in red and scroll to the witness
  stop entry that is the evidence source when clicked.

### R4.7 Verdict stamps

**Acceptance criteria**

- AC4.7a: SUPPORTED stamp: green `#2d6a2d`, bordered, slightly rotated.
- AC4.7b: CONTRADICTED stamp: red `#8b1a1a`, same treatment.
- AC4.7c: UNVERIFIED stamp: amber `#7a5c00`.
- AC4.7d: Stamps overlay the relevant line, not stacked below it.
- AC4.7e: Stamp press animation unless `prefers-reduced-motion` is set.

### R4.8 Chain check in the browser

The app verifies the paper in the browser using Web Crypto SHA-256. Canonical
JSON is `JSON.stringify` with keys sorted and no extra spacing. Non-ASCII
characters are kept literal (not `\uXXXX`-escaped) by using `JSON.stringify`
directly on the string value with no post-processing, relying on the fact that
`JSON.stringify` preserves non-BMP and non-ASCII printable characters literally
in modern engines when `ensure_ascii` is not forced. Control characters below
U+0020 that `JSON.stringify` escapes as `\uXXXX` are left as-is; the hash
fixture test (R6.2) confirms the Python and browser results match for all
relevant character classes.

**Acceptance criteria**

- AC4.8a: Intact paper → "Paper intact" indicator.
- AC4.8b: Broken paper → "Paper torn at line N" with a tear graphic at that
  line.
- AC4.8c: Browser SHA-256 matches Python for the fixture entry (confirmed by
  R6.2 test).
- AC4.8d: Chain check runs on load and after every entry update.

### R4.9 Tamper demo

**Acceptance criteria**

- AC4.9a: Clicking a printed line selects it as the tamper target (highlighted).
  Clicking again deselects.
- AC4.9b: "Tamper with the paper" with a line selected mutates that line's
  `data` in memory. With no selection, it mutates the first `execute_pwsh`
  entry of the current session, or the last entry if none exists.
- AC4.9c: After tampering, "Paper torn at line N" appears at the first
  line whose integrity fails.
- AC4.9d: "Restore" reloads original entries and shows "Paper intact".
- AC4.9e: Neither action writes to disk or the API.

### R4.10 Ghost clerk

A small ghost character, drawn as an original inline SVG wearing a green
clerk's eyeshade, sits in a fixed corner and shows one plain-language sentence.
The ghost has at least three distinct expressions — calm, pleased, and alarmed
— rendered as SVG variations and selected based on state. It must not resemble
any existing mascot. Its messages have a light, dry sense of humour while
always saying what to click next.

**Acceptance criteria**

- AC4.10a: On viewports wider than 640 px the ghost is in the bottom-right
  corner. On narrower viewports it is a slim bottom bar.
- AC4.10b: The ghost's expression changes: calm at rest, pleased when overall
  verdict is SUPPORTED, alarmed when CONTRADICTED or paper torn.
- AC4.10c: Messages are plain language with dry humour. No jargon.
- AC4.10d: First load, demo mode, no session selected: ghost says something
  like "I've pre-loaded the interesting session. Press Play when ready." and
  the expression is calm.
- AC4.10e: When the paper is torn: "Ah. Someone's been at the paper. Click
  Restore to fix it." Expression is alarmed.
- AC4.10f: When SUPPORTED: "Everything checks out. This agent did exactly what
  it claimed." Expression is pleased.
- AC4.10g: When CONTRADICTED: "The agent left something out. The red circle
  shows what the witness saw." Expression is alarmed.

### R4.11 "Tear off report" print stylesheet

**Acceptance criteria**

- AC4.11a: "Tear off report" button calls `window.print()`.
- AC4.11b: Print stylesheet hides: session list, replay controls, ghost clerk,
  tamper buttons.
- AC4.11c: Printed output includes: session ID, statement summary, paper-intact
  or paper-torn-at-line-N status, each per-path verdict with its evidence line
  number(s) in parentheses, undeclared changes, overall verdict as the last
  line.
- AC4.11d: Print output is clean monospace, no background colours.

### R4.12 Accessibility and motion

**Acceptance criteria**

- AC4.12a: Every interactive element is keyboard focusable and activatable.
- AC4.12b: Visible focus indicators on all interactive elements.
- AC4.12c: Verdict stamps carry text, not just colour.
- AC4.12d: `prefers-reduced-motion: reduce` disables replay and stamp
  animations.
- AC4.12e: No horizontal scrolling at 375 px viewport width.

### R4.13 Plain language

**Acceptance criteria**

- AC4.13a: No on-screen text contains "hash", "chain", "ledger", "entry",
  "seq", "JSONL", "SHA-256", "canonical", or "hex".
- AC4.13b: Chain status reads "Paper intact" or "Paper torn at line N".
- AC4.13c: Tamper button reads "Tamper with the paper".
- AC4.13d: Undeclared changes display as "Witness saw \<path\> \<change\>.
  The agent never mentioned it."

---

## R5 — MCP server

### R5.1 Tools

`papertrail/mcp_server.py` is a stdio MCP server.

| Tool | Input | Output |
|---|---|---|
| `list_sessions` | — | `[{session_id, entry_count, has_statement, overall_verdict\|null}]` |
| `get_entries` | `session_id: str` | All entries for that session in seq order. |
| `check_chain` | — | `{ok, broken_at, count}` |
| `verify_statement` | `session_id: str, n: int` | `verify` result or `{error: str}` |

**Acceptance criteria**

- AC5.1a: `list_sessions` returns one item per distinct session with correct
  `entry_count`.
- AC5.1b: `has_statement` is `true` when at least one `statement` entry exists.
- AC5.1c: `overall_verdict` is the string verdict or `null`.
- AC5.1d: `get_entries` returns only entries for the given session.
- AC5.1e: `check_chain` matches `ledger.verify_chain`.
- AC5.1f: `verify_statement` returns the verifier result or `{error: ...}`.

### R5.2 Workspace MCP registration

`.kiro/settings/mcp.json` registers the server as `"paper-trail"`.

**Acceptance criteria**

- AC5.2a: `.kiro/settings/mcp.json` has `"mcpServers"."paper-trail"` with
  `"command": "python"` and `"args": ["-m", "papertrail.mcp_server"]`.
- AC5.2b: No absolute paths or machine-specific values in the file.

### R5.3 MCP tests

`tests/test_mcp_server.py` calls handler functions directly with `tmp_path`.

**Acceptance criteria**

- AC5.3a–e: (same as prior AC4.3a–e, renumbered) empty ledger returns `[]`;
  two sessions returns two items; `get_entries` filters by session; chain check
  passes on valid ledger; `verify_statement` returns correct overall verdict.

---

## R6 — Tests

### R6.1 Generator tests

Already covered by R1.2.

### R6.2 Cross-language hash compatibility

`tests/fixtures/hash_fixture.json` contains one entry (without `hash`) and its
expected SHA-256. The entry's `data` contains strings with: straight double
quotes, a backslash, a newline (`\n`), a tab (`\t`), the control character
U+0001, an emoji (e.g. `"🔍"`), and a non-ASCII Latin character (e.g.
`"café"`). The expected hash is computed by Python and committed. Both the
Python test and the TypeScript test load this fixture and assert the computed
hash equals `expected_hash`.

**Acceptance criteria**

- AC6.2a: `tests/test_hash_compat.py` asserts
  `_compute_hash(fixture_entry) == expected_hash`.
- AC6.2b: `web/src/__tests__/chainCheck.test.ts` asserts the browser
  implementation produces `expected_hash`.
- AC6.2c: `web/src/__tests__/demoChain.test.ts` loads
  `web/public/demo/ledger.jsonl` (via import or file read in Vitest) and
  asserts `checkChain(entries)` returns `{ok: true}`.

### R6.3 Component tests

`web/src/__tests__/` uses Vitest + `@testing-library/react`.

**Acceptance criteria**

- AC6.3a: `Stamp.test.tsx` covers SUPPORTED (green class), CONTRADICTED (red),
  UNVERIFIED (amber).
- AC6.3b: `ChainStatus.test.tsx` covers `ok={true}` → "Paper intact" and
  `ok={false} brokenAt={3}` → "Paper torn at line 3".

### R6.4 Import isolation test

`tests/test_import_isolation.py` asserts that importing `papertrail.ledger`,
`papertrail.witness`, `papertrail.session`, and `papertrail.recorder` does not
cause `fastapi`, `uvicorn`, `httpx`, or `mcp` to appear in `sys.modules`.

**Acceptance criteria**

- AC6.4a: The test imports each of the four core modules in a subprocess
  (or uses `importlib` with a clean slate) and asserts none of the four
  optional packages are loaded as a side effect.
- AC6.4b: `pytest tests/test_import_isolation.py` exits 0.

### R6.5 Full suite green

**Acceptance criteria**

- AC6.5a: `pytest tests/ -q` exits 0 after all implementation tasks are done.
- AC6.5b: `npx vitest run` in `web/` exits 0.

---

## R7 — Non-functional

### R7.1 Performance

**Acceptance criteria**

- AC7.1a: `GET /api/ledger` with 10 000 entries completes in under 2 s.
- AC7.1b: Generator completes in under 5 s.
- AC7.1c: Hook scripts complete in under 1 s (unchanged from core spec).

### R7.2 Security

**Acceptance criteria**

- AC7.2a: API exposes no write endpoint other than `POST /api/verify`.
- AC7.2b: MCP server modifies no files outside `.papertrail/`.
- AC7.2c: No secrets, absolute paths, or machine-specific values in any
  committed file.
