# Requirements — Paper Trail Core

## Scope
Ledger, recorder hook, witness, statement format, verifier, sample project, and tests.
Not in scope: API, MCP server, web printout.

---

## R1 — Ledger

### R1.1 Append
The ledger appends one JSON object per line to `.papertrail/ledger.jsonl`.
Every entry has these fields: `seq` (integer, 1-based), `ts` (UTC ISO 8601),
`session_id` (string), `kind` (one of `tool`, `witness`, `statement`,
`verdict`, `error`), `data` (object), `prev_hash` (64-char hex string),
`hash` (64-char hex string).

**Acceptance criteria**
- AC1.1a: Appending an entry to an empty ledger creates the file and writes
  exactly one line of valid JSON with `seq` = 1 and `prev_hash` equal to 64
  zeros.
- AC1.1b: A second append produces `seq` = 2 and `prev_hash` equal to the
  `hash` of the first entry.
- AC1.1c: `hash` is the SHA-256 of the canonical JSON of the entry with every
  field present except `hash` itself (keys sorted, no extra whitespace, UTF-8
  encoded).
- AC1.1d: All file paths stored inside `data` are relative to the project root
  and use forward slashes. No absolute paths, user names or machine names are
  stored.

### R1.2 Read
The ledger can be read back as a list of entry dicts in append order.

**Acceptance criteria**
- AC1.2a: Reading a ledger returns the same entries that were appended, in
  order, as Python dicts.
- AC1.2b: Reading an absent file returns an empty list without raising.

### R1.3 Verify chain
Chain verification checks every entry's `hash`, every entry's `prev_hash`
against its predecessor, and the integrity of the `seq` sequence.

**Acceptance criteria**
- AC1.3a: A ledger where no entry has been modified passes verification and
  returns a result indicating success.
- AC1.3b: Modifying the `data` field of any single entry causes verification
  to fail and the returned result names the first broken entry by its `seq`
  number.
- AC1.3c: Modifying the `hash` field of any entry causes verification to fail
  at that entry or the next, whichever is first to show a mismatch.
- AC1.3d: An empty ledger passes verification.
- AC1.3e: A ledger with a gap in `seq` (e.g. entries 1, 2, 4) fails
  verification, reporting the first missing seq.
- AC1.3f: A ledger with a repeated `seq` fails verification, reporting the
  repeated seq.

### R1.4 Exclusive append lock
Concurrent appends must not corrupt `seq` or `prev_hash`.

**Acceptance criteria**
- AC1.4a: `append` acquires an exclusive file lock before reading the last
  entry and writing the new one, and releases it after the write is flushed.
- AC1.4b: The locking mechanism works on Windows using only the standard
  library (`os.O_CREAT | os.O_EXCL` on a lock file); it does not rely on
  `msvcrt` or `fcntl`.
- AC1.4c: If the lock cannot be acquired within 5 seconds, `append` raises
  `RuntimeError`. A stale lock file older than 10 seconds is removed and the
  acquisition retried immediately.

### R1.5 Privacy: string sanitisation
Before any string value is stored in the ledger, the project root and the user
home directory are redacted.

**Acceptance criteria**
- AC1.5a: Any occurrence of the project root path in a stored string is
  replaced with `"."`, matched case-insensitively and regardless of whether
  forward or back slashes are used.
- AC1.5b: Any occurrence of the user home directory path in a stored string is
  replaced with `"~"`, with the same case and slash insensitivity.
- AC1.5c: Characters outside those two substrings are preserved verbatim.
- AC1.5d: A test covers the path `c:\Work\Projects\paper-trail` appearing
  in a command string and confirms it is replaced with `"."`.

---

## R2 — Recorder hook

### R2.1 Script
`.kiro/hooks/record.py` reads one JSON object from stdin, extracts tool call
fields (`session_id`, `tool_name`, `tool_input`, `tool_response`,
`hook_event_name`), applies privacy sanitisation to all string values, converts
any absolute file paths in `tool_input` to project-relative forward-slash
paths, and appends a `tool` entry to the ledger.

**Acceptance criteria**
- AC2.1a: Given a PostToolUse payload for `fs_write`, the script appends a
  `tool` entry whose `data.tool_name` is `"fs_write"` and whose
  `data.tool_input.path` is a relative forward-slash path.
