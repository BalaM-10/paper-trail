# Requirements - Paper Trail Trust

## Scope
A record is only as good as the setup that writes it. If an agent can change the
hooks, the statement rule or the MCP settings during a turn, the rest of that
turn's record has to be read with care (R1). A long roll is hard to read when
most lines are fine, so a key keeps only the lines that need a look (R2). Anyone
should be able to see the checks work without a Kiro session (R3). The README and
the page say plainly what the record proves and what it does not (R4).

Rules that still hold: no file contents, no absolute path, user name or machine
name in the record; plain words on screen; everything keyboard operable; no
sideways scroll at 375 px; every file written as UTF-8 without a byte-order mark;
`.kiro/hooks` and `papertrail/assets/hooks` stay identical; no server is started
and `python -m papertrail archive` is not run by any check.

---

## R1 - Setup watch

The *recording setup* is: every file under `.kiro/hooks/`,
`.kiro/steering/statement.md` and `.kiro/settings/mcp.json`.

**Acceptance criteria**
- AC1.1: The witness always snapshots the setup, even when `.gitignore` or the
  built-in ignore list would skip it. Python cache files inside `.kiro/hooks`
  are not part of it.
- AC1.2: When a setup file is created, changed or deleted during a turn, the
  stop hook appends one separate record right after the stop record. It is a
  `witness` record with `event: "setup_changed"`, `files` (sorted, each once),
  the setup part of the difference, and the stop record it is about. No new kind
  of record is added. It is written whether or not the agent declared the change,
  and it does not change the statement's verdict.
- AC1.3: When the setup changes between two turns, the between-turns record
  carries `setup_changed` (the files) and its sentence ends with "The recording
  setup changed: <files>." No loud line is written for it, because the agent did
  not act.
- AC1.4: The loud line reads exactly: "RECORDING SETUP CHANGED DURING THIS TURN:
  <files>. Read this turn's record with care." (files joined with ", "). It is a
  line of its own, in the web page (red, on a bar), in the print-ready spool file
  (between two rows of `*`, at most 80 columns) and in the output of the MCP tool
  `print_session`. It belongs to the roll of the turn it happened in. The page's
  printed report carries it too.
- AC1.5: A claim about a setup path is judged by the witness even when
  `.gitignore` would skip that path (so it is never UNVERIFIED for that reason).
- AC1.6: The record holds the file names only: no contents, no absolute path.
- AC1.7: The demo record has one more session, `demo-session-e`: an honest agent
  edits a recording hook and says so. Its verdict is SUPPORTED, and its roll shows
  the loud line. `web/public/demo/ledger.jsonl` is regenerated from
  `sample/make_demo_ledger.py`.

## R2 - EXCEPTIONS ONLY key

**Acceptance criteria**
- AC2.1: The printer has an EXCEPTIONS ONLY key. It is a real button, so Tab,
  Enter and Space work; `aria-pressed` says whether it is down. It is off at first
  and never disabled.
- AC2.2: When it is down, each roll shows only: claims that are CONTRADICTED or
  UNVERIFIED (and an overall verdict that is not SUPPORTED, NO STATEMENT
  included), changes the agent never mentioned, between-turns lines,
  setup-changed lines, and the line where the paper is torn.
- AC2.3: The roll says how many lines are hidden ("N lines hidden.", "1 line
  hidden.", "No lines hidden."). A roll with nothing left says "Nothing to flag in
  this turn."
- AC2.4: It works on Demo, on "How this was built" and on the live record. Changing
  the key prints the roll again from the top. The printed report ("Tear off
  report") is not shortened.
- AC2.5: No word the page must not use appears (hash, chain, ledger, entry,
  and so on).

## R3 - Test cases anyone can run

**Acceptance criteria**
- AC3.1: `python sample/run_cases.py` plays seven cases, each in its own
  temporary folder, and never touches the project's own `.papertrail` folder or
  `os.environ`: (a) an honest agent, (b) a change it did not declare, (c) a claim
  that did not happen, (d) no statement, (e) a person changes a file between
  turns, (f) the record is edited afterwards, (g) the recording setup changes
  mid-turn.
- AC3.2: For each case it prints the expected result, the actual result and PASS
  or FAIL. The exit status is 0 only if all seven pass.
- AC3.3: `python sample/run_cases.py --write-readme` writes the results as a table
  into `README.md` between `<!-- cases:start -->` and `<!-- cases:end -->`. The
  table holds no date and no path of the machine it ran on.
- AC3.4: A test fails if the README table differs from a fresh run.

## R4 - README and page wording

**Acceptance criteria**
- AC4.1: The README opens (right after the title) and the page opens (right after
  the product name) with: "Git records what changed. Paper Trail records what the
  agent claimed, what actually happened, and whether the two agree."
- AC4.2: The README has a section "What this proves, and what it doesn't" that
  says what it proves (which files were created, changed or deleted in each turn,
  checked against a snapshot taken outside the agent's own log; whether each item
  in the statement matches; whether the record was edited after it was written)
  and what it does not (that the code is correct; anything, if the hooks are
  removed, since no record is not a clean record; protection from someone on the
  same machine who rewrites and recomputes the whole record, unless the final
  fingerprint was kept elsewhere, which is why the printout ends with it).
- AC4.3: The README says plainly that the statement is a structured list of
  files, checked exactly, with no AI judging the result, and that the record keeps
  relative paths, sizes and fingerprints, never file contents or absolute paths.
- AC4.4: The README has a short "How this differs" paragraph: other tools check
  claims against a Git commit range or sign tool-call logs; Paper Trail snapshots
  the folder at every prompt, keeps human changes between replies apart from the
  agent's, and runs inside Kiro through hooks, an MCP server and a power. It names
  no other product and does not claim to be first.
- AC4.5: The README lists this spec under "Built with Kiro", describes the
  setup line and the key, and shows the cases table.

## R5 - Checks

**Acceptance criteria**
- AC5.1: `python -m pytest tests/ -q`, `npx vitest run` (in `web/`) and
  `npm run build` (in `web/`) pass.
