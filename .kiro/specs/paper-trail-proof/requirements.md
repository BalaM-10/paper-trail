# Requirements — Paper Trail Proof

## Scope

Four things that make the evidence harder to wave away: an honest sample bug, a
verdict for the case where the agent says nothing, a print-ready file of a
session, and automated checks on three operating systems. Two small fixes to
the printout ride along.

Core modules that change, and only as listed: `session.py` (the stop hook
records NO_STATEMENT). New modules: `outcome.py`, `spool.py`. `api.py`,
`mcp_server.py` and `__main__.py` gain behaviour. Everything else in the core
stays as it is.

Rules that still hold everywhere: no file contents and no absolute paths in
the record or in any file written from it, plain words on screen, everything
keyboard operable, no sideways scroll at 375 px. Every file written for this
spec is UTF-8 without a byte-order mark.

Where this spec conflicts with an earlier one, this one wins. The conflicts
are listed in R7.

---

## R1 — An honest sample bug

The demo should not depend on a trick. The sample's cleanup script has an
ordinary mistake that anyone could make.

### R1.1 The script

`sample/cleanup.py` is meant to clear the build cache. It removes every
`*.bin` and `*.txt` file under `sample/`, because its author thought of the
cache as "build output and log files". That pattern is too broad: it also
matches `sample/notes.txt`. The script prints one line that mentions only the
cache. Nothing in it hides anything; it just does what its pattern says.

**Acceptance criteria**

- AC1.1a: Running `python sample/cleanup.py` deletes `sample/cache/output.bin`
  and `sample/notes.txt`.
- AC1.1b: It prints exactly one line, `Cleared build cache: removed
  cache/output.bin`, and exits 0.
- AC1.1c: It deletes nothing else: `cleanup.py`, `reset.py`, `README.md` and
  `src/main.py` are all still there afterwards.
- AC1.1d: It works from any working directory (paths come from
  `Path(__file__).parent`) and is safe to run twice.
- AC1.1e: Neither the code nor its comments call the behaviour a trick or a
  trap. A reader sees a pattern that is too broad.

### R1.2 Reset

**Acceptance criteria**

- AC1.2a: `sample/reset.py` has one function, `restore(folder)`, that writes
  the sample's starting files (`cache/output.bin`, `notes.txt`) and returns
  their relative paths. Importing the module writes nothing.
- AC1.2b: `python sample/reset.py` still restores both files from any working
  directory, and says which.
- AC1.2c: The demo generator uses `restore`, so the sample and the demo cannot
  drift apart.

### R1.3 README

**Acceptance criteria**

- AC1.3a: `sample/README.md` says what the script was meant to do, which line
  of its pattern is too broad and why, what the printed line says, and how to
  run the demo. It no longer says the script "silently" does anything.

### R1.4 The demo shows the real script

**Acceptance criteria**

- AC1.4a: The generator copies the real `sample/cleanup.py` into its temporary
  project and runs it. The recorded command output is the script's real output.
- AC1.4b: The witness diff of that session lists both deleted files because
  the script deleted them, not because the generator did.
- AC1.4c: `web/public/demo/ledger.jsonl` is regenerated and its chain is intact.

---

## R2 — The NO_STATEMENT verdict

An agent that changes files and says nothing is the strongest case for the
witness, and today it leaves no verdict at all.

### R2.1 The stop hook records it

When the stop hook runs, the witness has a diff with at least one change, and
no statement was promoted at this stop, it appends an overall `verdict` record:

```json
{"kind_detail": "statement_overall", "verdict": "NO_STATEMENT",
 "evidence_seq": [<stop seq>], "witness_seq": <stop seq>,
 "undeclared": [{"path": "...", "change": "created|modified|deleted"}]}
```

`undeclared` lists the diff, created first, then modified, then deleted, each in
the diff's own order. The record has the same shape as a verifier's overall
verdict, so everything that reads overall verdicts already understands it.

**Acceptance criteria**

- AC2.1a: A stop with changes and no `statement.json` appends the NO_STATEMENT
  verdict after the witness/stop record, with the diff as `undeclared`.
- AC2.1b: A stop with no changes appends nothing beyond the witness/stop
  record.
- AC2.1c: A stop that promotes a statement appends no NO_STATEMENT verdict.
- AC2.1d: A stop with no baseline (no start snapshot, so no diff) appends
  nothing.
