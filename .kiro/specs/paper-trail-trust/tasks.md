# Tasks - Paper Trail Trust

Each task ends with a **Check**. Run checks from the project root unless it says
otherwise. No check starts a server, and `python -m papertrail archive` is not
run. Every file is written as UTF-8 without a byte-order mark.

## Task 1 - Setup watch in the record (R1)
**Delivers:** `papertrail/watch.py`, the always-snapshot step in `witness.py`,
`setup_changed` records in `session.py`, the between-turns field, the verifier
guard, `tests/test_watch.py`.
**Check:** `python -m pytest tests/test_watch.py tests/test_witness.py tests/test_session.py tests/test_turns.py tests/test_verifier.py tests/test_ignore.py -q`

## Task 2 - The loud line, printed (R1)
**Delivers:** the sentence in `spool.py` and `entryText.ts`, the `*` rows in the
print file, `print-line--setup` and the report paragraph, new cases in
`tests/fixtures/sentences.json`.
**Check:** `python -m pytest tests/test_spool.py tests/test_mcp_server.py tests/test_watch.py -q`; in `web/`:
`npx vitest run src/__tests__/sentences.test.ts`

## Task 3 - Demo session E (R1.7)
**Delivers:** `_session_e` in `sample/make_demo_ledger.py`, the regenerated
`web/public/demo/ledger.jsonl`, updated counts in the Python and web tests.
**Check:** `python -m pytest tests/test_make_demo_ledger.py tests/test_rolls.py -q`

## Task 4 - EXCEPTIONS ONLY (R2)
**Delivers:** `lib/exceptions.ts`, `ExceptionsKey`, `ExceptionNotes`, the changes
in `App.tsx`, the style for filter notes, `exceptions.test.ts`,
`exceptionsOnly.test.tsx`.
**Check:** in `web/`: `npx vitest run src/__tests__/exceptions.test.ts src/__tests__/exceptionsOnly.test.tsx src/__tests__/a11y.test.tsx`

## Task 5 - Cases (R3)
**Delivers:** `sample/run_cases.py`, the README table between the markers,
`tests/test_run_cases.py`.
**Check:** `python sample/run_cases.py` (exit status 0), then
`python -m pytest tests/test_run_cases.py -q`

## Task 6 - Wording (R4)
**Delivers:** the opening sentence in the README and in `Header.tsx`, the two new
README sections, the spec named under "Built with Kiro".
**Check:** `python -m pytest tests/test_readme.py -q`

## Task 7 - Whole checks (R5)
**Check:** `python -m pytest tests/ -q`; in `web/`: `npx vitest run` and
`npm run build`. Also confirm that `.kiro/hooks` and `papertrail/assets/hooks`
are identical (`tests/test_install_assets.py`).
