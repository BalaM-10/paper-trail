"""Tests for papertrail.watch: the recording setup is always snapshotted and changes to it are flagged."""
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from papertrail import ledger, spool, watch
from papertrail.mcp_server import handle_print_session
from papertrail.session import on_start, on_stop, on_turn_start
from papertrail.witness import snapshot

SID = "sess-watch"
PAYLOAD = {"session_id": SID}
HOOK = ".kiro/hooks/record.py"
RULE = ".kiro/steering/statement.md"
MCP = ".kiro/settings/mcp.json"
LOUD = "RECORDING SETUP CHANGED DURING THIS TURN: "


def _put(root: Path, name: str, text: str | None = None) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(name if text is None else text, encoding="utf-8")


def _statement(root: Path, **lists) -> None:
    stmt = {"summary": "Did the work.", "files_read": [], "files_created": [], "files_modified": [],
            "files_deleted": [], **lists}
    _put(root, ".papertrail/statement.json", json.dumps(stmt))


def _entries(root: Path) -> list[dict]:
    return ledger.read(root / ".papertrail" / "ledger.jsonl")


def _setup_entries(root: Path) -> list[dict]:
    return [e for e in _entries(root) if e["kind"] == "witness" and e["data"].get("event") == "setup_changed"]


def _overall(root: Path) -> dict:
    return [e for e in _entries(root) if e["kind"] == "verdict" and e["data"].get("kind_detail") == "statement_overall"][-1]["data"]


def _project(root: Path) -> None:
    for name in (HOOK, ".kiro/hooks/witness.py", ".kiro/hooks/record-post-tool-use.json", RULE, MCP, "src/app.py"):
        _put(root, name)


# ---------------------------------------------------------------------------
# What counts as the setup
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    ".kiro/hooks/record.py", ".kiro/hooks/a/b/deep.json", ".kiro/steering/statement.md",
    ".kiro/settings/mcp.json", ".kiro\\hooks\\record.py", "./.kiro/settings/mcp.json",
])
def test_these_are_the_setup(path):
    assert watch.is_setup(path)


@pytest.mark.parametrize("path", [
    ".kiro/steering/product.md", ".kiro/specs/x/design.md", ".kiro/hooks", "kiro/hooks/a.py",
    "src/.kiro/hooks/a.py", "sample/notes.txt", ".kiro/settings/other.json", ".kiro/hooksX/a.py",
])
def test_these_are_not(path):
    assert not watch.is_setup(path)


def test_setup_paths_lists_what_exists_and_skips_python_caches(tmp_path):
    _project(tmp_path)
    _put(tmp_path, ".kiro/hooks/__pycache__/record.cpython-311.pyc")
    _put(tmp_path, ".kiro/hooks/old.pyc")
    assert watch.setup_paths(tmp_path) == sorted([
        HOOK, ".kiro/hooks/witness.py", ".kiro/hooks/record-post-tool-use.json", RULE, MCP,
    ])


def test_setup_paths_of_a_project_without_a_kiro_folder_is_empty(tmp_path):
    assert watch.setup_paths(tmp_path) == []


def test_changed_files_picks_out_the_setup_and_lists_each_once():
    diff = {"created": ["a.txt", HOOK], "modified": [HOOK, MCP], "deleted": [RULE, "b.txt"]}
    assert watch.changed_files(diff) == sorted([HOOK, MCP, RULE])
    assert watch.setup_changes(diff) == {"created": [HOOK], "modified": sorted([HOOK, MCP]), "deleted": [RULE]}
    assert watch.changed_files({"created": [], "modified": ["a"], "deleted": []}) == []


@given(st.lists(st.text(alphabet="ab/.", max_size=12), max_size=8))
@settings(max_examples=100, deadline=None)
def test_property_changed_files_only_holds_setup_paths_and_never_raises(paths):
    files = watch.changed_files({"created": paths, "modified": [], "deleted": paths})
    assert all(watch.is_setup(f) for f in files)
    assert files == sorted(set(files))


def test_the_loud_line_has_the_exact_words():
    assert watch.loud_line([HOOK, MCP]) == (
        f"RECORDING SETUP CHANGED DURING THIS TURN: {HOOK}, {MCP}. Read this turn's record with care."
    )


# ---------------------------------------------------------------------------
# Always snapshotted, even where .gitignore would skip it
# ---------------------------------------------------------------------------

