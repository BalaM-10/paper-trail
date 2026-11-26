# Design — Paper Trail Core

## Overview

The core is seven pieces that compose in one direction: hooks write to the
ledger; the verifier reads from it. Nothing writes back up the chain.

```
  SessionStart hook
  └── witness.py start  →  ledger: witness/start  (snapshot)

  PostToolUse hook
  └── record.py         →  ledger: tool

  Agent (at task end)
  └── writes  .papertrail/statement.json

  Stop hook
  └── witness.py stop   →  ledger: witness/stop   (snapshot + diff)
                        →  ledger: statement       (if statement.json valid)
                        →  .papertrail/statements/<session_id>-<n>.json
                        →  deletes .papertrail/statement.json
                        →  or moves to .papertrail/rejected/ if invalid

  python -m papertrail verify <session_id> [<n>]
  └── verifier.py       →  reads statement file (witness_seq → witness/stop)
                        →  reads tool entries
                        →  ledger: verdict × N  +  verdict/overall
                        →  (no-op if overall verdict already exists for
                            that witness_seq)
```

The promoted statement carries `witness_seq` — the `seq` of the `witness/stop`
entry written in the same hook run. The verifier uses that exact entry; it
never searches for the latest or highest-seq stop.

### Confirmed Kiro hook trigger names and payload fields

Trigger names are verified from Kiro hook documentation (`createHook` tool
schema):

| Event | Trigger name |
|---|---|
| Session opens | `SessionStart` |
| Agent turn ends | `Stop` |
| After every tool call | `PostToolUse` |
| After file deletion by Kiro tool | `PostFileDelete` |

Payload field names are confirmed in Task 0 by capturing live payloads to
`.papertrail/payloads/`. Until Task 0 runs, treat the following as the
expected field names based on the hook documentation and the observed
`evidence.log` entries from earlier in this session:

| Field | Expected name |
|---|---|
| Session identifier | `session_id` |
| Tool name | `tool_name` |
| Tool input object | `tool_input` |
| Tool response | `tool_response` |
| Hook event name | `hook_event_name` |

If Task 0 reveals different field names, update `papertrail/recorder.py` and
`papertrail/session.py` accordingly and record the corrections here.

---

## Module: `papertrail/ledger.py`

### Entry schema

```
{
  "seq":        int,    # 1-based, no gaps, no repeats
  "ts":         str,    # UTC ISO 8601, e.g. "2026-11-25T12:00:00.000000Z"
  "session_id": str,
  "kind":       str,    # "tool" | "witness" | "statement" | "verdict" | "error"
  "data":       dict,
  "prev_hash":  str,    # 64 hex chars; 64 zeros for seq=1
  "hash":       str     # SHA-256 of canonical JSON without "hash" field
}
```

### Hash

```python
canonical = json.dumps(entry_without_hash, sort_keys=True,
                       separators=(',', ':'), ensure_ascii=False).encode('utf-8')
hash = hashlib.sha256(canonical).hexdigest()
```

### Public interface

```python
def append(ledger_path: Path, session_id: str, kind: str, data: dict) -> dict:
    """
    Acquire exclusive lock, read last line for seq/hash, build and write new
    entry, flush, release lock. Return the written entry.
    Calls _sanitise_data() on every string leaf of data before hashing.
    """

def read(ledger_path: Path) -> list[dict]:
    """Return entries in append order. Empty list if file absent."""

def verify_chain(ledger_path: Path) -> tuple[bool, int | None]:
    """
    Check every entry's hash and prev_hash linkage, and that seq is a
    gap-free sequence starting at 1 with no repeats.
    Return (True, None) on success; (False, seq) at the first broken entry.
    """

def sanitise(value: str, root: Path, home: Path) -> str:
    """
    Replace all occurrences of root with "." and home with "~".
    root is replaced before home.
    Matching is case-insensitive and slash-style-insensitive.
    A match is only recognised when followed by /, \, ", whitespace, > or
    end of string, so a path that is a prefix of a longer path is not
    incorrectly redacted.
    Text outside those substrings is preserved verbatim.
    """

def to_relative(path: str, root: Path) -> str:
    """
    Absolute path under root  →  relative forward-slash form.
    Already relative          →  normalise separators to forward slash.
    Absolute outside root     →  pass through sanitise() and return as-is.
    """
```

### Exclusive append lock (all platforms)

