"""The recording setup: the files that decide what gets recorded.

If the hooks, the statement rule or the MCP settings change, the record of that
turn may be incomplete or different from what it would have been. So the witness
always snapshots these files, even when .gitignore would skip them, and the stop
hook says so in the record when one of them changed during a turn.

Standard library only: the hooks import this through `witness` and `session`.
"""
import os
from pathlib import Path

#: Every file under these folders is part of the setup.
SETUP_FOLDERS: tuple[str, ...] = (".kiro/hooks",)
#: These single files are part of the setup.
SETUP_FILES: tuple[str, ...] = (".kiro/steering/statement.md", ".kiro/settings/mcp.json")

#: The words printed for it (twin of setupChangedText in web/src/lib/entryText.ts).
LOUD_START = "RECORDING SETUP CHANGED DURING THIS TURN: "
LOUD_END = ". Read this turn's record with care."


def _key(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.casefold()


def is_setup(path: str) -> bool:
    """True if this project-relative path is part of the recording setup."""
    p = _key(path)
    if p in {f.casefold() for f in SETUP_FILES}:
        return True
    return any(p.startswith(folder.casefold() + "/") for folder in SETUP_FOLDERS)


def setup_paths(root: Path) -> list[str]:
    """The setup files that exist under root, as sorted forward-slash relative paths."""
    found: set[str] = set()
    for folder in SETUP_FOLDERS:
        base = Path(root) / folder
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name.endswith((".pyc", ".pyo")):
                    continue
                found.add((Path(dirpath) / name).relative_to(root).as_posix())
    for rel in SETUP_FILES:
        if (Path(root) / rel).is_file():
            found.add(rel)
    return sorted(found)


def setup_changes(diff: dict) -> dict[str, list[str]]:
    """The part of a snapshot difference that is about the setup."""
    return {
        change: sorted(p for p in diff.get(change, []) if is_setup(p))
        for change in ("created", "modified", "deleted")
    }


def changed_files(diff: dict) -> list[str]:
    """Every setup file the difference lists, sorted, each once."""
    changes = setup_changes(diff)
    return sorted({p for paths in changes.values() for p in paths})


def loud_line(files: list[str]) -> str:
    """The line printed when the setup changed during a turn."""
    return f"{LOUD_START}{', '.join(files)}{LOUD_END}"
