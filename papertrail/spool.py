"""A print-ready text file of one session: plain text, 80 columns, line numbers.

    python -m papertrail print <session_id>   ->   .papertrail/spool/<session_id>.txt

The lines are the sentences the screen prints. `entry_text` and its helpers are
the twin of web/src/lib/entryText.ts; tests/fixtures/sentences.json is read by
tests in both languages, so the two cannot drift apart unnoticed.

The last logical line is the fingerprint of the whole record (the hash of its
last entry) and the number of entries, so a printed page can be checked against
the record later. No file contents and no absolute paths appear here: everything
comes from the ledger, which never holds them.
"""

import textwrap
from pathlib import Path

from papertrail import ledger
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


def entry_text(entry: dict) -> str:
    """Plain-language description of one record. `kind` may also be "undeclared"."""
    kind = entry["kind"]
    d = entry["data"]

    if kind == "witness":
        if d.get("event") == "start":
            return "Witness took a snapshot of the project."
        diff = d.get("diff") or {}
        groups = [
            ("Created", _list(diff.get("created"))),
            ("Changed", _list(diff.get("modified"))),
            ("Deleted", _list(diff.get("deleted"))),
        ]
        parts = [f"{label}: {', '.join(files)}." for label, files in groups if files]
        summary = " ".join(parts) if parts else "No changes."
        return f"Witness compared the project to the earlier snapshot. {summary}"

    if kind == "tool":
        name = str(d.get("tool_name", "unknown"))
        tool_input = d.get("tool_input") or {}
        if name == "execute_pwsh":
            return f"Agent ran the command: {str(tool_input.get('command', ''))[:80]}."
        verb = TOOL_VERB.get(name)
        if verb:
            return f"Agent {verb} {tool_input.get('path', 'a file')}."
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


def render(entries: list[dict], session_id: str, chain: tuple[bool, int | None]) -> str:
    """
    The session as text, from all the record's entries and a chain check result.
    No line is longer than WIDTH characters.
    """
    mine = [e for e in entries if e["session_id"] == session_id]
    summaries = [e["data"].get("summary") for e in mine if e["kind"] == "statement"]
    statement = " ".join(str(summaries[-1]).split()) if summaries and summaries[-1] else "none written"
    ok, broken_at = chain
    status = "Paper intact" if ok else f"Paper torn at line {broken_at}"

    out: list[str] = []
    for header in (
        "PAPER TRAIL - evidence report",
        f"Session: {session_id}",
        f"Statement: {statement}",
        status,
    ):
        out.extend(_wrap(header, WIDTH))
    rule = "-" * WIDTH
    out.append(rule)

    rows = _numbered_lines(mine)
    gutter = max(3, max((len(number) for number, _ in rows), default=3)) + 2
    for number, text in rows:
        first, *rest = _wrap(text, WIDTH - gutter)
        out.append(number.rjust(gutter - 2) + "  " + first)
        out.extend(" " * gutter + more for more in rest)

    out.append(rule)
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