`append` uses a lock file at `.papertrail/ledger.lock`. The lock is acquired
by opening the file with `os.open(lock_path, os.O_CREAT | os.O_EXCL |
os.O_WRONLY)`, which atomically fails if the file already exists. If the open
fails (`FileExistsError`), the function checks the lock file's `mtime`. If it
is older than 10 seconds (stale lock from a crashed process), the lock file is
removed and the open retried immediately. Otherwise the function sleeps 100 ms
and retries. Total retry window is 5 seconds; after that `RuntimeError` is
raised. The lock file is always removed in a `finally` block after the write
is flushed. This mechanism uses only `os` from the standard library and works
on Windows and POSIX without `msvcrt` or `fcntl`.

### Privacy sanitisation

`sanitise` builds patterns by splitting the path on its separators, escaping
each segment, and joining with `[/\\]`:

```python
def _make_path_re(path: str) -> str:
    # Split on both / and \, escape each segment, rejoin with separator pattern
    parts = re.split(r'[/\\]', path)
    return r'[/\\]'.join(re.escape(p) for p in parts if p)

_BOUNDARY = r'(?=[/\\"\'<>\s]|$)'   # lookahead: sep, quote, whitespace, > or end

def _build_pattern(path: str) -> re.Pattern:
    return re.compile(_make_path_re(path) + _BOUNDARY, re.IGNORECASE)
```

`sanitise(value, root, home)` applies `root_re` first (replacing with `"."`),
then `home_re` on the result (replacing with `"~"`). Both patterns are
compiled once per call; callers that call `sanitise` in a loop should cache
the patterns.

`append` calls `_sanitise_data(data, root, home)` which walks every string
leaf of the `data` dict recursively and applies `sanitise`. The sanitised dict
is used for both the hash and the written JSON.

### verify_chain seq checks

After recomputing each entry's hash, `verify_chain` additionally asserts
`entry["seq"] == previous_seq + 1`. A gap (e.g. 1, 2, 4) is reported at the
missing number; a repeat (e.g. 1, 2, 2) is reported at the duplicate.

---

## Module: `.kiro/hooks/record.py`

Runs in the hook subprocess. Uses only the standard library plus
`papertrail.ledger` inserted into `sys.path`.

```
stdin
  → json.load()
  → extract: session_id, tool_name, tool_input, tool_response, hook_event_name
  → for each value in tool_input:
      if key in {"path", "cwd"} or value looks like a path:
          to_relative(value, root)
      else:
          sanitise(value, root, home)
  → sanitise tool_response string
  → ledger.append(kind="tool", data={...})
```

The script derives `root = Path(__file__).resolve().parents[2]` and inserts
`str(root)` into `sys.path[0]` before importing `papertrail.ledger`.
`home = Path.home()`.

On empty stdin, non-JSON stdin, or any exception: append `kind="error"` with
`data={"error": str(exc), "raw": raw_input[:500]}` and exit 0.

If `.papertrail/` does not exist, create it before the first `append`.

---

## Module: `.kiro/hooks/witness.py`

Uses only the standard library plus `papertrail.ledger` and
`papertrail.witness` inserted via `sys.path`.

Derives `root` and `home` the same way as `record.py`. Reads the hook payload
from stdin. Saves the raw payload write-once to
`.papertrail/payloads/session-start.json` (start) or `session-stop.json`
(stop) if the file does not already exist.

### start

```python
snap = witness.snapshot(root)
ledger.append(ledger_path, session_id, "witness",
              {"event": "start", "snapshot": snap})
```

### stop — full algorithm

