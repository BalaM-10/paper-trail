"""Statement parser for Paper Trail."""

import json
from pathlib import Path

AGENT_KEYS: frozenset[str] = frozenset({
    'summary',
    'files_read',
    'files_created',
    'files_modified',
    'files_deleted',
})

PROMOTED_KEYS: frozenset[str] = AGENT_KEYS | frozenset({
    'session_id',
    'ts',
    'witness_seq',
})

FILE_LISTS: frozenset[str] = frozenset({
    'files_read',
    'files_created',
    'files_modified',
    'files_deleted',
})


def parse(path: Path) -> dict:
    """
    Load JSON from path, validate the promoted eight-field form, and return
    the dict.

    Validation order:
      1. All eight keys present (raises ValueError naming the missing key).
      2. For each file list, no absolute paths (raises ValueError naming the path).
      3. No duplicates within each list.

    Back-slashes in file list paths are normalised to forward slashes before
    returning.

    Raises ValueError with a descriptive message on any violation.
    Raises json.JSONDecodeError on invalid JSON.
    """
    raw = json.loads(path.read_text(encoding='utf-8'))

    # 1. All eight promoted keys must be present.
    for key in sorted(PROMOTED_KEYS):
        if key not in raw:
            raise ValueError(f"missing required key: '{key}'")

    # 2 & 3. Validate and normalise file lists.
    for key in FILE_LISTS:
        seen: set[str] = set()
        normalised: list[str] = []
        for p in raw[key]:
            # Detect absolute paths (Windows drive letter or Unix leading slash).
            if _is_absolute(p):
                raise ValueError(
                    f"absolute path in '{key}': {p!r}"
                )
            norm = p.replace('\\', '/')
            if norm in seen:
                raise ValueError(
                    f"duplicate path in '{key}': {norm!r}"
                )
            seen.add(norm)
            normalised.append(norm)
        raw[key] = normalised

    return raw


def _is_absolute(p: str) -> bool:
    """True if p looks like an absolute path (drive letter or leading slash)."""
    if p.startswith('/') or p.startswith('\\'):
        return True
    # Windows drive letter: C:\ or C:/
    if len(p) >= 3 and p[1] == ':' and p[2] in ('/', '\\'):
        return True
    return False
