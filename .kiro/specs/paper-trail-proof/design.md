# Design — Paper Trail Proof

## Overview

```
sample/cleanup.py   ordinary broad pattern        sample/reset.py   restore(folder)
sample/make_demo_ledger.py   runs the real script; adds session C

papertrail/session.py   on_stop: NO_STATEMENT verdict (stdlib only)
papertrail/outcome.py   NO_STATEMENT, session ids, "what does this session say?"
papertrail/spool.py     sentences, the 80-column text, the file
papertrail/__main__.py  verify uses outcome; new `print`
papertrail/api.py       verify uses outcome; new route
papertrail/mcp_server.py   verify uses outcome; new print_session

web/                    NO STATEMENT stamp, wording, clerk, report fingerprint,
                        ring shape, conditional footer
tests/fixtures/sentences.json   one set of sentences, read by Python and TypeScript
.github/workflows/tests.yml     three operating systems
```

Import graph (all standard library, so the hook scripts stay light):

```
session  -> ledger, witness, statement, outcome
outcome  -> ledger, statement, verifier
spool    -> ledger, outcome
verifier -> ledger, witness
```

`test_import_isolation.py` already proves `session` pulls in nothing outside the
standard library; it keeps proving it.

---

## 1. The sample bug

`sample/cleanup.py`:

```python
"""Clear the build cache."""
from pathlib import Path

here = Path(__file__).parent

# Build output ends in .bin and the tools leave .txt logs beside it, so clear
# both kinds anywhere under this folder.
for pattern in ("*.bin", "*.txt"):
    for path in here.rglob(pattern):
        path.unlink()

print("Cleared build cache: removed cache/output.bin")
```

`*.txt` also matches `notes.txt`. Nothing is hidden; the printed line is simply
the one the author had in mind. `rglob` visits `cleanup.py`, `reset.py`,
`README.md` and `src/main.py` and skips them, because none ends in `.bin` or
`.txt`.

`sample/reset.py`:

```python
CACHE_BYTES = b"\x00FAKE_BUILD_OUTPUT\x00"
NOTES_TEXT  = "Project notes\n\nSee src/main.py for the entry point.\n"

def restore(folder: Path) -> list[str]:
    """Write the sample's starting files into folder. Returns their relative paths."""

def main() -> None:           # python sample/reset.py
    ...
if __name__ == "__main__":
    main()
```

The generator imports `restore`, so the demo's starting files are the sample's.

`make_demo_ledger.py` copies `sample/cleanup.py` into the temporary project's
`sample/` folder before `on_start`, so the script is in the start snapshot. After
`on_start` it runs it with `subprocess.run([sys.executable, script], cwd=root,
capture_output=True, text=True, check=True, timeout=30)` and records the real
standard output as the tool response. `os.environ` is never changed. The witness
diff then comes from what the script did.

---

## 2. NO_STATEMENT

### 2.1 `papertrail/outcome.py`

```python
NO_STATEMENT = "NO_STATEMENT"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

def valid_session_id(session_id: str) -> bool          # regex and no ".."
def undeclared_from_diff(diff: dict) -> list[dict]     # created, modified, deleted
def last_overall(entries, session_id) -> dict | None   # newest statement_overall verdict
def latest_no_statement(entries, session_id) -> dict | None
def no_statement_result(entry: dict) -> dict           # {"verdicts": [], "undeclared": [...], "overall": NO_STATEMENT}
def result_for(root, session_id, n=None) -> dict | None
```

`result_for` is the one place that answers "what does this session say?":

- `n` given: the statement file `<id>-<n>.json` must exist; run
  `verifier.verify` on it (this appends verdict records once, as before).
  Otherwise `None`.
- `n` omitted: take the highest-numbered statement file and the latest
  NO_STATEMENT verdict. If only one exists use it. If both, use the one with the
  larger `witness_seq` (the one that happened later). If neither, `None`.
- An unsafe session id gives `None`. A statement that cannot be parsed raises
  `ValueError`; callers turn it into their own error.

The CLI, the API and the MCP server all call it, so they cannot disagree.

### 2.2 `session.on_stop`

After promotion (or rejection) of any statement:

```python
if not promoted:
    _record_no_statement(ledger_path, session_id, stop_entry, diff, entries)
```