```python
snap_new = witness.snapshot(root)
entries  = ledger.read(ledger_path)

# 1. Determine the diff baseline from statement entries, not by position.
#
#    Baseline = snapshot of the witness/stop entry whose seq equals the
#    highest data.witness_seq among this session's statement entries.
#    If no statement entries exist for this session, fall back to the
#    session's witness/start snapshot.
#    If neither exists, baseline is "none".

session_entries = [e for e in entries if e["session_id"] == session_id]

witness_seqs_from_stmts = [
    e["data"]["witness_seq"]
    for e in session_entries
    if e["kind"] == "statement" and "witness_seq" in e.get("data", {})
]

baseline_snap  = None
baseline_label = "none"

if witness_seqs_from_stmts:
    ref_seq = max(witness_seqs_from_stmts)
    for e in session_entries:
        if e["seq"] == ref_seq and e["kind"] == "witness":
            baseline_snap  = e["data"]["snapshot"]
            baseline_label = f"prev_stop_seq:{ref_seq}"
            break
else:
    for e in session_entries:
        if e["kind"] == "witness" and e["data"].get("event") == "start":
            baseline_snap  = e["data"]["snapshot"]
            baseline_label = "start"
            break

# 2. Compute diff.
#    If baseline_snap is None (baseline="none"), diff is empty.
if baseline_snap is not None:
    diff = witness.diff(baseline_snap, snap_new)
else:
    diff = {"created": [], "deleted": [], "modified": []}

# 3. Append witness/stop entry.
stop_entry = ledger.append(
    ledger_path, session_id, "witness",
    {"event": "stop", "snapshot": snap_new,
     "diff": diff, "baseline": baseline_label}
)
witness_seq = stop_entry["seq"]

# 4. Promote statement.json if present and valid.
stmt_path = root / ".papertrail" / "statement.json"
if stmt_path.exists():
    raw_text = stmt_path.read_text(encoding="utf-8")
    try:
        raw = json.loads(raw_text)
        missing = AGENT_KEYS - raw.keys()
        if missing:
            raise ValueError(f"missing keys: {missing}")
    except (json.JSONDecodeError, ValueError) as exc:
        # Invalid: record error, move to rejected/, do not promote.
        ledger.append(ledger_path, session_id, "error", {
            "error":  f"invalid statement.json: {exc}",
            "source": "witness.py stop",
        })
        rejected = root / ".papertrail" / "rejected"
        rejected.mkdir(exist_ok=True)
        stmt_path.rename(rejected / f"statement-{witness_seq}.json")
    else:
        # Valid: promote.
        from datetime import datetime, timezone
        promoted = {
            **raw,
            "session_id":  session_id,
            "ts":          datetime.now(timezone.utc).isoformat(),
            "witness_seq": witness_seq,
        }
        ledger.append(ledger_path, session_id, "statement", promoted)

        stmts_dir = root / ".papertrail" / "statements"
        stmts_dir.mkdir(exist_ok=True)
        n = sum(1 for _ in stmts_dir.glob(f"{session_id}-*.json")) + 1
        out = stmts_dir / f"{session_id}-{n}.json"
        out.write_text(json.dumps(promoted, indent=2), encoding="utf-8")
        stmt_path.unlink()
# If stmt_path does not exist: witness entry already written; nothing else to do.
```

`AGENT_KEYS = {"summary", "files_read", "files_created", "files_modified",
"files_deleted"}` is imported from `papertrail.statement`.

On any exception not already caught: append `kind="error"` and exit 0.

---

## Module: `papertrail/witness.py`

```python
EXCLUDE: frozenset[str] = frozenset({
    '.git', '.papertrail', 'node_modules', '__pycache__', '.venv',
    'dist', 'build',
})

def snapshot(root: Path) -> dict[str, dict[str, int | str]]:
    """
    Walk root. At every level, skip directory names in EXCLUDE.
    Return {forward_slash_relative_path: {"size": int, "sha256": str}}.
    SHA-256 computed in 64 KB chunks.
    """

def diff(
    old: dict[str, dict],
    new: dict[str, dict],
) -> dict[str, list[str]]:
    """
    Return {"created": [...], "deleted": [...], "modified": [...]}.
    "modified" means same path, different sha256.
    All lists are sorted for determinism.
    """
```

`snapshot` uses `os.walk` with `topdown=True` and modifies `dirs` in-place to
prune excluded names at every depth level. Files that cannot be read are
silently skipped.

---

## Module: `papertrail/recorder.py`

Contains the logic extracted from `.kiro/hooks/record.py` so it can be unit-
tested without subprocess overhead.

```python
def record(payload: dict, root: Path, home: Path) -> dict:
    """
    Given a parsed hook payload dict, extract tool call fields, normalise
    paths and sanitise strings, call ledger.append, and return the appended
    entry. Raises on ledger failure (caller is responsible for error handling).
    """
```

`.kiro/hooks/record.py` becomes:

```python
import sys, json
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from papertrail.recorder import record
from papertrail import ledger

raw = ""
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

---

## Module: `papertrail/session.py`

Contains the logic extracted from `.kiro/hooks/witness.py` so it can be unit-
tested without subprocess overhead.

```python
def on_start(payload: dict, root: Path, home: Path) -> dict:
    """
    Take a snapshot and append a witness/start entry.
    Return the appended ledger entry.
    """

def on_stop(payload: dict, root: Path, home: Path) -> dict:
    """
    Determine baseline, compute diff, append witness/stop entry, optionally
    promote statement.json. Return the appended witness/stop entry.
    Raises on unrecoverable error (caller appends error entry).
    """
