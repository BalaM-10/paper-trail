# Requirements - Paper Trail Clean Record

## Scope

The record must be fit to publish. This spec closes the leak the export tool
found (R1), makes the stop hook check statements by itself (R2), lets a record
be put away so the next one starts clean (R3), and makes the page honest when
the published record covers only part of the build (R4).

Rules that still hold: no file contents in the record, plain words on screen,
everything keyboard operable, no sideways scroll at 375 px, every file written
as UTF-8 without a byte-order mark.

---

## R1 - The record never holds an absolute path, a user name or a machine name

**Acceptance criteria**

- AC1.1: One module, `papertrail/privacy.py`, defines what these are. The
  recorder cleans with it (`scrub`) and `sample/export_build_record.py` looks
  with it (`find`). Neither has its own patterns.
- AC1.2: `ledger.append` is the only place a record is written, and it cleans
  every string in `data`, every key in `data`, and the session id.
- AC1.3: The project folder becomes `.` and the home folder `~`; the rest of
  the path is kept. Recognised: backslash, forward slash, doubled and
  quadrupled backslashes (text inside JSON text), any letter case, and the
  folder inside a `file:///` address.
- AC1.4: Any other absolute path keeps only its last part behind the marker
  `[path]`, as `[path]/<last part>`. Recognised: drive paths (`C:\`, `C:/`),
  UNC paths (`\\server\share`, and the same with doubled backslashes),
  `file:///` addresses (`file:///[path]/<last part>`), and POSIX paths that
  start in `/Users`, `/home`, `/root`, `/var`, `/tmp`, `/private`, `/Volumes`,
  `/opt`, `/etc`, `/usr`, `/mnt`, `/srv`, `/media`, `/Library`,
  `/Applications`, `/proc` or `/dev`. A path ends at white space, a quote, or
  one of `< > | ` , ; ) ] }`. A full stop that ends a sentence is kept out of
  the last part.
- AC1.5: The user name becomes `[user]` and the machine name `[machine]`, in
  any letter case, anywhere in a string, including the Windows short form made
  from the name (`NAME~1`, `NAME~12`). The names are those of the machine the
  recorder runs on, three letters or longer.
- AC1.6: Text that holds none of these is stored unchanged. `file:///./x`,
  `https://...`, `a:b`, `12:30`, `src/Users/x` and the markers themselves are
  left alone.
- AC1.7: Cleaning twice gives the same as cleaning once, and whatever `scrub`
  returns passes `find` with no finding. This holds when the user name is a
  word that is also a marker (`user`, `path`).
- AC1.8: Hypothesis property tests: for generated text containing the things
  above in any mix (paths in every style, names in any case, short names,
  file addresses, the project and home folders, with quotes, escapes and
  punctuation around them), the stored entry passes the scan, the chain still
  checks, and no user or machine name is left. For generated text without
  them, the stored entry equals the input.
- AC1.9: An `error` record made from raw hook input, with a working folder and
  a user name in it, passes the scan.
- AC1.10: The export tool's findings, labels and messages keep their meaning.
  It now also finds the extra folders in AC1.4.

## R2 - Statements are checked when they are promoted

**Acceptance criteria**

- AC2.1: When the stop hook promotes a statement, it then runs the verifier on
  it and records the per-claim verdicts and the overall verdict, in the same
  hook run.
- AC2.2: Running `python -m papertrail verify <id>` afterwards, or calling the
  API or the MCP tool, adds nothing to the record: the same verdicts are
  returned from what is stored.
- AC2.3: Several statements in one session each get their own verdicts, once.
- AC2.4: A statement the hook rejects is not checked. A session with changes
  and no statement still gets NO_STATEMENT, as before.
- AC2.5: If the check fails for any reason, the hook still exits 0, the
  statement is still promoted, and an `error` record says what failed. It
  never raises.
- AC2.6: The stop hook with a promoted statement and 20 changed files takes
  under one second.

## R3 - `python -m papertrail archive`

**Acceptance criteria**

- AC3.1: It moves `.papertrail/ledger.jsonl` to
  `.papertrail/archive/ledger-<UTC timestamp>.jsonl` (`YYYYMMDDTHHMMSSZ`). The
  moved file is byte for byte the old record. Nothing is deleted or rewritten.
- AC3.2: It leaves no `ledger.jsonl`. The next record written starts a new
  record: line 1, with a previous fingerprint of zeros.
- AC3.3: It refuses, and moves nothing, if the record's fingerprints do not
  check, if it cannot be read, or if there is no record, and says which.
  Exit status 1.
- AC3.4: Two archives in the same second do not overwrite each other.
- AC3.5: It says in plain words what it did: how many lines, where the record
  went, its fingerprint, and that the next record starts new. Exit status 0.
- AC3.6: It holds the record's write lock while it moves the file, so a hook
  cannot write into the file mid-move.
- AC3.7: It uses the folder in `PAPERTRAIL_ROOT`, else the current folder.

## R4 - Honest about part of the build

**Acceptance criteria**

- AC4.1: The export tool writes `build-record.json` next to the published
  record, with `{"partial": true|false}`. `partial` is true when
  `.papertrail/archive/` holds earlier records. It is written only when the
  record is published.
- AC4.2: In the "How this was built" view the page says in plain words which
  dates the record covers, using the first and the last line:
  "This record runs from 1 March 2026 to 3 March 2026." (one day: "on 1 March
  2026"). Dates are in UTC.
- AC4.3: When `partial` is true it says: "This record covers only part of the
  build: from ... to .... Earlier work was archived and is not shown here."
- AC4.4: If `build-record.json` is missing or not valid, the page shows the
  dates sentence only and shows no error.
- AC4.5: The words stay plain (no banned word), the text wraps at 375 px with
  no sideways scroll, and the demo view shows none of this.

## R5 - Conflicts with earlier specs

- `ledger.sanitise` takes an optional `terms` argument and cleans more than the
  two folders.
- Statement promotion now appends verdict records; tests that counted the
  records after a stop are updated.
