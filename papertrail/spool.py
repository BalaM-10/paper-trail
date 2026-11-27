"""A print-ready text file of one session: plain text, 80 columns, line numbers.

    python -m papertrail print <session_id>   ->   .papertrail/spool/<session_id>.txt

The lines are the sentences the screen prints. `entry_text` and its helpers are
the twin of web/src/lib/entryText.ts; tests/fixtures/sentences.json is read by
tests in both languages, so the two cannot drift apart unnoticed.

A session with several turns is printed as several rolls, one per turn (see
papertrail/rolls.py), each its own report with its own heading, numbered within
the session and titled by its statement, and separated by a tear line. Line
numbers are the real record numbers.

The last logical line is the fingerprint of the whole record (the hash of its
last entry) and the number of entries, so a printed page can be checked against
the record later. No file contents and no absolute paths appear here: everything
comes from the ledger, which never holds them.
"""

import textwrap
from pathlib import Path

from papertrail import ledger, rolls, watch
from papertrail.outcome import NO_STATEMENT, is_overall, valid_session_id

WIDTH = 80

TOOL_VERB = {"read_file": "read", "fs_write": "wrote", "str_replace": "edited"}
CLAIM_VERB = {
    "files_created": "created",
    "files_modified": "changed",
    "files_deleted": "deleted",
    "files_read": "read",
}


# ---------------------------------------------------------------------------
# The sentences (twin of web/src/lib/entryText.ts)
# ---------------------------------------------------------------------------

def _list(value) -> list:
    return value if isinstance(value, list) else []


def verdict_word(verdict) -> str:
    """The word printed on a stamp. NO_STATEMENT is two words."""
    return str(verdict).replace("_", " ")


def evidence_ref(evidence) -> str:
    """Evidence line numbers, for example "(line 4)" or "(lines 2, 5)". Empty if none."""
    lines = _list(evidence)
    if not lines:
        return ""
    return f"({'line' if len(lines) == 1 else 'lines'} {', '.join(str(n) for n in lines)})"


def undeclared_text(item: dict) -> str:
    return f"Witness saw {item['path']} {item['change']}. The agent never mentioned it."


def verdict_sentence(d: dict) -> str:
    """One verdict as a sentence, for example "Agent said it deleted a.txt. Witness agrees (line 4)."."""
    verb = CLAIM_VERB.get(str(d.get("claim")), "touched")
    said = f"Agent said it {verb} {d.get('path')}."
    ref = evidence_ref(d.get("evidence_seq"))
    where = f" {ref}" if ref else ""
    verdict = d.get("verdict")
    if verdict == "SUPPORTED":
        who = "The record agrees" if d.get("claim") == "files_read" else "Witness agrees"
        return f"{said} {who}{where}."
    if verdict == "CONTRADICTED":
        return f"{said} Witness says otherwise{where}."
    return f"{said} There is no evidence either way."


def overall_sentence(verdict) -> str:
    """The last line of a checked statement."""
    if verdict == "SUPPORTED":
        return "Overall: the statement matches the evidence."
    if verdict == "CONTRADICTED":
        return "Overall: the statement does not match the evidence."
    if verdict == NO_STATEMENT:
        return "Overall: the agent changed files and said nothing."
    return "Overall: some of the statement could not be checked."


def between_turns_text(d: dict) -> str:
    """What changed between two turns, outside the agent."""
    diff = d.get("diff") or {}
    groups = [
        ("created", _list(diff.get("created"))),
        ("changed", _list(diff.get("modified"))),
        ("deleted", _list(diff.get("deleted"))),
    ]
    listing = "; ".join(f"{label} {', '.join(files)}" for label, files in groups if files) or "no changes"
    if d.get("unfinished") is True:
        text = f"Since the unfinished turn before this one: {listing}. The agent may have made some of these changes."
    else:
        text = f"Between turns, outside the agent: {listing}."
    setup = [f for f in _list(d.get("setup_changed")) if isinstance(f, str)]
    if setup:
        text += f" The recording setup changed: {', '.join(setup)}."
    return text


def setup_changed_text(d: dict) -> str:
    """The loud line for a turn in which the recording setup changed."""
    files = [f for f in _list(d.get("files")) if isinstance(f, str)]
    return watch.loud_line(files)


def command_sentence(command) -> str:
    """
    The line for a shell command. Twin of commandSentence in web/src/lib/entryText.ts;
    tests/fixtures/sentences.json holds the cases for both.
    The recorder keeps a command of more than 2000 characters only as
    {"size": bytes, "sha256": ...}, so its text is not in the record and cannot be printed.
    """
    if isinstance(command, str) and command:
        return f"Agent ran the command: {command[:80]}."
    if (
        isinstance(command, dict)
        and isinstance(command.get("size"), int)
        and not isinstance(command.get("size"), bool)
        and command["size"] >= 0
        and isinstance(command.get("sha256"), str)
    ):
        size = command["size"]
        return f"Agent ran a long command. The record keeps its size, {size} {'byte' if size == 1 else 'bytes'}, not its text."
    return "Agent ran a command."


