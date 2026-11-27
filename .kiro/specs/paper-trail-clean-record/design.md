# Design - Paper Trail Clean Record

## 1. One definition of private: `papertrail/privacy.py`

Standard library only (the hooks import it through the ledger).

```python
identity_terms() -> dict[str, str]      # lower-case name -> "the user name" | "the machine name"
scrub(text, root, home, terms=None) -> str
find(text, terms=None) -> list[(what, start, end)]
```

`scrub` works in three steps, in this order:

1. **Project folder, then home folder.** A pattern built from the folder's
   parts, joined by `[/\\]+` (so a doubled or quadrupled backslash matches),
   case-insensitive, followed by a boundary (`/ \ " ' < >`, white space, end).
   They become `.` and `~`; the rest of the path stays as written.
2. **Other absolute paths.** One regex with four alternatives, tried left to
   right, each running to the end of the token (`[^\s"'<>|`,;)\]}]*`):
   `file:///` + anything absolute; a drive path (a single letter not after a
   letter or `]`, then `:` and a slash); a UNC path (two or four leading
   backslashes); a POSIX path that starts in a listed folder after a boundary
   character. The replacement keeps the last part: the token is split on
   `[/\\]+`, a leading drive is dropped, the last part loses a trailing run of
   `. : ! ?`, and the result is `[path]/<last>`. A trailing separator is put back
   (so `\"` after a path survives); a trailing `:` is not put back after a
   separator, because `:\` would look like a drive again.
3. **Names.** For each name, a case-insensitive pattern for the name and one for
   its Windows short form (the first six letters or digits plus `~` and digits).
   The short form is tried first, so `ALICE~1` is one name. The text is split
   on the markers `[user]`, `[machine]`, `[path]` first and only the pieces
   between them are changed, so a user whose name is `user` or `path` is not
   scrubbed over and over.

`find` uses the same `PATH_RE` and the same name patterns, over the same
pieces, and labels each hit "a drive path", "a network path", "a path under a
user or system folder", "the user name" or "the machine name". Overlapping name
hits are one finding.

Why `scrub(x)` always passes `find`: the output of step 2 is `[path]/<last>`,
which no path alternative matches (it starts with `[`, the drive pattern is
guarded against a preceding `]`, UNC likewise, and the `file:///` pattern
refuses `[`); the output of step 3 is a marker, which the name patterns skip.
The property tests check this.

Known limit: a path with a space in it ends at the space, so
`C:\Program Files\x` becomes `[path]/Program Files\x`. Nothing in the result
looks like an absolute path, but the folder names after the space are kept.

### The recorder

`ledger.sanitise(value, root, home, terms=None)` calls `privacy.scrub`.
`_sanitise_data` gets the names once, then cleans every string, every key and,
in `append`, the session id. `append` is the only writer, so everything the
recorder writes passes the scan. `to_relative` and `recorder.py` need no change.

### The export tool

`sample/export_build_record.py` imports `identity_terms` and `find` from
`privacy`. `_scan_text` turns `find` into (what, snippet). Its own patterns and
`identity_terms` are removed. Its tests build records by hand (without
`append`), because `append` now cleans what those tests need to find.

## 2. Checking a statement in the stop hook

`session.on_stop`, after it promotes a statement:

```python
promoted_stmt = statement.parse(out)                       # the file just written
entries = ledger.read(ledger_path)
verifier.verify(promoted_stmt, entries, session_id, ledger_path=ledger_path)
```

`verifier.verify` already does what is needed: it is idempotent on the pair
(session, `witness_seq`) and appends the per-claim verdicts and the overall
verdict once. So `verify` run later (CLI, API, MCP) finds the stored overall
verdict and appends nothing.

The call is inside its own `try`. On any exception the hook appends an `error`
record (`source: "session.py auto-check"`) inside a second `try`, and goes on.
The hook scripts already catch everything and exit 0. Cost: one more read of the
record and one more pass over it; on a project of 2,000 records and 20 changed
files this stays far under a second (tested with 20 files).

## 3. `python -m papertrail archive`

`archive.py` (standard library only):

```python
def archive(root: Path, now: datetime | None = None) -> Archived   # raises ArchiveError(reason)
```

1. No `ledger.jsonl`, or an empty one: `ArchiveError("there is no record to archive")`.
2. Take `ledger._file_lock` on `.papertrail/ledger.lock`.
3. Check the chain with `ledger.verify_chain`; unreadable or torn: `ArchiveError`
   saying so and where.
4. `archive/` is created; the name is `ledger-<UTC %Y%m%dT%H%M%SZ>.jsonl`, with
   `-2`, `-3` ... added if it exists.
5. `os.replace(ledger.jsonl, target)` (same folder, so atomic). Release the lock.
6. Return the number of lines, the archived path (relative) and the last hash.

Nothing is read into memory more than once; nothing is rewritten. The CLI prints:

```
Moved the record (459 lines) to .papertrail/archive/ledger-20260301T090000Z.jsonl.
Fingerprint of the archived record: <hash>
Nothing was deleted. The next line Paper Trail records starts a new record.
```

and on refusal `Did not archive: <reason>. Nothing was moved.` with status 1.
The statements, payloads and spool files are left where they are.

## 4. The page says which part of the build it shows

- `export_build_record.py` writes `build-record.json` after a successful copy,
  `{"partial": <bool>}`; `partial` is whether `.papertrail/archive/` holds any
  `ledger-*.jsonl`. `--meta` sets its path (default: next to `--dest`).
- `useEntries` in the build view also fetches `./demo/build-record.json`; a
  failure, a wrong shape or a non-boolean gives `null`. It returns `buildInfo`.
- `lib/coverage.ts`: `coverageText(entries, partial)` formats the dates of the
  first and last record in UTC, `D Month YYYY`:
  - not partial or unknown: "This record runs from A to B." (same day: "This record is from A.")
  - partial: "This record covers only part of the build: from A to B. Earlier work was archived and is not shown here." (same day: "...: A. Earlier ...")
- `BuildTotals` shows it under the totals. CSS: the same class as the totals,
  with `overflow-wrap: anywhere`.

## 5. Tests

| File | Covers |
|------|--------|
| `tests/test_privacy.py` | R1, with the Hypothesis properties |
| `tests/test_session.py` additions | R2 |
| `tests/test_archive.py` | R3, and the CLI |
| `tests/test_export_build_record.py` additions | `build-record.json` |
| `web/src/__tests__/coverage.test.ts`, `buildView.test.tsx` | R4 |

## 6. After the checks (the closing steps asked for)

1. Write `.papertrail/statement.json`.
2. `python -m papertrail archive`: the record of this build is put away.
3. `python sample/export_build_record.py`: report what it says. The new record
   holds only what the hooks wrote after the archive, so a published copy would
   cover only the last few lines, and `partial` is true.
