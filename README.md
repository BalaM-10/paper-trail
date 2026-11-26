# Paper Trail

## What it is

Paper Trail is an evidence recorder and claim verifier for AI coding agents.
It revives a retired security practice: sending audit logs to a line printer,
because a printed page cannot be edited after the fact. Paper Trail gives an
AI agent the same kind of record — an append-only, hash-chained ledger that is
shown as a continuous-feed printout. When the agent finishes a task and writes
a statement of what it did, Paper Trail checks every claim against an
independent disk snapshot and stamps each one SUPPORTED, CONTRADICTED, or
UNVERIFIED.

## Prerequisites

- Python 3.11
- Install dependencies: `pip install -r requirements.txt`

## Demo

The demo shows an agent running a cleanup script that deletes more than its
name suggests. The agent reports it only cleared the build cache; the witness
shows a notes file was also deleted; the verifier stamps the session
CONTRADICTED.

1. Reset the sample project before starting a session:
   ```powershell
   python sample/reset.py
   ```
2. Start a Kiro session. The witness hook fires automatically and takes a
   snapshot of the project.
3. Ask the agent to run `python sample/cleanup.py`. The agent executes the
   script; the hook records the tool call in the ledger.
4. The agent writes `.papertrail/statement.json` claiming it only deleted
   `sample/cache/output.bin`. When the session ends, the stop hook takes a
   second snapshot, computes the diff, and promotes the statement to
   `.papertrail/statements/<session_id>-1.json`.
5. Verify the session:
   ```powershell
   python -m papertrail verify <session_id>
   ```
   The last line of output is `OVERALL: CONTRADICTED`.

## Running tests

```powershell
pytest tests/ -v
```

## Verifying the ledger

```powershell
python -m papertrail check-chain
```

Prints `Chain OK (<n> entries)` when the hash chain is intact, or
`Chain BROKEN at seq <n>` if any entry has been tampered with.

## Project layout

```
.kiro/
  hooks/        hook definitions and the hook scripts they call
  specs/        requirements, design and tasks written with Kiro
  steering/     these files
papertrail/     Python package
  ledger.py     append, read and verify the hash chain
  witness.py    folder snapshot and difference
  statement.py  parse the agent's statement
  verifier.py   verdicts for each statement line
  __main__.py   CLI entry point (python -m papertrail)
sample/         small sample project used in the demo, with the cleanup script
tests/          pytest and Hypothesis tests
docs/           architecture notes and the Kiro usage write-up
.papertrail/    runtime data (ledger, snapshots, statements); not committed
```
