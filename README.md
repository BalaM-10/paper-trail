# Paper Trail

**Did the agent do what it said?**

Paper Trail checks an AI coding agent's report of its own work against the
folder on disk, and prints the result on fan-fold paper.

## In 30 seconds

An agent finishes a task and tells you what it did. Normally you take its word
for it. Paper Trail does not.

1. **Record.** Kiro hooks write down every tool call the agent makes.
2. **Witness.** When a session starts and when it stops, Paper Trail takes its
   own snapshot of the project folder. The difference between the two is what
   really changed. The witness trusts neither the agent nor the record, so it
   also sees what a shell command did behind the agent's back.
3. **Statement.** The agent writes a short statement: files read, created,
   changed and deleted.
4. **Verdict.** Each line of the statement is checked against the witness and
   the record. Anything the witness saw that the statement leaves out is listed
   as a change the agent never mentioned.
5. **Printout.** A web page prints the record one line at a time and stamps the
   verdicts. Each line carries a fingerprint that depends on the line before it,
   so editing any line tears the paper at that point.

The idea comes from an old security habit: sending audit logs to a line printer,
because a printed page cannot be edited afterwards.

## Install in one command

You need Windows, macOS or Linux, Python 3.11 or later, and Kiro. In PowerShell:

```powershell
pip install .
python -m papertrail init C:\path\to\your\project
```

The first line installs Paper Trail once, from this folder. The second sets up
one project. It copies the four hook files and two hook scripts into
`.kiro/hooks`, the statement rule into `.kiro/steering`, adds the `paper-trail`
server to `.kiro/settings/mcp.json` (your other servers stay as they are) and
adds `.papertrail/` to `.gitignore`.

- It never overwrites a file that differs from Paper Trail's. It says "Left
  alone" and exits with status 1. Add `--force` to replace the file.
- Running it twice changes nothing the second time.
- Check the result any time: `python -m papertrail doctor C:\path\to\your\project`.
  It says what is missing and how to fix it.

Start a Kiro session in that project. Records appear in `.papertrail/`.

Kiro Powers can carry the MCP server and instructions, but not hooks or an
always-on steering rule, so a Power does not replace `init`. See
[power/paper-trail](power/paper-trail) and the reasons in
`.kiro/specs/paper-trail-install/design.md`.

## The verdicts

| Stamp | Meaning |
|-------|---------|
| SUPPORTED | The evidence agrees with the statement. |
| CONTRADICTED | The evidence shows otherwise. The page points at the line and the file. |
| UNVERIFIED | There is no evidence either way. Not the same as wrong. |
| NO STATEMENT | The agent changed files and wrote no statement. The changes are listed. |

## Try the demo

The demo shows an agent running a cleanup script with an ordinary mistake: it
was meant to clear the build cache, but its pattern is too broad and it also
deletes `sample/notes.txt`. The agent says it only cleared the cache. The
witness saw the notes file go. The verdict is CONTRADICTED.

1. Reset the sample project: `python sample/reset.py`
2. Start a Kiro session in this folder. The witness takes a snapshot.
3. Ask the agent to run `python sample/cleanup.py`, then to write its statement.
4. When the session ends, the stop hook takes a second snapshot and keeps the
   statement. Check it: `python -m papertrail verify <session_id>`. The last line
   is `OVERALL: CONTRADICTED`.

To see the printout without running anything, build the page (below) and open
the "Demo" roll. It has three recorded sessions: SUPPORTED, CONTRADICTED and NO
STATEMENT.

## The web page

```powershell
cd web
npm ci
npm run build        # or: npm run dev
```

`python -m papertrail serve` shows the live record next to it. The page has two
rolls, chosen with the switch above the sessions:

- **Demo**: the sample sessions, or the live record when the local server is up.
- **How this was built**: the record of building Paper Trail itself, with its
  real verdicts and totals. A long session is fine: SKIP TO END prints it all.

The build record is published with `python sample/export_build_record.py`. It
copies `.papertrail/ledger.jsonl` unchanged, so the fingerprints still check. It
refuses, and lists each finding, if the record holds an absolute path, the user
name or the machine name. Until a clean record has been published, the page says
the build record is not published yet.

The page shows a "View on GitHub" link only if it is built with an address:

```powershell
$env:VITE_REPO_URL = "https://github.com/<you>/paper-trail"; npm run build
```

## More commands

```powershell
python -m papertrail verify <session_id>   # check a statement
python -m papertrail print <session_id>    # write .papertrail/spool/<session_id>.txt
python -m papertrail check-chain           # is the paper intact?
```

`print` writes plain text: 80 columns, numbered lines, the same sentences as the
screen, and a last line with the fingerprint of the whole record and its line
count. The MCP tool `print_session` returns the same text.

## Built with Kiro

Paper Trail was built with Kiro, and it records its own building.

- **Specs** (`.kiro/specs/`): `paper-trail-core` (recorder, witness, verifier),
  `paper-trail-printout` (API, MCP server, the page), `paper-trail-proof` (an
  honest sample bug, NO STATEMENT, the print file, CI) and `paper-trail-install`
  (init, doctor, pip, the build record). Each has requirements, a design and
  tasks.
- **Hooks** (`.kiro/hooks/`): `record-post-tool-use.json` and
  `record-file-delete.json` write the record; `witness-session-start.json` and
  `witness-stop.json` take the two snapshots. They call `record.py` and
  `witness.py`, which use only the standard library and never disturb the agent.
- **Steering** (`.kiro/steering/`): `product.md`, `tech.md` and `structure.md`
  hold the product, the stack and the layout. `statement.md` makes the agent
  write `.papertrail/statement.json` before it reports it is done.
- **MCP server** (`papertrail/mcp_server.py`): five tools, `list_sessions`,
  `get_entries`, `check_chain`, `verify_statement` and `print_session`, so the
  agent can check its own work.
- **Property-based tests** (Hypothesis): `tests/test_ledger.py` (the fingerprint
  chain), `tests/test_witness.py` (snapshots and differences) and
  `tests/test_install.py` (`init` loses nothing in an existing `mcp.json`, and
  twice is once).

## Running the tests

```powershell
python -m pytest tests/ -q
cd web
npx vitest run
npm run build
```

The same checks run on Windows, macOS and Linux in `.github/workflows/tests.yml`.

## Project layout

```
.kiro/          hooks, specs and steering (committed)
papertrail/     Python package: ledger, witness, statement, verifier, outcome,
                spool, install, api, mcp_server; assets/ is what init copies
power/          the Kiro Power: MCP server and two skills
sample/         the demo project, its generator, the build-record exporter
tests/          pytest and Hypothesis tests
web/            React + TypeScript printout page
.papertrail/    runtime data (record, snapshots, statements); not committed
```

## License

MIT. See `LICENSE`.