```

`.kiro/hooks/witness.py` becomes:

```python
import sys, json
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from papertrail.session import on_start, on_stop
from papertrail import ledger

raw = ""
try:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    _save_payload(sys.argv[1], payload, root)   # write-once capture
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

`_save_payload` writes the raw JSON once to
`.papertrail/payloads/session-<event>.json` if the file does not already exist.

---

## Module: `papertrail/statement.py`

The promoted statement has eight fields:

```
summary        str
files_read     list[str]
files_created  list[str]
files_modified list[str]
files_deleted  list[str]
session_id     str
ts             str   (UTC ISO 8601)
witness_seq    int
```

```python
AGENT_KEYS    = frozenset({
    "summary", "files_read", "files_created", "files_modified", "files_deleted"
})
PROMOTED_KEYS = AGENT_KEYS | frozenset({"session_id", "ts", "witness_seq"})
FILE_LISTS    = frozenset({
    "files_read", "files_created", "files_modified", "files_deleted"
})

def parse(path: Path) -> dict:
    """
    Load JSON, validate all eight keys present, validate each file list:
      - no absolute paths
      - forward-slash normalised (replace \\ with /)
      - no duplicates within a list
    Raises ValueError with a descriptive message on any violation.
    """
```

Validation order: (1) all required keys present, (2) for each file list, no
absolute path, (3) no duplicates within each list. The function normalises
back-slashes to forward-slashes in every path before returning.

---

## Module: `papertrail/verifier.py`

### Path normalisation

```python
import sys

def _norm(p: str) -> str:
    """Unify separators; lowercase on Windows for case-insensitive match."""
    p = p.replace('\\', '/')
    if sys.platform == 'win32':
        p = p.lower()
    return p
```

Applied at match time only; stored and returned paths are unchanged.

### Exclusion check

```python
from papertrail.witness import EXCLUDE

def _in_excluded(path: str) -> bool:
    """True if any path segment is in EXCLUDE."""
    return any(seg in EXCLUDE for seg in _norm(path).split('/'))
```

Importing `EXCLUDE` from `papertrail.witness` keeps the excluded-directory
set as a single source of truth.

### Public interface

```python
def verify(
    statement: dict,          # promoted statement (8 fields)
    ledger_entries: list[dict],
    session_id: str,
) -> dict:
    """
    Returns {
      "verdicts": [
        {
          "path":         str,
          "claim":        str,   # "files_created" | "files_modified" | ...
          "verdict":      str,   # "SUPPORTED" | "CONTRADICTED" | "UNVERIFIED"
          "evidence_seq": list[int],
        },
        ...
      ],
      "undeclared": [
        {"path": str, "change": str},  # change = "created"|"modified"|"deleted"
        ...
      ],
      "overall": str,   # "SUPPORTED" | "CONTRADICTED" | "UNVERIFIED"
    }

    Idempotent: if a verdict entry with data.kind == "statement_overall" and
    data.witness_seq == statement["witness_seq"] already exists in
    ledger_entries, the function reads those stored verdicts, reconstructs the
    result dict, and returns it without appending anything.
    """
```

### Idempotency check

```python
witness_seq = statement["witness_seq"]

existing_overall = next(
    (e for e in ledger_entries
     if e["kind"] == "verdict"
     and e["data"].get("kind_detail") == "statement_overall"
     and e["data"].get("witness_seq") == witness_seq),
    None,
)
if existing_overall:
    # Reconstruct result from stored verdict entries and return.
    ...
    return result
```

If the overall verdict entry is found, `verify` collects all per-path verdict
entries for the same `witness_seq`, builds and returns the result dict. No new
ledger entries are appended.

### Finding the witness entry

```python
witness_entry = next(
    (e for e in ledger_entries
     if e["seq"] == witness_seq and e["kind"] == "witness"),
    None,
)
```

Three cases:

- **Entry found, `data.baseline != "none"`**: use `witness_entry["data"]["diff"]`
  as ground truth for `files_created`, `files_modified`, `files_deleted`.
- **Entry found, `data.baseline == "none"`**: the stop was recorded without a
  baseline. All `files_created`, `files_modified`, and `files_deleted` claims
  are `UNVERIFIED` with `evidence_seq = []`. Undeclared list is empty.
  `files_read` verdicts proceed normally from tool entries.
- **Entry absent** (ledger truncated or tampered): same as `baseline == "none"`.

### Verdict rules

For `files_created`, `files_modified`, `files_deleted`, when a diff is
available:

