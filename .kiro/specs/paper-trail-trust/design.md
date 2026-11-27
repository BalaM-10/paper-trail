# Design - Paper Trail Trust

## R1 - Setup watch

### Module
`papertrail/watch.py` (standard library only, because the hooks import it) holds
the list and the helpers: `is_setup(path)`, `setup_paths(root)`,
`setup_changes(diff)`, `changed_files(diff)` and `loud_line(files)`. The words of
the loud line live here once; `web/src/lib/entryText.ts` has the twin
(`setupChangedText`), and `tests/fixtures/sentences.json` holds cases that both
languages must print identically.

### Always snapshotted
`witness.snapshot` walks the folder as before (skipping `EXCLUDE` and what the
ignore rule skips), then adds every path from `setup_paths(root)` that the walk
did not reach. So a `.gitignore` line such as `.kiro/` cannot hide the setup.
`__pycache__` folders and `.pyc` files under `.kiro/hooks` are left out, because
Python writes them without anyone changing the setup. `witness.without_ignored`
(which reads an older baseline through today's ignore rule) keeps setup paths, and
the verifier does not turn a claim about a setup path into UNVERIFIED because of
`.gitignore`.

### The record
At stop, after the stop record is appended, `session.on_stop` calls
`watch.changed_files(diff)`. If it is not empty it appends

```
kind: "witness"
data: { event: "setup_changed", files: [...], diff: {created, modified, deleted},
        baseline, witness_seq: <stop seq>, evidence_seq: [<stop seq>] }
```

right after the stop record, before any statement or verdict, so it sits in the
same turn (a roll starts at a `turn` record and holds everything up to the next).
`witness` is an existing kind and `event` an existing field, so nothing that reads
records has to learn a new kind: the roll splitter, the chain check, the MCP
tools and the page already carry unknown `witness` events. The record holds names
only.

`session.on_turn_start` adds `setup_changed: [files]` to the between-turns record
when the difference between the two snapshots touches the setup. Both entries are
independent of the statement: `verify` is not told about them.

### Printing
- Spool file (`papertrail/spool.py`): `entry_text` returns the loud sentence for
  `setup_changed`; `render` prints a row that starts with it between two rows of
  80 `*`. The file stays within 80 columns. `print_session` over MCP returns the
  same text, because `handle_print_session` calls `spool.render_session`.
- Between turns: `between_turns_text` appends " The recording setup changed:
  <files>." when `setup_changed` is present.
- Page: `PrintLine` gives the line the class `print-line--setup` (red text, a red
  bar, bold). `PrintReport` adds the line as a bordered paragraph (`print-setup`).

### Demo
`sample/make_demo_ledger.py` gains `_session_e`: a stand-in `.kiro/hooks/record.py`
exists before the session, the agent edits it and writes a notes file, and the
statement declares both. The verdict is SUPPORTED, the loud line is still printed,
which shows that the line does not depend on the agent's honesty.

## R2 - EXCEPTIONS ONLY

`web/src/lib/exceptions.ts`: `isException(line, brokenAt)` and
`exceptionsOnly(lines, brokenAt)` return the lines to keep and how many were
hidden. Rules, in order: the torn line is kept; `undeclared` lines are kept; a
`verdict` line is kept unless its verdict is SUPPORTED (so an overall
CONTRADICTED, UNVERIFIED or NO STATEMENT stays, and so does a per-claim one);
`witness` lines are kept when the event is `between_turns` or `setup_changed`;
everything else (snapshots, tool calls, the statement, errors) is hidden.

`App` holds one boolean. `lines` (what the replay prints) becomes the filtered
list, `allLines` stays for the report. The filter is applied after the torn line
is known (`brokenAt` comes from the chain check) so the torn line survives, and
the tear index is looked up in the filtered list. The replay key becomes
`"<roll>|<on/off>"`, so changing the key starts the roll again from the top, as
choosing another roll does.

`ExceptionNotes` prints, at the top of the paper and outside the replay, "N lines
hidden." and, if nothing is left, "Nothing to flag in this turn." They are notes
about the page, not lines of the record, so they have no number and are not
counted among the hidden lines.

`ExceptionsKey` is a `Key` with `pressed`, in its own group "Filter". It is never
disabled, so it can be set before a roll is picked on the live page. One known
limit: a kept "not mentioned" line normally jumps to the witness line that
proves it; with the key down that line is hidden, so the jump finds nothing. The
line's text already names the file and the change.

## R3 - Cases

`sample/run_cases.py` holds seven `Case` records (letter, name, story, expected
text, a function that plays it) and the helpers `run_case`, `run_all`, `table`,
`readme_block`, `update_readme`, `main`. Each case runs in its own
`tempfile.TemporaryDirectory`, calls `on_start`, `on_turn_start`, `on_stop` with the
temporary folder passed in, and reduces the record to one short line:

| Case | Played as | Expected |
|---|---|---|
| a | one file written and declared | `SUPPORTED` |
| b | two files written, one declared | `CONTRADICTED; undeclared: extra.txt` |
| c | a file declared that was never written | `CONTRADICTED; contradicted claim: ghost.txt` |
| d | a file changed, no statement | `NO_STATEMENT; undeclared: changed.txt` |
| e | a person edits a file between two turns | `SUPPORTED; between turns: person.txt` |
| f | the stop line of the record is edited afterwards | `Paper torn at line 2` |
| g | a hook is edited and declared | `SUPPORTED; setup changed: .kiro/hooks/record.py` |

Expected texts are written by hand, not derived from the run, so a case passes
only when the real behaviour matches what a person wrote down. The table has no
date and no path, so a fresh run on any machine gives the same text.
`tests/test_run_cases.py` runs each case, checks that the project record and the
environment are untouched, and compares the README block with a fresh table.

## R4 - Wording

The opening sentence is a constant in two places: the first paragraph after the
README title, and `page-header__tagline` in `Header.tsx`, placed right after the
product name and before the question. The README sections are plain text; the
tests only require that the cases table and the new spec name are present, and
the existing README tests (paths exist, order of the top sections) still pass.

## Tests

| Area | File |
|---|---|
| Setup list, snapshot, record, between turns, printing | `tests/test_watch.py` |
| Sentences in both languages | `tests/fixtures/sentences.json` |
| Demo session E | `tests/test_make_demo_ledger.py` |
| Cases and the README table | `tests/test_run_cases.py` |
| The filter rules | `web/src/__tests__/exceptions.test.ts` |
| The key in Demo, build and live; the loud line; the opening sentence | `web/src/__tests__/exceptionsOnly.test.tsx` |
