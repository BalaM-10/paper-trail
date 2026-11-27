# Design - Paper Trail Install

## Overview

```
papertrail/assets/            what init copies (one source of truth)
  hooks/*.json, record.py, witness.py
  steering/statement.md
  mcp-server.json             the "paper-trail" entry for mcp.json
papertrail/install.py         init() and doctor(); standard library only
papertrail/__main__.py        init, doctor subcommands
pyproject.toml                pip install, console script, package data
power/paper-trail/            the part a Power can carry (section 4)
sample/export_build_record.py copy the real record, after scanning it
web/                          switch, totals, SKIP TO END, ring fix
```

## 1. Install

### 1.1 One source of truth

The files `init` copies live in `papertrail/assets/` so that a wheel carries
them. This repository's own `.kiro/hooks/*` and `.kiro/steering/statement.md`
are copies of those files. `tests/test_install_assets.py` compares them byte
for byte (line endings ignored) so they cannot drift. `capture.py` is a
development helper and is not shipped.

### 1.2 Hook scripts

Both scripts now start like this, with the standard library only:

```python
here = Path(__file__).resolve()
project = here.parents[2]                      # <project>/.kiro/hooks/x.py
root = Path(os.environ.get("PAPERTRAIL_ROOT") or project)
if (project / "papertrail").is_dir():          # this repository
    sys.path.insert(0, str(project))
try:
    from papertrail import ledger
    from papertrail.recorder import record
except Exception as exc:                       # not installed, wrong Python
    note_and_exit(root, "record.py", exc)      # one line, exit 0
```

`note_and_exit` appends `record.py: <exception text>` to
`.papertrail/hook-errors.txt`, ignoring any error of its own, then exits 0. The
text is the exception message only: no paths are added by the script. The rest of
each script is unchanged.

Hook commands stay `python .kiro/hooks/record.py`. Kiro runs them from the
project folder, as it does for this repository's own hooks.

### 1.3 `install.py`

```python
@dataclass(frozen=True)
class Step:
    status: str   # created | replaced | unchanged | kept | error
    target: str   # path relative to the project, forward slashes
    note: str = ""

def init(project: Path, force: bool = False) -> list[Step]
def describe(step: Step) -> str            # one plain sentence
def doctor(project: Path, probe=probe_python) -> list[Check]
```

`init` does the file copies through one helper, `_place(dest, wanted, force)`:

| dest | same text (after `\r\n` to `\n`) | status |
|------|------|------|
| missing | | created (parent folders made) |
| present | yes | unchanged, nothing written |
| present | no, no force | kept |
| present | no, force | replaced |

Files are written as bytes from a string with `\n` endings: UTF-8, no byte-order
mark. A file the project already has with `\r\n` and the same text counts as
unchanged, so a Windows checkout with autocrlf is not touched.

`mcp.json`: read with `utf-8-sig`. A missing file starts as
`{"mcpServers": {}}`. Invalid JSON, or a top-level value that is not an object,
or `mcpServers` that is not an object, gives an `error` step and the file is not
written. The entry from `assets/mcp-server.json` is compared with
`mcpServers["paper-trail"]` using the parsed values (key order does not matter):
same, then `unchanged`; absent, then added; different, then `kept` or, with
`--force`, replaced. The file is rewritten only when the entry changes, with
`json.dumps(indent=2)` and a final newline. Keys and servers already there keep
their order and values; the file's indentation may change, which the README
says.

`.gitignore`: a line counts as the entry if, stripped, it is one of
`.papertrail`, `.papertrail/`, `/.papertrail`, `/.papertrail/`. If none is, the
text `.papertrail/` is appended, after a newline if the file does not end with
one, using the file's own line ending (`\r\n` if it already has one, else
`\n`). A missing file is created.

`init` rejects a path that is not an existing folder before doing anything.

CLI exit status: 0 when every step is created, replaced or unchanged; 1 when any
step is kept or error, or the folder is bad. Messages, in plain words:

```
Created .kiro/hooks/record.py
Already in place: .kiro/hooks/witness.py
Left alone: .kiro/steering/statement.md is different from Paper Trail's. Run again with --force to replace it.
Added the paper-trail server to .kiro/settings/mcp.json
Added .papertrail/ to .gitignore

Next: run  python -m papertrail doctor <folder>  to check the setup.
```