- AC2.1b: Given a PostToolUse payload for `execute_pwsh`, the script appends
  a `tool` entry whose `data.tool_input.command` has the project root replaced
  with `"."` and the home directory replaced with `"~"`.
- AC2.1c: If stdin is empty or contains invalid JSON, the script appends an
  `error` entry and exits 0 without raising.
- AC2.1d: If the ledger directory does not exist, the script creates it before
  writing.
- AC2.1e: The script completes in well under one second on any valid input.
- AC2.1f: The script imports `papertrail.ledger` by inserting the project root
  (derived from `Path(__file__).resolve().parents[2]`) into `sys.path`. It
  does not depend on the working directory or any installed package outside
  the standard library.

### R2.2 Hook wiring
The existing `record-post-tool-use.json` hook points at
`python .kiro/hooks/record.py` with trigger `PostToolUse` and no matcher
(all tools).

**Acceptance criteria**
- AC2.2a: `.kiro/hooks/record-post-tool-use.json` exists, has
  `"trigger": "PostToolUse"`, `"type": "command"`, and
  `"command": "python .kiro/hooks/record.py"`.
- AC2.2b: There is no matcher field, or the matcher is empty, so all tools are
  recorded.

---

## R3 — Witness

### R3.1 Snapshot
A snapshot maps every relative file path under the project root (excluding
`.git`, `.papertrail`, `node_modules`, `__pycache__`, `.venv`, `dist`,
`build`) to its byte size and SHA-256 hex digest.

**Acceptance criteria**
- AC3.1a: A snapshot of a directory with known files returns the correct size
  and SHA-256 for each file.
- AC3.1b: Excluded directories are not present in the snapshot.
- AC3.1c: All paths in the snapshot use forward slashes and are relative to
  the project root.

### R3.2 Difference
Comparing two snapshots produces a dict with three lists: `created` (paths in
new snapshot but not old), `deleted` (paths in old snapshot but not new),
`modified` (paths in both but with different hash).

**Acceptance criteria**
- AC3.2a: A file present in the new snapshot but absent in the old appears in
  `created`.
- AC3.2b: A file absent in the new snapshot but present in the old appears in
  `deleted`.
- AC3.2c: A file present in both but with a different SHA-256 appears in
  `modified`.
- AC3.2d: A file present in both with the same SHA-256 appears in none of the
  three lists.
- AC3.2e: Two identical snapshots produce empty `created`, `deleted` and
  `modified` lists.

### R3.3 Session-start hook
A `SessionStart` hook runs `python .kiro/hooks/witness.py start`. The script
reads the hook payload from stdin to extract `session_id`, takes a snapshot of
the project root, and appends a `witness` entry to the ledger with
`data.event` = `"start"` and `data.snapshot` as the snapshot dict.

`SessionStart` is the confirmed Kiro trigger name for this event.

**Acceptance criteria**
- AC3.3a: `.kiro/hooks/witness-session-start.json` exists with
  `"trigger": "SessionStart"` and
  `"command": "python .kiro/hooks/witness.py start"`.
- AC3.3b: Running the script appends a ledger entry with `kind` = `"witness"`,
  `data.event` = `"start"`, and `data.snapshot` as a non-empty dict when the
  project root contains files.
- AC3.3c: The first task that uses the witness hooks saves the raw stdin
  payload to `.papertrail/payloads/session-start.json` so the actual payload
  shape can be inspected and the session_id field name confirmed.

### R3.4 Session-stop hook
A `Stop` hook runs `python .kiro/hooks/witness.py stop`. The script reads the
hook payload from stdin to extract `session_id`, takes a new snapshot,
determines the diff baseline (the snapshot from the most recent promoting stop
in this session, or the session-start snapshot if no statement has been
promoted yet), computes the difference, and appends a `witness` entry with
`data.event` = `"stop"`, `data.snapshot` as the new snapshot, `data.diff` as
the difference dict, and `data.baseline` as a label identifying which snapshot
was used. If no baseline exists (no start and no prior promoting stop), the
entry is appended with an empty diff and `data.baseline` = `"none"`.

`Stop` is the confirmed Kiro trigger name for the agent-stop event.

The `Stop` trigger may fire more than once per session. Each firing diffs
against the current baseline as defined above.

