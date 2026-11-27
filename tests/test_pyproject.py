"""pip packaging: pyproject.toml, the wheel, and hooks that work from any folder."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from papertrail import install, ledger

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_project_is_declared_for_pip():
    project = PYPROJECT["project"]
    assert project["name"] == "paper-trail"
    assert project["requires-python"] == ">=3.11"
    assert project["scripts"]["papertrail"] == "papertrail.__main__:main"
    assert any(d.startswith("mcp") for d in project["dependencies"])
    assert PYPROJECT["tool"]["setuptools"]["packages"] == ["papertrail"]


def test_no_dependency_is_needed_by_the_hooks():
    """AC1.3e: the hooks use the standard library; the base install only adds the MCP SDK."""
    assert [d.split(">")[0].split("<")[0] for d in PYPROJECT["project"]["dependencies"]] == ["mcp"]
    extras = PYPROJECT["project"]["optional-dependencies"]
    assert set(extras) == {"api", "dev"}
    assert {"pytest", "hypothesis"} <= set(extras["dev"])


def test_package_data_covers_every_asset():
    patterns = PYPROJECT["tool"]["setuptools"]["package-data"]["papertrail"]
    assets = ROOT / "papertrail" / "assets"
    for path in assets.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT / "papertrail")
        folder = relative.parent.as_posix()
        assert any(Path(relative.as_posix()).match(p) and p.rsplit("/", 1)[0] == folder for p in patterns), relative


def test_the_readme_and_license_named_by_the_project_exist():
    assert (ROOT / PYPROJECT["project"]["readme"]).is_file()
    assert (ROOT / "LICENSE").is_file()


def _copy_project(work: Path) -> None:
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copyfile(ROOT / name, work / name)
    shutil.copytree(ROOT / "papertrail", work / "papertrail", ignore=shutil.ignore_patterns("__pycache__"))


def _build_wheel(work: Path) -> Path | None:
    """A wheel built offline, or None if this Python's setuptools cannot build one."""
    out = work / "out"
    done = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--quiet", "-w", str(out), str(work)],
        capture_output=True, text=True, cwd=str(work), timeout=300,
    )
    if done.returncode != 0 and "bdist_wheel" in done.stdout + done.stderr:
        return None
    assert done.returncode == 0, done.stdout + done.stderr
    found = list(out.glob("paper_trail-*.whl"))
    assert len(found) == 1
    return found[0]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    pytest.importorskip("setuptools")
    work = tmp_path_factory.mktemp("build")
    _copy_project(work)
    built = _build_wheel(work)
    if built is None:
        pytest.skip("this Python has no wheel support; the metadata checks need it")
    return built


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """A folder holding only the built package, as a user's site-packages would."""
    pytest.importorskip("setuptools")
    work = tmp_path_factory.mktemp("site-build")
    _copy_project(work)
    folder = work / "site"
    built = _build_wheel(work)
    if built is not None:
        with zipfile.ZipFile(built) as z:
            z.extractall(folder)
    else:  # an old setuptools without wheel: the same build step, without the zip
        done = subprocess.run(
            [sys.executable, "-c", "from setuptools import setup; setup()", "build_py", "--build-lib", str(folder)],
            capture_output=True, text=True, cwd=str(work), timeout=300,
        )
        assert done.returncode == 0, done.stdout + done.stderr
    return folder


def test_the_build_carries_the_package_and_the_assets(site):
    names = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
    for name in (
        "papertrail/__init__.py",
        "papertrail/__main__.py",
        "papertrail/install.py",
        "papertrail/assets/mcp-server.json",
        "papertrail/assets/steering/statement.md",
        *(f"papertrail/assets/hooks/{n}" for n in install.HOOK_FILES),
    ):
        assert name in names, name
    assert not any(n.startswith(("tests/", "web/", "sample/", ".kiro/")) for n in names)


def test_the_wheel_declares_the_command_and_python(wheel):
    with zipfile.ZipFile(wheel) as z:
        entry = next(n for n in z.namelist() if n.endswith("entry_points.txt"))
        meta = next(n for n in z.namelist() if n.endswith("/METADATA"))
        entry_points = z.read(entry).decode("utf-8")
        metadata = z.read(meta).decode("utf-8")
    assert "papertrail = papertrail.__main__:main" in entry_points
    assert "Requires-Python: >=3.11" in metadata
    assert "Requires-Dist: mcp" in metadata


def test_hooks_work_from_any_folder_with_only_the_installed_package(site, tmp_path):
    """AC1.3c: the project has no papertrail folder, python runs from a third folder,
    and the only copy of the package is the built one."""
    project = tmp_path / "their-project"
    project.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PAPERTRAIL_ROOT")}
    env["PYTHONPATH"] = str(site)
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    init = subprocess.run(
        [sys.executable, "-m", "papertrail", "init", str(project)],
        capture_output=True, text=True, cwd=str(elsewhere), env=env, timeout=60,
    )
    assert init.returncode == 0, init.stderr
    assert not (project / "papertrail").exists()

    payload = {
        "session_id": "any-folder",
        "hook_event_name": "PostToolUse",
        "cwd": str(project),
        "tool_name": "read_file",
        "tool_input": {"path": "notes.txt"},
        "tool_response": "ignored",
    }
    hook = subprocess.run(
        [sys.executable, str(project / ".kiro" / "hooks" / "record.py")],
        input=json.dumps(payload), capture_output=True, text=True, cwd=str(elsewhere), env=env, timeout=60,
    )
    assert hook.returncode == 0, hook.stderr
    entries = ledger.read(project / ".papertrail" / "ledger.jsonl")
    assert [e["kind"] for e in entries] == ["tool"]
    assert entries[0]["session_id"] == "any-folder"
    assert not (project / ".papertrail" / "hook-errors.txt").exists()
    assert str(tmp_path) not in json.dumps(entries)