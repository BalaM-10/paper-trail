# Tasks - Paper Trail Clean Record

Each task ends with a **Check**. Run checks from the project root unless it
says otherwise. No check starts a server. Every file is written as UTF-8
without a byte-order mark.

## Task 1 - One module for what is private (R1)

**Delivers:** `papertrail/privacy.py`; `ledger.sanitise` and `_sanitise_data`
using it (keys and the session id too); the export tool using it;
`tests/test_privacy.py` with the Hypothesis properties; the export tests
building their records by hand.
**Check:** `python -m pytest tests/test_privacy.py tests/test_export_build_record.py tests/test_ledger.py tests/test_recorder.py -q`

## Task 2 - Check the statement in the stop hook (R2)

**Delivers:** the verifier call in `session.on_stop`, in its own `try`; tests
in `tests/test_session.py`; updated counts in tests that stop with a statement.
**Check:** `python -m pytest tests/test_session.py tests/test_cli.py tests/test_api.py tests/test_mcp_server.py -q`

## Task 3 - Archive (R3)

**Delivers:** `papertrail/archive.py`, the `archive` subcommand, `tests/test_archive.py`.
**Check:** `python -m pytest tests/test_archive.py -q`

## Task 4 - Say which part of the build (R4)

**Delivers:** `build-record.json` from the export tool, `useEntries` reading it,
`lib/coverage.ts`, the line under the totals, tests.
**Check:** `cd web; npx vitest run`

## Task 5 - README, then everything

1. README: the archive command, what the record never holds, the build roll.
2. `python -m pytest tests/ -q`; from `web/`: `npx vitest run`, `npm run build`.
3. Write `.papertrail/statement.json`.
4. `python -m papertrail archive`, then `python sample/export_build_record.py`,
   and report what each says.

---

## As built

- **Result of the checks:** pytest 587 passed, 1 skipped (the wheel metadata test,
  needs the `wheel` package); vitest 403 passed; the build is clean.
- **Interplay found by the property tests.** Replacing a name by a marker can
  create a path that was not there (`aLicea:\` became `[user]a:\`, which looks like
  a drive). The drive and UNC patterns now refuse to start right after `]`. The
  property tests found this on the first run.
- **A path ends at a space.** `C:\Program Files\x` becomes `[path]/Program Files\x`;
  nothing in that looks like an absolute path, but the folder names after the space
  stay. Stated in the design.
- **`verify` already recorded once.** `verifier.verify` was idempotent on the
  statement's witness line, so part 2 is one call in `on_stop`; no new
  bookkeeping.
- **Export tests.** They write their records by hand, because `ledger.append` now
  cleans exactly what those tests need to find.
- **A new session's stop after `archive`.** The stop hook of the session that runs
  `archive` writes its last records into the new record. That record then holds
  records of a session whose start is in the archive. It is a consequence of
  archiving in the middle of a session, noted in the closing report.