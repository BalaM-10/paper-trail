"""Tests for papertrail.ignore and what it does to the witness and the verifier."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from papertrail import ledger
from papertrail.ignore import BUILTIN, RULE_NAME, Matcher
from papertrail.session import on_start, on_stop
from papertrail.witness import snapshot

SID = "sess-ignore"
PAYLOAD = {"session_id": SID}


def ignored(lines: list[str], path: str, is_dir: bool = False) -> bool:
    return Matcher(lines).is_ignored(path, is_dir)


# ---------------------------------------------------------------------------
# The matcher: the cases a .gitignore is made of
# ---------------------------------------------------------------------------

def test_a_name_matches_at_every_depth():
    assert ignored(["secret.txt"], "secret.txt")
    assert ignored(["secret.txt"], "a/b/secret.txt")
    assert not ignored(["secret.txt"], "a/b/not-secret.txt")


def test_a_folder_name_with_a_slash_at_the_end_matches_folders_only():
    assert ignored(["out/"], "out", True)
    assert not ignored(["out/"], "out", False)  # a file called out
    assert ignored(["out/"], "out/a.txt")  # a file inside the folder
    assert ignored(["out/"], "src/out/a.txt")


def test_a_slash_in_the_middle_anchors_to_the_project_folder():
    assert ignored(["docs/build"], "docs/build")
    assert not ignored(["docs/build"], "src/docs/build")
    assert ignored(["/todo.txt"], "todo.txt")
    assert not ignored(["/todo.txt"], "sub/todo.txt")


def test_star_and_question_mark_never_cross_a_slash():
    assert ignored(["*.log"], "a/b/run.log")
    assert ignored(["src/*.tmp"], "src/x.tmp")
    assert not ignored(["src/*.tmp"], "src/deep/x.tmp")
    assert ignored(["f?.txt"], "fa.txt")
    assert not ignored(["f?.txt"], "fab.txt")


def test_character_classes():
    assert ignored(["file[0-9].txt"], "file7.txt")
    assert not ignored(["file[0-9].txt"], "filex.txt")
    assert ignored(["file[!0-9].txt"], "filex.txt")
    assert not ignored(["file[!0-9].txt"], "file7.txt")
    assert ignored(["a[b"], "a[b")  # an unclosed class is a plain character


def test_double_star():
    assert ignored(["**/logs"], "logs")
    assert ignored(["**/logs"], "a/b/logs")
    assert ignored(["logs/**"], "logs/a.txt")
    assert ignored(["logs/**"], "logs/a/b.txt")
    assert not ignored(["logs/**"], "logs", False)
    assert ignored(["a/**/z"], "a/z")
    assert ignored(["a/**/z"], "a/b/c/z")
    assert not ignored(["a/**/z"], "b/a/z")


def test_the_last_matching_line_wins_and_negation_brings_a_file_back():
    assert not ignored(["*.log", "!keep.log"], "keep.log")
    assert ignored(["*.log", "!keep.log"], "other.log")
    assert ignored(["!keep.log", "*.log"], "keep.log")


def test_a_file_inside_an_ignored_folder_cannot_be_brought_back():
    assert ignored(["cache/", "!cache/keep.txt"], "cache/keep.txt")
    assert not ignored(["cache/*", "!cache/keep.txt"], "cache/keep.txt")


def test_comments_blank_lines_and_escapes():
    assert not ignored(["# not a rule", "", "   "], "# not a rule")
    assert ignored(["\\#hash"], "#hash")
    assert ignored(["\\!bang"], "!bang")
    assert ignored(["trail\\ "], "trail ")
    assert ignored(["plain   "], "plain")  # unescaped trailing spaces are dropped


def test_windows_line_endings_and_backslashes_in_the_path():
    assert ignored(["out/\r"], "out/a.txt")
    assert ignored(["out/"], "out\\a.txt")
    assert ignored(["out/"], "./out/a.txt")


def test_letter_case_follows_the_flag():
    assert not Matcher(["Build/"]).is_ignored("build/x")
    assert Matcher(["Build/"], ignore_case=True).is_ignored("build/x")


def test_bad_lines_do_not_raise():
    m = Matcher(["[", "[]", "[z-a]", "**", "***", "\\", "!", "/", "a//b", "(", "{", "a**b"])
    m.is_ignored("a/b")


# ---------------------------------------------------------------------------
# The same answers as git (skipped when git is not installed)
# ---------------------------------------------------------------------------

GIT_RULES = [
    "*.log", "!keep.log", "build-out/", "/rooted.txt", "docs/gen", "**/deep", "tmp/**",
    "a/**/z", "file[0-9].txt", "q?.md", "# comment", "", "\\#lit", "src/*.o",
]
GIT_PATHS = [
    "x.log", "keep.log", "sub/keep.log", "build-out/a.txt", "sub/build-out/a.txt", "rooted.txt",
    "sub/rooted.txt", "docs/gen", "sub/docs/gen", "deep", "a/deep", "tmp/a.txt", "tmp",
    "a/z", "a/b/z", "b/a/z", "file7.txt", "filex.txt", "qa.md", "qab.md", "#lit", "src/x.o",
    "src/sub/x.o", "plain.txt",
]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_matcher_agrees_with_git(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("\n".join(GIT_RULES) + "\n", encoding="utf-8")
    matcher = Matcher(GIT_RULES)
    for path in GIT_PATHS:
        git = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", "--", path], cwd=tmp_path
        ).returncode == 0
        assert matcher.is_ignored(path) == git, path


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

WORD = st.text(alphabet="abxyz", min_size=1, max_size=4)
PATH = st.lists(WORD, min_size=1, max_size=4).map("/".join)
LINE = st.one_of(
    st.text(max_size=12),
    st.builds(lambda a, b: f"{a}/{b}", WORD, WORD),
    st.builds(lambda a: f"*{a}", WORD),
    st.builds(lambda a: f"!{a}", WORD),
    st.builds(lambda a: f"{a}/", WORD),
    st.builds(lambda a: f"**/{a}", WORD),
    st.builds(lambda a: f"{a}/**", WORD),
)


@given(st.lists(st.text(max_size=20), max_size=8), st.text(max_size=30), st.booleans())
@settings(max_examples=200, deadline=None)
def test_property_the_matcher_never_raises_on_any_text(lines, path, is_dir):
    Matcher(lines).is_ignored(path, is_dir)
    Matcher(lines, ignore_case=True).matches(path, is_dir)


@given(st.lists(LINE, max_size=8), PATH, st.booleans())
@settings(max_examples=200, deadline=None)
def test_property_the_same_question_gets_the_same_answer(lines, path, is_dir):
    first = Matcher(lines).is_ignored(path, is_dir)
    assert Matcher(lines).is_ignored(path, is_dir) == first
    assert Matcher(tuple(lines)).is_ignored(path, is_dir) == first


@given(st.lists(LINE, max_size=6), PATH, st.booleans(), st.lists(st.sampled_from(["", "   ", "# a note", "#x"]), max_size=4))
@settings(max_examples=200, deadline=None)
def test_property_blank_and_comment_lines_change_nothing(lines, path, is_dir, noise):
    mixed = [n for pair in zip(lines, noise + [""] * len(lines)) for n in pair] + noise
    assert Matcher(mixed).is_ignored(path, is_dir) == Matcher(lines).is_ignored(path, is_dir)


@given(WORD, PATH, st.booleans())
@settings(max_examples=200, deadline=None)
def test_property_a_plain_name_is_ignored_at_every_depth(name, parents, is_dir):
    path = f"{parents}/{name}"
    assert Matcher([name]).is_ignored(path, is_dir)
    assert Matcher([name]).is_ignored(name, is_dir)


@given(st.lists(WORD, min_size=0, max_size=3), WORD, PATH, st.booleans(),
       st.lists(st.tuples(st.booleans(), st.sampled_from(["", "**/"]), st.text(alphabet="xyz", min_size=1, max_size=3)), max_size=4))
@settings(max_examples=200, deadline=None)
def test_property_a_file_under_an_ignored_folder_stays_ignored(before, rest, more, is_dir, later):
    # the folder name "cache" shares no letter with the later lines (x, y, z), so none of
    # them can match the folder itself; only the folder rule decides about it
    lines = [*before, "cache/"] + [f"{'!' if neg else ''}{prefix}{name}" for neg, prefix, name in later]
    lines += [f"!cache/{rest}"]
    assert Matcher(lines).is_ignored(f"cache/{more}", is_dir)


@given(WORD, st.lists(WORD, max_size=2), st.booleans())
@settings(max_examples=200, deadline=None)
def test_property_a_negation_of_the_same_pattern_brings_the_path_back(name, parents, as_folder_rule):
    pattern = f"{name}/" if as_folder_rule else name
    path = "/".join([*parents, name])
    assert Matcher([pattern]).is_ignored(path, as_folder_rule)
    assert not Matcher([pattern, f"!{pattern}"]).is_ignored(path, as_folder_rule)


# ---------------------------------------------------------------------------
# Matcher.load and the snapshot
# ---------------------------------------------------------------------------

def _put(root: Path, *names: str) -> None:
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(name, encoding="utf-8")


def test_the_built_in_list_is_skipped_without_a_gitignore(tmp_path):
    _put(tmp_path, "real.py", ".hypothesis/examples/a", ".pytest_cache/v/cache/lastfailed",
         ".mypy_cache/x.json", "pkg/mod.pyc", "pkg/__pycache__/mod.pyc", ".idea/workspace.xml",
         "notes.txt~", ".DS_Store", "web/.eslintcache", "web/tsconfig.tsbuildinfo", ".coverage",
         "pkg.egg-info/PKG-INFO", ".vscode/settings.json")
    assert sorted(snapshot(tmp_path)) == [".vscode/settings.json", "real.py"]


def test_the_gitignore_is_followed(tmp_path):
    _put(tmp_path, "real.py", "scratch/a.txt", "logs/run.log", "logs/keep.log", "top.tmp", "sub/top.tmp")
    (tmp_path / ".gitignore").write_text("scratch/\n*.log\n!keep.log\n/top.tmp\n", encoding="utf-8")
    assert sorted(snapshot(tmp_path)) == [".gitignore", "logs/keep.log", "real.py", "sub/top.tmp"]


def test_a_gitignore_with_a_byte_order_mark_and_odd_bytes_is_still_read(tmp_path):
    _put(tmp_path, "real.py", "scratch/a.txt")
    (tmp_path / ".gitignore").write_bytes(b"\xef\xbb\xbfscratch/\r\n\xff\xfe junk\r\n")
    assert sorted(snapshot(tmp_path)) == [".gitignore", "real.py"]


def test_a_gitignore_line_can_bring_a_built_in_folder_back(tmp_path):
    _put(tmp_path, ".cache/a.txt", "real.py")
    (tmp_path / ".gitignore").write_text("!.cache/\n", encoding="utf-8")
    assert ".cache/a.txt" in snapshot(tmp_path)


def test_the_old_excluded_folders_cannot_be_brought_back(tmp_path):
    _put(tmp_path, "node_modules/p/i.js", "dist/a.js", ".papertrail/x", "real.py")
    (tmp_path / ".gitignore").write_text("!node_modules/\n!dist/\n!.papertrail/\n", encoding="utf-8")
    assert sorted(snapshot(tmp_path)) == [".gitignore", "real.py"]


def test_a_nested_gitignore_is_not_read(tmp_path):
    _put(tmp_path, "sub/a.txt", "sub/b.txt")
    (tmp_path / "sub" / ".gitignore").write_text("a.txt\n", encoding="utf-8")
    assert "sub/a.txt" in snapshot(tmp_path)


def test_every_builtin_line_is_a_rule():
    assert len(BUILTIN) == len(set(BUILTIN))
    m = Matcher(BUILTIN)
    assert m.is_ignored(".pytest_cache/x") and m.is_ignored(".hypothesis/x")


def test_the_snapshot_never_stores_what_it_skipped(tmp_path):
    _put(tmp_path, "real.py", ".hypothesis/secret-name-a", "scratch/secret-name-b")
    (tmp_path / ".gitignore").write_text("scratch/\n", encoding="utf-8")
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    text = (tmp_path / ".papertrail" / "ledger.jsonl").read_text(encoding="utf-8")
    assert "secret-name" not in text
    assert "scratch" not in text  # not even the pattern
    (start,) = ledger.read(tmp_path / ".papertrail" / "ledger.jsonl")
    assert start["data"]["ignore"] == RULE_NAME


# ---------------------------------------------------------------------------
# AC1.7: the case that was reported
# ---------------------------------------------------------------------------

def _statement(root: Path, **lists) -> None:
    stmt = {"summary": "Did the work.", "files_read": [], "files_created": [], "files_modified": [],
            "files_deleted": [], **lists}
    (root / ".papertrail").mkdir(parents=True, exist_ok=True)
    (root / ".papertrail" / "statement.json").write_text(json.dumps(stmt), encoding="utf-8")


def _overall(root: Path) -> dict:
    entries = ledger.read(root / ".papertrail" / "ledger.jsonl")
    return [e for e in entries if e["kind"] == "verdict" and e["data"].get("kind_detail") == "statement_overall"][-1]["data"]


def _test_run_then_honest_statement(root: Path, cache: str) -> None:
    """A test run leaves about 50 cache files; the agent made one real file and says only that."""
    _put(root, "keep.txt")
    on_start(PAYLOAD, root, root / "home")
    for i in range(30):
        _put(root, f"{cache}/examples/{i:02d}/entry")
    for i in range(20):
        _put(root, f".pytest_cache/v/cache/item{i:02d}")
    _put(root, "real.py")
    _statement(root, files_created=["real.py"])
    on_stop(PAYLOAD, root, root / "home")


def test_cache_files_from_a_test_run_do_not_contradict_an_honest_statement(tmp_path):
    (tmp_path / ".gitignore").write_text(".hypothesis/\n.pytest_cache/\n", encoding="utf-8")
    _test_run_then_honest_statement(tmp_path, ".hypothesis")
    overall = _overall(tmp_path)
    assert overall["verdict"] == "SUPPORTED"
    assert overall["undeclared"] == []


def test_the_built_in_list_alone_is_enough_without_a_gitignore(tmp_path):
    _test_run_then_honest_statement(tmp_path, ".hypothesis")
    assert _overall(tmp_path)["verdict"] == "SUPPORTED"


def test_control_a_folder_that_no_rule_names_is_still_counted(tmp_path):
    _test_run_then_honest_statement(tmp_path, "scratch-output")
    overall = _overall(tmp_path)
    assert overall["verdict"] == "CONTRADICTED"
    assert len(overall["undeclared"]) == 30
    assert all(u["path"].startswith("scratch-output/") for u in overall["undeclared"])


def test_the_same_folder_named_in_the_gitignore_is_not_counted(tmp_path):
    (tmp_path / ".gitignore").write_text("scratch-output/\n", encoding="utf-8")
    _test_run_then_honest_statement(tmp_path, "scratch-output")
    assert _overall(tmp_path)["verdict"] == "SUPPORTED"


def test_a_snapshot_from_before_the_rule_does_not_report_cache_files_as_deleted(tmp_path):
    # an old record: its snapshot lists a cache file, and has no "ignore" field
    _put(tmp_path, "keep.txt", ".hypothesis/old")
    lp = tmp_path / ".papertrail" / "ledger.jsonl"
    lp.parent.mkdir(parents=True)
    old = {"keep.txt": {"size": 8, "sha256": "x"}, ".hypothesis/old": {"size": 15, "sha256": "y"}}
    ledger.append(lp, SID, "witness", {"event": "start", "snapshot": old})
    (tmp_path / "keep.txt").write_text("keep.txt", encoding="utf-8")  # same text, same size
    shutil.rmtree(tmp_path / ".hypothesis")
    _statement(tmp_path)
    stop = on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    assert ".hypothesis/old" not in stop["data"]["diff"]["deleted"]


# ---------------------------------------------------------------------------
# AC1.4: a claim about a skipped path is UNVERIFIED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("claim", ["files_created", "files_modified", "files_deleted"])
def test_a_claim_about_a_skipped_path_stays_unverified(tmp_path, claim):
    (tmp_path / ".gitignore").write_text("scratch/\n", encoding="utf-8")
    _put(tmp_path, "real.py")
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, "made.py", "scratch/a.txt", ".hypothesis/b")
    lists = {"files_created": ["made.py"], "files_modified": [], "files_deleted": []}
    lists[claim] = lists[claim] + ["scratch/a.txt", ".hypothesis/b"]
    _statement(tmp_path, **lists)
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    entries = ledger.read(tmp_path / ".papertrail" / "ledger.jsonl")
    verdicts = {
        (e["data"]["claim"], e["data"]["path"]): e["data"]["verdict"]
        for e in entries
        if e["kind"] == "verdict" and "path" in e["data"]
    }
    skipped = [v for (c, p), v in verdicts.items() if "scratch" in p or "hypothesis" in p]
    assert skipped and set(skipped) == {"UNVERIFIED"}
    assert verdicts[("files_created", "made.py")] == "SUPPORTED"
    assert _overall(tmp_path)["verdict"] == "UNVERIFIED"


def test_a_claim_about_a_path_the_rule_does_not_skip_is_judged_as_before(tmp_path):
    (tmp_path / ".gitignore").write_text("scratch/\n", encoding="utf-8")
    on_start(PAYLOAD, tmp_path, tmp_path / "home")
    _put(tmp_path, "made.py")
    _statement(tmp_path, files_created=["made.py", "never-made.py"])
    on_stop(PAYLOAD, tmp_path, tmp_path / "home")
    overall = _overall(tmp_path)
    assert overall["verdict"] == "CONTRADICTED"


def test_a_record_without_the_ignore_field_is_judged_as_before(tmp_path):
    """The old behaviour: a claim about a path in .hypothesis is judged by the diff."""
    from papertrail import verifier

    lp = tmp_path / ".papertrail" / "ledger.jsonl"
    lp.parent.mkdir(parents=True)
    stop = ledger.append(lp, SID, "witness", {
        "event": "stop", "snapshot": {}, "baseline": "start",
        "diff": {"created": [".hypothesis/a"], "modified": [], "deleted": []},
    })
    stmt = {"files_read": [], "files_created": [".hypothesis/a"], "files_modified": [], "files_deleted": [],
            "witness_seq": stop["seq"]}
    result = verifier.verify(stmt, ledger.read(lp), SID, ledger_path=lp)
    assert result["verdicts"][0]["verdict"] == "SUPPORTED"
