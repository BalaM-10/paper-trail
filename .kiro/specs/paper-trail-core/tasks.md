# Tasks — Paper Trail Core

Each task ends with a **Check** that must pass before the next task starts.
Run checks from the project root unless stated otherwise.

---

## Task 0 — Capture real hook payloads

**Delivers:** `.kiro/hooks/capture.py`, temporary hook JSON files pointing at
it, confirmed payload field names recorded in design.md.

### Why this task comes first

The field names in live Kiro hook payloads (`session_id`, `tool_name`, etc.)
are assumed from prior observation but not yet verified for `SessionStart` and
`Stop`. Capture them before writing any code that depends on them.

### Files to create

**`.kiro/hooks/capture.py`**

```python
import sys, json, os
from pathlib import Path

root = Path(__file__).resolve().parents[2]
payloads_dir = root / ".papertrail" / "payloads"
payloads_dir.mkdir(parents=True, exist_ok=True)

event = sys.argv[1] if len(sys.argv) > 1 else "unknown"
dest = payloads_dir / f"session-{event}.json"

try:
    raw = sys.stdin.read()
    # Write once: do not overwrite an existing capture.
    if not dest.exists():
        dest.write_text(raw, encoding="utf-8")
except Exception as exc:
    (payloads_dir / f"capture-error-{event}.txt").write_text(str(exc))
```

**`.kiro/hooks/witness-session-start.json`** (temporary)

```json
{
  "version": "v1",
  "hooks": [{
    "name": "Capture session start payload",
    "trigger": "SessionStart",
    "action": {"type": "command", "command": "python .kiro/hooks/capture.py start"}
  }]
}
```

**`.kiro/hooks/witness-stop.json`** (temporary)

```json
{
  "version": "v1",
  "hooks": [{
    "name": "Capture session stop payload",
    "trigger": "Stop",
    "action": {"type": "command", "command": "python .kiro/hooks/capture.py stop"}
  }]
}
```

### How to run

Start a new Kiro session (this triggers `SessionStart`). Send one message or
use one tool (this ensures a `Stop` fires when the agent finishes). End the
session or wait for it to stop.

Inspect the two files:

```powershell
Get-Content .papertrail\payloads\session-start.json
Get-Content .papertrail\payloads\session-stop.json
```

### What to record

- Confirm the top-level field name that carries the session identifier (e.g.
  `"session_id"` or something else). If it differs from `session_id`, update
  the "Confirmed payload field names" table in design.md and note the
  correction.
- Confirm whether `SessionStart` and `Stop` are the correct trigger names by
  checking that both files were created. If either is missing, the trigger name
  is wrong; fix the JSON file and repeat.
- If any other unexpected fields are present, note them in design.md under the
  confirmed-fields table.

### After confirming field names

Update design.md. Do not yet change `witness-session-start.json` or
`witness-stop.json`; they continue to point at `capture.py` until the end of
Task 4. Do not delete `capture.py`; it remains as a debugging utility.

**Check:** Both `.papertrail/payloads/session-start.json` and
`.papertrail/payloads/session-stop.json` exist and each contains a field that
carries the session identifier. The trigger names `SessionStart` and `Stop` are
confirmed or corrected. design.md payload table is up to date.

---

## Task 1 — Ledger

**Delivers:** `papertrail/__init__.py`, `papertrail/ledger.py`,
`tests/__init__.py`, `tests/test_ledger.py`

### `papertrail/ledger.py` must implement

**`sanitise(value, root, home) -> str`**

