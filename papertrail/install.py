"""Set up Paper Trail in another Kiro project (`init`) and check one (`doctor`).

    python -m papertrail init <project_folder> [--force]
    python -m papertrail doctor [project_folder]

`init` copies the files in papertrail/assets/ and never overwrites a file that
differs unless `force` is set. Running it twice changes nothing the second time.
`doctor` only reads. Standard library only.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ASSETS = Path(__file__).resolve().parent / "assets"

HOOK_FILES = (
    "record-post-tool-use.json",
    "record-file-delete.json",
    "witness-session-start.json",
    "witness-stop.json",
    "record.py",
    "witness.py",
)
STEERING_FILE = "statement.md"
SERVER_NAME = "paper-trail"
MCP_PATH = ".kiro/settings/mcp.json"
GITIGNORE_PATH = ".gitignore"
IGNORE_LINE = ".papertrail/"
IGNORE_FORMS = {".papertrail", ".papertrail/", "/.papertrail", "/.papertrail/"}
HOOK_ERRORS_PATH = ".papertrail/hook-errors.txt"

INIT_FIX = "python -m papertrail init <project_folder>"
PIP_FIX = "pip install <the Paper Trail folder>  (see Install in the README)"


@dataclass(frozen=True)
class Step:
    """One thing `init` did, or chose not to do."""

    status: str  # created | added | replaced | unchanged | kept | error
    target: str  # relative to the project, forward slashes
    note: str = ""


@dataclass(frozen=True)
class Check:
    """One line of the `doctor` report."""

    level: str  # ok | missing | warn
    label: str
    fix: str = ""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").lstrip("\ufeff")


def _asset_text(relative: str) -> str:
    return _norm((ASSETS / relative).read_bytes().decode("utf-8"))


def _mcp_entry() -> dict:
    return json.loads(_asset_text("mcp-server.json"))


def _read_text(path: Path) -> str | None:
    """The file's text with plain line endings, or None if it cannot be read as UTF-8."""
    try:
        return _norm(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def _write(path: Path, text: str) -> None:
    """UTF-8, no byte-order mark, `\\n` line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _place(project: Path, relative: str, wanted: str, force: bool) -> Step:
    dest = project / relative
    try:
        if dest.is_dir():
            return Step("error", relative, "a folder is in the way")
        if not dest.exists():
            _write(dest, wanted)
            return Step("created", relative)
        if _read_text(dest) == wanted:
            return Step("unchanged", relative)
        if not force:
            return Step("kept", relative)
        _write(dest, wanted)
        return Step("replaced", relative)
    except OSError as exc:
        return Step("error", relative, exc.strerror or "the file could not be written")


def _dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _merge_mcp(project: Path, force: bool) -> Step:
    entry = _mcp_entry()
    path = project / MCP_PATH
    try:
        if not path.exists():
            _write(path, _dump({"mcpServers": {SERVER_NAME: entry}}))
            return Step("created", MCP_PATH)
        try:
            data = json.loads(path.read_bytes().decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            return Step("error", MCP_PATH, "it is not valid JSON, so it was not touched")
        if not isinstance(data, dict):
            return Step("error", MCP_PATH, "it does not hold a JSON object, so it was not touched")
        servers = data.get("mcpServers")
        if servers is None:
            servers = {}
        if not isinstance(servers, dict):
            return Step("error", MCP_PATH, "its mcpServers is not an object, so it was not touched")
        current = servers.get(SERVER_NAME)
        if current == entry:
            return Step("unchanged", MCP_PATH)
        if current is not None and not force:
            return Step("kept", MCP_PATH)
        servers[SERVER_NAME] = entry
        data["mcpServers"] = servers
        _write(path, _dump(data))
        return Step("replaced" if current is not None else "added", MCP_PATH)
    except OSError as exc:
        return Step("error", MCP_PATH, exc.strerror or "the file could not be written")


def _has_ignore_line(raw: bytes) -> bool:
    for line in raw.splitlines():
        if line.decode("utf-8", "ignore").lstrip("\ufeff").strip() in IGNORE_FORMS:
            return True
    return False


def _add_ignore(project: Path) -> Step:
    path = project / GITIGNORE_PATH
    try:
        if not path.exists():
            _write(path, IGNORE_LINE + "\n")
            return Step("created", GITIGNORE_PATH)
        raw = path.read_bytes()
        if _has_ignore_line(raw):
            return Step("unchanged", GITIGNORE_PATH)
        eol = b"\r\n" if b"\r\n" in raw else b"\n"
        if raw and not raw.endswith((b"\n", b"\r")):
            raw += eol
        path.write_bytes(raw + IGNORE_LINE.encode("ascii") + eol)
        return Step("added", GITIGNORE_PATH)
    except OSError as exc:
        return Step("error", GITIGNORE_PATH, exc.strerror or "the file could not be written")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def init(project: Path, force: bool = False) -> list[Step]:
    """Set up Paper Trail in `project`. Raises NotADirectoryError if it is not a folder."""
    project = Path(project)
    if not project.is_dir():
        raise NotADirectoryError(f"{project} is not a folder")
    steps = [
        _place(project, f".kiro/hooks/{name}", _asset_text(f"hooks/{name}"), force)
        for name in HOOK_FILES
    ]
    steps.append(
        _place(project, f".kiro/steering/{STEERING_FILE}", _asset_text(f"steering/{STEERING_FILE}"), force)
    )
    steps.append(_merge_mcp(project, force))
    steps.append(_add_ignore(project))
    return steps


def succeeded(steps: list[Step]) -> bool:
    """True when nothing was left alone and nothing failed."""
    return all(s.status in ("created", "added", "replaced", "unchanged") for s in steps)


def describe(step: Step) -> str:
    """One plain sentence for a step."""
    target = step.target
    is_mcp = target == MCP_PATH
    is_ignore = target == GITIGNORE_PATH
    if step.status == "created":
        return f"Created {target}" + (" with the paper-trail server" if is_mcp else "")
    if step.status == "added":
        return f"Added the paper-trail server to {target}" if is_mcp else f"Added {IGNORE_LINE} to {target}"
    if step.status == "replaced":
        return f"Replaced the paper-trail server in {target}" if is_mcp else f"Replaced {target}"
    if step.status == "unchanged":
        return f"Already in place: {target}"
    if step.status == "kept":
        what = f"the paper-trail server in {target}" if is_mcp else target
        return f"Left alone: {what} is different from Paper Trail's. Run again with --force to replace it."
    note = f": {step.note}" if step.note else ""
    return f"Could not set up {target}{note}" if not is_ignore else f"Could not update {target}{note}"


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

Probe = Callable[[Path, str], "tuple[bool, str]"]


def probe_python(project: Path, module: str) -> tuple[bool, str]:
    """Can the `python` command (the one the hooks use) import `module` from the project folder?"""
    exe = shutil.which("python")
    if exe is None:
        return False, "there is no python command on the path"
    try:
        done = subprocess.run(
            [exe, "-c", f"import {module}"],
            cwd=str(project), capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "python took too long to answer"
    except OSError:
        return False, "python could not be started"
    if done.returncode == 0:
        return True, ""
    return False, f"python cannot import {module}"


def _file_check(project: Path, relative: str, wanted: str) -> Check:
    path = project / relative
    if not path.is_file():
        return Check("missing", f"{relative} is missing", INIT_FIX)
    if _read_text(path) != wanted:
        return Check("warn", f"{relative} is different from Paper Trail's version")
    return Check("ok", f"{relative} is in place")


def _mcp_check(project: Path) -> Check:
    path = project / MCP_PATH
    if not path.is_file():
        return Check("missing", f"{MCP_PATH} is missing, so Kiro does not know the paper-trail server", INIT_FIX)
    try:
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
        entry = data["mcpServers"][SERVER_NAME]
    except (ValueError, UnicodeDecodeError, KeyError, TypeError):
        return Check("missing", f"{MCP_PATH} has no paper-trail server (or cannot be read)", INIT_FIX)
    if isinstance(entry, dict) and entry.get("disabled") is True:
        return Check("warn", "the paper-trail server is switched off in " + MCP_PATH)
    if entry != _mcp_entry():
        return Check("warn", f"the paper-trail server in {MCP_PATH} is different from Paper Trail's")
    return Check("ok", f"the paper-trail server is set up in {MCP_PATH}")


def doctor(project: Path, probe: Probe = probe_python) -> list[Check]:
    """Check an installed project. Reads only. Raises NotADirectoryError if it is not a folder."""
    project = Path(project)
    if not project.is_dir():
        raise NotADirectoryError(f"{project} is not a folder")
    checks = [
        _file_check(project, f".kiro/hooks/{name}", _asset_text(f"hooks/{name}"))
        for name in HOOK_FILES
    ]
    checks.append(
        _file_check(project, f".kiro/steering/{STEERING_FILE}", _asset_text(f"steering/{STEERING_FILE}"))
    )
    checks.append(_mcp_check(project))

    ignore = project / GITIGNORE_PATH
    if ignore.is_file() and _has_ignore_line(ignore.read_bytes()):
        checks.append(Check("ok", f"{IGNORE_LINE} is in {GITIGNORE_PATH}"))
    else:
        checks.append(Check("missing", f"{IGNORE_LINE} is not in {GITIGNORE_PATH}", INIT_FIX))

    for module, why in (("papertrail", "the hooks"), ("mcp", "the paper-trail server")):
        found, reason = probe(project, module)
        if found:
            checks.append(Check("ok", f"python can import {module} (needed by {why})"))
        else:
            checks.append(Check("missing", f"{reason} (needed by {why})", PIP_FIX))

    errors = project / HOOK_ERRORS_PATH
    if errors.is_file():
        try:
            first = errors.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        except (OSError, IndexError):
            first = "(unreadable)"
        checks.append(Check("warn", f"the hooks reported a problem: {first[:100]}"))
    return checks


def describe_check(check: Check) -> list[str]:
    """Report lines for one check: the line itself, then how to fix it."""
    word = {"ok": "OK     ", "missing": "MISSING", "warn": "WARN   "}[check.level]
    lines = [f"{word} {check.label}"]
    if check.fix:
        lines.append(f"        Fix: {check.fix}")
    return lines


def healthy(checks: list[Check]) -> bool:
    return not any(c.level == "missing" for c in checks)