```python
def _record_no_statement(ledger_path, session_id, stop_entry, diff, entries):
    undeclared = undeclared_from_diff(diff)
    if not undeclared:
        return None                      # nothing changed, or no baseline
    last = last_overall(entries, session_id)
    if last and last["data"].get("verdict") == NO_STATEMENT \
            and last["data"].get("undeclared") == undeclared:
        return None                      # already said exactly this
    return ledger.append(ledger_path, session_id, "verdict", {
        "kind_detail": "statement_overall", "verdict": NO_STATEMENT,
        "evidence_seq": [stop_entry["seq"]], "witness_seq": stop_entry["seq"],
        "undeclared": undeclared,
    })
```

`entries` is the list `on_stop` already read before appending anything; the
records it appends itself (the stop, an error) are never overall verdicts, so
reusing the list is exact and costs no second read. A rejected statement leaves
`promoted` false, so it falls through to this call.

The `witness_seq` of a NO_STATEMENT verdict is a stop that promoted nothing, and
a statement's `witness_seq` is a stop that promoted something, so the two can
never collide, and the verifier's idempotency lookup never mistakes one for the
other.

---

## 3. The spool file

### 3.1 Layout

```
PAPER TRAIL - evidence report
Session: demo-session-b
Statement: Cleared the build cache.
Paper intact
--------------------------------------------------------------------------------
   9  Witness took a snapshot of the project.
  10  Agent ran the command: python sample/cleanup.py.
  11  Witness compared the project to the earlier snapshot. Deleted:
      sample/cache/output.bin, sample/notes.txt.
  12  Agent stated: Cleared the build cache.
  13  SUPPORTED: Agent said it deleted sample/cache/output.bin. Witness agrees
      (line 11).
   !  Witness saw sample/notes.txt deleted. The agent never mentioned it.
  14  Overall: the statement does not match the evidence. (CONTRADICTED)
--------------------------------------------------------------------------------
Fingerprint of the record:
<64 hex characters> (19 lines)
```

- 80 columns: `textwrap.wrap(width=80 - gutter, break_long_words=True,
  break_on_hyphens=False)` for the lines; the same at full width for the header.
  The gutter is `max(3, digits of the largest number) + 2` characters.
- The fingerprint is one logical line, `Fingerprint of the record: <hash> (<n>
  lines)`, wrapped at 80 columns without breaking words. The hash is 64
  characters, so it always lands whole on the last physical line with the count.
  A single record reads "(1 line)".
- Only the session's records are numbered; the fingerprint and the count are of
  the whole record, because that is what the chain protects.

### 3.2 `papertrail/spool.py`

```python
def entry_text(entry: dict) -> str            # twin of entryText.ts
def verdict_word(verdict) -> str              # "NO_STATEMENT" -> "NO STATEMENT"
def fingerprint_line(entries) -> str
def render(entries, session_id, chain) -> str
def render_session(root, session_id) -> str   # raises LookupError for no records
def spool_path(root, session_id) -> Path
def write(root, session_id) -> Path
```

`render_session` reads the ledger, runs `ledger.verify_chain` for the status line
and calls `render`. `write` makes `.papertrail/spool/`, writes UTF-8 without a
byte-order mark and with `\n` endings (`newline="\n"` on a text handle opened with
`encoding="utf-8"`), and returns the path. The CLI prints the path relative to
the project root. The MCP tool calls `render_session` and writes nothing.

### 3.3 One set of sentences

`entry_text` and `entryText.ts` are twins. `tests/fixtures/sentences.json`:

```json
{ "sentences":    [ {"name": "...", "entry": {"kind": "...", "data": {...}}, "text": "..."} ],
  "fingerprints": [ {"name": "...", "entries": [{"hash": "..."}], "text": "..."} ] }
```

Both test suites read it and assert every case. Cases cover each kind, each
verdict (including a file read, which is checked against the record), all four
overall sentences, the undeclared line, errors, unknown kinds, a command cut at
80 characters, and the fingerprint line for zero, one and several records.
(Cutting at 80 counts characters in Python and UTF-16 units in JavaScript; the
fixture keeps to ASCII, where they are the same.)

---

## 4. Showing it

`outcome.result_for` feeds `__main__._cmd_verify` (which formats exactly as
before), `api.post_verify` / `post_verify_latest`, and
`mcp_server.handle_verify_statement`.

API routes after this spec: `GET /api/ledger`, `GET /api/chain`,
`POST /api/verify/{session_id}/{n}`, `POST /api/verify/{session_id}`.

MCP tools: `list_sessions`, `get_entries`, `check_chain`, `verify_statement
(session_id, n=None)`, `print_session(session_id)`.

### Web

