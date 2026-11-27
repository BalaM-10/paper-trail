"""Tests for the wording the README and the page must carry (paper-trail-trust, R4)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
OPENING = (
    "Git records what changed. Paper Trail records what the agent claimed, what actually happened, "
    "and whether the two agree."
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_readme_opens_with_the_sentence():
    after_title = README.split("\n", 1)[1].lstrip("\n")
    assert _flat(after_title).startswith(OPENING)


def test_the_page_opens_with_the_same_sentence():
    header = _flat((ROOT / "web" / "src" / "components" / "Header.tsx").read_text(encoding="utf-8"))
    assert OPENING in header
    assert header.index("Paper Trail</p>") < header.index(OPENING) < header.index("<h1>")


def _section(title: str) -> str:
    start = README.index(f"## {title}")
    end = README.find("\n## ", start + 1)
    return README[start:end if end != -1 else None]


def test_what_this_proves_and_what_it_doesnt():
    text = _flat(_section("What this proves, and what it doesn't"))
    for phrase in (
        "Which files were created, changed or deleted in each turn, checked against a snapshot taken outside the agent's own log",
        "Whether each item in the agent's statement matches",
        "Whether the record was edited after it was written",
        "That the code is correct",
        "Anything, if the hooks are removed. No record is not a clean record",
        "unless the final fingerprint was kept somewhere else",
        "The printout ends with the fingerprint for that reason",
    ):
        assert phrase in text, phrase


def test_the_statement_and_what_the_record_keeps_are_said_plainly():
    text = _flat(README)
    assert "The statement is a structured list of files, checked exactly, with no AI judging the result." in text
    assert "The record keeps relative paths, sizes and fingerprints, never file contents or absolute paths." in text


def test_how_this_differs_names_no_product_and_claims_no_first():
    text = _flat(_section("How this differs"))
    for phrase in ("Git commit range", "sign the log of its tool calls", "snapshots the folder at every prompt",
                   "keeps human changes between replies apart from the agent's",
                   "hooks, an MCP server and a power"):
        assert phrase in text, phrase
    lowered = text.lower()
    for word in ("first", "only tool", "unique", "no other"):
        assert word not in lowered, word
    assert len(text.split()) < 90  # a short paragraph


def test_the_loud_line_and_the_key_are_described():
    text = _flat(README)
    assert "RECORDING SETUP CHANGED DURING THIS TURN: <files>. Read this turn's record with care." in text
    assert "EXCEPTIONS ONLY" in README
    assert "paper-trail-trust" in README
    assert "python sample/run_cases.py" in README