# Product: Paper Trail

## What it is
Paper Trail is an evidence recorder and claim verifier for AI coding agents.
It revives a retired security practice: sending audit logs to a line printer,
because a printed page cannot be edited after the fact. Paper Trail gives an
AI agent the same kind of record: an append-only, hash-chained ledger that is
shown as a continuous-feed printout.

Kiroween 2026 category: Resurrection.

## The problem
An agent finishes a task and reports what it did. Today that report is taken
on trust. Nothing independent confirms it, and the agent's own tool log misses
side effects (for example, a shell command or script that deletes a file).

## How it works
1. Recorder. Kiro agent hooks append every tool call to the ledger.
2. Witness. An independent snapshot of the project folder is taken when a
   session starts and when the agent stops. The difference between the two is
   the ground truth of what changed on disk. The witness never trusts the
   agent or the recorder.
3. Statement. When the agent finishes, it writes a short statement of what it
   did: files read, created, modified and deleted.
4. Verifier. Each line of the statement is checked against the witness and the
   ledger and receives one verdict:
   - SUPPORTED: the evidence agrees.
   - CONTRADICTED: the evidence shows otherwise.
   - UNVERIFIED: there is no evidence either way.
   Anything the witness saw that the statement leaves out is listed as an
   UNDECLARED CHANGE.
5. Printout. A web view renders the ledger as fan-fold printer paper and
   replays a session line by line. Verdicts appear as ink stamps.

## The demo story (must always work)
A sample project contains a cleanup script that removes more than its name
suggests. The agent runs it and states that it only cleared the build cache.
The witness shows that a notes file was also deleted. The printout replays the
session and stamps the statement CONTRADICTED, pointing at the exact ledger
line and the missing file.

## Principles
- Evidence over claims. A verdict must cite ledger entries or witness facts.
- The witness is independent. It reads the disk directly.
- Append-only. Ledger entries are never edited or removed. Tampering breaks
  the hash chain and the printout shows where.
- Plain language in the interface. No jargon on screen.
- Honest limits. If something cannot be verified, say UNVERIFIED.

## Out of scope for this version
User accounts, multi-user or cloud storage, blocking or approving agent
actions, support for agents other than Kiro.
