# Spec prompt

Paste the text below into a new Kiro session using the Spec agent.

---

Create a spec named "paper-trail-core" for the product described in the
steering files. Follow product.md, tech.md and structure.md exactly.

Scope of this spec:

1. Ledger: append-only, hash-chained JSON Lines file with append, read and
   verify-chain functions. Tampering with any entry must be detected and the
   first broken entry reported.
2. Recorder hook: replace the current test script at .kiro/hooks/record.py
   with a recorder that reads the Kiro hook JSON from standard input, converts
   paths to project-relative form, and appends a `tool` entry to the ledger.
   Keep the existing PostToolUse hook pointing at it.
3. Witness: folder snapshot and difference, plus hooks that take a snapshot
   when a session starts and when the agent stops, and append a `witness`
   entry with the difference.
4. Statement: a steering rule and file format so the agent ends each task by
   writing `.papertrail/statements/<session_id>.json` listing files read,
   created, modified and deleted, with one plain-language summary sentence.
5. Verifier: compare a session's statement with the witness difference and
   the ledger. Give each statement line SUPPORTED, CONTRADICTED or UNVERIFIED,
   list UNDECLARED CHANGES, and append `verdict` entries that cite the ledger
   sequence numbers used as evidence.
6. Sample project in `sample/` with a cleanup script that clears a build
   cache folder and also deletes `notes.txt`, so the demo story in product.md
   can be reproduced.
7. Tests: pytest for each module and Hypothesis property-based tests for the
   hash chain (any single-entry change is detected) and for the snapshot
   difference.

Not in this spec: the API, the MCP server and the web printout. Those come in
a second spec.

Write requirements with acceptance criteria, then the design, then a task
list small enough that each task can be run and checked on its own.
