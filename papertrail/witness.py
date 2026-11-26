"""Folder snapshot and diff for Paper Trail."""

import hashlib
import os
from pathlib import Path

EXCLUDE: frozenset[str] = frozenset({
    '.git', '.papertrail', 'node_modules', '__pycache__', '.venv',
    'dist', 'build',
})


def snapshot(root: Path) -> dict[str, dict[str, int | str]]:
    """
    Walk root, skipping any directory whose name is in EXCLUDE at every depth.

    Returns {forward_slash_relative_path: {"size": int, "sha256": str}}.
    SHA-256 is computed in 64 KB chunks. Files that cannot be read are silently
    skipped.
    """
    result: dict[str, dict[str, int | str]] = {}

    for dirpath, dirs, files in os.walk(root, topdown=True):
        # Prune excluded directories in-place so os.walk won't descend into them.
        dirs[:] = [d for d in dirs if d not in EXCLUDE]

        for filename in files:
            abs_path = Path(dirpath) / filename
            try:
                size = abs_path.stat().st_size
                sha256 = _sha256(abs_path)
            except OSError:
                continue

            rel = abs_path.relative_to(root).as_posix()
            result[rel] = {'size': size, 'sha256': sha256}

    return result


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def diff(
    old: dict[str, dict],
    new: dict[str, dict],
) -> dict[str, list[str]]:
    """
    Return {"created": [...], "deleted": [...], "modified": [...]}.

    "modified" means same path, different sha256. All lists are sorted.
    """
    old_keys = set(old)
    new_keys = set(new)

    created = sorted(new_keys - old_keys)
    deleted = sorted(old_keys - new_keys)
    modified = sorted(
        p for p in old_keys & new_keys
        if old[p]['sha256'] != new[p]['sha256']
    )

    return {'created': created, 'deleted': deleted, 'modified': modified}