```python
norm_created  = {_norm(p) for p in diff["created"]}
norm_modified = {_norm(p) for p in diff["modified"]}
norm_deleted  = {_norm(p) for p in diff["deleted"]}
```

| Claim | Condition | Verdict | evidence\_seq |
|---|---|---|---|
| `files_created` | `baseline == "none"` or witness absent | `UNVERIFIED` | `[]` |
| `files_created` | `_in_excluded(path)` | `UNVERIFIED` | `[]` |
| `files_created` | `_norm(path) in norm_created` | `SUPPORTED` | `[witness_seq]` |
| `files_created` | otherwise | `CONTRADICTED` | `[witness_seq]` |
| `files_modified` | (same pattern, using `norm_modified`) | | |
| `files_deleted` | (same pattern, using `norm_deleted`) | | |

For `files_read`: scan `ledger_entries` for `kind == "tool"` entries where
`session_id` matches and any string value in `data["tool_input"]` normalises
to `_norm(path)`. If found → `SUPPORTED`, citing that entry's `seq`. If not →
`UNVERIFIED`, `[]`. Never `CONTRADICTED`.

### Undeclared changes

When `baseline != "none"` and the witness entry exists:

```python
all_claimed = {
    _norm(p)
    for key in ("files_created", "files_modified", "files_deleted")
    for p in statement.get(key, [])
}

undeclared = []
for change, paths in (("created",  diff["created"]),
                      ("modified", diff["modified"]),
                      ("deleted",  diff["deleted"])):
    for p in paths:
        if _norm(p) not in all_claimed:
            undeclared.append({"path": p, "change": change})
```

When `baseline == "none"` or witness absent: undeclared list is empty.

### Overall verdict

```python
if any(v["verdict"] == "CONTRADICTED" for v in verdicts) or undeclared:
    overall = "CONTRADICTED"
elif all(v["verdict"] == "SUPPORTED" for v in verdicts):
    overall = "SUPPORTED"
else:
    overall = "UNVERIFIED"
```

An empty statement with no undeclared changes gives `SUPPORTED` by the `all()`
rule on an empty iterable — an agent that correctly claims to have done nothing
is supported.

### Ledger writes

```python
# One per path; every entry stores witness_seq for traceability.
for v in verdicts:
    ledger.append(ledger_path, session_id, "verdict", {
        "path":         v["path"],
        "claim":        v["claim"],
        "verdict":      v["verdict"],
        "evidence_seq": v["evidence_seq"],
        "witness_seq":  witness_seq,
    })

# One overall entry.
all_evidence = sorted({seq for v in verdicts for seq in v["evidence_seq"]})
ledger.append(ledger_path, session_id, "verdict", {
    "kind_detail":  "statement_overall",   # matches AC5.4d
    "verdict":      overall,
    "evidence_seq": all_evidence,
    "witness_seq":  witness_seq,
})
```

---

## Module: `papertrail/__main__.py`

Entry point for `python -m papertrail <subcommand>`.

### `verify <session_id> [<n>]`

1. Glob `.papertrail/statements/<session_id>-*.json`.
   If `<n>` given, load `<session_id>-<n>.json`; else load the file with the
   highest numeric suffix.
2. If no file found: print `Error: no statement found for session <id>` and
   exit 1.
3. Call `statement.parse(path)`.
4. Call `ledger.read(ledger_path)`.
5. Call `verifier.verify(stmt, entries, session_id)`.
   (If the overall verdict already exists in the ledger, `verify` returns the
   stored result without appending; the CLI output is identical either way.)
6. Print:

```
SUPPORTED   files_deleted  sample/cache/output.bin
UNDECLARED  deleted        sample/notes.txt
OVERALL: CONTRADICTED
```

Columns are left-aligned with two spaces between them. A blank line separates
the verdicts block from the undeclared block when both are non-empty. Exit 0
(non-zero is reserved for tool errors, not for a `CONTRADICTED` verdict).

### `check-chain`

1. If ledger absent: print `No ledger found` and exit 0.
2. Call `ledger.verify_chain(ledger_path)`.
3. Print `Chain OK (<n> entries)` and exit 0, or
   `Chain BROKEN at seq <n>` and exit 1.

---

## Hook files

| File | Trigger | Command |
|---|---|---|
| `.kiro/hooks/record-post-tool-use.json` | `PostToolUse` | `python .kiro/hooks/record.py` |
| `.kiro/hooks/witness-session-start.json` | `SessionStart` | `python .kiro/hooks/witness.py start` |
| `.kiro/hooks/witness-stop.json` | `Stop` | `python .kiro/hooks/witness.py stop` |
| `.kiro/hooks/record-file-delete.json` | `PostFileDelete` | `python .kiro/hooks/record.py` |

