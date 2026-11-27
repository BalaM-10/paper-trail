"""A session split into rolls, one per turn.

Kiro keeps one session id across many replies, so a session can hold many
statements. A turn is one reply: it starts when the person sends a prompt (a
`witness` record with `event: "turn"`) and ends with the agent's stop and the
verdict on its statement. Each turn is its own roll of paper, titled by its
statement and numbered within the session.

The rules (web/src/lib/rolls.ts is the twin; tests/fixtures/rolls.json is read
by tests in both languages):

1. A session with no turn record is one roll, exactly as before.
2. Otherwise roll k holds the records from turn start k up to the next turn
   start. Records before the first turn start (the session start) join roll 1.
   So a tool call belongs to the turn it happened in.
3. A verdict record belongs to the roll of the stop it checked (its
   `witness_seq`), even if it was written later, for example by `verify`.
4. Line numbers are never changed: a roll holds the real records.

Standard library only.
"""

from dataclasses import dataclass

NO_STATEMENT_TITLE = "No statement written"
NOTHING_CHANGED_TITLE = "Nothing changed"
IN_PROGRESS_TITLE = "Turn in progress"


def is_turn_start(entry: dict) -> bool:
    return entry["kind"] == "witness" and entry["data"].get("event") == "turn"


def is_overall(entry: dict) -> bool:
    return entry["kind"] == "verdict" and entry["data"].get("kind_detail") == "statement_overall"


@dataclass(frozen=True)
class Roll:
    session_id: str
    number: int  # 1-based, within the session
    count: int  # rolls in the session
    turn_start: bool  # the session has turn records, so "turn n of N" means something
    entries: tuple[dict, ...]
    title: str
    overall: str | None  # verdict of the newest overall verdict in the roll
    statement_number: int | None  # the n of `verify <session> <n>` for the roll's newest statement
    has_unverified_statement: bool
    date: str  # "YYYY-MM-DD" of the first record

    @property
    def first_seq(self) -> int:
        return self.entries[0]["seq"]

    @property
    def last_seq(self) -> int:
        return self.entries[-1]["seq"]

    @property
    def has_statement(self) -> bool:
        return any(e["kind"] == "statement" for e in self.entries)


def _title(session_id: str, entries: list[dict], turn_start: bool, overall: str | None) -> str:
    statements = [e for e in entries if e["kind"] == "statement"]
    if statements:
        summary = statements[-1]["data"].get("summary")
        return str(summary) if summary is not None else session_id[:8]
    if overall == "NO_STATEMENT":
        return NO_STATEMENT_TITLE
    if turn_start:
        stopped = any(e["kind"] == "witness" and e["data"].get("event") == "stop" for e in entries)
        return NOTHING_CHANGED_TITLE if stopped else IN_PROGRESS_TITLE
    return session_id[:8]


def split_session(entries: list[dict]) -> list[Roll]:
    """The rolls of ONE session. `entries` are its records, in order."""
    if not entries:
        return []
    session_id = entries[0]["session_id"]
    starts = [i for i, e in enumerate(entries) if is_turn_start(e)]
    turn_start = bool(starts)
    if not starts:
        groups = [list(entries)]
    else:
        bounds = [0] + starts[1:] + [len(entries)]
        groups = [list(entries[bounds[k]:bounds[k + 1]]) for k in range(len(starts))]

    # A verdict belongs to the roll of the stop it checked.
    home = {e["seq"]: k for k, group in enumerate(groups) for e in group if e["kind"] == "witness"}
    moved = [[e for e in group] for group in groups]
    for k, group in enumerate(groups):
        for e in group:
            if e["kind"] != "verdict":
                continue
            target = home.get(e["data"].get("witness_seq"))
            if target is not None and target != k:
                moved[k].remove(e)
                moved[target].append(e)
    groups = [sorted(group, key=lambda e: e["seq"]) for group in moved]

    statements = [e for e in entries if e["kind"] == "statement"]
    checked = {e["data"].get("witness_seq") for e in entries if is_overall(e)}

    rolls = []
    for k, group in enumerate(groups):
        overalls = [e for e in group if is_overall(e)]
        overall = str(overalls[-1]["data"]["verdict"]) if overalls else None
        mine = [e for e in group if e["kind"] == "statement"]
        latest = mine[-1] if mine else None
        number_of_latest = (
            next(i for i, s in enumerate(statements, start=1) if s["seq"] == latest["seq"]) if latest else None
        )
        rolls.append(Roll(
            session_id=session_id,
            number=k + 1,
            count=len(groups),
            turn_start=turn_start,
            entries=tuple(group),
            title=_title(session_id, group, turn_start, overall),
            overall=overall,
            statement_number=number_of_latest,
            has_unverified_statement=latest is not None and latest["data"].get("witness_seq") not in checked,
            date=str(group[0].get("ts", ""))[:10] if group else "",
        ))
    return [r for r in rolls if r.entries]


def split(entries: list[dict]) -> list[Roll]:
    """The rolls of every session, in the order the sessions first appear."""
    order: list[str] = []
    by_session: dict[str, list[dict]] = {}
    for e in entries:
        if e["session_id"] not in by_session:
            by_session[e["session_id"]] = []
            order.append(e["session_id"])
        by_session[e["session_id"]].append(e)
    return [roll for sid in order for roll in split_session(by_session[sid])]