**Acceptance criteria**
- AC3.4a: `.kiro/hooks/witness-stop.json` exists with `"trigger": "Stop"` and
  `"command": "python .kiro/hooks/witness.py stop"`.
- AC3.4b: Running the script after a start snapshot appends a ledger entry
  with `kind` = `"witness"`, `data.event` = `"stop"`, and `data.diff`
  containing at minimum `created`, `deleted` and `modified` lists.
- AC3.4c: If no start snapshot exists for the current session, the script
  appends a `witness/stop` entry with an empty diff and exits 0.
- AC3.4d: If `Stop` fires a second time in the same session after a statement
  was promoted, the second stop diffs against the snapshot from the first
  promoting stop, not against the session-start snapshot.
- AC3.4e: The first task that uses the witness hooks saves the raw stdin
  payload to `.papertrail/payloads/session-stop.json` so the actual payload
  shape can be inspected.

---

## R4 — Statement

### R4.1 Agent-written file
At the end of every task the agent writes `.papertrail/statement.json`
(no session ID in the filename) containing:

```json
{
  "summary": "<one plain-language sentence>",
  "files_read":     ["<relative/path>"],
  "files_created":  ["<relative/path>"],
  "files_modified": ["<relative/path>"],
  "files_deleted":  ["<relative/path>"]
}
```

The agent does not include `session_id` or `ts`; the stop hook adds those.
All paths are relative, forward-slash, and unique within their list.

**Acceptance criteria**
- AC4.1a: The file at `.papertrail/statement.json` is valid JSON and contains
  all five top-level keys (`summary` plus the four file lists).
- AC4.1b: Each path in every file list is relative, uses forward slashes, and
  is not duplicated within that list.
- AC4.1c: `summary` is a single sentence (no newlines, ends with `.`).

### R4.2 Stop-hook promotion
The `Stop` hook script (`witness.py stop`) reads `.papertrail/statement.json`
if it exists, adds `session_id` (from the hook payload), `ts` (current UTC
time), and `witness_seq` (the `seq` of the `witness/stop` ledger entry
appended in this same hook run), appends a `statement` ledger entry whose
`data` is the full eight-field object, saves the promoted copy, and then
deletes `.papertrail/statement.json` so each statement file is consumed
exactly once.

A session may produce more than one statement (the agent stops, writes a
statement, the session continues, and the agent stops again). The promoted
copies are saved as `.papertrail/statements/<session_id>-1.json`,
`<session_id>-2.json`, and so on, numbered in promotion order. The CLI `verify`
command uses the highest-numbered file unless a specific number is given.

After a statement is promoted, the diff baseline for subsequent stops in the
same session advances to the snapshot taken at that stop. A stop that fires
with no pending `statement.json` appends its witness entry and diffs as usual,
but does not advance the baseline.

**Acceptance criteria**
- AC4.2a: After the first stop hook promotion, `.papertrail/statements/
  <session_id>-1.json` exists with all eight fields (`summary`, the four file
  lists, `session_id`, `ts`, and `witness_seq`), and
  `.papertrail/statement.json` has been deleted.
- AC4.2b: The ledger contains a `statement` entry for the session with
  `data.session_id` matching the session and `data.summary` matching what the
  agent wrote.
- AC4.2c: If `.papertrail/statement.json` does not exist when the stop hook
  fires, the hook skips statement promotion without error.
- AC4.2d: If the agent writes a second statement and the session stops again,
  the second promoted copy is saved as `<session_id>-2.json`. Both files exist
  and are distinct.
- AC4.2e: The second stop's witness diff is computed against the snapshot from
  the first promoting stop, not the session-start snapshot.
- AC4.2f: A stop with no pending statement does not advance the diff baseline.
- AC4.2g: `witness_seq` in the promoted file equals the `seq` of the
  `witness/stop` ledger entry written in the same hook run, linking the
  statement to its evidence.
- AC4.2h: After a statement is promoted, a later `Stop` in the same session
  that finds no pending `statement.json` does not alter any existing
  `.papertrail/statements/` file, does not append a new `statement` ledger
  entry, and does not change the result of running
  `python -m papertrail verify <session_id> 1`.

### R4.3 Steering rule
A steering file instructs the agent to write the statement at the end of every
task.

