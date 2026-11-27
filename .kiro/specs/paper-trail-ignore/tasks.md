# Tasks - Paper Trail Ignore

Each task ends with a **Check**. Run checks from the project root unless it says
otherwise. No check starts a server, and `python -m papertrail archive` is not
run. Every file is written as UTF-8 without a byte-order mark.

## Task 1 - The matcher (R1)
**Delivers:** `papertrail/ignore.py`, `tests/test_ignore.py` with cases and
Hypothesis properties.
**Check:** `python -m pytest tests/test_ignore.py -q`

## Task 2 - Snapshot, records and verifier (R1)
**Delivers:** `witness.snapshot` uses the matcher; `session.py` adds
`"ignore": "gitignore"` to snapshot records; `verifier.py` gives UNVERIFIED for
skipped paths; the reproduction test and its control.
**Check:** `python -m pytest tests/test_ignore.py tests/test_witness.py tests/test_session.py tests/test_verifier.py tests/test_turns.py -q`

## Task 3 - Command text in both languages (R2)
**Delivers:** `command_sentence` in `papertrail/spool.py`, `commandSentence` in
`web/src/lib/entryText.ts`, new cases in `tests/fixtures/sentences.json`.
**Check:** `python -m pytest tests/test_spool.py -q`, then in `web/`:
`npx vitest run src/__tests__/sentences.test.ts src/__tests__/entryText.test.ts`

## Task 4 - Roll titles (R3)
**Delivers:** the tooltip in `SessionSpool.tsx`, the clamp in `paper.css`,
`web/src/__tests__/rollTitle.test.tsx`, a style test.
**Check:** in `web/`: `npx vitest run src/__tests__/rollTitle.test.tsx src/__tests__/styles.test.ts`

## Task 5 - Whole checks and clean-up (R4)
**Delivers:** all three suites green; `hello.txt` removed; `statement.json`
lists it under `files_deleted`.
**Check:** `python -m pytest tests/ -q`; in `web/`: `npx vitest run` and
`npm run build`.
