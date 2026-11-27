# Design - Paper Trail Turns

## 1. What Kiro's documentation says (read while writing this spec)

Sources: Kiro docs "Hooks", "Hook triggers", "Hook actions", "What's new in 1.0:
Hooks" (the trigger-name table), and the AWS Labs "Kiro IDE hook payload"
reference (measured on IDE 1.0.242 and 1.2.37).

- **The trigger exists.** The JSON name is `UserPromptSubmit` ("Prompt Submit"
  in the docs, legacy `promptSubmit`). It fires when the person sends a
  message. It is available in the IDE, CLI V3 and Kiro Web.
- **The hook receives** a JSON object on standard input: `session_id`, `cwd`,
  `hook_event_name`, `prompt`. The measured payload on IDE 1.0.242 had an empty
  `prompt`; the session id was always there. The text is also in the
  `USER_PROMPT` environment variable.
- **Exit codes.** 0: standard output is added to the agent's context. 2: the
  prompt is blocked (IDE). Any other non-zero code is an error. So the hook
  must exit 0 and print nothing; anything it prints would reach the agent.
- **Messages typed while the agent is working** do not fire the hook in CLI V3
  (measured on 3.0.0). They are part of the running turn, which is right.
- **Kiro's own prompts** (for example a "workflow completed" notice) also fire
  it. A second turn start inside a reply is therefore possible; section 3 says
  what the record does then.
- **SessionStart is not always delivered.** On some builds a new chat runs no
  SessionStart hook. The turn start is a second source of a baseline, so a
  session whose start was missed now has one from its first prompt.

So `UserPromptSubmit` is the trigger. No fallback is needed. The prompt text is
never read or stored: it may hold paths, names or file contents.

## 2. The record

New `witness` records (no new `kind`; the five kinds in tech.md stay):

```
event "turn"          {"event": "turn", "snapshot": {...}}
event "between_turns" {"event": "between_turns",
                       "diff": {"created": [], "modified": [], "deleted": []},
                       "baseline": "stop:<seq>" | "start:<seq>" | "turn:<seq>",
                       "witness_seq": <turn seq>,
                       "evidence_seq": [<compared-from seq>, <turn seq>],
                       "unfinished": false}
event "stop"          as before; "baseline": "turn:<seq>" | "prev_stop_seq:<seq>" | "start" | "none"
```

The turn record comes first (it holds the snapshot), then the between-turns
record, so the between-turns line is the second line of the roll it opens.

## 3. Hook logic (`papertrail/session.py`)

### `on_turn_start(payload, root, home)`

1. `session_id` from the payload (`"unknown"` if absent). The prompt is ignored.
2. `snap = witness.snapshot(root)`.
3. The compared-from record is the latest `witness` record of the session whose
   `event` is `stop`, `turn` or `start` (it holds a snapshot). If it is a
   `turn`, no stop closed that turn: `unfinished = true`.
4. Append the `turn` record.
5. If there was a compared-from record and `witness.diff` is not empty, append
   `between_turns`.

A second turn start before any stop (interrupted turn, or a Kiro-generated
prompt) is therefore recorded as "unfinished" rather than as the person's work.

### `on_stop`

`turn` = the session's latest `turn` record. `scope` = the session's records
from that turn on (all of them when there is no turn). Baseline:

1. the stop that the highest `witness_seq` among the statements in `scope`
   points at, label `prev_stop_seq:<seq>` (a second stop in one turn);
2. else the turn record's snapshot, label `turn:<seq>`;
3. else (no turn in the session) the old rules: statements of the whole
   session, then the session start, else `none`.

Everything after that is unchanged, except that `_record_no_statement` looks
for its duplicate only inside `scope`.

### `witness.py`

`start`, `stop`, `turn` are dispatched by name; any other word is an `error`
record. For `turn` the saved payload copy has `prompt` replaced by its length.
Nothing is printed.

### Cost

One more snapshot per turn, the same work as the one at the stop (the walk and
the hashes). The turn record holds the snapshot, so the record grows by one
snapshot per turn. Kiro waits for a `UserPromptSubmit` command (60 s default),
so on a very large folder the prompt starts later; this is the price of an
honest baseline and is not optimised here.

## 4. The verifier

`verify` already reads the diff of the stop it is given, so the diff is now the
turn's. One change: the index of tool calls for `files_read` is limited to the
records after the latest `turn` before that stop (and before the stop), when
there is one. A read in an earlier turn is not evidence for this turn.