**Acceptance criteria**
- AC4.3a: `.kiro/steering/statement.md` exists and specifies:
  - Write `.papertrail/statement.json` before reporting task completion.
  - The exact five-field JSON schema (no `session_id`, no `ts`).
  - All paths must be relative and use forward slashes.
  - `summary` must be a single sentence ending with `.`.

### R4.4 Parser
`papertrail/statement.py` parses and validates a promoted statement file
(eight fields: `summary`, the four file lists, `session_id`, `ts`, and
`witness_seq`), raising a clear error if any required field is missing or any
path is absolute.

**Acceptance criteria**
- AC4.4a: Parsing a valid promoted statement returns a dict with all eight
  keys.
- AC4.4b: Parsing a file missing any required key raises `ValueError` naming
  the missing key.
- AC4.4c: Parsing a file containing an absolute path in any file list raises
  `ValueError` naming the offending path.

---

## R5 — Verifier

### R5.1 Per-line verdicts
The witness diff is the ground truth for `files_created`, `files_modified`,
and `files_deleted`. Tool ledger entries are the ground truth for `files_read`.
Paths that fall inside an excluded directory cannot be verified by the witness.

The verifier identifies the relevant witness entry using the promoted
statement's `witness_seq` field, which points to the specific `witness/stop`
ledger entry appended in the same hook run as the statement. It never searches
for "the latest" stop entry.

Each path in every file list receives one verdict:

- `SUPPORTED` — the ground truth confirms the claimed action.
- `CONTRADICTED` — the ground truth shows the claimed action did not happen.
- `UNVERIFIED` — no ground truth is available for this claim.

When comparing a statement path against a witness diff path or a ledger path,
both sides are normalised: separators are unified to forward slashes and the
comparison is case-insensitive on Windows. This normalisation is applied only
for matching; stored values are not changed.

Verdict rules by claim type:

| Claim | SUPPORTED | CONTRADICTED | UNVERIFIED |
|---|---|---|---|
| `files_created` | path in `witness.diff.created` | path not in `witness.diff.created` and not inside an excluded dir | path is inside an excluded dir |
| `files_modified` | path in `witness.diff.modified` | path not in `witness.diff.modified` and not inside an excluded dir | path is inside an excluded dir |
| `files_deleted` | path in `witness.diff.deleted` | path not in `witness.diff.deleted` and not inside an excluded dir | path is inside an excluded dir |
| `files_read` | a `tool` ledger entry for the session shows this path was read | (never contradicted) | no matching tool entry |

**Acceptance criteria**
- AC5.1a: A path in `files_created` that is in `witness.diff.created` receives
  `SUPPORTED`, citing the witness stop entry's `seq`.
- AC5.1b: A path in `files_created` that is absent from `witness.diff.created`
  and is not inside an excluded directory receives `CONTRADICTED`, citing the
  witness stop entry's `seq`.
- AC5.1c: A path in `files_created` that is inside an excluded directory
  receives `UNVERIFIED` with an empty evidence list.
- AC5.1d: A path in `files_deleted` that is in `witness.diff.deleted` receives
  `SUPPORTED`.
- AC5.1e: A path in `files_deleted` that is not in `witness.diff.deleted` and
  is not inside an excluded directory receives `CONTRADICTED`.
- AC5.1f: A path in `files_read` confirmed by a `tool` ledger entry receives
  `SUPPORTED`, citing that entry's `seq`.
- AC5.1g: A path in `files_read` with no matching tool entry receives
  `UNVERIFIED` with an empty evidence list.
- AC5.1h: Each verdict cites at least one ledger `seq` number when evidence
  exists, or an empty list when the verdict is `UNVERIFIED`.
- AC5.1i: A statement path written with back slashes (e.g. `sample\notes.txt`)
  matches a witness diff path written with forward slashes (`sample/notes.txt`)
  and produces the same verdict as the forward-slash form.
- AC5.1j: A statement path that differs from a witness diff path only in letter
  case matches correctly on Windows.

### R5.2 Undeclared changes
Any path in the witness diff (created, modified, or deleted) that does not
appear in any list in the statement is reported as an `UNDECLARED CHANGE`,
labelled with the change type (`created`, `modified`, or `deleted`).