def test_the_setup_is_in_the_snapshot_even_when_gitignore_skips_the_kiro_folder(tmp_path):
    _project(tmp_path)
    (tmp_path / ".gitignore").write_text(".kiro/\n", encoding="utf-8")
    snap = snapshot(tmp_path)
    for name in (HOOK, ".kiro/hooks/witness.py", RULE, MCP):
        assert name in snap
    assert "src/app.py" in snap


def test_other_kiro_files_follow_gitignore_as_before(tmp_path):
    _project(tmp_path)
    _put(tmp_path, ".kiro/specs/x/design.md")
    (tmp_path / ".gitignore").write_text(".kiro/\n", encoding="utf-8")
    assert ".kiro/specs/x/design.md" not in snapshot(tmp_path)


# ---------------------------------------------------------------------------
# During a turn
# ---------------------------------------------------------------------------

def test_a_setup_change_in_a_turn_is_recorded_on_its_own_line_when_the_agent_declares_it(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, HOOK, "changed")
    _statement(tmp_path, files_modified=[HOOK])
    stop = on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    (setup,) = _setup_entries(tmp_path)
    assert setup["kind"] == "witness"  # fits the existing kinds
    assert setup["data"]["files"] == [HOOK]
    assert setup["data"]["diff"] == {"created": [], "modified": [HOOK], "deleted": []}
    assert setup["data"]["witness_seq"] == stop["seq"] and setup["data"]["evidence_seq"] == [stop["seq"]]
    assert setup["seq"] == stop["seq"] + 1
    assert _overall(tmp_path)["verdict"] == "SUPPORTED"  # the verdict itself is not touched


def test_the_line_is_recorded_when_the_agent_did_not_declare_the_change_too(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, RULE, "changed")
    _put(tmp_path, "made.txt")
    _statement(tmp_path, files_created=["made.txt"])
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    (setup,) = _setup_entries(tmp_path)
    assert setup["data"]["files"] == [RULE]
    overall = _overall(tmp_path)
    assert overall["verdict"] == "CONTRADICTED"
    assert overall["undeclared"] == [{"path": RULE, "change": "modified"}]


def test_the_line_is_recorded_when_there_is_no_statement_at_all(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    (tmp_path / MCP).unlink()
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    (setup,) = _setup_entries(tmp_path)
    assert setup["data"]["files"] == [MCP]
    assert setup["data"]["diff"]["deleted"] == [MCP]
    assert _overall(tmp_path)["verdict"] == "NO_STATEMENT"


def test_created_changed_and_deleted_are_all_listed_together(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, ".kiro/hooks/new.py")
    _put(tmp_path, HOOK, "changed")
    (tmp_path / MCP).unlink()
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    (setup,) = _setup_entries(tmp_path)
    assert setup["data"]["files"] == sorted([".kiro/hooks/new.py", HOOK, MCP])


def test_a_change_that_gitignore_would_skip_is_still_flagged(tmp_path):
    _project(tmp_path)
    (tmp_path / ".gitignore").write_text(".kiro/\n", encoding="utf-8")
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, HOOK, "changed")
    _statement(tmp_path, files_modified=[HOOK])
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    assert [e["data"]["files"] for e in _setup_entries(tmp_path)] == [[HOOK]]
    assert _overall(tmp_path)["verdict"] == "SUPPORTED"  # judged on the witness, not UNVERIFIED


def test_nothing_is_recorded_when_the_setup_did_not_change(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, "made.txt")
    _statement(tmp_path, files_created=["made.txt"])
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    assert _setup_entries(tmp_path) == []


def test_other_kiro_files_changing_do_not_count_as_the_setup(tmp_path):
    _project(tmp_path)
    _put(tmp_path, ".kiro/specs/x/design.md", "a")
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, ".kiro/specs/x/design.md", "b")
    _put(tmp_path, ".kiro/steering/product.md", "b")
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    assert _setup_entries(tmp_path) == []


def test_the_chain_is_intact_with_the_new_line(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, HOOK, "changed")
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    assert ledger.verify_chain(tmp_path / ".papertrail" / "ledger.jsonl") == (True, None)


def test_the_record_holds_no_content_and_no_absolute_path(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, HOOK, "SECRET-TEXT-IN-THE-HOOK")
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    text = (tmp_path / ".papertrail" / "ledger.jsonl").read_text(encoding="utf-8")
    assert "SECRET-TEXT-IN-THE-HOOK" not in text
    assert str(tmp_path) not in text and str(tmp_path).replace("\\", "\\\\") not in text


