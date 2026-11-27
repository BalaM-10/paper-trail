# Tasks - Paper Trail Turns

Each task ends with a **Check**. Run checks from the project root unless it says
otherwise. No check starts a server, and `python -m papertrail archive` is not
run. Every file is written as UTF-8 without a byte-order mark.

## Task 1 - Project folder before punctuation (R4)
**Delivers:** the boundary fix in `papertrail/privacy.py`, new cases and
properties in `tests/test_privacy.py`.
**Check:** `python -m pytest tests/test_privacy.py -q`

## Task 2 - Turn start and the stop baseline (R1)
**Delivers:** `on_turn_start`, the new `on_stop` baseline, `witness.py` dispatch,
the verifier's per-turn tool index, `tests/test_turns.py`.
**Check:** `python -m pytest tests/test_turns.py tests/test_session.py tests/test_cli.py -q`

## Task 3 - Rolls, `list_sessions`, spool (R2)
**Delivers:** `papertrail/rolls.py`, `tests/fixtures/rolls.json`, the new
sentences in `spool.py` and `sentences.json`, one block per roll, `list_sessions`
and `get_entries(turn)`, `tests/test_rolls.py`.
**Check:** `python -m pytest tests/test_rolls.py tests/test_spool.py tests/test_mcp_server.py -q`

## Task 4 - Install, doctor, docs (R5)
**Delivers:** the asset and `.kiro/hooks` files, `doctor` and `init` through
`HOOK_FILES`, the README, the Power's skills, updated tests.
**Check:** `python -m pytest tests/test_install.py tests/test_install_assets.py tests/test_readme.py tests/test_power.py -q`

## Task 5 - The demo record (R5.4)
**Delivers:** `demo-session-d` in `sample/make_demo_ledger.py`, the regenerated
`web/public/demo/ledger.jsonl`, updated generator tests.
**Check:** `python -m pytest tests/test_make_demo_ledger.py -q`

## Task 6 - The screen (R2.6, R2.10, R3)
**Delivers:** `web/src/lib/rolls.ts`, `entryText.ts`, `PrintLine`, `PrintReport`,
`SessionSpool`, `SessionList`, `App`, `buildTotals`, CSS, tests. Then look at the
built page in headless Chrome at 1280 px and 375 px.
**Check:** `cd web; npx vitest run`

## Task 7 - Everything
1. `python -m pytest tests/ -q`; from `web/`: `npx vitest run`, `npm run build`.
2. Write `.papertrail/statement.json` last. Do not run `archive`.

---

## As built

- **Result of the checks:** pytest 680 passed, 1 skipped (the wheel metadata test,
  which needs the `wheel` package); vitest 445 passed; the build is clean. No
  server was started and `archive` was not run.
- **The trigger.** `UserPromptSubmit`, from Kiro's "What's new in 1.0: Hooks" trigger
  table. The hook cannot be tried here (it needs a running Kiro), so the payload
  fields (`session_id`, `cwd`, `hook_event_name`, `prompt`) are the ones the
  documentation and a measured third-party reference give. `witness.py` reads only
  `session_id`, and saves the first payload it sees with the prompt replaced by its
  length, so the real one can be inspected in `.papertrail/payloads/`.
- **Found while writing it.** `ledger.py` roots were matched without their leading
  slash, so on macOS and Linux a project folder came out as `/.` instead of `.`.
  The folder pattern now names a rooted path's leading separator (`privacy.py`).
  This was not visible on Windows, where the earlier tests ran.
- **Unfinished turns.** A prompt that arrives while the latest snapshot is a turn
  start with no stop (an interrupted turn, or a prompt Kiro sends itself) is
  recorded as between turns with `unfinished: true`, and the line says the agent
  may have made some of those changes. Not in the request; added because the
  alternative was to call the agent's own work the person's.
- **Demo.** `demo-session-d` is added (two turns). Sessions A to C have no turn
  records and are one roll each, which also keeps the old shape under test.
  Counts that tests had hard-coded (19 lines) are now computed or updated (34).
- **`sample/` was in its "deleted" state** (from the earlier request to run
  `cleanup.py`), which broke `test_readme` and the sample tests. `python
  sample/reset.py` restored `sample/notes.txt` and `sample/cache/output.bin`.
- **Not done:** the screen's "Check this statement" key is unchanged (it takes the
  session's statement number, which the roll still carries); the record grows by
  one snapshot per turn, which is noted in the design as the cost.