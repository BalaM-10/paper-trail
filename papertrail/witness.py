"""Folder snapshot and diff for Paper Trail."""

import hashlib
import os
from pathlib import Path

from papertrail.ignore import Matcher
from papertrail.watch import is_setup, setup_paths

EXCLUDE: frozenset[str] = frozenset({
    '.git', '.papertrail', 'node_modules', '__pycache__', '.venv',
    'dist', 'build',
})


def snapshot(root: Path, matcher: Matcher | None = None) -> dict[str, dict[str, int | str]]:
    """
    Walk root, skipping any directory whose name is in EXCLUDE at every depth, and
    anything the project's .gitignore or the built-in list of caches ignores
    (see papertrail/ignore.py). `matcher` is for tests; by default it is built from root.

    Returns {forward_slash_relative_path: {"size": int, "sha256": str}}.
    SHA-256 is computed in 64 KB chunks. Files that cannot be read are silently
    skipped. What was skipped is not recorded.
    """
    if matcher is None:
        matcher = Matcher.load(root)
    result: dict[str, dict[str, int | str]] = {}

    for dirpath, dirs, files in os.walk(root, topdown=True):
        here = Path(dirpath).relative_to(root).as_posix()
        here = "" if here == "." else here + "/"
        # Prune excluded and ignored directories in-place so os.walk won't descend into
        # them. Nothing below a pruned folder is asked about, so `matches` is enough.
        dirs[:] = [d for d in dirs if d not in EXCLUDE and not matcher.matches(here + d, True)]

        for filename in files:
            if matcher.matches(here + filename, False):
                continue
            abs_path = Path(dirpath) / filename
            try:
                size = abs_path.stat().st_size
                sha256 = _sha256(abs_path)
            except OSError:
                continue

            rel = abs_path.relative_to(root).as_posix()
            result[rel] = {'size': size, 'sha256': sha256}

    # The recording setup is always snapshotted, even where .gitignore would skip it.
    for rel in setup_paths(root):
        if rel in result:
            continue
        abs_path = Path(root) / rel
        try:
            result[rel] = {'size': abs_path.stat().st_size, 'sha256': _sha256(abs_path)}
        except OSError:
            continue

    return result


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def without_ignored(snap: dict[str, dict], root: Path) -> dict[str, dict]:
    """
    A snapshot taken before the ignore rule existed still lists cache files. Drop what
    the rule skips, so comparing it with a newer snapshot does not report them as deleted.
    """
    matcher = Matcher.load(root)
    return {p: v for p, v in snap.items() if is_setup(p) or not matcher.is_ignored(p, False)}


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
