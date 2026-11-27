# Tasks - Paper Trail Install

Each task ends with a **Check**. Run checks from the project root unless it says
otherwise. No check starts a server. Every file is written as UTF-8 without a
byte-order mark. In Windows PowerShell 5, `Set-Content -Encoding utf8` adds one,
so use the file tools, or `[IO.File]::WriteAllText(path, text,
(New-Object Text.UTF8Encoding $false))`.

---

## Task 1 - Assets, hook scripts and the project root (R1.3b-d, AC1.1j)

**Delivers:** `papertrail/assets/` (six hook files, `steering/statement.md`,
`mcp-server.json`), the changed `.kiro/hooks/record.py` and `witness.py` (copies
of the assets), `_get_root` and `_root` falling back to the current folder,
`tests/test_install_assets.py`.

1. Write the assets from the repository's current files; change the two scripts
   as in design 1.2.
2. Copy the two scripts back into `.kiro/hooks/`.
3. Tests: assets equal `.kiro/` copies; the scripts exit 0 and write
   `hook-errors.txt` when `papertrail` cannot be imported (run with an empty
   `PYTHONPATH` from a folder without the package); they still record in this
   repository.
**Check:** `python -m pytest tests/test_install_assets.py tests/test_session.py tests/test_cli.py -q`

## Task 2 - `init` and `doctor` (R1.1, R1.2)

**Delivers:** `papertrail/install.py`, the two subcommands in `__main__.py`,
`tests/test_install.py`, additions to `tests/test_cli.py`.

1. `install.py` as in design 1.3 and 1.4.
2. `__main__`: `init <folder> [--force]`, `doctor [folder]`, usage text lists both.
3. Tests for every acceptance criterion in R1.1 and R1.2, the Hypothesis
   property for `mcp.json`, and an end-to-end run through the CLI.
**Check:** `python -m pytest tests/test_install.py tests/test_cli.py -q`

## Task 3 - pip and the Power (R1.3a, R1.4)

**Delivers:** `pyproject.toml`, `power/paper-trail/` (manifest, `mcp.json`, two
skills), `tests/test_pyproject.py`, `tests/test_power.py`.
**Check:** `python -m pytest tests/test_pyproject.py tests/test_power.py -q`

## Task 4 - The export tool (R2.1)

**Delivers:** `sample/export_build_record.py`, `tests/test_export_build_record.py`.
Then run it once against this repository's record and report what it says.
**Check:** `python -m pytest tests/test_export_build_record.py -q`

## Task 5 - The ring (R3)

**Delivers:** the CSS change, `ring.test.ts` extended. First measure the real
page in headless Chrome (the cause was found this way) and keep the numbers.
**Check:** `cd web; npx vitest run src/__tests__/ring.test.ts`

## Task 6 - The second roll and long sessions (R2.2, R2.3)

**Delivers:** `useEntries` with `view`, `RecordSwitch`, `buildTotals`, `App`
and `GhostClerk` changes, `useReplay.skipToEnd`, the SKIP TO END key,
`React.memo` on `PrintLine`, a generator for test records, and the web tests
from design 6. Existing tests that count keys or sessions are updated.
**Check:** `cd web; npx vitest run`

## Task 7 - README (R4)

**Delivers:** the rewritten top of `README.md`, a Power and build-record
section, `tests/test_readme.py`.
**Check:** `python -m pytest tests/test_readme.py -q`

## Task 8 - Everything, and the real browser

1. `python -m pytest tests/ -q`, then from `web/`: `npx vitest run` and
   `npm run build`.
2. Headless Chrome on the built page: the rings at 1280 px and 375 px (rectangles
   from the page, plus a picture); the switch; a 2,000-line record with SKIP TO
   END timed; no sideways scroll at 375 px. Temporary files are deleted.
3. Check no file in the repository starts with a byte-order mark
   (`tests/test_encoding.py` does this).
4. `python sample/reset.py`, then write `.papertrail/statement.json` last.

---

## As built

Where the work differs from, or adds to, what is written above.

- **Ring.** The ring was found by measuring the real page in headless Chrome
  (task 5): the page rule `svg, img { max-width: 100% }` capped the ring at the
  button's width. The path was redrawn with smaller corners, the vertical margin
  is 1 em and the overhang 0.8 em (design section 4 has the numbers). The test
  uses a winding-number check, not even-odd, because the loop's end overlaps its
  start; it models the cap, so it fails if the cap comes back.
- **Wheel tests.** Python 3.11's bundled setuptools (65.5) cannot build a wheel
  without the `wheel` package. `tests/test_pyproject.py` then builds the package
  with `setuptools build_py` instead (same package data), and only the metadata
  test is skipped. All of it passes in a fresh virtual environment with
  `wheel` and `setuptools>=68`.
- **Long sessions.** `React.memo` on `PrintLine` and `PrintReport` was enough. In
  headless Chrome, driven over the DevTools protocol (the browser's own virtual
  clock gave a wrong 1,200 ms), a 2,000-line session took 66 to 182 ms for SKIP TO
  END plus two frames, 20 to 35 ms to feed one line, and 24 to 62 ms to pick a
  line, at 1280 px and 375 px. No windowing, no `content-visibility`. A test
  removes `memo` and fails, so the count test is real.
- **The export tool, run on this repository's real record.** It refuses: 57
  findings, among them drive paths in shell commands (`C:\Program Files\...`), the
  working folder in three `error` records that kept the start of the hook's raw
  input, and the user name inside those. `build-ledger.jsonl` is therefore not
  published, and the page says so. The recorder was not changed (out of scope,
  and the record is append-only). Two causes are worth a later spec: `sanitise`
  removes only the project folder and the home folder, and it does not see them
  inside text that is itself JSON (doubled backslashes).
- **Root of the project.** `api.py` falls back to the current folder too, like
  the CLI and the MCP server, so `serve` also works in an installed project.