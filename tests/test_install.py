"""Tests for papertrail/install.py and the init and doctor subcommands."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from papertrail import install
from papertrail.install import HOOK_FILES, Check, Step

ROOT = Path(__file__).resolve().parents[1]
ENTRY = json.loads((ROOT / "papertrail" / "assets" / "mcp-server.json").read_text(encoding="utf-8"))


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def _statuses(steps: list[Step]) -> dict[str, str]:
    return {s.target: s.status for s in steps}


def _mcp(folder: Path) -> dict:
    return json.loads((folder / ".kiro" / "settings" / "mcp.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# AC1.1a: a fresh folder
# ---------------------------------------------------------------------------

def test_init_on_an_empty_folder_creates_everything(tmp_path):
    steps = install.init(tmp_path)
    assert all(s.status in ("created", "added") for s in steps)
    for name in HOOK_FILES:
        assert (tmp_path / ".kiro" / "hooks" / name).is_file()
    assert (tmp_path / ".kiro" / "steering" / "statement.md").is_file()
    assert _mcp(tmp_path) == {"mcpServers": {"paper-trail": ENTRY}}
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == ".papertrail/\n"
    assert install.succeeded(steps)


def test_nothing_else_is_created(tmp_path):
    install.init(tmp_path)
    names = set(_snapshot(tmp_path))
    expected = {f".kiro/hooks/{n}" for n in HOOK_FILES} | {
        ".kiro/steering/statement.md",
        ".kiro/settings/mcp.json",
        ".gitignore",
    }
    assert names == expected


def test_copied_files_are_the_packaged_ones_with_no_bom_and_lf(tmp_path):
    install.init(tmp_path)
    for name in HOOK_FILES:
        copy = (tmp_path / ".kiro" / "hooks" / name).read_bytes()
        assert copy == (ROOT / "papertrail" / "assets" / "hooks" / name).read_bytes().replace(b"\r\n", b"\n")
    for path in tmp_path.rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            assert not raw.startswith(b"\xef\xbb\xbf")
            assert b"\r" not in raw


# ---------------------------------------------------------------------------
# AC1.1b, AC1.1f: twice changes nothing
# ---------------------------------------------------------------------------

def test_running_twice_changes_nothing(tmp_path):
    install.init(tmp_path)
    before = _snapshot(tmp_path)
    mtimes = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    again = install.init(tmp_path)
    assert {s.status for s in again} == {"unchanged"}
    assert _snapshot(tmp_path) == before
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()} == mtimes


def test_running_twice_with_force_changes_nothing_the_second_time(tmp_path):
    install.init(tmp_path, force=True)
    before = _snapshot(tmp_path)
    again = install.init(tmp_path, force=True)
    assert {s.status for s in again} == {"unchanged"}
    assert _snapshot(tmp_path) == before


def test_an_identical_file_with_windows_line_endings_is_left_alone(tmp_path):
    install.init(tmp_path)
    steering = tmp_path / ".kiro" / "steering" / "statement.md"
    crlf = steering.read_bytes().replace(b"\n", b"\r\n")
    steering.write_bytes(crlf)
    steps = _statuses(install.init(tmp_path))
    assert steps[".kiro/steering/statement.md"] == "unchanged"
    assert steering.read_bytes() == crlf


# ---------------------------------------------------------------------------
# AC1.1c: never overwrite without --force
# ---------------------------------------------------------------------------

def test_a_different_file_is_kept_and_reported(tmp_path):
    hook = tmp_path / ".kiro" / "hooks" / "record.py"
    hook.parent.mkdir(parents=True)
    hook.write_text("# my own version\n", encoding="utf-8")
    steps = install.init(tmp_path)
    assert _statuses(steps)[".kiro/hooks/record.py"] == "kept"
    assert hook.read_text(encoding="utf-8") == "# my own version\n"
    assert not install.succeeded(steps)
    assert "--force" in install.describe(next(s for s in steps if s.status == "kept"))
    # the rest were still set up
    assert (tmp_path / ".kiro" / "hooks" / "witness.py").is_file()


def test_force_replaces_it(tmp_path):
    hook = tmp_path / ".kiro" / "hooks" / "record.py"
    hook.parent.mkdir(parents=True)
    hook.write_text("# my own version\n", encoding="utf-8")
    steps = install.init(tmp_path, force=True)
    assert _statuses(steps)[".kiro/hooks/record.py"] == "replaced"
    assert hook.read_text(encoding="utf-8") != "# my own version\n"
    assert install.succeeded(steps)


def test_a_folder_in_the_way_is_an_error_not_a_crash(tmp_path):
    (tmp_path / ".kiro" / "hooks" / "record.py").mkdir(parents=True)
    steps = _statuses(install.init(tmp_path, force=True))
    assert steps[".kiro/hooks/record.py"] == "error"


# ---------------------------------------------------------------------------
# AC1.1d: mcp.json
# ---------------------------------------------------------------------------

def test_other_servers_and_keys_survive(tmp_path):
    path = tmp_path / ".kiro" / "settings" / "mcp.json"
    path.parent.mkdir(parents=True)
    original = {
        "mcpServers": {"fetch": {"command": "uvx", "args": ["mcp-server-fetch"], "autoApprove": ["fetch"]}},
        "somethingElse": {"keep": [1, 2, 3]},
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    steps = _statuses(install.init(tmp_path))
    assert steps[".kiro/settings/mcp.json"] == "added"
    merged = _mcp(tmp_path)
    assert merged["mcpServers"]["fetch"] == original["mcpServers"]["fetch"]
    assert merged["somethingElse"] == original["somethingElse"]
    assert merged["mcpServers"]["paper-trail"] == ENTRY
    assert list(merged["mcpServers"]) == ["fetch", "paper-trail"]


def test_a_file_without_mcp_servers_gets_the_key(tmp_path):
    path = tmp_path / ".kiro" / "settings" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    install.init(tmp_path)
    assert _mcp(tmp_path) == {"mcpServers": {"paper-trail": ENTRY}}


@pytest.mark.parametrize("bad", ["{ not json", "", "[1, 2]", '{"mcpServers": []}', '"text"'])
def test_a_file_that_is_not_usable_is_not_touched(tmp_path, bad):
    path = tmp_path / ".kiro" / "settings" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(bad, encoding="utf-8")
    steps = install.init(tmp_path)
    assert _statuses(steps)[".kiro/settings/mcp.json"] == "error"
    assert path.read_text(encoding="utf-8") == bad
    assert not install.succeeded(steps)


def test_a_different_paper_trail_server_is_kept_unless_forced(tmp_path):
    path = tmp_path / ".kiro" / "settings" / "mcp.json"
    path.parent.mkdir(parents=True)
    mine = {"mcpServers": {"paper-trail": {"command": "py", "args": ["-m", "papertrail.mcp_server"]}}}
    path.write_text(json.dumps(mine), encoding="utf-8")
    assert _statuses(install.init(tmp_path))[".kiro/settings/mcp.json"] == "kept"
    assert json.loads(path.read_text(encoding="utf-8")) == mine
    assert _statuses(install.init(tmp_path, force=True))[".kiro/settings/mcp.json"] == "replaced"
    assert _mcp(tmp_path)["mcpServers"]["paper-trail"] == ENTRY


def test_a_switched_off_server_counts_as_different(tmp_path):
    path = tmp_path / ".kiro" / "settings" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"paper-trail": {**ENTRY, "disabled": True}}}), encoding="utf-8")
    assert _statuses(install.init(tmp_path))[".kiro/settings/mcp.json"] == "kept"


def test_a_byte_order_mark_is_read_and_not_written_back(tmp_path):
    path = tmp_path / ".kiro" / "settings" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"mcpServers": {"x": {"command": "y"}}}).encode("utf-8"))
    assert _statuses(install.init(tmp_path))[".kiro/settings/mcp.json"] == "added"
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert _mcp(tmp_path)["mcpServers"]["x"] == {"command": "y"}


# ---------------------------------------------------------------------------
# AC1.1e: .gitignore
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line", [".papertrail", ".papertrail/", "/.papertrail", "/.papertrail/", "  .papertrail/  "])
def test_an_equivalent_line_is_enough(tmp_path, line):
    path = tmp_path / ".gitignore"
    path.write_text(f"node_modules/\n{line}\n", encoding="utf-8")
    before = path.read_bytes()
    assert _statuses(install.init(tmp_path))[".gitignore"] == "unchanged"
    assert path.read_bytes() == before


def test_the_line_is_appended_and_the_rest_kept(tmp_path):
    path = tmp_path / ".gitignore"
    path.write_bytes(b"dist/\n*.log")  # no final newline
    assert _statuses(install.init(tmp_path))[".gitignore"] == "added"
    assert path.read_bytes() == b"dist/\n*.log\n.papertrail/\n"


def test_windows_line_endings_are_kept(tmp_path):
    path = tmp_path / ".gitignore"
    path.write_bytes(b"dist/\r\nbuild/\r\n")
    install.init(tmp_path)
    assert path.read_bytes() == b"dist/\r\nbuild/\r\n.papertrail/\r\n"


def test_a_similar_but_different_line_does_not_count(tmp_path):
    path = tmp_path / ".gitignore"
    path.write_text(".papertrail-old/\n# .papertrail/\n", encoding="utf-8")
    assert _statuses(install.init(tmp_path))[".gitignore"] == "added"
    assert path.read_text(encoding="utf-8").splitlines()[-1] == ".papertrail/"


# ---------------------------------------------------------------------------
# AC1.1g: words
# ---------------------------------------------------------------------------

def test_every_step_reads_as_a_plain_sentence(tmp_path):
    steps = install.init(tmp_path)
    again = install.init(tmp_path)
    for step in [*steps, *again]:
        text = install.describe(step)
        assert text and "\n" not in text
        assert str(tmp_path) not in text
    assert "Created .kiro/hooks/record.py" in [install.describe(s) for s in steps]
    assert "Added the paper-trail server to .kiro/settings/mcp.json" not in [install.describe(s) for s in steps]
    assert "Already in place: .gitignore" in [install.describe(s) for s in again]


# ---------------------------------------------------------------------------
# AC1.1h: the folder
# ---------------------------------------------------------------------------

def test_a_missing_folder_is_an_error_and_nothing_is_created(tmp_path):
    target = tmp_path / "nope"
    with pytest.raises(NotADirectoryError):
        install.init(target)
    assert not target.exists()


def test_a_file_is_not_a_folder(tmp_path):
    file = tmp_path / "a-file"
    file.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        install.init(file)


# ---------------------------------------------------------------------------
# Property: whatever mcp.json held, it is still there, and twice is once
# ---------------------------------------------------------------------------

_json_values = st.recursive(
    st.none() | st.booleans() | st.integers(-1000, 1000) | st.text(max_size=12),
    lambda inner: st.lists(inner, max_size=3) | st.dictionaries(st.text(min_size=1, max_size=8), inner, max_size=3),
    max_leaves=8,
)
_servers = st.dictionaries(
    st.text(min_size=1, max_size=10).filter(lambda s: s != "paper-trail"),
    st.dictionaries(st.text(min_size=1, max_size=8), _json_values, max_size=3),
    max_size=4,
)
_other_keys = st.dictionaries(
    st.text(min_size=1, max_size=8).filter(lambda s: s != "mcpServers"), _json_values, max_size=3
)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(servers=_servers, others=_other_keys)
def test_property_nothing_in_mcp_json_is_lost_and_twice_is_once(tmp_path_factory, servers, others):
    folder = tmp_path_factory.mktemp("prop")
    path = folder / ".kiro" / "settings" / "mcp.json"
    path.parent.mkdir(parents=True)
    original = {**others, "mcpServers": servers}
    path.write_text(json.dumps(original), encoding="utf-8")

    install.init(folder)
    merged = _mcp(folder)
    for key, value in others.items():
        assert merged[key] == value
    for name, value in servers.items():
        assert merged["mcpServers"][name] == value
    assert merged["mcpServers"]["paper-trail"] == ENTRY

    before = _snapshot(folder)
    install.init(folder)
    assert _snapshot(folder) == before


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def _probe(found: set[str]):
    def probe(project: Path, module: str):
        return (module in found, "" if module in found else f"python cannot import {module}")

    return probe


def _levels(checks: list[Check]) -> list[str]:
    return [c.level for c in checks]


def test_doctor_on_a_fresh_setup_has_nothing_missing(tmp_path):
    install.init(tmp_path)
    checks = install.doctor(tmp_path, _probe({"papertrail", "mcp"}))
    assert _levels(checks) == ["ok"] * len(checks)
    assert len(checks) == 6 + 1 + 1 + 1 + 2  # hooks, steering, mcp, gitignore, two imports
    assert install.healthy(checks)


def test_doctor_on_an_empty_folder_lists_everything(tmp_path):
    checks = install.doctor(tmp_path, _probe(set()))
    assert _levels(checks) == ["missing"] * len(checks)
    assert not install.healthy(checks)
    text = "\n".join(line for c in checks for line in install.describe_check(c))
    for name in HOOK_FILES:
        assert f".kiro/hooks/{name} is missing" in text
    assert ".kiro/steering/statement.md is missing" in text
    assert "paper-trail server" in text
    assert ".papertrail/ is not in .gitignore" in text
    assert "python cannot import papertrail" in text
    assert "python cannot import mcp" in text
    # AC1.2d: each missing item says how to fix it
    assert all(c.fix for c in checks)
    assert "python -m papertrail init" in text and "pip install" in text


def test_doctor_names_only_what_is_missing(tmp_path):
    install.init(tmp_path)
    (tmp_path / ".kiro" / "hooks" / "witness.py").unlink()
    checks = install.doctor(tmp_path, _probe({"papertrail", "mcp"}))
    missing = [c for c in checks if c.level == "missing"]
    assert [c.label for c in missing] == [".kiro/hooks/witness.py is missing"]


def test_a_changed_file_and_a_switched_off_server_are_warnings(tmp_path):
    install.init(tmp_path)
    (tmp_path / ".kiro" / "hooks" / "record.py").write_text("# mine\n", encoding="utf-8")
    path = tmp_path / ".kiro" / "settings" / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"paper-trail": {**ENTRY, "disabled": True}}}), encoding="utf-8")
    checks = install.doctor(tmp_path, _probe({"papertrail", "mcp"}))
    warns = [c.label for c in checks if c.level == "warn"]
    assert ".kiro/hooks/record.py is different from Paper Trail's version" in warns
    assert any("switched off" in w for w in warns)
    assert install.healthy(checks)  # warnings do not fail


def test_a_mcp_file_that_cannot_be_read_is_missing(tmp_path):
    install.init(tmp_path)
    (tmp_path / ".kiro" / "settings" / "mcp.json").write_text("{ nope", encoding="utf-8")
    checks = install.doctor(tmp_path, _probe({"papertrail", "mcp"}))
    assert [c.level for c in checks if "mcp.json" in c.label] == ["missing"]


def test_hook_errors_are_shown_as_a_warning(tmp_path):
    install.init(tmp_path)
    (tmp_path / ".papertrail").mkdir()
    (tmp_path / ".papertrail" / "hook-errors.txt").write_text(
        "record.py: cannot import papertrail (ModuleNotFoundError: papertrail)\nsecond\n", encoding="utf-8"
    )
    checks = install.doctor(tmp_path, _probe({"papertrail", "mcp"}))
    warn = [c for c in checks if c.level == "warn"]
    assert len(warn) == 1
    assert "cannot import papertrail (ModuleNotFoundError: papertrail)" in warn[0].label
    assert "second" not in warn[0].label


def test_doctor_writes_nothing(tmp_path):
    install.init(tmp_path)
    before = _snapshot(tmp_path)
    install.doctor(tmp_path, _probe({"papertrail"}))
    assert _snapshot(tmp_path) == before
    empty = tmp_path / "empty"
    empty.mkdir()
    install.doctor(empty, _probe(set()))
    assert list(empty.iterdir()) == []


def test_doctor_rejects_a_missing_folder(tmp_path):
    with pytest.raises(NotADirectoryError):
        install.doctor(tmp_path / "nope")


def test_the_real_probe_finds_what_python_can_import(tmp_path):
    ok, _ = install.probe_python(tmp_path, "json")
    assert ok
    ok, reason = install.probe_python(tmp_path, "no_such_module_here")
    assert not ok and "no_such_module_here" in reason


def test_the_probe_reports_a_missing_python(tmp_path, monkeypatch):
    monkeypatch.setattr(install.shutil, "which", lambda name: None)
    ok, reason = install.probe_python(tmp_path, "json")
    assert not ok and "no python command" in reason


# ---------------------------------------------------------------------------
# The command line, end to end (AC1.1h, AC1.2c, AC1.2g)
# ---------------------------------------------------------------------------

def _cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PAPERTRAIL_ROOT"}
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "papertrail", *args], capture_output=True, text=True, cwd=str(cwd), env=env, timeout=120
    )


def test_cli_init_then_doctor(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    first = _cli(["init", str(project)], tmp_path)
    assert first.returncode == 0, first.stderr
    assert "Created .kiro/hooks/record.py" in first.stdout
    assert "Next: run" in first.stdout and "doctor" in first.stdout
    second = _cli(["init", str(project)], tmp_path)
    assert second.returncode == 0
    assert "Created" not in second.stdout
    assert second.stdout.count("Already in place:") == len(HOOK_FILES) + 3

    done = _cli(["doctor", str(project)], tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "MISSING" not in done.stdout  # AC1.2g
    assert "Everything Paper Trail needs is in place." in done.stdout


def test_cli_doctor_fails_on_an_empty_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    result = _cli(["doctor", str(project)], tmp_path)
    assert result.returncode == 1
    assert "MISSING" in result.stdout
    assert "Fix: python -m papertrail init" in result.stdout
    assert list(project.iterdir()) == []


def test_cli_init_exit_codes(tmp_path):
    assert _cli(["init"], tmp_path).returncode == 1
    bad = _cli(["init", str(tmp_path / "nope")], tmp_path)
    assert bad.returncode == 1 and "is not a folder" in bad.stderr
    assert not (tmp_path / "nope").exists()
    project = tmp_path / "proj"
    (project / ".kiro" / "hooks").mkdir(parents=True)
    (project / ".kiro" / "hooks" / "record.py").write_text("# mine\n", encoding="utf-8")
    kept = _cli(["init", str(project)], tmp_path)
    assert kept.returncode == 1 and "--force" in kept.stdout
    assert _cli(["init", str(project), "--force"], tmp_path).returncode == 0


def test_cli_doctor_defaults_to_the_current_folder(tmp_path):
    install.init(tmp_path)
    result = _cli(["doctor"], tmp_path)
    assert "OK      .kiro/hooks/record.py is in place" in result.stdout
