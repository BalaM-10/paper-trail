# Requirements - Paper Trail Install

## Scope

Four things that let someone else use Paper Trail and see how it was made: a
one-command install into another Kiro project, a second roll that replays the
record of building Paper Trail itself, a fix for the red ring, and a README for
a first-time visitor.

Rules that still hold everywhere: no file contents and no absolute paths in the
record or in any file written from it, plain words on screen, everything
keyboard operable, no sideways scroll at 375 px. Every file written for this
spec is UTF-8 without a byte-order mark.

Where this spec conflicts with an earlier one, this one wins. The conflicts are
listed in R5.

---

## R1 - Install into another project

### R1.1 `python -m papertrail init <project_folder> [--force]`

It sets up Paper Trail in an existing project folder:

1. Copies the four hook files and the two hook scripts into
   `<project>/.kiro/hooks/`.
2. Copies the statement steering rule into `<project>/.kiro/steering/`.
3. Adds a `paper-trail` server to `<project>/.kiro/settings/mcp.json`. Other
   servers and other keys in that file are kept.
4. Adds `.papertrail/` to `<project>/.gitignore`.

**Acceptance criteria**

- AC1.1a: After `init` on an empty folder, these exist: `.kiro/hooks/` with
  `record-post-tool-use.json`, `record-file-delete.json`,
  `witness-session-start.json`, `witness-stop.json`, `record.py`, `witness.py`;
  `.kiro/steering/statement.md`; `.kiro/settings/mcp.json` with a
  `paper-trail` server; `.gitignore` with a `.papertrail/` line.
- AC1.1b: A file that already exists and is identical (ignoring line endings)
  is left as it is and reported as already in place.
- AC1.1c: A file that exists and differs is never overwritten without
  `--force`. It is reported as left alone, with the way to replace it, and the
  command exits with status 1. With `--force` it is replaced.
- AC1.1d: Other servers in `mcp.json` and any other top-level keys survive,
  with their values unchanged. If `mcp.json` is not valid JSON, it is not
  touched, the problem is reported, and the command exits with status 1. If it
  already has a `paper-trail` server that differs, the rule in AC1.1c applies.
- AC1.1e: `.gitignore` gets the line only if no line already means the same
  (`.papertrail`, `.papertrail/`, `/.papertrail`, `/.papertrail/`). Existing
  lines, their order and their line endings are kept. A missing file is created.
- AC1.1f: Running `init` twice in a row changes nothing the second time: no
  file is written, every step is reported as already in place, exit status 0.
  This holds for each of the cases above, including `--force`.
- AC1.1g: The output is plain words, one line per step, and ends with what to
  do next. It never prints the contents of a file.
- AC1.1h: A folder that does not exist, or a path that is a file, is an error:
  nothing is created and the exit status is 1. No folder argument prints the
  usage and exits with status 1.
- AC1.1i: Every file written is UTF-8 without a byte-order mark, with `\n` line
  endings in files that `init` creates. A `mcp.json` that starts with a
  byte-order mark is read correctly and written back without one.
- AC1.1j: The copied files are the ones in the package (`papertrail/assets/`).
  A test fails if `.kiro/hooks/*` or `.kiro/steering/statement.md` in this
  repository drift from them.

### R1.2 `python -m papertrail doctor [project_folder]`

It checks an installed project (default: the current folder) and says what is
missing.

**Acceptance criteria**

- AC1.2a: It checks and reports, one line each: the six hook files, the
  statement rule, the `paper-trail` server in `mcp.json` (present, not switched
  off), the `.gitignore` line, that the `python` command can import
  `papertrail`, and that it can import `mcp`.
- AC1.2b: Each line starts with OK, MISSING or WARN. A file that is present but
  differs from the packaged one is WARN. A server that is switched off is WARN.
  Anything absent is MISSING.
- AC1.2c: The exit status is 1 if anything is MISSING, otherwise 0. Warnings do
  not fail it.
- AC1.2d: For each missing item the output says how to fix it: `init` for
  files, the pip command for the two imports.
- AC1.2e: It reads the project and runs `python -c "import ..."`. It writes
  nothing.
- AC1.2f: If the hooks have written `.papertrail/hook-errors.txt`, doctor
  shows its first line as a WARN.
- AC1.2g: On a project that `init` just set up, with Paper Trail installed, it
  prints no MISSING line.

### R1.3 Installable with pip

**Acceptance criteria**

- AC1.3a: `pyproject.toml` makes `pip install .` work. The wheel contains the
  `papertrail` package and `papertrail/assets/**`. It declares a `papertrail`
  command that runs `papertrail.__main__:main`, and Python 3.11 or later.
- AC1.3b: The hook scripts need only the standard library to start. If the
  `papertrail` package cannot be imported they write one line to
  `.papertrail/hook-errors.txt`, exit with status 0 and disturb nothing.
- AC1.3c: The hook scripts use a `papertrail` folder next to `.kiro` if there
  is one (this repository), otherwise the installed package. From a different
  working folder, with only the installed package on the path, `record.py`
  writes the project's ledger.
- AC1.3d: Without `PAPERTRAIL_ROOT`, the CLI and the MCP server take the
  current folder as the project, not the folder the package lives in.
- AC1.3e: No dependency is added for the hooks. The base install needs only
  `mcp`; the local API and the tests are extras.

### R1.4 A Power, if one can carry this

**Acceptance criteria**

- AC1.4a: The design records, from Kiro's documentation, what a Power can
  contain, and says whether it can package the hooks, the steering rule and the
  MCP server.
- AC1.4b: If it can package part of this, `power/paper-trail/` holds that part,
  with `plugin.json`, `mcp.json` and skills, and a test checks that it follows
  the documented layout. The README says what it covers and what `init` still
  has to do.