def entry_text(entry: dict) -> str:
    """Plain-language description of one record. `kind` may also be "undeclared"."""
    kind = entry["kind"]
    d = entry["data"]

    if kind == "witness":
        if d.get("event") == "start":
            return "Witness took a snapshot of the project."
        if d.get("event") == "turn":
            return "Witness took a snapshot of the project at the start of this turn."
        if d.get("event") == "between_turns":
            return between_turns_text(d)
        if d.get("event") == "setup_changed":
            return setup_changed_text(d)
        diff = d.get("diff") or {}
        groups = [
            ("Created", _list(diff.get("created"))),
            ("Changed", _list(diff.get("modified"))),
            ("Deleted", _list(diff.get("deleted"))),
        ]
        parts = [f"{label}: {', '.join(files)}." for label, files in groups if files]
        summary = " ".join(parts) if parts else "No changes."
        since = "the snapshot from the start of this turn" if str(d.get("baseline", "")).startswith("turn:") else "the earlier snapshot"
        return f"Witness compared the project to {since}. {summary}"

    if kind == "tool":
        name = str(d.get("tool_name", "unknown"))
        tool_input = d.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}
        if name == "execute_pwsh":
            return command_sentence(tool_input.get("command"))
        verb = TOOL_VERB.get(name)
        if verb:
            path = tool_input.get("path")
            return f"Agent {verb} {path if isinstance(path, str) and path else 'a file'}."
        return f"Agent used a tool: {name}."

    if kind == "statement":
        return f"Agent stated: {d.get('summary', '')}"

    if kind == "verdict":
        if d.get("kind_detail") == "statement_overall":
            return overall_sentence(d.get("verdict"))
        return verdict_sentence(d)

    if kind == "undeclared":
        return undeclared_text(d)

    if kind == "error":
        return f"Something went wrong: {d.get('error', 'unknown error')}."

    return f"Record: {kind}."


def fingerprint_line(entries: list[dict]) -> str:
    """The fingerprint of the whole record and how many lines it has."""
    n = len(entries)
    count = f"{n} line" if n == 1 else f"{n} lines"
    tip = entries[-1]["hash"] if entries else "none yet"
    return f"Fingerprint of the record: {tip} ({count})"


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def _printed_text(entry: dict) -> str:
    """A line as it is printed: verdicts carry their word, as in the report on screen."""
    text = entry_text(entry)
    if entry["kind"] != "verdict":
        return text
    word = verdict_word(entry["data"].get("verdict"))
    return f"{text} ({word})" if is_overall(entry) else f"{word}: {text}"


def _numbered_lines(session_entries: list[dict]) -> list[tuple[str, str]]:
    """(number, text) for each printed line; undeclared lines go just before the overall line."""
    rows: list[tuple[str, str]] = []
    for e in session_entries:
        if is_overall(e):
            for item in e["data"].get("undeclared", []):
                rows.append(("!", undeclared_text(item)))
        rows.append((str(e["seq"]), _printed_text(e)))
    return rows


def _wrap(text: str, width: int, *, break_words: bool = True) -> list[str]:
    return textwrap.wrap(
        text, width=width, break_long_words=break_words, break_on_hyphens=False
    ) or [""]


TEAR = ("- " * 12 + "tear here " + "- " * 12).rstrip()


def render(entries: list[dict], session_id: str, chain: tuple[bool, int | None]) -> str:
    """
    The session as text, from all the record's entries and a chain check result.
    One report per roll (turn). No line is longer than WIDTH characters.
    """
    mine = [e for e in entries if e["session_id"] == session_id]
    session_rolls = rolls.split_session(mine)
    ok, broken_at = chain
    status = "Paper intact" if ok else f"Paper torn at line {broken_at}"

    rows_by_roll = [_numbered_lines(list(r.entries)) for r in session_rolls]
    gutter = max(3, max((len(number) for rows in rows_by_roll for number, _ in rows), default=3)) + 2
    rule = "-" * WIDTH

    out: list[str] = []
    for index, (roll, rows) in enumerate(zip(session_rolls, rows_by_roll)):
        if index:
            out.append(TEAR)
        summaries = [e["data"].get("summary") for e in roll.entries if e["kind"] == "statement"]
        statement = " ".join(str(summaries[-1]).split()) if summaries and summaries[-1] else "none written"
        headers = ["PAPER TRAIL - evidence report", f"Session: {session_id}"]
        if roll.count > 1:
            headers.append(f"Turn: {roll.number} of {roll.count}")
        headers += [f"Statement: {statement}", status]
        for header in headers:
            out.extend(_wrap(header, WIDTH))
        out.append(rule)
        for number, text in rows:
            loud = text.startswith(watch.LOUD_START)  # the setup line stands out on paper
            if loud:
                out.append("*" * WIDTH)
            first, *rest = _wrap(text, WIDTH - gutter)
            out.append(number.rjust(gutter - 2) + "  " + first)
            out.extend(" " * gutter + more for more in rest)
            if loud:
                out.append("*" * WIDTH)
        out.append(rule)

    if not session_rolls:  # a session with no records still prints a heading
        out.extend(_wrap("PAPER TRAIL - evidence report", WIDTH))
        out.extend(_wrap(f"Session: {session_id}", WIDTH))
        out.extend([_wrap("Statement: none written", WIDTH)[0], status, rule, rule])

    # One logical line; at 80 columns the hash and the count land together on the last row.
    out.extend(_wrap(fingerprint_line(entries), WIDTH, break_words=False))
    return "\n".join(out) + "\n"


def render_session(root: Path, session_id: str) -> str:
    """The text for one session of the project at `root`. LookupError if it has no records."""
    if not valid_session_id(session_id):
        raise LookupError(f"{session_id!r} is not a usable session id")
    ledger_path = root / ".papertrail" / "ledger.jsonl"
    entries = ledger.read(ledger_path)
    if not any(e["session_id"] == session_id for e in entries):
        raise LookupError(f"no records found for session {session_id}")
    return render(entries, session_id, ledger.verify_chain(ledger_path))


def spool_path(root: Path, session_id: str) -> Path:
    if not valid_session_id(session_id):
        raise LookupError(f"{session_id!r} is not a usable session id")
    return root / ".papertrail" / "spool" / f"{session_id}.txt"


def write(root: Path, session_id: str) -> Path:
    """Write the session's text file (UTF-8, no byte-order mark, LF) and return its path."""
    text = render_session(root, session_id)
    path = spool_path(root, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path