### 1.4 `doctor`

`doctor(project, probe)` returns `Check(level, label, fix)` with level `ok`,
`missing` or `warn`. It reads the same assets as `init`:

1. For each of the six hook files and the steering file: absent, then
   missing (fix: `python -m papertrail init <folder>`); different text, then
   warn; same, then ok.
2. `mcp.json`: absent or unreadable or no `paper-trail` entry, then missing;
   `disabled: true`, then warn; entry differs from the packaged one, then warn.
3. `.gitignore`: no matching line, then missing.
4. `probe(project, "papertrail")` and `probe(project, "mcp")`. The probe runs
   `[shutil.which("python"), "-c", "import <module>"]` with the project as the
   working folder and a 30 second limit. No `python` on the path, a non-zero
   exit or a timeout is missing (fix: the pip command from the README).
   Tests pass in a fake probe, so no test depends on the machine.
5. `.papertrail/hook-errors.txt` present: warn with its first line (cut to
   100 characters).

It writes nothing. Exit status 1 if any check is missing.

### 1.5 Root of the project

`__main__._get_root` and `mcp_server._root` return `PAPERTRAIL_ROOT` if set,
otherwise `Path.cwd()`. This replaces "the package's parent folder", which is
`site-packages` once the package is installed. Kiro starts a workspace MCP
server in the workspace folder; if a setup starts it elsewhere, setting
`PAPERTRAIL_ROOT` in the server's `env` fixes it. `init` does not write an
absolute path into `mcp.json`.

### 1.6 `pyproject.toml`

```toml
[build-system]   requires = ["setuptools>=68"]  build-backend = "setuptools.build_meta"
[project]        name = "paper-trail", version = "0.1.0", requires-python = ">=3.11"
                 license = { text = "MIT" }, dependencies = ["mcp>=2,<3"]
[project.optional-dependencies]
                 api = ["fastapi", "uvicorn[standard]"]
                 dev = ["pytest", "hypothesis", "httpx", "fastapi", "uvicorn[standard]"]
[project.scripts] papertrail = "papertrail.__main__:main"
[tool.setuptools]              packages = ["papertrail"]
[tool.setuptools.package-data] papertrail = ["assets/*.json", "assets/hooks/*", "assets/steering/*"]
```

`requirements.txt` stays for CI. `tests/test_pyproject.py` parses the file with
`tomllib`; a second test copies `pyproject.toml`, `README.md`, `LICENSE` and the
package into a temporary folder, builds a wheel there with
`pip wheel --no-deps --no-build-isolation`, lists it, unpacks it into a
temporary "site" folder, runs `init` into a project and then runs the project's
`record.py` from a third folder with only the "site" folder on `PYTHONPATH`. The
project's ledger must get a record. That test is skipped only if `setuptools`
cannot be imported.

## 2. Can a Power carry this?

Source: Kiro's documentation, "Powers" and "Create powers" (checked while
writing this spec).

- A power is a directory with a required `plugin.json` (name, version,
  description, author, keywords) and two optional parts: `skills/<name>/SKILL.md`
  (with `references/` and `scripts/`) and `mcp.json` (MCP servers).
- It activates by keyword: Kiro loads the power's context and tools when the
  conversation mentions one of its keywords, and unloads it afterwards.
- Hooks and steering are not components of a power. Steering is described
  separately as always/auto/fileMatch/manual project context.

So:

| Part | Can a power carry it? | Why |
|------|----------------------|-----|
| MCP server | Yes (`mcp.json`) | listed component |
| Instructions for the agent | As a skill | listed component, loads on keyword |
| Four hook files, two scripts | **No** | a power has no hooks component, and a hook must run on every session, not when a keyword is mentioned |
| Statement steering rule | **No, not equivalently** | the rule must apply to every reply that changes a file; a skill loads only on keywords, so the agent could skip it exactly when it matters |

