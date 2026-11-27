---
name: check-my-work
description: Check what happened in a Kiro session against the agent's own statement, using Paper Trail's tools. Use when the user asks whether the agent did what it said, or wants a printable record of a session.
---

# Check what the agent really did

Use the `paper-trail` server's tools. They read the record; they never change it.

## Step 1: Find the session

Call `list_sessions`. It returns one item per turn (one reply of the agent): the
session id, the turn number (`turn` of `turns`), a title (the statement), and the
overall verdict. A chat is one session with many turns; each turn is checked on
its own.

## Step 2: Check the statement

Call `verify_statement` with the session id (a statement is normally checked when
the turn ends, so this shows the stored result). To look at one turn's records,
call `get_entries` with the session id and the turn number. Each line of the statement gets one
verdict:

- SUPPORTED: the evidence agrees.
- CONTRADICTED: the evidence shows otherwise.
- UNVERIFIED: there is no evidence either way.

Anything the witness saw that the statement leaves out is an undeclared change.
If the session changed files and has no statement, the overall verdict is
NO_STATEMENT.

## Step 3: Say it plainly

Report the overall verdict first, then each CONTRADICTED line and each undeclared
change, naming the file. A line that says "Between turns, outside the agent" is
something the person changed between replies: mention it, but it is not the
agent's. Do not describe an UNVERIFIED line as wrong: it only
means nothing could confirm it.

## Step 4: Print it, if asked

Call `print_session` with the session id. It returns the same text as
`python -m papertrail print <session_id>`: 80 columns, numbered lines, and a last
line with the fingerprint of the whole record.

To check that the record itself was not edited, call `check_chain`.
