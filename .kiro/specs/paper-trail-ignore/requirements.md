# Requirements - Paper Trail Ignore

## Scope
Three things went wrong in real use. An honest statement was stamped
CONTRADICTED because a test run left about 50 cache files under `.hypothesis`
and `.pytest_cache` and the witness counted them as the agent's changes (R1).
Some recorded commands print as "[object Object]" (R2). Long roll titles push
the stamp out of view (R3). R4 is housekeeping for this change.

Rules that still hold: no file contents, no absolute path, user name or machine
name in the record; plain words on screen; everything keyboard operable; no
sideways scroll at 375 px; every file written as UTF-8 without a byte-order mark.

---

## R1 - The witness skips throwaway files

**Acceptance criteria**
- AC1.1: The witness skips every file and folder that the project's `.gitignore`
  ignores. The rules read are: blank lines and `#` comments are skipped; `!`
  negation; a leading `/` or a `/` inside the pattern anchors the pattern to the
  project folder; a trailing `/` matches folders only; `*`, `?` and `[...]`
  never match `/`; `**` matches any number of folders; `\#`, `\!` and `\ `
  escape their character; the last matching line wins; a file inside an ignored
  folder stays ignored, as in git. Nested `.gitignore` files are not read (the
  design says why).
- AC1.2: The witness also skips a built-in list of common cache folders and
  files for Python, Node and editors, with or without a `.gitignore`. A line in
  the project's `.gitignore` can bring one of them back with `!`. The folders
  the witness already skipped (`.git`, `.papertrail`, `node_modules`,
  `__pycache__`, `.venv`, `dist`, `build`) are still skipped and cannot be
  brought back.
- AC1.3: The list of skipped paths is never stored. The record holds only the
  rule: each snapshot record carries `"ignore": "gitignore"`, meaning "this
  snapshot follows .gitignore and the built-in list". It holds no pattern and
  no path.
- AC1.4: A statement line about a path the rule skips is UNVERIFIED, as for the
  folders skipped today, whether the agent says the path was created, changed or
  deleted. A line about a path that is not skipped is judged as before. A record
  written before this change (no `ignore` field) is judged as before.
- AC1.5: Skipped files are never an undeclared change.
- AC1.6 (properties, Hypothesis): for any generated rule list and path, (a) the
  matcher gives the same answer when asked twice; (b) a path under an ignored
  folder is ignored whatever the later lines say; (c) a name matched by a plain
  `name` pattern is ignored at every depth; (d) a pattern followed by `!` the
  same pattern leaves the path not ignored (when no folder above it is
  ignored); (e) blank lines and comment lines never change any answer; (f) the
  matcher never raises on any text.
- AC1.7 (the test that reproduces the report): a test run creates about 50 files
  under `.hypothesis` and `.pytest_cache`; the agent creates one real file and
  declares only that file; the overall verdict is SUPPORTED and nothing is
  undeclared. The control: the same run with the cache folder named in no rule
  gives CONTRADICTED with the cache files listed as undeclared.

## R2 - Every recorded command prints as text

**Acceptance criteria**
- AC2.1: The design records the shape found in the ledger. Where the command
  text is longer than 2000 characters the recorder stores
  `{"size": <bytes>, "sha256": <hex>}` instead of the text, so the screen and
  the print file showed "[object Object]" (and the print file a Python dict).
- AC2.2: A command stored as text prints as before: "Agent ran the command: X."
  with X cut at 80 characters.
- AC2.3: A command stored as a size and fingerprint prints
  "Agent ran a long command. The record keeps its size, N bytes, not its text."
  The text was never stored, so it cannot be printed; the sentence says so.
- AC2.4: A command that is missing, empty or any other shape prints
  "Agent ran a command." No tool line can print "[object Object]", a dict or
  "None": a `path` that is not text prints as "a file".
- AC2.5: Python (`papertrail/spool.py`) and TypeScript (`web/src/lib/entryText.ts`)
  print exactly the same sentences. The cases live in
  `tests/fixtures/sentences.json`, which both test suites read.

## R3 - Long roll titles

**Acceptance criteria**
- AC3.1: A roll shows at most three lines of its title, then an ellipsis. A
  shorter title shows in full with no ellipsis.
- AC3.2: The full title stays the accessible name of the roll (it is still the
  text of the button) and is the tooltip of the title.
- AC3.3: The stamp stays inside the roll, visible without scrolling the list,
  however long the title is. A title with no spaces wraps and cannot widen the
  roll.
- AC3.4: At 375 px wide the page does not scroll sideways, and the roll is
  still operated with the keyboard (Tab to it, Enter or Space to open it).

## R4 - Housekeeping

**Acceptance criteria**
- AC4.1: `hello.txt` is removed from the project root and the statement lists
  it under `files_deleted`.
- AC4.2: `python -m pytest tests/ -q`, `npx vitest run` (in `web/`) and
  `npm run build` (in `web/`) pass. No server is started and `python -m
  papertrail archive` is not run.