`power/paper-trail/` therefore holds `plugin.json`, `mcp.json` (the same server)
and two skills: `install` (run `init` and `doctor` in the user's project) and
`check-my-work` (use the MCP tools to read and verify a session). The README
says that the power is a convenience for the server and the instructions, and
that `python -m papertrail init` is still what puts the hooks and the rule in a
project. The power is not a way to skip `init`.

`tests/test_power.py` checks the layout against the documentation: kebab-case
name, semantic version, description, author name, keywords, `mcp.json` with a
`paper-trail` stdio server using `python -m papertrail.mcp_server`, and each
skill's front matter name equals its folder name.

## 3. The build record

### 3.1 `sample/export_build_record.py`

```python
@dataclass(frozen=True)
class Finding: line: int; seq: object; kind: str; field: str; what: str; text: str
def identity_terms() -> list[str]        # user name, machine name (lower case, >= 3 chars)
def scan(lines: list[str], terms) -> list[Finding]
def export(source: Path, dest: Path, terms=None) -> tuple[bool, list[str]]
```

`scan` parses each line, walks every key and string value, and reports:

- drive path: `(?<![A-Za-z])[A-Za-z]:[\\/]` (so `https://` and `file:///` are
  not matches, but `file:///C:/x` is, through the `C:/` part);
- UNC path: `\\\\server\share` at the start of a word;
- POSIX home-like path: `(^|[\s"'=(:])/(Users|home|root|var|tmp|private|Volumes)/`;
- each identity term, case-insensitive, as a substring.

It also searches the raw line for identity terms, which covers terms inside
escaped text. A finding keeps the first 40 characters around the match; matches
with the same line, field and kind are reported once.

`export` refuses in this order: source missing or empty; a line that is not a
record (not JSON, or missing `seq`, `hash`, `prev_hash`, `session_id`, `kind`,
`data`); the chain check from `papertrail.ledger.verify_chain`; the scan.
Only then does it copy the bytes (`shutil.copyfile` to a temporary name in the
destination folder, then `os.replace`), and compare the SHA-256 of both files.
Exit status 0 or 1. The destination is never created on refusal and an
existing destination is left as it was.

The command line takes `--source` and `--dest` (defaults: the repository's
`.papertrail/ledger.jsonl` and `web/public/demo/build-ledger.jsonl`).

**Known outcome today.** The recorder keeps command text as typed, so a
command that names a drive path is stored with it, and `error` records keep
the start of the hook's raw input. `sanitise` removes only the project folder
and the user's home folder, and it does not see the doubled backslashes inside
a JSON string that is itself stored as text. The scan will therefore refuse
this repository's current record. The tool does what it is for: it says which
lines. This spec does not change the recorder, and the record is append-only,
so the web view is built and tested against generated records, and the file
`build-ledger.jsonl` is published when a clean record exists.

### 3.2 Web

New and changed pieces:

- `useEntries(pollMs, view)`: `view` is `"demo"` or `"build"`. For `"build"` it
  fetches `./demo/build-ledger.jsonl`, with no API call and no polling. A
  failure, a non-200 answer or text that does not parse (a dev server may
  answer with the app's own page) gives `source = "build-missing"`; success gives
  `"build"`. Changing `view` resets the loaded records and tampering.
- `Source` gains `"build"` and `"build-missing"`. They behave like `"demo"`
  everywhere (no LIVE badge, no Check button).
- `RecordSwitch`: a group named "Record to show" with two keys, "Demo" and "How
  this was built", placed above the rolls, in the page's column.
- `lib/buildTotals.ts`: `buildTotals(entries)` and `totalsText(totals)`.
  - sessions: distinct session ids.
  - lines: number of records.
  - checked: distinct (session, witness line) pairs that have an overall verdict
    other than NO_STATEMENT; the latest verdict for a pair counts.
  - matched: checked pairs whose latest verdict is SUPPORTED.
  - silent: distinct pairs whose latest verdict is NO_STATEMENT.
  - unchecked: statements with no overall verdict for their witness line.
  - The text reads, for example: "3 sessions, 459 lines. 2 statements checked,
    1 matched the evidence. 1 session changed files and said nothing. 1
    statement was written and never checked." Parts that are zero are left out,
    except "0 statements checked".
- `App`: `view` state; changing it clears the picked roll and the tamper target.
  In the build view the roll that is picked first is the first CONTRADICTED one,
  otherwise the first. `build-missing` shows a notice and the clerk speaks:
  "The build record isn't published yet. Click Demo to go back." (calm).
- `useReplay.skipToEnd()`, a `Key` "Skip to end" in `ReplayControls`
  (aria-label "Skip to end"), disabled with the other replay keys and when
  `cursor >= total`.

### 3.3 Long sessions

Cost with 2,000 lines is in rebuilding every line on every step.

- `PrintLine` is wrapped in `React.memo`. Its props are `entry` (kept by
  `useMemo` while the record is the same), four booleans and `onSelect`, which
  is a `useCallback` with no dependencies (it uses the functional form of the
  state setter). The list of rows is built in a `useMemo` over those inputs.
  One step then changes the props of two rows.
- `UndeclaredCircle` and `MarkerArrow` are only mounted for printed lines, as now.
- No windowing and no `content-visibility`: `MarkerArrow` and `jumpToLine`
  measure other lines, and a skipped line would give them wrong numbers. This is
  decided from the browser check in task 7; if SKIP TO END takes longer than a
  second there, the decision is revisited and recorded in tasks.md.
- `useChainCheck` already walks the records once per change; it stays.

The test uses a generated 2,000-line record whose hashes are real, and counts
calls to `entryText` with a module mock.

## 4. The ring

Two defects, two causes.

**The right edge.** `paper.css` has `svg, img { max-width: 100% }`. The ring is
an `svg` that is wider than its button, so the page rule shrank it to the
button's width while `left: -2.2em` still pulled it left. Its right edge landed
on the text. The fix is `max-width: none` on `.undeclared-circle__ring`.

**Neighbours.** The ring stuck out 1 em above and below its button, and the
path used y 2.5 to 37 of 40. The buttons were 0.6 em apart (two margins of
0.3 em), so the rings of two neighbouring lines overlapped. Now the ring sticks
out 0.8 em, the path uses y 1.5 to 38.5 of 40, and the vertical margin of the
button is 1 em, so two buttons are 2 em apart. The stroke of one ring ends at
most 0.65 em beyond its button, which leaves at least 0.4 em of clear paper
between two rings. The padding at the top and bottom stays 0.6 em.

**The shape.** The first rounded loop had corners as tall as 30% of the ring,
which swallowed the corners of a tall (four line) text. The corners are now
small (about 12% of the height and 5% of the width), the left edge runs
straight, and the end of the stroke still overshoots the start.
`ring.test.ts` gains:

1. The cap: the effective ring width is `min(declared, box)` unless the ring
   sets `max-width: none`; a case with the cap fails, a case without passes.
2. Neighbours: for every pair of line counts from 1 to 4, the gap between the
   bottom of the first ring's path and the top of the second ring's path (box
   gap = both vertical margins) is at least 0.25 em more than the stroke width.
3. The existing checks, with the corrected model.

The task 7 check measures the real page in headless Chrome (button, text and
ring rectangles) at 1280 px and 375 px.

## 5. README

The top of `README.md` is rewritten (R4). `tests/test_readme.py` finds every
backticked path and every `python -m papertrail <word>` in the README and checks
that it exists (paths) or is a subcommand in `__main__` (words). Placeholders in
angle brackets are skipped.

## 6. Tests

| File | Covers |
|------|--------|
| `tests/test_install.py` | AC1.1a-i, AC1.2a-g with a fake probe |
| `tests/test_install_assets.py` | AC1.1j, hook scripts import fallback (AC1.3b, AC1.3c) |
| `tests/test_pyproject.py` | AC1.3a, wheel contents, the any-folder run |
| `tests/test_power.py` | AC1.4b |
| `tests/test_cli.py` additions | `init`, `doctor` end to end, exit codes, root default (AC1.3d) |
| `tests/test_export_build_record.py` | AC2.1a-f |
| `tests/test_readme.py` | AC4.3, AC4.4 |
| `web/src/__tests__/buildTotals.test.ts` | AC2.2d |
| `web/src/__tests__/RecordSwitch.test.tsx`, `App.test.tsx` | AC2.2a-g, AC2.3a |
| `web/src/__tests__/longSession.test.tsx` | AC2.3b, AC2.3c, AC2.3e |
| `web/src/__tests__/ring.test.ts` | AC3.1, AC3.2, AC3.4 |

Hypothesis is used for `init`: for generated existing `mcp.json` contents
(objects with generated servers and keys), after `init` every original server and
key is still there with the same value, and a second `init` writes nothing.