**Acceptance criteria**
- AC5.2a: A file deleted by the agent but absent from `files_deleted` appears
  in undeclared changes with `change` = `"deleted"`.
- AC5.2b: A file created by the agent but absent from `files_created` appears
  in undeclared changes with `change` = `"created"`.
- AC5.2c: A file modified by the agent but absent from `files_modified`
  appears in undeclared changes with `change` = `"modified"`.

### R5.3 Statement-level verdict
After computing per-line verdicts and undeclared changes, the verifier assigns
one overall verdict to the statement:

- `CONTRADICTED` if any per-line verdict is `CONTRADICTED`, or if any
  undeclared change exists.
- `SUPPORTED` if every per-line verdict is `SUPPORTED` and there are no
  undeclared changes.
- `UNVERIFIED` in all other cases (mix of `SUPPORTED` and `UNVERIFIED`, no
  `CONTRADICTED`, no undeclared changes).

**Acceptance criteria**
- AC5.3a: A statement where all lines are `SUPPORTED` and undeclared changes
  is empty receives overall verdict `SUPPORTED`.
- AC5.3b: A statement where any line is `CONTRADICTED` receives overall verdict
  `CONTRADICTED`, regardless of other lines.
- AC5.3c: A statement with no `CONTRADICTED` lines but at least one undeclared
  change receives overall verdict `CONTRADICTED`.
- AC5.3d: A statement with a mix of `SUPPORTED` and `UNVERIFIED` lines and no
  undeclared changes receives overall verdict `UNVERIFIED`.
- AC5.3e: The overall verdict is included in the return value of `verify` and
  in the statement-level `verdict` ledger entry.

### R5.4 Verdict ledger entries
After computing verdicts the verifier appends ledger entries: one `verdict`
entry per path across all file lists, then one additional `verdict` entry for
the statement-level overall verdict.

**Acceptance criteria**
- AC5.4a: After verification, the ledger contains one `verdict` entry per
  path across all file lists in the statement.
- AC5.4b: Each per-path `verdict` entry's `data.verdict` is one of
  `SUPPORTED`, `CONTRADICTED`, or `UNVERIFIED`.
- AC5.4c: Each per-path `verdict` entry's `data.evidence_seq` is a list of
  integers (may be empty).
- AC5.4d: The statement-level `verdict` entry has `data.kind_detail` =
  `"statement_overall"`, `data.verdict` as the overall verdict string, and
  `data.evidence_seq` as the union of all per-path evidence seq numbers.

---

## R6 — Sample project

### R6.1 Structure
`sample/` contains a small project with at minimum:
- `src/main.py` — a trivial Python file.
- `notes.txt` — a short plaintext file.
- `cache/output.bin` — a build artifact (in `cache/`, not `build/`, so the
  witness does not ignore it).
- `cleanup.py` — a script described as "clear the build cache" that prints
  `"Cleared build cache: removed cache/output.bin"` and exits. It deletes
  `cache/output.bin` and also silently deletes `notes.txt` without printing
  anything about `notes.txt`. Both paths are resolved relative to
  `cleanup.py`'s own directory using `Path(__file__).parent`, not relative to
  the working directory.
- `reset.py` — restores `notes.txt` and `cache/output.bin`. Paths are also
  resolved relative to `reset.py`'s own directory.

**Acceptance criteria**
- AC6.1a: Running `python sample/cleanup.py` from any working directory
  deletes `sample/cache/output.bin` and `sample/notes.txt`.
- AC6.1b: Running `python sample/cleanup.py` prints exactly
  `"Cleared build cache: removed cache/output.bin"` to stdout, does not raise,
  and exits 0.
- AC6.1c: Running `python sample/reset.py` restores both files regardless of
  working directory.
- AC6.1d: Running cleanup then reset then cleanup again succeeds each time
  (idempotent).

### R6.2 Demo story
The demo story from product.md must be reproducible and end with the statement
stamped `CONTRADICTED`:

1. Run `python sample/reset.py` to ensure both sample files exist (done
   before the session starts, so both appear in the start snapshot).
2. Start a session (witness `SessionStart` hook fires, start snapshot taken;
   both `sample/notes.txt` and `sample/cache/output.bin` are in the snapshot).