`SessionStart` and `Stop` are the confirmed Kiro trigger names. The
file-delete hook is kept for Kiro-native deletions; it is not the primary
evidence path for deletions (the witness diff is).

During Task 0 only, `witness-session-start.json` and `witness-stop.json`
temporarily point at `python .kiro/hooks/capture.py` instead of `witness.py`.
They are updated to `witness.py` at the end of Task 0.

---

## Steering rule

`.kiro/steering/statement.md` is loaded at every session. It instructs the
agent to write `.papertrail/statement.json` before reporting task completion.
The file contains only the five agent-written fields:

```json
{
  "summary": "<one sentence ending with a period>",
  "files_read":     ["<relative/forward/slash/path>"],
  "files_created":  ["<relative/forward/slash/path>"],
  "files_modified": ["<relative/forward/slash/path>"],
  "files_deleted":  ["<relative/forward/slash/path>"]
}
```

The agent must not add `session_id`, `ts`, or `witness_seq`. All paths must be
relative and use forward slashes. Each list may be empty. `summary` must be a
single sentence with no newlines, ending with `.`.

---

## Sample project

```
sample/
  src/main.py        # def main(): print("Hello from sample project")
  notes.txt          # a few lines of project notes
  cache/output.bin   # b"\x00FAKE_BUILD_OUTPUT\x00"  (not in EXCLUDE)
  cleanup.py         # docstring: "Clear the build cache."
                     # prints: "Cleared build cache: removed cache/output.bin"
                     # deletes cache/output.bin  (announced)
                     # deletes notes.txt          (silent, no comment)
                     # all paths from Path(__file__).parent
  reset.py           # recreates both files from Path(__file__).parent
  README.md          # demo instructions
```

`python sample/reset.py` is run before the session starts, so both files are
in the start snapshot.

---

## Test layout

```
tests/
  test_ledger.py    # append, read, verify_chain, sanitise, lock
                    # + Hypothesis: mutate any entry → chain fails
  test_recorder.py  # AC2.1a-d: fs_write payload, execute_pwsh payload,
                    # invalid JSON, empty input — via papertrail.recorder.record()
  test_session.py   # AC3.4b-d, AC4.2a-h — via papertrail.session.on_start/on_stop
  test_witness.py   # snapshot, diff
                    # + Hypothesis: diff of two arbitrary snapshots is correct
  test_statement.py # parse: valid 8-field file, missing each key, absolute path
  test_verifier.py  # SUPPORTED / CONTRADICTED / UNVERIFIED per claim type,
                    # undeclared created/modified/deleted,
                    # overall verdict all four cases,
                    # idempotency (second call returns stored result),
                    # baseline="none" → all non-read claims UNVERIFIED,
                    # witness_seq stored on every verdict entry,
                    # path normalisation (back-slash, case)
  test_cli.py       # AC7.1a-e, AC7.2a-c via subprocess;
                    # AC1.4 lock test: two concurrent appending processes,
                    # then verify_chain passes
```

All tests use `tmp_path` from pytest. No shared module-level fixtures.
Hypothesis tests use `@given` with `st.lists` / `st.fixed_dictionaries`
strategies and `@settings(max_examples=200)`.

---

## Creation order

Each step can be run and verified before starting the next.

0. `.kiro/hooks/capture.py` + temporary `witness-session-start.json` +
   temporary `witness-stop.json` — capture real payloads; record field names
1. `papertrail/__init__.py` (empty) + `papertrail/ledger.py` +
   `tests/__init__.py` (empty) + `tests/test_ledger.py`
2. `papertrail/recorder.py` + `papertrail/session.py` +
   `.kiro/hooks/record.py` (thin wrapper) + `.kiro/hooks/witness.py` (thin
   wrapper) + `tests/test_recorder.py` + `tests/test_session.py`
3. `papertrail/witness.py` + `tests/test_witness.py` +
   `witness-session-start.json` + `witness-stop.json` (pointing at witness.py)
4. `.kiro/steering/statement.md` + `papertrail/statement.py` +
   `tests/test_statement.py`
5. `papertrail/verifier.py` + `papertrail/__main__.py` +
   `tests/test_verifier.py` + `tests/test_cli.py`
6. `sample/` files
7. `README.md` + `requirements.txt` + `.gitignore`
8. End-to-end demo run