## 5. Rolls

`papertrail/rolls.py` (standard library only) and `web/src/lib/rolls.ts` hold
one algorithm:

1. Records of one session, in order. The turn starts are the `witness` records
   with `event: "turn"`.
2. No turn start: one roll holding everything. Otherwise roll k holds the
   records from turn start k up to the next one; records before the first turn
   start join roll 1.
3. A `verdict` record whose `witness_seq` is the line of a `witness` record in
   another roll moves to that roll (a statement checked later still belongs to
   its turn). Records stay in line order.
4. Per roll: `number`, `count`, `title` (R2.3), `overall` (the newest overall
   verdict), `statement_number` (the position of its newest statement among all
   the session's statements, which is what `verify <id> <n>` takes),
   `has_unverified_statement`, `date`, the first and last line.

`tests/fixtures/rolls.json` holds cases (records in, expected rolls out), read
by `tests/test_rolls.py` and `web/src/__tests__/rolls.test.ts`.

### Sentences

Both languages gain (the shared `sentences.json` fixture):

| Record | Sentence |
|--------|----------|
| turn | Witness took a snapshot of the project at the start of this turn. |
| between_turns | Between turns, outside the agent: created c.py; changed m.py, n.py; deleted d.py. |
| between_turns, unfinished | Since the unfinished turn before this one: deleted a.txt. The agent may have made some of these changes. |
| stop, baseline `turn:` | Witness compared the project to the snapshot from the start of this turn. Created: ... |

## 6. Where rolls are used

- **Screen.** `App` builds the rolls, a roll is chosen by its key
  (`<session id>#<number>`; `#` cannot be in a session id), and its records are
  the paper. `SessionList` shows one spool per roll with "turn n of N". The
  between-turns line is a normal line with class `print-line--between` (grey,
  italic). The report names the turn.
- **`list_sessions`, `get_entries`.** One item per roll; `get_entries(session,
  turn)` returns one roll's records.
- **Spool.** One file per session. Each roll is a block: the report heading, the
  session, "Turn n of N" (only if N > 1), "Statement: ...", the paper status,
  a rule, its numbered lines (undeclared `!` lines before the overall line), a
  rule. Blocks are separated by a tear line. The line-number column is as wide
  as the widest number in the file. The fingerprint of the whole record is the
  last line.
- **Build totals.** "3 sessions, 9 turns, 459 lines." when the two numbers
  differ.

## 7. Project folder before punctuation (`privacy.py`)

The boundary after the folder was a list (`/ \ " ' < >`, white space, end).
`;` was missing, so `cd C:\work\proj; ls` was caught by the drive-path rule and
became `[path]/proj`. The list is replaced by "not followed by a character that
continues a folder name": `(?![\w~-]|\.[\w~-])`. A look-behind `(?<![\w])`
stops a match in the middle of a word. A longer name (`proj-two`, `proj.old`)
still does not match. Both folders use the same rule.

## 8. Install

`assets/hooks/witness-turn-start.json` (trigger `UserPromptSubmit`) and the new
`witness.py` join the assets; `HOOK_FILES` has seven names (five JSON, two
scripts). `doctor` loops over it. This repository's `.kiro/hooks/` gets the same
files, and `tests/test_install_assets.py` keeps them equal.

## 9. Demo record

`sample/make_demo_ledger.py` adds `demo-session-d`, two turns: turn 1 the agent
writes a plan and says so; a person deletes `drafts/old-a.txt` and
`drafts/old-b.txt`; turn 2 the agent deletes `drafts/draft-1.txt` and
`drafts/draft-2.txt` and says so. The roll of turn 2 has the between-turns line
and is SUPPORTED. Sessions A to C are left as they are (no turn records: one
roll each), which also shows the old shape.

## 10. Tests

| File | Covers |
|------|--------|
| `tests/test_turns.py` | R1, including the reported case and its control |
| `tests/test_rolls.py` + `fixtures/rolls.json` | R2.1 to R2.4 |
| `tests/test_spool.py`, `test_mcp_server.py` | R2.7 to R2.9 |
| `tests/test_privacy.py` | R4 and its properties |
| `tests/test_install*.py`, `test_readme.py`, `test_power.py` | R5 |
| `web/src/__tests__/rolls.test.ts`, `App.test.tsx`, `sentences.test.ts`, `buildTotals.test.ts` | R2, R3 |