- AC2.1e: A statement that is rejected as unusable counts as no statement: the
  error record and the move to `rejected/` happen as before, and the
  NO_STATEMENT verdict follows if there are changes.
- AC2.1f: A later stop that finds exactly the same changes and the session's
  latest overall verdict is already that NO_STATEMENT does not record it again.
  New or different changes are recorded.
- AC2.1g: Changes made after a promoted statement are measured from that
  statement's stop (the existing baseline rule), so only newer changes appear.
- AC2.1h: The stop hook still never raises, still finishes well under a second,
  and `session.py` still imports only the standard library.
- AC2.1i: The record contains no file contents and no absolute paths.

### R2.2 Everything that reads verdicts shows it

**Acceptance criteria**

- AC2.2a: `python -m papertrail verify <session_id>` for a session with no
  statement file but a NO_STATEMENT verdict prints the undeclared lines and
  `OVERALL: NO_STATEMENT`, exit 0, writing nothing to the record.
- AC2.2b: With no number given, `verify` shows whichever is newer, the
  highest-numbered statement or the latest NO_STATEMENT verdict. With a number
  it needs that statement file, as before.
- AC2.2c: `POST /api/verify/{session_id}` (new, no number) returns the newer of
  the two in the same shape as the numbered route: `verdicts` (empty for
  NO_STATEMENT), `undeclared` and `overall`. `POST /api/verify/{session_id}/{n}`
  is unchanged. `GET /api/ledger` carries the verdict record as it does every
  other.
- AC2.2d: The MCP `list_sessions` reports `overall_verdict: "NO_STATEMENT"` and
  `has_statement: false`. `verify_statement` takes an optional number; without
  one it behaves as in AC2.2b.
- AC2.2e: All three routes still refuse unsafe session ids.

### R2.3 The screen shows it

**Acceptance criteria**

- AC2.3a: Its overall line reads "Overall: the agent changed files and said
  nothing." with its own stamp. The stamp says NO STATEMENT (never the
  underscore form), has its own colour that is not green, red or amber, and
  contrasts at least 4.5:1 on a green bar and on paper.
- AC2.3b: Each undeclared change is a circled line that links to the witness
  line, exactly as for a contradicted statement, and the overall line comes
  after them.
- AC2.3c: The session's roll is titled "No statement written" and carries the
  small stamp.
- AC2.3d: The clerk is alarmed and says something like "The agent changed files
  and said nothing. Click a red circle to see what the witness saw." (96
  characters at most, says what to click).
- AC2.3e: No "Check this statement" button is offered for it.
- AC2.3f: In the tear-off report the changes are headed "Changes the witness
  saw:", and the overall sentence is followed by (NO STATEMENT).

### R2.4 A third demo session

**Acceptance criteria**

- AC2.4a: The generator adds a third session, `demo-session-c`, recorded in
  the same project and ledger after the other two. The agent edits
  `sample/src/main.py`, creates `sample/src/helpers.py`, and stops without a
  statement.
- AC2.4b: The session ends with the NO_STATEMENT verdict listing both changes
  as undeclared, created first. It has no statement record.
- AC2.4c: The generated ledger now has three sessions and its chain is intact.

---

## R3 — A print-ready spool file

### R3.1 The command

`python -m papertrail print <session_id>` writes
`.papertrail/spool/<session_id>.txt`.

**Acceptance criteria**

- AC3.1a: The file is plain text in UTF-8 without a byte-order mark, with
  `\n` line endings, and no line is longer than 80 characters, including very
  long paths.
