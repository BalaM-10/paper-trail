# Requirements - Paper Trail Turns

## Scope

Kiro keeps one session id across many replies. That breaks two things today:
the stop hook compares against the previous stop, so anything a person changed
between two replies is blamed on the agent (R1), and one session holds many
statements but is shown as one roll (R2, R3). This spec makes a turn, one reply
of the agent, the unit of evidence. It also fixes how the project folder is
recognised in text (R4) and updates the installer and the docs (R5).

Rules that still hold: no file contents, no absolute path, user name or machine
name in the record; plain words on screen; everything keyboard operable; no
sideways scroll at 375 px; every file written as UTF-8 without a byte-order mark.

---

## R1 - Changes between turns are not the agent's

A *turn* starts when the person sends a prompt and ends when the agent stops.

**Acceptance criteria**

- AC1.1 (the trigger): Kiro's `UserPromptSubmit` trigger fires when the person
  sends a prompt. A new hook file `witness-turn-start.json` runs
  `python .kiro/hooks/witness.py turn` on it. The design records what Kiro's
  documentation says about the trigger and how that shapes the hook.
- AC1.2: `witness.py turn` takes a snapshot of the project and appends a
  `witness` record with `event: "turn"` holding it. The text of the prompt is
  never stored, not in the record and not in `.papertrail/payloads/`.
- AC1.3: If the session already has a snapshot, the turn hook compares it with
  the new one. When they differ it appends one more `witness` record with
  `event: "between_turns"`, holding the difference, the line it was compared
  from and the turn-start line. When they do not differ it appends nothing.
- AC1.4: The compared-from snapshot is the latest one in the session: the last
  stop, or the session start when no turn has run yet. If the latest is the
  start of a turn that never stopped (interrupted), the record says so
  (`unfinished: true`), because some of those changes may be the agent's.
- AC1.5: The stop hook compares against the snapshot at the start of the turn.
  When the turn already has a stop that kept a statement, it compares against
  that stop, as before. When the session has no turn start (the hook is not
  installed, or did not fire) it compares as it did before this spec.
- AC1.6: A change recorded as between turns is never listed as undeclared, is
  never part of a statement's verdict, and never causes NO_STATEMENT.
- AC1.7 (the test that reproduces the report): two files are deleted by a
  person between two turns; the agent then deletes two other files and declares
  them; the overall verdict is SUPPORTED, there are no undeclared changes, and
  the two files the person deleted appear in the between-turns record. The same
  steps without the turn hook give CONTRADICTED with those two files listed as
  undeclared (the control).
- AC1.8: The `NO_STATEMENT` rule compares only with verdicts of the current
  turn, so the same change made in two different turns is reported in both.
- AC1.9: `files_read` claims are checked against the tool calls of the turn the
  statement belongs to, not the whole session.
- AC1.10: The hook never raises, exits 0, prints nothing to standard output
  (Kiro adds that output to the agent's context), and takes under one second
  with 20 changed files. An unknown event name is an `error` record, not a stop.

## R2 - One roll per turn

**Acceptance criteria**

- AC2.1: A session is split into rolls, one per `turn` record. Records before
  the first turn start (the session start) belong to the first roll. A session
  with no turn record is one roll, exactly as before.
- AC2.2: Every record belongs to the roll in which it was written, so a tool
  call belongs to the turn it happened in. A verdict record belongs to the roll
  of the stop it checked (its `witness_seq`), even if it was written later.
- AC2.3: A roll is numbered within its session (`turn 2 of 3`) and titled by
  its statement: the summary of its latest statement; else "No statement
  written" when its overall verdict is NO_STATEMENT; else "Nothing changed" when
  its turn has stopped; else "Turn in progress"; else, for a session without
  turn records, the first 8 characters of the session id.
- AC2.4: The screen, `list_sessions`, `print` and the spool file all use the
  same rolls. A shared fixture (`tests/fixtures/rolls.json`) is read by tests in
  Python and in TypeScript so the two cannot drift.
- AC2.5: Line numbers are the real record numbers. A verdict's evidence cites
  the same line numbers as before; nothing is renumbered per roll.
- AC2.6 (screen): each roll is its own roll of paper in the list, with its title,
  its date, its stamp, and "turn n of N" when the session has more than one.
  Choosing a roll prints only that roll. Starting a roll again is by the roll,
  not by the session.
- AC2.7 (`list_sessions`): one item per roll with `session_id`, `turn`, `turns`,
  `title`, `entry_count` (of the roll), `has_statement`, `overall_verdict`.
  `get_entries` takes an optional `turn`.
- AC2.8 (`print`, spool): one file per session, `.papertrail/spool/<id>.txt`,
  holding each roll as its own report (header with session, "Turn n of N" when
  more than one, the statement, the paper status; then its numbered lines),
  separated by a tear line. The last line is still the fingerprint of the whole
  record and its line count. No line is over 80 columns.
- AC2.9: A session with one roll prints and shows exactly as before.
- AC2.10: The tear-off report on screen names the turn.

## R3 - Between turns, on the screen

**Acceptance criteria**

- AC3.1: A between-turns record is one plain line on the paper, in the roll
  that follows it, for example "Between turns, outside the agent: deleted a.txt,
  b.txt." Several kinds read "created c.py; changed m.py, n.py; deleted d.py".
- AC3.2: The line has no stamp, no red ring, no arrow. It is shown in a quieter
  style (grey, italic) that still meets the contrast rule.
- AC3.3: An unfinished earlier turn reads "Since the unfinished turn before this
  one: deleted a.txt. The agent may have made some of these changes."
- AC3.4: A turn start reads "Witness took a snapshot of the project at the
  start of this turn." A stop compared with a turn start reads "Witness
  compared the project to the snapshot from the start of this turn. ..."
- AC3.5: The tear-off report lists the between-turns line before the verdicts.
- AC3.6: The spool file prints the same sentences (shared fixture).

## R4 - The project folder before punctuation

**Acceptance criteria**

- AC4.1: `cd <project folder>; ...` is stored as `cd .; ...`. The project folder
  and the home folder are recognised when followed by any character that cannot
  continue a folder name: `; , ) ] } | : ! ?`, a quote, a slash, white space, a
  full stop that is not followed by a name character, or the end of the text.
- AC4.2: A longer folder name is still not the project folder (`proj-two`,
  `proj.old`), and a folder is not recognised in the middle of a word.
- AC4.3: Property tests: for generated text with the project folder or the home
  folder followed by each of those characters, in any letter case and slash
  style, the result is exactly the text with `.` or `~` in its place.

## R5 - Install, doctor, docs

**Acceptance criteria**

- AC5.1: `init` copies `witness-turn-start.json` and the updated `witness.py`;
  `doctor` checks them (an absent file is MISSING, a changed one WARN). The hook
  files are now five and the scripts two.
- AC5.2: The packaged assets and this repository's `.kiro/hooks/` agree.
- AC5.3: The README (the install text, the verdicts, "Built with Kiro") and the
  skills of the Power describe turns, the new hook and the roll per turn.
- AC5.4: The demo record shows a session of two turns, with a between-turns
  line, so the page can show it without running Kiro.

## R6 - Conflicts with earlier specs

- `session.on_stop` baseline: turn start first (R1.5).
- The stop sentence changes when compared with a turn start (R3.4).
- `list_sessions` returns one item per roll (R2.7); `SessionMeta` on the screen
  is per roll.
- The build totals say "turns" when a session holds more than one.
