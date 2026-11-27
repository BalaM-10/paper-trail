# Tasks — Paper Trail Proof

Each task ends with a **Check**. Run checks from the project root unless it says
otherwise. No check starts a server. Every file is written as UTF-8 without a
byte-order mark. In Windows PowerShell 5, `Set-Content -Encoding utf8` adds one,
so use the file tools, or `[IO.File]::WriteAllText(path, text,
(New-Object Text.UTF8Encoding $false))`.

---

## Task 1 — The honest sample bug (R1)

**Delivers:** `sample/cleanup.py`, `sample/reset.py`, `sample/README.md`, the
generator running the real script, `tests/test_sample.py`.

1. `cleanup.py`: the loop from design section 1. One printed line.
2. `reset.py`: `CACHE_BYTES`, `NOTES_TEXT`, `restore(folder)`, `main()` behind
   `if __name__ == "__main__"`.
3. `README.md`: what the script was meant to do, the pattern that is too broad,
   the printed line, how to run the demo. No "silently".
4. `make_demo_ledger.py`: build session B's project with `restore`, copy the
   real `cleanup.py` in before `on_start`, run it after, record its real output.
5. `tests/test_sample.py`: copies `sample/` to a temporary folder, runs the
   script there with a different working directory, and checks AC1.1a to AC1.1d;
   checks `restore` and that importing `reset` writes nothing (AC1.2); checks
   the README and script for the words "silently", "trick" and "trap".

**Check:** `python -m pytest tests/test_sample.py tests/test_make_demo_ledger.py -q`

---

## Task 2 — NO_STATEMENT in the hook and everything that reads verdicts (R2.1, R2.2)

**Delivers:** `papertrail/outcome.py`, `papertrail/session.py`,
`papertrail/__main__.py`, `papertrail/api.py`, `papertrail/mcp_server.py`, and
their tests.

1. `outcome.py` as in design 2.1, with `tests/test_outcome.py`.
2. `session.on_stop` records the verdict (design 2.2). New cases in
   `tests/test_session.py`: AC2.1a to AC2.1i, including a rejected statement, a
   repeated stop, changes after a promoted statement, and that no record holds
   a file's contents or an absolute path.
3. `__main__._cmd_verify` uses `result_for`; same output format.
   `tests/test_cli.py`: AC2.2a, AC2.2b (a statement older than a NO_STATEMENT
   verdict, and the other way round, and an explicit number).
4. `api.py`: both verify routes use `result_for`; the new route; session ids
   checked with `valid_session_id`. `tests/test_api.py`: AC2.2c, AC2.2e, and the
   route list.
5. `mcp_server.py`: `handle_verify_statement(root, id, n=None)` uses
   `result_for`; `valid_session_id` replaces the local copy.
   `tests/test_mcp_server.py`: AC2.2d.

**Check:** `python -m pytest tests/ -q`

---

## Task 3 — A third demo session (R2.4)

**Delivers:** session C in the generator, the regenerated
`web/public/demo/ledger.jsonl`, updated generator and MCP tests.

1. Generator: `SESSION_C = "demo-session-c"`. The project gets
   `sample/src/main.py` (copied from the real sample). The agent edits it
   (`str_replace`), creates `sample/src/helpers.py` (`fs_write`), and stops with
   no statement.
2. `python sample/make_demo_ledger.py`.
3. Tests: three sessions; the three overall verdicts; session C has no statement
   record; its last record is the NO_STATEMENT verdict with the two changes,
   created first; session B's command output is the real script's.

**Check:** `python -m pytest tests/test_make_demo_ledger.py tests/test_mcp_server.py -q`, and
`python -m papertrail check-chain` against a temporary root holding the new
ledger prints `Chain OK (19 entries)`.

---

## Task 4 — The spool file (R3)

**Delivers:** `papertrail/spool.py`, `python -m papertrail print`, the MCP tool
`print_session`, `tests/fixtures/sentences.json`, `tests/test_spool.py`.

1. `spool.py` as in design 3.2. `entry_text` mirrors `web/src/lib/entryText.ts`
   (including the NO_STATEMENT sentence).
2. `__main__` gets `print <session_id>`.
3. `mcp_server.py` gets `handle_print_session` and the `print_session` tool.
4. `sentences.json` (design 3.3), written by hand so that neither language
   produced its own answers.
5. `tests/test_spool.py`: every case in the fixture; AC3.1a to AC3.1h (no line
   over 80 columns even for a 200-character path, no byte-order mark, line
   numbers match the record, undeclared before overall, last physical line is
   the hash and the count, fingerprint is the last entry's hash and the whole
   record's count, overwrite, unsafe ids, no absolute paths); CLI output and
   exit codes; the MCP text equals the file.

**Check:** `python -m pytest tests/ -q`

---

## Task 5 — The screen (R2.3, R3.2, R4)

**Delivers:** the web changes in design section 4.

1. `entryText.ts`: NO_STATEMENT sentence, `verdictWord`, `fingerprintText`.
2. `Stamp`, `stamps.css`: the NO STATEMENT stamp.
3. `sessionMeta`, `GhostClerk`, `PrintReport`, `PrintLine` (uses `verdictWord`
   through `Stamp`), `App` (passes the fingerprint; `repoUrl` prop).
4. `Footer`: nothing unless the address is `http(s)://`.
5. `UndeclaredCircle`: the new loop path. `stamps.css`: base and phone offsets
   that pass `ring.test.ts`.
6. Tests: `sentences.test.ts` (the shared fixture), `ring.test.ts` (design 4,
   with the negative case), `Footer.test.tsx`, plus cases in `App`,
   `GhostClerk`, `Stamp`, `sessionMeta`, `a11y`, `styles`. The demo is now three
   sessions, so counts and titles in the existing tests move with it.

**Check:** `cd web; npx vitest run; npm run build`

---

## Task 6 — Automated checks and the encoding guard (R5, R6)

**Delivers:** `.github/workflows/tests.yml`, `tests/test_workflow.py`,
`tests/test_encoding.py`.

**Check:** `python -m pytest tests/test_workflow.py tests/test_encoding.py -q`

---

## Task 7 — Everything together

1. `python -m pytest tests/ -q`
2. `cd web; npx vitest run`
3. `cd web; npm run build`
4. Look at the built app in one-shot headless Chrome (no server): the NO
   STATEMENT session finished, the ring on desktop and at 375 px, and the page
   without the footer link. Delete the throwaway files.
5. `python sample/reset.py` so the sample is back in its starting state.
6. Write `.papertrail/statement.json`.

**Check:** the three commands above, all green.
