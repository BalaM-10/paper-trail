# Design - Paper Trail Ignore

## R1 - The witness skips throwaway files

### Where it lives
A new module `papertrail/ignore.py` (standard library only, because the hooks
import it) holds a small matcher. `witness.snapshot(root)` builds one matcher
from `<root>/.gitignore` and the built-in list, and asks it about every folder
and file as it walks. The verifier asks the same matcher about the paths a
statement names.

### The matcher
`Matcher(lines, ignore_case=False)` compiles each line to a rule
`(regex, negated, folders_only)`.
- A line is skipped when blank or when it starts with `#`. A trailing space is
  dropped unless escaped with a backslash. `\#` and `\!` at the start stand for
  a literal `#` and `!`.
- A pattern with a `/` anywhere except at the end is anchored to the project
  folder. A pattern without one matches a name at any depth.
- Translation to a regular expression: `*` becomes `[^/]*`, `?` becomes `[^/]`,
  `[...]` is kept as a class (`[!...]` becomes `[^...]`; an unclosed `[` is a
  literal), `**/` at the start or in the middle matches any number of folders,
  `/**` at the end matches everything inside. Everything else is escaped. A
  line that cannot be translated is skipped, so the matcher never raises.
- `is_ignored(path, is_dir)` tests the folders above the path first, top down.
  The first ignored folder ends the search with "ignored", because git cannot
  bring back a file inside an ignored folder. Otherwise the last rule that
  matches the path itself decides; a negated rule makes it "not ignored".
- Windows: `Matcher.load(root)` sets `ignore_case` on Windows, because git does
  there (`core.ignorecase`). The class default is case-sensitive so the
  property tests give the same answers everywhere.

### Built-in list
Prepended as ordinary lines, so a project's `!name` can bring one back:
folders `.pytest_cache/`, `.hypothesis/`, `.mypy_cache/`, `.ruff_cache/`,
`.tox/`, `.nox/`, `.eggs/`, `*.egg-info/`, `htmlcov/`, `.ipynb_checkpoints/`,
`.cache/`, `.parcel-cache/`, `.turbo/`, `.next/`, `.nyc_output/`, `.idea/`,
`.vs/`, `venv/`; files `*.pyc`, `*.pyo`, `.coverage`, `.coverage.*`,
`*.tsbuildinfo`, `.eslintcache`, `*.swp`, `*.swo`, `*~`, `.DS_Store`,
`Thumbs.db`. `.vscode/` is left out on purpose, because its settings are often
real project files.

The old `EXCLUDE` set (`.git`, `.papertrail`, `node_modules`, `__pycache__`,
`.venv`, `dist`, `build`) stays a hard rule in `witness.py`, checked before the
matcher, so no `.gitignore` line can bring those back.

### Left out, on purpose
- Nested `.gitignore` files, `.git/info/exclude` and the user's global ignore
  file. The root file plus the built-in list covers the reported case, and each
  extra source is another way for the witness to disagree with the verifier
  about the same path. A project that needs more can add the lines to its root
  `.gitignore`.

### What the record holds
Witness `start`, `turn` and `stop` records gain `"ignore": "gitignore"`. It
says the snapshot follows the rule; it holds no patterns and no skipped path.
The snapshot itself simply has no entry for a skipped file, as it never had for
`node_modules`.

### The verifier
`verify` reads the `ignore` field of the stop record it checks. When it is
present, a claim about a created, modified or deleted path goes to UNVERIFIED
(evidence `[]`) if the matcher, loaded from the project folder, skips that path.
The project folder is two levels above the ledger path
(`<root>/.papertrail/ledger.jsonl`). Claims are normalised (backslashes to
`/`, a leading `./` dropped) before matching. A record without the field is
judged exactly as before, so old records and the demo keep their verdicts. The
`.gitignore` is read when the check runs, which is normally the stop itself
(`session.on_stop` checks the statement it just promoted).

### The reproduction test
`tests/test_ignore.py` builds a project in `tmp_path` with a `.gitignore`
naming `.hypothesis/` and `.pytest_cache/`, calls `on_start`, writes about 50
cache files and one real file, writes `statement.json` declaring the real file,
calls `on_stop`, and reads the overall verdict. The control repeats it with a
cache folder that no rule names.

## R2 - Command text

### What the ledger holds
`recorder._process_input_value` replaces any string longer than 2000
characters, or under a content key, with `{"size": n, "sha256": h}`. A long
PowerShell command (a here-string, a generated script) therefore has
`tool_input.command` as an object, and `String(object)` is "[object Object]".
Seven of the 60 shell-command records in this project's own ledger have that
shape. The text of those commands was never stored (it may hold anything), so
it cannot be printed; the line says that, and gives the size.

### The shared rule
One function in each language, `command_sentence` / `commandSentence`, returns:
1. a string: as before, with the first 80 characters;
2. an object with an integer `size` (not a boolean, not negative) and a text
   `sha256`: the digest sentence;
3. anything else: nothing, and the line reads "Agent ran a command."
The same guard (`text_or`) is applied to `path`: only text counts, else
"a file". Cases go into `tests/fixtures/sentences.json`, which
`tests/test_spool.py` and `web/src/__tests__/sentences.test.ts` already run
through, so both languages are held to the same words.

## R3 - Long roll titles

`SessionSpool` keeps the title in `.spool__title` and adds `title={meta.title}`
(the tooltip). The text stays in the button, so the accessible name still holds
the whole title. CSS clamps the title to three lines:
`display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3;
line-clamp: 3; overflow: hidden;` with `overflow-wrap: anywhere` kept so a
title with no spaces wraps instead of widening the roll. The roll's height is
now bounded (three title lines, the meta line, the stamp), so the stamp always
sits inside the card. jsdom has no layout, so the tests check the DOM (full
text, tooltip) and the stylesheet (the clamp rules), as the existing style
tests do.

## Tests

| Area | File |
|---|---|
| Matcher cases and Hypothesis properties | `tests/test_ignore.py` |
| Snapshot skips, verifier UNVERIFIED, reproduction | `tests/test_ignore.py`, `tests/test_witness.py` |
| Command sentences, both languages | `tests/fixtures/sentences.json` |
| Roll title | `web/src/__tests__/rollTitle.test.tsx`, `styles.test.ts` |
