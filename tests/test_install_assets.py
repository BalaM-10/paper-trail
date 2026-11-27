"""The files `init` copies, and the hook scripts that ship with them."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from papertrail import ledger

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "papertrail" / "assets"
HOOK_FILES = [
    "record-post-tool-use.json",
    "record-file-delete.json",
    "witness-session-start.json",
    "witness-stop.json",
    "record.py",
    "witness.py",
]


def _text(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


@pytest.mark.parametrize("name", HOOK_FILES)
def test_the_repository_hooks_are_the_packaged_files(name):
    """AC1.1j: this repository's own hooks cannot drift from what init copies."""
    assert _text(ROOT / ".kiro" / "hooks" / name) == _text(ASSETS / "hooks" / name)


def test_the_repository_steering_rule_is_the_packaged_file():
    assert _text(ROOT / ".kiro" / "steering" / "statement.md") == _text(ASSETS / "steering" / "statement.md")


def test_the_repository_mcp_entry_is_the_packaged_one():
    entry = json.loads((ASSETS / "mcp-server.json").read_text(encoding="utf-8"))
    repo = json.loads((ROOT / ".kiro" / "settings" / "mcp.json").read_text(encoding="utf-8-sig"))
    assert repo["mcpServers"]["paper-trail"] == entry


def test_hook_commands_start_with_python_and_use_the_scripts():
    for name in HOOK_FILES:
        if not name.endswith(".json"):
            continue
        hook = json.loads((ASSETS / "hooks" / name).read_text(encoding="utf-8"))["hooks"][0]
        command = hook["action"]["command"]
        assert command.startswith("python .kiro/hooks/")
        assert command.split()[1].removeprefix(".kiro/hooks/") in HOOK_FILES


def test_capture_helper_is_not_shipped():
    assert not (ASSETS / "hooks" / "capture.py").exists()


def test_asset_files_have_no_bom_and_no_carriage_returns():
    for path in ASSETS.rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            assert not raw.startswith(b"\xef\xbb\xbf"), path.name
            assert b"\r" not in raw, path.name


# ---------------------------------------------------------------------------
# The scripts, run the way Kiro runs them
# ---------------------------------------------------------------------------

def _clean_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PAPERTRAIL_ROOT")}
    env.update(extra or {})
    return env


def _bare_project(tmp_path: Path) -> Path:
    """A project that has the hook scripts but no papertrail package beside .kiro."""
    project = tmp_path / "other-project"
    hooks = project / ".kiro" / "hooks"
    hooks.mkdir(parents=True)
    for name in ("record.py", "witness.py"):
        shutil.copyfile(ASSETS / "hooks" / name, hooks / name)
    return project


@pytest.mark.parametrize("script,args", [("record.py", []), ("witness.py", ["start"]), ("witness.py", ["stop"])])
def test_without_the_package_the_hook_leaves_one_line_and_exits_zero(tmp_path, script, args):
    """AC1.3b. -S is not used; an empty folder that is not the repository is the cwd,
    and python is told not to look beside the script for `papertrail`."""
    project = _bare_project(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    # -I isolates from PYTHONPATH and from the current folder, so `papertrail` can only
    # come from an installation. Skip the check if this Python has it installed.
    probe = subprocess.run(
        [sys.executable, "-I", "-c", "import papertrail"], capture_output=True, cwd=str(elsewhere)
    )
    if probe.returncode == 0:
        pytest.skip("papertrail is installed in this Python")
    result = subprocess.run(
        [sys.executable, "-I", str(project / ".kiro" / "hooks" / script), *args],
        input=json.dumps({"session_id": "s"}),
        capture_output=True, text=True, cwd=str(elsewhere), timeout=30,
        env=_clean_env({"PAPERTRAIL_ROOT": str(project)}),
    )
    assert result.returncode == 0
    note = (project / ".papertrail" / "hook-errors.txt").read_text(encoding="utf-8")
    lines = note.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith(f"{script}: cannot import papertrail (")
    assert str(tmp_path) not in note
    assert not (project / ".papertrail" / "ledger.jsonl").exists()


def test_in_this_repository_the_hook_still_records(tmp_path):
    """AC1.3c, first half: a papertrail folder beside .kiro is used."""
    payload = {
        "session_id": "via-assets",
        "hook_event_name": "PostToolUse",
        "cwd": str(tmp_path),
        "tool_name": "read_file",
        "tool_input": {"path": "a.txt"},
        "tool_response": "x",
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / ".kiro" / "hooks" / "record.py")],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30,
        cwd=str(tmp_path), env=_clean_env({"PAPERTRAIL_ROOT": str(tmp_path)}),
    )
    assert result.returncode == 0
    entries = ledger.read(tmp_path / ".papertrail" / "ledger.jsonl")
    assert [e["kind"] for e in entries] == ["tool"]
    assert not (tmp_path / ".papertrail" / "hook-errors.txt").exists()


def test_the_root_falls_back_to_the_current_folder(tmp_path):
    """AC1.3d for the CLI: the project is where you are, not where the package lives."""
    (tmp_path / ".papertrail").mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "papertrail", "check-chain"],
        capture_output=True, text=True, timeout=30,
        cwd=str(tmp_path), env=_clean_env({"PYTHONPATH": str(ROOT)}),
    )
    assert result.returncode == 0
    assert "No ledger found" in result.stdout