# ---------------------------------------------------------------------------
# Between turns
# ---------------------------------------------------------------------------

def test_a_setup_change_between_turns_is_said_in_the_between_turns_line(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    on_turn_start(PAYLOAD, tmp_path, tmp_path / "home")
    _statement(tmp_path)
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, HOOK, "a person edited the hook")  # a person, between the replies
    _put(tmp_path, "notes.txt")
    on_turn_start(PAYLOAD, tmp_path, tmp_path / "home")
    (between,) = [e for e in _entries(tmp_path) if e["data"].get("event") == "between_turns"]
    assert between["data"]["setup_changed"] == [HOOK]
    assert sorted(between["data"]["diff"]["created"] + between["data"]["diff"]["modified"]) == sorted(["notes.txt", HOOK])
    assert spool.entry_text(between).endswith(f" The recording setup changed: {HOOK}.")
    assert _setup_entries(tmp_path) == []  # it is not the agent's turn: no loud line


def test_a_between_turns_line_without_a_setup_change_has_no_such_field(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, "notes.txt")
    on_turn_start(PAYLOAD, tmp_path, tmp_path / "home")
    (between,) = [e for e in _entries(tmp_path) if e["data"].get("event") == "between_turns"]
    assert "setup_changed" not in between["data"]
    assert "recording setup" not in spool.entry_text(between)


def test_the_between_turns_change_is_not_blamed_on_the_next_turn(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    on_turn_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, HOOK, "a person edited the hook")
    on_turn_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, "made.txt")
    _statement(tmp_path, files_created=["made.txt"])
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    assert _setup_entries(tmp_path) == []
    assert _overall(tmp_path)["verdict"] == "SUPPORTED"


# ---------------------------------------------------------------------------
# Printed: the print file, and print_session over MCP
# ---------------------------------------------------------------------------

def _changed_session(root: Path) -> None:
    _project(root)
    on_start(PAYLOAD, root, root / "home")
    _put(root, HOOK, "changed")
    _put(root, MCP, "changed")
    _statement(root, files_modified=[HOOK, MCP])
    on_stop(PAYLOAD, root, root / "home")


def test_the_print_file_carries_the_loud_line_on_a_line_of_its_own(tmp_path):
    _changed_session(tmp_path)
    text = spool.render_session(tmp_path, SID)
    lines = text.split("\n")
    assert all(len(line) <= spool.WIDTH for line in lines)
    start = next(i for i, line in enumerate(lines) if LOUD in line)
    assert lines[start - 1] == "*" * spool.WIDTH
    block = []
    for line in lines[start:]:
        if line == "*" * spool.WIDTH:
            break
        block.append(line.strip())
    sentence = " ".join(" ".join(block).split())
    sentence = sentence.split(" ", 1)[1]  # drop the line number
    assert sentence == watch.loud_line([HOOK, MCP])


def test_print_session_over_mcp_returns_the_same_loud_line(tmp_path):
    _changed_session(tmp_path)
    assert handle_print_session(tmp_path, SID) == spool.render_session(tmp_path, SID)
    assert LOUD in handle_print_session(tmp_path, SID)


def test_a_turn_with_no_setup_change_prints_no_loud_line(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, "made.txt")
    _statement(tmp_path, files_created=["made.txt"])
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    text = spool.render_session(tmp_path, SID)
    assert LOUD not in text and "*" * 10 not in text


def test_the_loud_line_belongs_to_the_turn_it_happened_in(tmp_path):
    _project(tmp_path)
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    on_turn_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, HOOK, "changed")
    _statement(tmp_path, files_modified=[HOOK])
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    on_turn_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, "made.txt")
    _statement(tmp_path, files_created=["made.txt"])
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    first, second = spool.render_session(tmp_path, SID).split(spool.TEAR)
    assert LOUD in first and LOUD not in second


def test_the_demo_record_has_a_session_that_shows_the_line():
    demo = Path(__file__).resolve().parents[1] / "web" / "public" / "demo" / "ledger.jsonl"
    entries = [json.loads(line) for line in demo.read_text(encoding="utf-8").splitlines() if line.strip()]
    text = spool.render(entries, "demo-session-e", ledger.verify_chain(demo))
    assert LOUD + HOOK + ". Read this turn's record with care." in " ".join(text.split())
