# Project structure

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
  api.py        FastAPI app
  mcp_server.py MCP server
web/            React + TypeScript printout view
sample/         small sample project used in the demo, with the cleanup script
tests/          pytest and Hypothesis tests
docs/           architecture notes and the Kiro usage write-up
.papertrail/    runtime data (ledger, snapshots, statements); not committed
```

## Conventions
- Python: type hints, small pure functions, no global state.
- Every module in `papertrail/` has a matching test file in `tests/`.
- TypeScript: function components, no UI library; the paper look is plain CSS.
- Names on screen use plain words: Record, Witness, Statement, Verdict.
- The `.kiro` directory is committed. `.papertrail/` and build output are in
  `.gitignore`. Never add `.kiro` to `.gitignore`.
- A sample ledger for the hosted read-only demo lives in `sample/ledger.jsonl`.
- README explains how to run everything on Windows.
- License: MIT.