3. Run `python sample/cleanup.py` (agent uses the execute_pwsh tool).
   Only `"Cleared build cache: removed cache/output.bin"` is printed.
4. Agent writes `.papertrail/statement.json` claiming only
   `sample/cache/output.bin` was deleted; `sample/notes.txt` is not mentioned.
5. Session ends (`Stop` hook fires): stop snapshot taken, diff computed,
   statement promoted to `.papertrail/statements/<session_id>-1.json`.
6. Run `python -m papertrail verify <session_id>`.
7. Verifier finds `sample/notes.txt` in `witness.diff.deleted` but not in the
   statement — undeclared change exists — overall verdict is `CONTRADICTED`.

**Acceptance criteria**
- AC6.2a: The witness diff after running `cleanup.py` includes both
  `sample/cache/output.bin` and `sample/notes.txt` in `deleted`.
- AC6.2b: A statement that lists only `sample/cache/output.bin` as deleted
  produces an `UNDECLARED CHANGE` for `sample/notes.txt`.
- AC6.2c: `python -m papertrail verify <session_id>` exits with the overall
  verdict `CONTRADICTED` printed to stdout.

---

## R7 — CLI

### R7.1 `python -m papertrail verify <session_id> [<n>]`
Loads a promoted statement for the given session, runs the verifier, and
prints results to stdout: per-path verdicts, undeclared changes, and the
overall verdict. If `<n>` is given, loads `<session_id>-<n>.json`; otherwise
loads the highest-numbered file for that session.

**Acceptance criteria**
- AC7.1a: Running the command with a valid session ID prints each per-path
  verdict in the form `<verdict> <claim> <path>`.
- AC7.1b: Undeclared changes are listed after per-path verdicts, labelled
  `UNDECLARED <change_type> <path>`.
- AC7.1c: The final line is `OVERALL: <verdict>`.
- AC7.1d: Running the command with an unknown session ID prints a clear error
  message and exits non-zero.
- AC7.1e: Running the command with `<session_id> 1` loads
  `<session_id>-1.json` specifically, even when a higher-numbered file exists.

### R7.2 `python -m papertrail check-chain`
Runs `verify_chain` on the ledger and prints the result.

**Acceptance criteria**
- AC7.2a: On a valid chain, prints `Chain OK (<n> entries)` and exits 0.
- AC7.2b: On a broken chain, prints `Chain BROKEN at seq <n>` and exits 1.
- AC7.2c: On an absent ledger, prints `No ledger found` and exits 0.

---

## R8 — Tests

### R8.1 Unit tests
Every module in `papertrail/` has a matching test file in `tests/`.

**Acceptance criteria**
- AC8.1a: `tests/test_ledger.py`, `tests/test_witness.py`,
  `tests/test_statement.py`, and `tests/test_verifier.py` all exist.
- AC8.1b: `pytest tests/` passes with no failures.

### R8.2 Hypothesis: hash chain
A property-based test asserts that mutating any single entry's `data` field
in any position in the chain is always detected by `verify_chain`.

**Acceptance criteria**
- AC8.2a: The test uses `hypothesis.given` with a strategy that generates a
  list of one or more entry dicts and an index to mutate.
- AC8.2b: `verify_chain` returns a failure result for every generated case
  where a mutation was applied.

### R8.3 Hypothesis: snapshot difference
A property-based test asserts that the diff of two independently generated
snapshots correctly identifies created, deleted, and modified paths with no
false positives or false negatives.

**Acceptance criteria**
- AC8.3a: The test uses `hypothesis.given` with a strategy that generates two
  snapshot dicts.
- AC8.3b: Every path in the generated `created` list is in the new snapshot
  but not the old, every path in `deleted` is in the old but not the new, and
  every path in `modified` is in both with differing hashes.

### R8.4 Privacy sanitisation test
A unit test specifically covers path redaction in stored strings.

**Acceptance criteria**
- AC8.4a: A test in `tests/test_ledger.py` calls the sanitisation function
  with a string containing `c:\Work\Projects\paper-trail` (back-slash form)
  and asserts the result contains `"."` in place of that path.
- AC8.4b: A second case covers the forward-slash form
  `c:/Work/Projects/paper-trail` and confirms the same substitution.
- AC8.4c: A third case confirms text outside the redacted substrings is
  unchanged.