---

## R2 - The roll "How Paper Trail was built"

### R2.1 `sample/export_build_record.py`

**Acceptance criteria**

- AC2.1a: It copies `.papertrail/ledger.jsonl` to
  `web/public/demo/build-ledger.jsonl` byte for byte. After the copy the two
  files have the same SHA-256 and the copy passes the chain check.
- AC2.1b: Before copying it reads every record and refuses if any text in it
  (keys and values, at any depth, and the raw line) contains: a drive path such
  as `C:\` or `C:/`, a UNC path, a path under `/Users/`, `/home/`, `/root/`,
  `/var/`, `/tmp/`, `/private/`, `/Volumes/`, the current user name, or the
  machine name (compared without regard to case).
- AC2.1c: When it refuses, nothing is written. It prints a list: for each
  finding the line number, the kind of record, which field, what kind of thing
  was found and a shortened piece of the text. It ends with a count and exits
  with status 1.
- AC2.1d: It also refuses, writing nothing, when the source is missing, empty,
  not valid records, or its chain check fails. Each refusal says which.
- AC2.1e: It never changes the source. Running it twice on a clean ledger
  gives the same output file.
- AC2.1f: `https://...` and `file:///` text is not mistaken for a path.

### R2.2 The switch

**Acceptance criteria**

- AC2.2a: Above the rolls there is a switch with two keys, "Demo" and "How this
  was built". It is a group with a name; each key says which one is chosen
  (`aria-pressed`) and works with Tab, Enter and Space.
- AC2.2b: "Demo" is what the page showed before. "How this was built" loads
  `./demo/build-ledger.jsonl`, never calls the API and never polls.
- AC2.2c: In the second view the rolls are the build record's sessions, each
  with its real verdict stamp. Nothing is invented: a session with no checked
  statement shows no stamp.
- AC2.2d: Under the switch, in plain words, are the totals: sessions, lines,
  statements checked, how many matched the evidence, how many sessions changed
  files and said nothing, and how many statements were written but never
  checked. Singular and plural are correct, and zero counts are left out except
  "0 statements checked".
- AC2.2e: If the file is missing or is not a record, the page says in plain
  words that the build record has not been published yet, and shows no error
  dialog. The clerk says so too.
- AC2.2f: Changing the switch starts from a clean state: no roll picked, no
  line picked for tampering, replay at the top, tampering undone.
- AC2.2g: The page makes no banned word visible: hash, chain, ledger, entry,
  entries, seq, JSONL, SHA-256, canonical, hex.

### R2.3 Long sessions

**Acceptance criteria**

- AC2.3a: A SKIP TO END key sits with PLAY and FEED. It prints every remaining
  line at once and leaves the replay finished. It is disabled when there is
  nothing to print or the end is reached. Its accessible name contains its
  printed label.
- AC2.3b: With 2,000 lines on one roll, picking one line for tampering
  redraws that line and the previous pick, not the other 1,998. Feeding one
  line redraws the line just printed and the one that comes next.
- AC2.3c: With 2,000 lines, SKIP TO END shows every line, the paper status
  still reads as intact, and the page stays usable: no frozen state in the
  browser check (R2.3d).
- AC2.3d: In headless Chrome with a 2,000-line record, SKIP TO END followed by
  the next paint takes under one second on the development machine, and the
  page does not scroll sideways at 375 px.
- AC2.3e: Jumping to a line (the red circle) still works for any line.

---

## R3 - The red ring

**Acceptance criteria**

- AC3.1: On the longest line, the ring's right edge is clear of the last word
  at every width from 8 em to 60 em on desktop and to 20 em on a phone. The
  cause was the page rule `svg { max-width: 100% }`, which shrank the ring to the
  button's width. The ring now sets `max-width: none`.
- AC3.2: Two rings on neighbouring lines do not touch or overlap, for any
  mix of 1 to 4 lines each, on desktop and on phone, with a gap of at least a
  quarter of an em between the two strokes.
- AC3.3: The ring keeps its hand-drawn look: an uneven rounded loop whose end
  overshoots its start, drawn with the marker filter.
- AC3.4: `ring.test.ts` fails if the page's `svg` rule caps the ring again, and
  fails if two rings are too close. It reads the numbers from the stylesheets.
- AC3.5: In headless Chrome, with the real page, the ring's right edge is at
  least half an em beyond the last word on every ring, and no ring touches the
  next one, at 1280 px and at 375 px.

---

## R4 - README

**Acceptance criteria**

- AC4.1: The top of `README.md` opens with the question "Did the agent do what
  it said?", then a 30-second explanation in plain words (record, witness,
  statement, verdict, printout), then the one-command install, then the three
  verdicts plus NO STATEMENT with what each means.
- AC4.2: A "Built with Kiro" section names what was actually used, each
  matched by a file in the repository: the four specs, the four hook files,
  the four steering files, the MCP server and its tools, and the
  property-based tests (Hypothesis) with the files that hold them.
- AC4.3: The install command in the README is the one `init` takes. The
  commands for printing and for the build record are present and match the CLI.
- AC4.4: A test checks that every file path and every `python -m papertrail`
  subcommand the README names exists.
- AC4.5: Windows is the first platform described. The license (MIT) is named.

---

## R5 - Conflicts with earlier specs

- `__main__._get_root` and `mcp_server._root` fall back to the current folder
  instead of the package's parent folder (R1.3d). From this repository's root
  nothing changes.
- The hook scripts no longer put the project folder on the path unless it has
  a `papertrail` folder (R1.3c). The "never raise" rule now also covers a
  failed import.
- The step 5 of the earlier README demo (verify) is kept; the README's top is
  rewritten (R4).
- `Source` in the web app gains two values for the second view.