- AC3.1b: It has a header (title, session id, statement summary or "none
  written", and "Paper intact" or "Paper torn at line N"), a rule, the
  session's lines with line numbers, a rule, and the fingerprint line.
- AC3.1c: Line numbers are the record's own, so "(line 11)" in a sentence
  points at line 11 of the file. Continuation lines are indented under their
  text. An undeclared line is marked `!` where a number would be.
- AC3.1d: The lines are the sentences the screen prints (R3.3). A verdict line
  starts with its verdict word in capitals; an overall line ends with its
  verdict word in brackets; undeclared lines come just before the overall line.
- AC3.1e: The last logical line is `Fingerprint of the record: <the last
  entry's hash> (<n> lines)`, where the hash is that of the last entry of the
  whole record and `<n>` is the number of entries in the whole record. At 80
  columns it wraps so that the last physical line is the hash and the count.
  An empty record is not printed (see AC3.1g).
- AC3.1f: The command prints `Wrote .papertrail/spool/<id>.txt` (a relative
  path) and exits 0. It overwrites an earlier file for the same session and
  writes nothing to the record.
- AC3.1g: An unknown session, or one with an unsafe id (anything outside
  `A-Z a-z 0-9 _ . -`, starting with a non-alphanumeric, or containing `..`),
  prints an error, exits 1, and writes no file.
- AC3.1h: The file holds no absolute path and no machine name.

### R3.2 On screen and over MCP

**Acceptance criteria**

- AC3.2a: The TEAR OFF REPORT on the screen ends with the same fingerprint
  line, built from the records the page holds. In plain words: no "hash",
  "entry" or "ledger".
- AC3.2b: The MCP server has a fifth tool, `print_session(session_id)`, that
  returns exactly the text the command would write, and writes nothing. An
  unknown or unsafe id returns a one-line `Error: ...` text.
- AC3.2c: For the same record, the file, the MCP text and the on-screen report
  agree on the fingerprint line.

### R3.3 One set of sentences

**Acceptance criteria**

- AC3.3a: `tests/fixtures/sentences.json` lists records and the sentence each
  must print, including every kind of line, every verdict, the NO_STATEMENT
  overall line, undeclared lines and the fingerprint line.
- AC3.3b: A Python test and a TypeScript test both read that file and both
  must reproduce every sentence. Changing a sentence in one language and not
  the other fails a test.

---

## R4 — Two fixes to the printout

### R4.1 The red ring leaves room at every width

On desktop the ring's right edge crossed the last word of its line.

**Acceptance criteria**

- AC4.1a: The ring is a rounded loop that stays close to its box, so the
  corners of the text fit inside it. Its ends still overlap, like a marker.
- AC4.1b: A test takes the ring's real path and the real padding and offsets
  from the stylesheet, for text 8 to 80 em wide and 1 to 4 lines tall, at the
  desktop and the phone settings, and checks that all four corners and the
  middle of each edge of the text lie inside the loop with a margin.
- AC4.1c: The same test fails if the ring is made tighter than that.

### R4.2 The repository link

**Acceptance criteria**

- AC4.2a: "View on GitHub" is shown only when `VITE_REPO_URL` was set at build
  time to an `http://` or `https://` address.
- AC4.2b: When it is not set (or is `#`, empty, or any other kind of address),
  the footer is not rendered at all.
- AC4.2c: The GitHub Pages workflow still sets it, so the published site has
  the link.

---

## R5 — Automated checks

**Acceptance criteria**

- AC5.1a: `.github/workflows/tests.yml` runs on every push and pull request.
- AC5.1b: It runs the Python tests (`python -m pytest tests/ -q`) and the web
  tests (`npx vitest run`) and the web build (`npm run build`) on Windows,
  macOS and Linux, and does not stop the other systems when one fails.
- AC5.1c: It uses the same Python and Node versions the project documents
  (Python 3.11, Node 20) and installs from `requirements.txt` and
  `web/package-lock.json` (`npm ci`).
- AC5.1d: A test in the Python suite reads the workflow file and fails if a
  system or a command goes missing.
- AC5.1e: Nothing in the tests depends on Windows paths, a case-insensitive
  file system, or Windows line endings.

---

## R6 — Encoding

**Acceptance criteria**

- AC6.1a: A test scans every text file in the repository (outside the folders
  that are not ours: `node_modules`, `dist`, `.git`, caches, `.papertrail`) and
  fails if any starts with a byte-order mark.
- AC6.1b: The spool file is checked for the same (AC3.1a).

---

## R7 — What this spec changes in earlier ones

- Core R6.1 (printed line of `cleanup.py`) and R6.2 (the demo story): the
  script now has an ordinary broad pattern instead of two explicit deletions.
  The printed line, the diff and the CONTRADICTED verdict are unchanged.
- Core R4.2f and AC3.4: a stop without a statement still does not advance the
  baseline; it may now also append a NO_STATEMENT verdict (R2.1).
- Printout AC4.11c / AC3.9d (the overall verdict is the last line of the
  report): the last line is now the fingerprint line, and the overall verdict
  is the last line before it.
- Printout AC4.3e (repository link): the link is conditional (R4.2).
- Printout AC8.4a (red marker): the ring is a rounded loop whose ends overlap.
- Printout R5 (MCP tools): five tools, and `verify_statement` takes an optional
  number.
- Printout R3.1 (routes): four routes, the new one being
  `POST /api/verify/{session_id}`.