- `lib/entryText.ts`: `overallSentence("NO_STATEMENT")`; `verdictWord`;
  `fingerprintText(entries)`.
- `Stamp`: shows `verdictWord`, and the class `stamp--no-statement`
  (`#3d3a8f`, an indigo; about 7.9:1 on a bar).
- `sessionMeta`: title "No statement written" when a session has a NO_STATEMENT
  verdict and no statement.
- `ghostFor`: finished with NO_STATEMENT: alarmed, "The agent changed files and
  said nothing. Click a red circle to see what the witness saw."
- `PrintReport`: gets `fingerprint` text; the undeclared heading is "Changes the
  witness saw:" for NO_STATEMENT; the fingerprint is the last paragraph.
- `Footer`: returns `null` unless `repoUrl` starts with `http://` or `https://`.
  `App` takes an optional `repoUrl` prop, defaulting to `__REPO_URL__`, so tests
  can set it.

### The ring

The old path was an ellipse. An ellipse cuts the corners of the text's rectangle,
and on desktop the first row of a two-line sentence is as wide as the box, so its
last word crossed the curve. The new path is a loop drawn as a rounded rectangle,
with corner radii of roughly 13% of the width and 14 units of the 40-unit height,
a slightly tilted top edge, and an end that overshoots the start:

```
M 5 15  C 4 8, 8 4, 18 3  C 40 1, 66 2, 85 3  C 94 4, 98 9, 98 17
        C 99 25, 97 33, 88 36  C 70 39, 40 38, 16 37  C 7 36, 2 30, 3 22
        C 3 17, 4 12, 8 8  C 12 5, 18 4, 26 3.5
```

`ring.test.ts` checks the shape against the stylesheet:

1. Read the base `.undeclared-circle` padding and the ring's `top`, `left`,
   `width: calc(100% + X em)` and `height` from `stamps.css`, and the same from
   the phone block (the last `@media (max-width: 640px)`).
2. Render `UndeclaredCircle`, take the path's `d`, and flatten each cubic into 40
   points. Even-odd test for containment.
3. For text `W` em wide and `L` lines tall (`L x 1.35` em), place the text
   rectangle inside the button (inset by the padding), the button inside the ring
   (inset by the offsets), and map it into the path's 100 x 40 space. Inflate it
   by 0.3 em (the stroke and the filter's wobble).
4. All four corners and the four edge midpoints must be inside.

Because only ratios matter, units cancel and nothing needs a browser. The
negative test shrinks the offsets to the old values and the old ellipse path and
expects the check to find a point outside, so the test cannot pass vacuously.

---

## 5. The workflow

```yaml
name: Tests
on: { push: {}, pull_request: {} }
jobs:
  tests:
    strategy:
      fail-fast: false
      matrix: { os: [ubuntu-latest, windows-latest, macos-latest] }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5   # 3.11, pip cache
      - run: python -m pip install -r requirements.txt
      - run: python -m pytest tests/ -q
      - uses: actions/setup-node@v4     # 20, npm cache on web/package-lock.json
      - run: npm ci                     # working-directory: web
      - run: npx vitest run
      - run: npm run build
```

`tests/test_workflow.py` reads the file as text and checks the three systems,
`fail-fast: false`, the three test commands, Python 3.11, Node 20, `npm ci`, and
that it runs on push and pull request. It does not parse YAML, so no dependency
is added.

Things that would differ between systems and are already handled: path case
(the verifier lowercases only on Windows, and the test accepts both outcomes),
line endings (every reader splits on `\r?\n` or uses text mode), and temporary
folders (the sanitiser works on the path the ledger was given).

---

## 6. Encoding guard

`tests/test_encoding.py` walks the repository for `.py .md .json .jsonl .txt .ts
.tsx .css .html .yml .yaml` files, skipping `node_modules`, `dist`, `.git`,
`.hypothesis`, `.pytest_cache`, `__pycache__` and `.papertrail`, and asserts that
none starts with the three bytes `EF BB BF`.

---

## 7. Tests

New: `test_outcome.py`, `test_spool.py`, `test_sample.py`, `test_workflow.py`,
`test_encoding.py`, `sentences.test.ts`, `ring.test.ts`, `Footer.test.tsx`, and
new cases in `test_session.py`, `test_cli.py`, `test_api.py`,
`test_mcp_server.py`, `test_make_demo_ledger.py`, `App.test.tsx`,
`GhostClerk.test.tsx`, `Stamp.test.tsx`, `sessionMeta.test.ts` and
`styles.test.ts`.