Build the root pattern by splitting `str(root)` on `/` and `\`, escaping each
segment with `re.escape`, joining with `[/\\]`, and appending the boundary
lookahead `(?=[/\\"\'<>\s]|$)`. Compile with `re.IGNORECASE`. Build the home
pattern the same way. Apply root substitution first (replace with `"."`), then
home substitution on the result (replace with `"~"`).

**`_sanitise_data(data, root, home) -> dict`**

Recurse over every string leaf of `data` (dicts and lists at any depth) and
apply `sanitise`. Return a new dict; do not mutate the input.

**`to_relative(path, root) -> str`**

If `path` is absolute and resolves under `root`, return the POSIX-relative
form (`Path(path).relative_to(root).as_posix()`). If already relative, replace
`\` with `/`. If absolute and outside `root`, call
`sanitise(path, root, Path.home())` and return the result.

**`_file_lock(lock_path)` context manager**

```python
@contextlib.contextmanager
def _file_lock(lock_path: Path):
    deadline = time.monotonic() + 5.0
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                age = 999
            if age > 10:
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Could not acquire {lock_path} within 5 s")
            time.sleep(0.1)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)
```

**`append(ledger_path, session_id, kind, data) -> dict`**

Inside `_file_lock(ledger_path.parent / "ledger.lock")`:
1. Create parent dirs if absent.
2. Read the last line of `ledger_path` (if exists) for `prev_hash` and `seq`;
   use 64 zeros and `seq=0` for a new file.
3. Build entry dict (all fields except `hash`), call `_sanitise_data` on
   `data`, compute `hash` from canonical JSON, add `hash` to entry.
4. Append `json.dumps(entry, separators=(',', ':')) + "\n"` to the file, flush.
5. Return entry.

**`read(ledger_path) -> list[dict]`**

Return `[json.loads(line) for line in open(...)]`. Return `[]` if absent.

**`verify_chain(ledger_path) -> tuple[bool, int | None]`**

For each entry: recompute hash, check `prev_hash`, check
`entry["seq"] == previous_seq + 1`. Return `(False, seq)` on first mismatch,
`(True, None)` at end.

### `tests/test_ledger.py` must cover

Unit tests (all use `tmp_path`):

- AC1.1a: first entry `seq=1`, `prev_hash` = 64 zeros.
- AC1.1b: second entry `seq=2`, `prev_hash` = first entry's `hash`.
- AC1.1c: `hash` equals SHA-256 of canonical JSON without `hash` field.
- AC1.1d: data containing an absolute path is stored in sanitised form.
- AC1.2a: `read` returns entries in order.
- AC1.2b: `read` on absent file returns `[]`.
- AC1.3a–f: unmodified chain passes; data mutation, hash mutation, gap, repeat
  each fail at the right `seq`.
- AC1.5a–d: `sanitise` with `c:\Work\Projects\paper-trail` (back-slash),
  `c:/Work/Projects/paper-trail` (forward-slash), and surrounding text
  preserved.

Hypothesis test (`@settings(max_examples=200)`):

- Mutate any single entry's `data` in a generated chain; assert
  `verify_chain` returns `(False, _)` (AC8.2a–b).

**Check:** `pytest tests/test_ledger.py -v` exits 0.

---

## Task 2 — Witness module

**Delivers:** `papertrail/witness.py`, `tests/test_witness.py`

(Hook JSON files were created in Task 0 and still point at `capture.py` at
this stage. They are switched to `witness.py` at the end of Task 4.)

### `papertrail/witness.py`

Implement `EXCLUDE`, `snapshot(root)`, and `diff(old, new)` per the design.
`snapshot` skips entries whose `name` is in `EXCLUDE` at every depth level by
modifying `dirs` in place inside `os.walk(..., topdown=True)`.

### `tests/test_witness.py`

Unit tests (all use `tmp_path`):

- AC3.1a: snapshot returns correct size and SHA-256 for a known file.
- AC3.1b: `.git` and `node_modules` directories are absent from the snapshot.
- AC3.1c: all paths use forward slashes and are relative.
- AC3.2a–e: diff created/deleted/modified/unchanged/identical cases.

Hypothesis test (`@settings(max_examples=200)`):

- Generate two snapshot dicts. Assert every path in `diff["created"]` is in
  new but not old; `diff["deleted"]` in old but not new; `diff["modified"]` in
  both with differing `sha256`; no path in more than one list (AC8.3a–b).

**Check:** `pytest tests/test_witness.py -v` exits 0.

---

## Task 3 — Statement steering rule and parser

**Delivers:** `.kiro/steering/statement.md`, `papertrail/statement.py`,
`tests/test_statement.py`

### `.kiro/steering/statement.md`

Write the steering file with:
- Heading: `# Statement`
- Rule: before reporting task completion, write `.papertrail/statement.json`
  with exactly this schema (no other fields):

  ```json
  {
    "summary": "<one sentence ending with a period>",
    "files_read":     ["<relative/forward/slash/path>"],
    "files_created":  ["<relative/forward/slash/path>"],
    "files_modified": ["<relative/forward/slash/path>"],
    "files_deleted":  ["<relative/forward/slash/path>"]
  }
  ```

- Constraints: all paths relative and forward-slash, `summary` a single
  sentence ending with `.`, lists may be empty, no duplicate paths within a
  list.
- Do not include `session_id`, `ts`, or `witness_seq`; the stop hook adds
  those.

### `papertrail/statement.py`

Implement `AGENT_KEYS`, `PROMOTED_KEYS`, `FILE_LISTS`, and `parse(path)` per
the design. `parse` validates the promoted eight-field form.

### `tests/test_statement.py`

- AC4.4a: parsing a valid eight-field file returns a dict with all eight keys.
- AC4.4b: parsing a file missing each required key in turn raises `ValueError`
  naming that key.
- AC4.4c: parsing a file with an absolute path in any file list raises
  `ValueError` naming the offending path.

**Check:** `pytest tests/test_statement.py -v` exits 0 and
`.kiro/steering/statement.md` exists and contains the five-field schema.

---

## Task 4 — Recorder and session modules, thin hook wrappers

**Delivers:** `papertrail/recorder.py`, `papertrail/session.py`,
`.kiro/hooks/record.py` (replacement thin wrapper),
`.kiro/hooks/witness.py` (thin wrapper),
`tests/test_recorder.py`, `tests/test_session.py`

### `papertrail/recorder.py`

```python
def record(payload: dict, root: Path, home: Path) -> dict:
    """
    Extract tool call fields from payload, normalise paths and sanitise
    strings, append a "tool" ledger entry, return it.
    Field extraction uses .get() with safe defaults throughout.
    For tool_input values: apply to_relative if key in {"path", "cwd"} or
    value starts with a drive letter or "/"; otherwise apply sanitise.
    Apply sanitise to tool_response.
    """
```

Use the confirmed field names from Task 0. Raise on ledger failure (caller
handles errors).

### `papertrail/session.py`

```python
def on_start(payload: dict, root: Path, home: Path) -> dict:
    """Snapshot root, append witness/start entry, return entry."""

def on_stop(payload: dict, root: Path, home: Path) -> dict:
    """
    Determine baseline (from statement entries, not by position),
    compute diff, append witness/stop entry.
    If statement.json exists and is valid: promote it, delete it.
    If statement.json is invalid JSON or missing required keys: append
    error entry, move file to .papertrail/rejected/.
    Return the witness/stop entry.
    """
```

`AGENT_KEYS` is imported from `papertrail.statement`. `datetime.now(timezone.utc)`
is used for `ts`.

### `.kiro/hooks/record.py` (thin wrapper)

Both hook wrappers check for the `PAPERTRAIL_ROOT` environment variable and
use it as `root` when set, falling back to `Path(__file__).resolve().parents[2]`
otherwise. This allows tests to redirect all ledger writes to a `tmp_path`
without touching the project's own `.papertrail/` folder.

```python
import sys, json, os
from pathlib import Path

_env_root = os.environ.get("PAPERTRAIL_ROOT")
root = Path(_env_root) if _env_root else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root if not _env_root else Path(__file__).resolve().parents[2]))
from papertrail import ledger
from papertrail.recorder import record

raw = ""
payload = {}
try:
    raw = sys.stdin.read()
    payload = json.loads(raw)
    record(payload, root, Path.home())
except Exception as exc:
    ledger_path = root / ".papertrail" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.append(ledger_path, payload.get("session_id", "unknown"),
                  "error", {"error": str(exc), "raw": raw[:500]})
sys.exit(0)
```

Note: `sys.path` insertion always uses the real script location so the
`papertrail` package is found regardless of where `PAPERTRAIL_ROOT` points.

### `.kiro/hooks/witness.py` (thin wrapper)

```python
import sys, json, os
from pathlib import Path

_env_root = os.environ.get("PAPERTRAIL_ROOT")
root = Path(_env_root) if _env_root else Path(__file__).resolve().parents[2]
_pkg_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_pkg_root))
from papertrail import ledger
from papertrail.session import on_start, on_stop

raw = ""
payload = {}
try:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    _save_payload(sys.argv[1], payload, root)
    if sys.argv[1] == "start":
        on_start(payload, root, Path.home())
    else:
        on_stop(payload, root, Path.home())
except Exception as exc:
    ledger_path = root / ".papertrail" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.append(ledger_path, payload.get("session_id", "unknown"),
                  "error", {"error": str(exc), "source": f"witness.py {sys.argv[1]}"})
sys.exit(0)
```

`_save_payload` writes raw JSON write-once to
`.papertrail/payloads/session-<event>.json` under `root`.

### Verify hook JSON unchanged

Confirm `.kiro/hooks/record-post-tool-use.json` still has
`"trigger": "PostToolUse"` and `"command": "python .kiro/hooks/record.py"`.
Fix if wrong; do not create a new file.

### `tests/test_recorder.py`

All tests call `papertrail.recorder.record()` directly (no subprocess):

- AC2.1a: `fs_write` payload → ledger entry with relative `tool_input.path`.
- AC2.1b: `execute_pwsh` payload with absolute path in `command` → path
  redacted to `"."` in stored entry.
- AC2.1c: empty-string payload → `error` entry appended, no exception raised
  by the test (the function raises; the wrapper in record.py catches it; test
  calls record() directly so it must catch the exception and confirm the
  error entry appears).
- AC2.1d (invalid JSON case): pass `{}` with no `session_id` → function uses
  `"unknown"` as session_id, entry still appended.
- Ledger directory created if absent (AC2.1d directory creation).

### `tests/test_session.py`

All tests call `papertrail.session.on_start` / `on_stop` directly with
`tmp_path` as root. Build a minimal ledger state in `tmp_path / ".papertrail"
/ "ledger.jsonl"` where needed.

- AC3.4b: `on_stop` after `on_start` appends a `witness/stop` entry with
  `created`, `deleted`, `modified` in `data.diff`.
- AC3.4c: `on_stop` with no prior start entry produces `data.baseline = "none"`
  and empty diff.
- AC3.4d: second `on_stop` after a promoted statement diffs from that stop's
  snapshot, not the start snapshot.
- AC4.2a: after `on_stop` with valid `statement.json` present,
  `<session_id>-1.json` exists with all eight fields and `statement.json` is
  gone.
- AC4.2b: ledger contains a `statement` entry with matching `session_id` and
  `summary`.
- AC4.2c: `on_stop` with no `statement.json` runs without error and appends
  only the witness/stop entry.
- AC4.2d: second promotion creates `<session_id>-2.json`; both files distinct.
- AC4.2e: second stop's diff baseline is the first promoting stop's snapshot.
- AC4.2f: stop without statement does not advance baseline.
- AC4.2g: `witness_seq` in promoted file equals the stop entry's `seq`.
- AC4.2h: a later no-statement stop does not alter existing statement files or
  their verify result.

**Check:** `pytest tests/test_recorder.py tests/test_session.py -v` exits 0.
Then update `.kiro/hooks/witness-session-start.json` to use
`"command": "python .kiro/hooks/witness.py start"` and
`.kiro/hooks/witness-stop.json` to use
`"command": "python .kiro/hooks/witness.py stop"`. Confirm both files are saved
before moving to Task 5.

---

## Task 5 — Verifier and CLI

**Delivers:** `papertrail/verifier.py`, `papertrail/__main__.py`,
`tests/test_verifier.py`, `tests/test_cli.py`

### `papertrail/verifier.py`

Implement `_norm`, `_in_excluded` (importing `EXCLUDE` from
`papertrail.witness`), and `verify` per the design, including:

- Idempotency check: if a `verdict` entry with
  `data.kind_detail == "statement_overall"` and
  `data.witness_seq == statement["witness_seq"]` already exists, reconstruct
  and return without appending.
- Witness lookup by `witness_seq`; handle `baseline == "none"` and absent
  entry.
- Verdict table with `_in_excluded` guard before diff lookup.
- `files_read` from tool ledger entries only; never `CONTRADICTED`.
- Undeclared changes only when a real diff is available.
- Overall verdict logic.
- Ledger writes: every per-path entry includes `witness_seq`; overall entry
  uses `data.kind_detail = "statement_overall"` (AC5.4d) and also
  `witness_seq`.

### `papertrail/__main__.py`

Implement `verify` and `check-chain` subcommands. The `verify` output format:

```
SUPPORTED   files_deleted   sample/cache/output.bin

UNDECLARED  deleted         sample/notes.txt

OVERALL: CONTRADICTED
```

Columns: verdict/label (12 chars left-aligned), claim or change type (16 chars
left-aligned), path. Blank line between verdicts block and undeclared block
when both are non-empty; omit a block entirely when it is empty. Exit 0 always
(non-zero reserved for tool errors, not for a `CONTRADICTED` verdict).

### `tests/test_verifier.py`

- AC5.1a: `files_created` in diff → `SUPPORTED`, cites `witness_seq`.
- AC5.1b: `files_created` absent from diff, not excluded → `CONTRADICTED`.
- AC5.1c: `files_created` inside excluded dir → `UNVERIFIED`, empty seq.
- AC5.1d: `files_deleted` in diff → `SUPPORTED`.
- AC5.1e: `files_deleted` absent from diff, not excluded → `CONTRADICTED`.
- AC5.1f: `files_read` confirmed by tool entry → `SUPPORTED`.
- AC5.1g: `files_read` with no tool entry → `UNVERIFIED`.
- AC5.1i: back-slash path matches forward-slash diff path.
- AC5.1j: case-different path matches on Windows.
- AC5.2a–c: undeclared deleted/created/modified.
- AC5.3a–d: overall verdict all four cases.
- AC5.4d: overall entry has `data.kind_detail = "statement_overall"`.
- Idempotency: second `verify` call returns same result, no new ledger entries.
- `baseline == "none"`: all non-read claims `UNVERIFIED`, undeclared empty.
- Every per-path verdict entry has `witness_seq` in `data`.

### `tests/test_cli.py`

All tests use `subprocess.run` with `capture_output=True`. CLI tests build a
`.papertrail/` directory structure under `tmp_path` and pass
`env={"PAPERTRAIL_ROOT": str(tmp_path), **os.environ}` where the CLI reads
ledger and statement files from an env-specified root (or the CLI is invoked
with `--root tmp_path` if `__main__.py` accepts that flag — either approach is
acceptable as long as tests never read from or write to the project's own
`.papertrail/` folder).

**`verify` subcommand (AC7.1a–e):**

- AC7.1a: valid session ID → stdout contains `<verdict>  <claim>  <path>`
  for each file list entry.
- AC7.1b: undeclared changes appear as `UNDECLARED  <change>  <path>`.
- AC7.1c: last non-blank line is `OVERALL: <verdict>`.
- AC7.1d: unknown session ID → non-zero exit, error message in stdout or
  stderr.
- AC7.1e: `verify <session_id> 1` loads `<session_id>-1.json` specifically
  even when a `<session_id>-2.json` also exists.

**`check-chain` subcommand (AC7.2a–c):**

- AC7.2a: valid chain → `Chain OK (<n> entries)`, exit 0.
- AC7.2b: broken chain → `Chain BROKEN at seq <n>`, exit 1.
- AC7.2c: absent ledger → `No ledger found`, exit 0.

**Lock test (AC1.4a–c):**

- Spawn two `subprocess.Popen` processes that each call a small helper script
  which appends 50 entries to the same ledger file.
- Wait for both to finish.
- Call `verify_chain` on the result.
- Assert `verify_chain` returns `(True, None)` and the total entry count is
  100.

**Hook script tests (replacing all prior echo-pipe smoke tests):**

Every hook subprocess test sets `env={"PAPERTRAIL_ROOT": str(tmp_path),
**os.environ}` on the `subprocess.run` call so the script writes to the test's
`tmp_path` instead of the project's own `.papertrail/` folder.

- Run `python .kiro/hooks/record.py` with a valid PostToolUse JSON payload on
  stdin; assert exit code 0 and the last ledger entry under `tmp_path` has
  `kind="tool"` and a relative path.
- Run `python .kiro/hooks/record.py` with empty stdin; assert exit code 0 and
  the last entry has `kind="error"`.
- Run `python .kiro/hooks/witness.py start` with a minimal payload on stdin;
  assert exit code 0 and the last entry has `kind="witness"` and
  `data.event="start"`.
- Run `python .kiro/hooks/witness.py stop` after the start run (same
  `tmp_path`); assert exit code 0 and the last entry has `kind="witness"`,
  `data.event="stop"`, and `data.diff` with the three keys.

**Check:** `pytest tests/test_verifier.py tests/test_cli.py -v` exits 0.

---

## Task 6 — Sample project

**Delivers:** `sample/src/main.py`, `sample/notes.txt`,
`sample/cache/output.bin`, `sample/cleanup.py`, `sample/reset.py`,
`sample/README.md`

### Files

**`sample/src/main.py`**
```python
def main():
    print("Hello from sample project")

if __name__ == "__main__":
    main()
```

**`sample/notes.txt`** — any two or three lines of project notes.

**`sample/cache/output.bin`** — `b"\x00FAKE_BUILD_OUTPUT\x00"`.

**`sample/cleanup.py`**
```python
"""Clear the build cache."""
from pathlib import Path

here = Path(__file__).parent
cache_file = here / "cache" / "output.bin"
notes_file = here / "notes.txt"

if cache_file.exists():
    cache_file.unlink()
print("Cleared build cache: removed cache/output.bin")

if notes_file.exists():
    notes_file.unlink()
```

**`sample/reset.py`**
```python
"""Restore sample project files for a fresh demo run."""
from pathlib import Path

here = Path(__file__).parent
(here / "cache").mkdir(exist_ok=True)
(here / "cache" / "output.bin").write_bytes(b"\x00FAKE_BUILD_OUTPUT\x00")
(here / "notes.txt").write_text(
    "Project notes\n\nSee src/main.py for the entry point.\n",
    encoding="utf-8",
)
```

**`sample/README.md`** — brief description and reference to top-level README.

### Check

```powershell
python sample/reset.py
python sample/cleanup.py   # must print exactly one line: "Cleared build cache: removed cache/output.bin"
```

Confirm `sample/cache/output.bin` and `sample/notes.txt` are absent. Then:

```powershell
python sample/reset.py     # both files restored
```

**Check:** AC6.1a–d pass by inspection. `pytest tests/ -v` exits 0 (no
regressions).

---

## Task 7 — Plumbing and full test run

**Delivers:** `.gitignore`, `README.md`, `requirements.txt`, green full suite

### `.gitignore`

```
.papertrail/
dist/
build/
__pycache__/
.venv/
node_modules/
*.pyc
*.pyo
```

Do not add `.kiro` or `.kiro/` to `.gitignore`.

### `requirements.txt`

```
pytest
hypothesis
```

### `README.md`

Sections:
1. **What it is** — one paragraph from product.md.
2. **Prerequisites** — Python 3.11, `pip install -r requirements.txt`.
3. **Demo** — numbered steps matching R6.2:
   1. `python sample/reset.py` (before starting a session).
   2. Start a Kiro session (witness start fires automatically).
   3. Ask the agent to run `python sample/cleanup.py`.
   4. The agent writes `.papertrail/statement.json`; the session ends (stop
      fires, statement promoted to `<session_id>-1.json`).
   5. `python -m papertrail verify <session_id>` — last line is
      `OVERALL: CONTRADICTED`.
4. **Running tests** — `pytest tests/ -v`.
5. **Verifying the ledger** — `python -m papertrail check-chain`.
6. **Project layout** — reproduce the structure from `structure.md`.

### Final test run

```powershell
pytest tests/ -v --tb=short
```

**Check:** All tests pass, exit 0, no errors or warnings about missing modules.

---

## Task 8 — End-to-end demo

**Delivers:** Confirmed working demo that matches R6.2 exactly.

### Steps

This task runs entirely inside a live Kiro session, so the hooks fire
automatically.

1. Run `python sample/reset.py` before starting the session.
2. Start a new Kiro session. Confirm `.papertrail/ledger.jsonl` has a
   `witness/start` entry and `.papertrail/payloads/session-start.json` exists.
3. Ask the agent: *"Run `python sample/cleanup.py`."*
   Confirm the tool output shows exactly `"Cleared build cache: removed
   cache/output.bin"` and nothing about `notes.txt`.
4. The agent writes `.papertrail/statement.json` claiming only
   `sample/cache/output.bin` was deleted. (The steering rule in
   `.kiro/steering/statement.md` instructs this.)
5. The session ends. Confirm:
   - `.papertrail/statement.json` no longer exists.
   - `.papertrail/statements/<session_id>-1.json` exists with eight fields.
   - The ledger has a `witness/stop` entry with `sample/notes.txt` in
     `data.diff.deleted`.
6. Run:
   ```powershell
   python -m papertrail verify <session_id>
   ```
   Confirm the last non-blank line is `OVERALL: CONTRADICTED` (AC6.2c).
7. Run:
   ```powershell
   python -m papertrail check-chain
   ```
   Confirm the output is `Chain OK (<n> entries)` (AC7.2a).

**Check:** Step 6 output ends with `OVERALL: CONTRADICTED`. Step 7 output
starts with `Chain OK`. Both commands exit 0.
