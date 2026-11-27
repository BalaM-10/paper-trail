"""Tests for papertrail/privacy.py and for what the recorder lets into the record."""

import itertools
import json
import re
import string
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from papertrail import ledger, privacy
from papertrail.privacy import find, scrub
from sample import export_build_record as export_mod

ROOT = Path(r"C:\work\proj")
HOME = Path(r"C:\Users\alice")
TERMS = {"alice": privacy.USER_LABEL, "box-7": privacy.MACHINE_LABEL}
REAL_IDENTITY_TERMS = privacy.identity_terms  # before the fixture below replaces it


@pytest.fixture(scope="module", autouse=True)
def fixed_names():
    """The recorder asks privacy.identity_terms() for the names; make them these two."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(privacy, "identity_terms", lambda: dict(TERMS))
        yield


def clean(text: str) -> str:
    return scrub(text, ROOT, HOME, TERMS)


# ---------------------------------------------------------------------------
# The project folder and the home folder
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        (r"C:\work\proj\src\a.py", r".\src\a.py"),
        (r"c:\WORK\Proj\src\a.py", r".\src\a.py"),
        ("c:/work/proj/src/a.py", "./src/a.py"),
        ("C:/Work/PROJ", "."),
        (r"C:\\work\\proj\\src\\a.py", r".\\src\\a.py"),  # inside JSON text
        (r"C:\\\\work\\\\proj\\\\x", r".\\\\x"),  # inside JSON text inside JSON text
        (r'{\"cwd\":\"c:\\\\work\\\\proj\"}', r'{\"cwd\":\".\"}'),
        ("file:///c:/work/proj/web/x.js", "file:///./web/x.js"),
        (r"C:\work\project-two\x", r"[path]/x"),  # a longer folder name is not the project
        (r"C:\Users\alice\AppData\Local", r"~\AppData\Local"),
        (r"c:\users\ALICE\x", r"~\x"),
        (r"C:\\Users\\alice\\x", r"~\\x"),
        ("C:/Users/alice", "~"),
    ],
)
def test_the_project_folder_and_the_home_folder(text, expected):
    assert clean(text) == expected


# ---------------------------------------------------------------------------
# Any other absolute path keeps its last part
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        (r"C:\tools\node.exe", "[path]/node.exe"),
        (r"c:\TOOLS\Node.EXE", "[path]/Node.EXE"),
        ("d:/a/b/c.txt", "[path]/c.txt"),
        (r"C:\\tools\\node.exe", "[path]/node.exe"),
        (r"C:\\\\tools\\\\node.exe", "[path]/node.exe"),
        ("D:\\", "[path]\\"),
        ("E:/", "[path]/"),
        (r"\\srv\share\f\x.txt", "[path]/x.txt"),
        (r"\\\\srv\\share\\f\\x.txt", "[path]/x.txt"),
        (r"\\SRV\Share", "[path]/Share"),
        ("file:///C:/Other/dir/x.txt", "file:///[path]/x.txt"),
        ("file:///c:/other/x.txt", "file:///[path]/x.txt"),
        ("file:///home/bob/x", "file:///[path]/x"),
        ("file:///etc/hosts", "file:///[path]/hosts"),
        ("file:///./web/node_modules/x.js", "file:///./web/node_modules/x.js"),
        ("/home/bob/x.txt", "[path]/x.txt"),
        ("ls /var/log/syslog now", "ls [path]/syslog now"),
        ('"/Users/bob/a.txt"', '"[path]/a.txt"'),
        ("cd=/opt/tool/bin", "cd=[path]/bin"),
        ("see C:\\x\\y.txt.", "see [path]/y.txt."),
        ("(C:\\x\\y)", "([path]/y)"),
        (r"C:\Users\ALICE~1\AppData\Local\Temp", "[path]/Temp"),
        (r"C:\Program Files\nodejs", "[path]/Program Files\\nodejs"),  # a path ends at a space
    ],
)
def test_other_absolute_paths(text, expected):
    assert clean(text) == expected


def test_a_path_that_ends_in_an_escaped_quote_keeps_the_quote_escape():
    assert clean(r'{\"p\":\"C:\\tools\\x\"}') == r'{\"p\":\"[path]/x\"}'


# ---------------------------------------------------------------------------
# The names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("hello alice", "hello [user]"),
        ("ALICE and Alice and aLiCe", "[user] and [user] and [user]"),
        ("pytest-of-alice/pytest-1", "pytest-of-[user]/pytest-1"),
        ("host BOX-7 answered", "host [machine] answered"),
        ("box-7.example.org", "[machine].example.org"),
        ("ALICE~1", "[user]"),
        ("alice~12", "[user]"),
    ],
)
def test_the_user_name_and_the_machine_name(text, expected):
    assert clean(text) == expected


def test_names_taken_from_this_machine_are_found():
    terms = {"someone": privacy.USER_LABEL}
    assert scrub("x SOMEONE y", ROOT, HOME, terms) == "x [user] y"
    assert [w for w, *_ in find("x SOMEONE y", terms)] == [privacy.USER_LABEL]


def test_a_user_whose_name_is_a_marker_word_is_not_scrubbed_forever():
    terms = {"user": privacy.USER_LABEL, "path": privacy.USER_LABEL, "machine": privacy.MACHINE_LABEL}
    once = scrub("the user at /home/bob/x on machine", ROOT, HOME, terms)
    assert once == "the [user] at [path]/x on [machine]"
    assert scrub(once, ROOT, HOME, terms) == once
    assert find(once, terms) == []


def test_the_real_names_of_this_machine_come_from_the_system():
    terms = REAL_IDENTITY_TERMS()
    assert terms and all(t == t.lower() and len(t) >= 3 for t in terms)
    assert set(terms.values()) <= {privacy.USER_LABEL, privacy.MACHINE_LABEL}


# ---------------------------------------------------------------------------
# Plain text is left alone
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "",
        "Created: a.md. Changed: b.py.",
        "see https://example.org/a/b and http://localhost:5173/x",
        "ratio a:b and key: value and c: and x:y",
        "12:30:45 and 8:00",
        "src/Users/readme.md and docs/home/index.md",
        "ssh://git@github.com/x/y.git",
        "file:///./web/node_modules/x.js",
        "regex \\d+\\s*\\w and a\\b",
        "[path] [user] [machine] are only words here",
        "unicode caf\u00e9 \u65e5\u672c \U0001f600",
        "a/b/c and ./rel/path and ../up and ~/home-ish",
    ],
)
def test_text_without_any_of_it_is_unchanged(text):
    assert clean(text) == text
    assert find(text, TERMS) == []


def test_scrubbing_twice_changes_nothing_more():
    text = (
        r'C:\Users\alice\x and C:\work\proj\y and D:\tools\z.exe and \\srv\share\q and '
        r'file:///home/bob/f and /var/tmp/g and ALICE~1 and BOX-7'
    )
    once = clean(text)
    assert clean(once) == once
    assert find(once, TERMS) == []


# ---------------------------------------------------------------------------
# find and scrub agree
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,what",
    [
        (r"C:\x", privacy.WHAT_DRIVE),
        ("d:/x", privacy.WHAT_DRIVE),
        (r"\\srv\share", privacy.WHAT_NETWORK),
        (r"\\\\srv\\share", privacy.WHAT_NETWORK),
        ("/home/bob", privacy.WHAT_FOLDER),
        ("x /Users/bob/y", privacy.WHAT_FOLDER),
        ("file:///C:/x/y", privacy.WHAT_DRIVE),
        ("file:///home/x/y", privacy.WHAT_FOLDER),
        ("Alice", privacy.USER_LABEL),
        ("box-7", privacy.MACHINE_LABEL),
        ("ALICE~3", privacy.USER_LABEL),
    ],
)
def test_find_says_what_it_found(text, what):
    assert [w for w, *_ in find(text, TERMS)] == [what]


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

NAME_CHARS = string.ascii_letters + string.digits + "_.-"
names = st.text(alphabet=NAME_CHARS, min_size=1, max_size=8).filter(lambda s: s.strip("."))
separators = st.sampled_from(["\\", "/", "\\\\", "\\\\\\\\"])
letters = st.sampled_from(list(string.ascii_letters))
folders = st.sampled_from(privacy.POSIX_FOLDERS)


@st.composite
def drive_paths(draw):
    sep = draw(separators)
    parts = draw(st.lists(names, min_size=0, max_size=4))
    tail = draw(st.sampled_from(["", sep]))
    return f"{draw(letters)}:{sep}" + sep.join(parts) + (tail if parts else "")


@st.composite
def unc_paths(draw):
    double = draw(st.booleans())
    lead, sep = ("\\\\\\\\", "\\\\") if double else ("\\\\", "\\")
    host, share = draw(names), draw(names)
    rest = draw(st.lists(names, max_size=3))
    return lead + host + sep + share + "".join(sep + p for p in rest)


@st.composite
def posix_paths(draw):
    parts = draw(st.lists(names, min_size=1, max_size=4))
    return "/" + draw(folders) + "/" + "/".join(parts)


@st.composite
def file_addresses(draw):
    inner = draw(st.one_of(drive_paths().map(lambda p: p.replace("\\", "/")), posix_paths().map(lambda p: p[1:])))
    return "file:///" + inner


def case_mixed(word: str):
    return st.lists(st.booleans(), min_size=len(word), max_size=len(word)).map(
        lambda flags: "".join(c.upper() if f else c.lower() for c, f in zip(word, flags))
    )


user_names = st.one_of(case_mixed("alice"), case_mixed("alice~1"), case_mixed("alice~12"))
machine_names = case_mixed("box-7")
the_project = st.sampled_from([r"C:\work\proj\src\a.py", "c:/WORK/proj/x", r"C:\\work\\proj\\y", r"c:\work\proj"])
the_home = st.sampled_from([r"C:\Users\alice\AppData", "c:/users/ALICE/x", r"C:\\Users\\alice\\z", r"C:\Users\Alice"])

private_pieces = st.one_of(
    drive_paths(), unc_paths(), posix_paths(), file_addresses(), user_names, machine_names, the_project, the_home,
)
before = st.sampled_from(["", " ", "\"", "'", "(", "x=", "cd ", "\n", ">", "{\\\""])
after = st.sampled_from(["", " tail", "\"", ".", ",", "\\", "/", ")", ";", "\\\"", " and"])
filler = st.text(alphabet=string.ascii_letters + " ", max_size=10)


@st.composite
def private_text(draw):
    out = [draw(filler)]
    for _ in range(draw(st.integers(1, 3))):
        out += [draw(before), draw(private_pieces), draw(after), draw(filler)]
    return "".join(out)


SLOW = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])


@SLOW
@given(private_text())
def test_property_whatever_is_scrubbed_passes_the_scan(text):
    cleaned = clean(text)
    assert find(cleaned, TERMS) == [], (text, cleaned)
    assert not re.search("alice|box-7", cleaned, re.IGNORECASE)
    assert clean(cleaned) == cleaned  # and cleaning again changes nothing


@SLOW
@given(st.text())
def test_property_what_the_scan_does_not_flag_is_unchanged(text):
    assume(find(text, TERMS) == [])
    assume(not re.search(r"work[\\/]+proj|users[\\/]+alice", text, re.IGNORECASE))  # the two folders
    assert clean(text) == text


@SLOW
@given(st.text(alphabet=string.ascii_letters + string.digits + " .,:;!?-_()[]{}'\"<>=+*#@%&^|\n\t\u00e9\u65e5", max_size=60))
def test_property_text_with_no_slash_and_no_name_is_unchanged(text):
    assume(not re.search("alice|box-7", text, re.IGNORECASE))
    assume(find(text, TERMS) == [])
    assert clean(text) == text


# ---------------------------------------------------------------------------
# The record itself
# ---------------------------------------------------------------------------

def _scan_file(path: Path) -> list:
    lines = path.read_text(encoding="utf-8").splitlines()
    return export_mod.scan(lines, TERMS)


@SLOW
@given(private_text(), private_text(), private_text())
def test_property_the_stored_entry_passes_the_scan(tmp_path_factory, a, b, c):
    folder = tmp_path_factory.mktemp("record")
    path = folder / ".papertrail" / "ledger.jsonl"
    ledger.append(path, "s-" + a, "tool", {"tool_input": {"command": a, b: [c, {"deep": a + b}]}, "tool_response": c})
    ledger.append(path, "s", "error", {"error": b, "raw": json.dumps({"cwd": c, "x": a})})
    assert _scan_file(path) == []
    assert ledger.verify_chain(path) == (True, None)


@SLOW
@given(st.text(alphabet=string.ascii_letters + string.digits + " .,:;!?-_()'\u00e9", max_size=40))
def test_property_text_without_it_is_stored_unchanged(tmp_path_factory, text):
    assume(not re.search("alice|box-7", text, re.IGNORECASE))
    folder = tmp_path_factory.mktemp("plain")
    path = folder / ".papertrail" / "ledger.jsonl"
    entry = ledger.append(path, "s", "tool", {"tool_input": {"command": text}, "list": [text], text: "v"})
    assert entry["data"] == {"tool_input": {"command": text}, "list": [text], text: "v"}


def test_the_recorder_never_stores_the_hooks_raw_input_with_a_path_in_it(tmp_path):
    """The error record that used to keep `raw[:500]` with the working folder and the user name."""
    raw = json.dumps({"cwd": r"C:\Users\alice\work\other", "tool_input": {"path": r"D:\data\secret\x.txt"}})
    path = tmp_path / ".papertrail" / "ledger.jsonl"
    entry = ledger.append(path, "s", "error", {"error": "boom", "raw": raw[:500]})
    stored = json.dumps(entry)
    assert "alice" not in stored.lower()
    assert "D:" not in stored and "secret" not in stored
    assert _scan_file(path) == []


def test_the_recorder_cleans_names_in_keys_and_the_session_id(tmp_path):
    path = tmp_path / ".papertrail" / "ledger.jsonl"
    entry = ledger.append(path, "sess-alice", "witness", {"snapshot": {"notes-of-alice.txt": {"size": 1}}})
    assert entry["session_id"] == "sess-[user]"
    assert list(entry["data"]["snapshot"]) == ["notes-of-[user].txt"]


def test_the_project_folder_is_derived_from_the_record_not_the_working_folder(tmp_path):
    path = tmp_path / ".papertrail" / "ledger.jsonl"
    entry = ledger.append(path, "s", "tool", {"cwd": str(tmp_path), "p": str(tmp_path / "src" / "a.py")})
    assert entry["data"]["cwd"] == "."
    assert entry["data"]["p"].replace("\\", "/") == "./src/a.py"


# ---------------------------------------------------------------------------
# The project folder and the home folder before punctuation (paper-trail-turns R4)
# ---------------------------------------------------------------------------

ENDINGS = [";", ",", ")", "]", "}", "|", ":", "!", "?", "'", '"', "/", "\\", " ", "\n", "\t", ">", "&", "", "."]


@pytest.mark.parametrize(
    "text,expected",
    [
        (r"cd C:\work\proj; ls", "cd .; ls"),
        (r"cd C:\work\proj;ls", "cd .;ls"),
        (r"cd 'C:\work\proj'; python x.py", "cd '.'; python x.py"),
        ('cd "C:\\work\\proj"; python x.py', 'cd "."; python x.py'),
        (r"cd C:\work\proj && dir", "cd . && dir"),
        (r"(C:\work\proj)", "(.)"),
        (r"[C:\work\proj]", "[.]"),
        (r"a,C:/work/proj,b", "a,.,b"),
        (r"x | C:\WORK\PROJ|y", "x | .|y"),
        (r"C:\work\proj.", ".."),
        (r"in C:\work\proj. Then", "in .. Then"),
        (r"cd C:\Users\alice; ls", "cd ~; ls"),
        (r"(C:\Users\alice)", "(~)"),
        (r"cd C:\Users\alice;cd C:\work\proj;ls", "cd ~;cd .;ls"),
        (r"cd C:\\work\\proj\"; ls", r"cd .\"; ls"),
        # a longer or different name is not the project folder
        (r"cd C:\work\proj-two; ls", "cd [path]/proj-two; ls"),
        (r"cd C:\work\proj.old; ls", "cd [path]/proj.old; ls"),
        (r"cd C:\work\proj2; ls", "cd [path]/proj2; ls"),
        (r"cd C:\work\project; ls", "cd [path]/project; ls"),
        # not in the middle of a word
        (r"xC:\work\proj", "xC:\\work\\proj"),
    ],
)
def test_the_project_and_home_folder_before_punctuation(text, expected):
    got = clean(text)
    assert got == expected
    assert find(got, TERMS) == []


def test_the_reported_case_cd_then_semicolon():
    command = r"cd C:\work\proj; python sample/cleanup.py"
    assert clean(command) == "cd .; python sample/cleanup.py"
    assert "[path]" not in clean(command)


@pytest.mark.parametrize("posix_root", ["/home/me/proj", "/srv/app"])
def test_a_posix_project_folder_before_punctuation(posix_root):
    for end in [";", ",", ")", "]", "'", '"', " ", ""]:
        text = f"cd {posix_root}{end} ls"
        assert scrub(text, Path(posix_root), Path("/home/me"), TERMS) == f"cd .{end} ls"
    # a longer name is not the project folder; under the home folder it is still ~/...
    two = scrub(f"cd {posix_root}-two; ls", Path(posix_root), Path("/home/me"), TERMS)
    assert not two.startswith("cd .;") and "-two; ls" in two
    assert scrub("see /home/me;", Path("/srv/app"), Path("/home/me"), TERMS) == "see ~;"


@settings(max_examples=300, deadline=None)
@given(
    ending=st.sampled_from(ENDINGS),
    folder=st.sampled_from(["project", "home"]),
    sep=st.sampled_from(["\\", "/", "\\\\", "\\\\\\\\"]),
    case=st.lists(st.booleans(), min_size=1, max_size=40),
    lead=st.sampled_from(["", "cd ", "x=", "(", "'", '"', "echo ", "\n"]),
    tail=st.text(alphabet=string.ascii_letters + " ", max_size=8),
)
def test_property_the_folders_are_dot_and_tilde_before_any_punctuation(ending, folder, sep, case, lead, tail):
    parts = ["C:", "work", "proj"] if folder == "project" else ["C:", "Users", "alice"]
    flags = itertools.cycle(case)
    written = sep.join("".join(c.upper() if next(flags) else c.lower() for c in part) for part in parts)
    # a full stop or a name character straight after would be a different folder, so only the
    # characters that end a name are tried; "." and "nothing" are followed by a space so they end the name
    follow = ending + (" " if ending in (".", "") else "")
    text = f"{lead}{written}{follow}{tail}"
    expected = f"{lead}{'.' if folder == 'project' else '~'}{follow}{tail}"
    assert clean(text) == expected, (text, clean(text))
    assert find(clean(text), TERMS) == []


@settings(max_examples=200, deadline=None)
@given(
    extra=st.text(alphabet=string.ascii_letters + string.digits + "-_~", min_size=1, max_size=5),
    folder=st.sampled_from([r"C:\work\proj", r"C:\Users\alice"]),
)
def test_property_a_longer_name_is_never_the_project_or_home_folder(extra, folder):
    text = f"cd {folder}{extra}; ls"
    got = clean(text)
    assert not got.startswith("cd .;") and not got.startswith("cd ~;")
    assert find(got, TERMS) == []