"""Put the record away so the next one starts clean. Nothing is deleted.

    python -m papertrail archive

Moves .papertrail/ledger.jsonl to .papertrail/archive/ledger-<UTC time>.jsonl.
The next entry the recorder writes starts a new record (line 1, previous
fingerprint all zeros). It refuses if the record's fingerprints do not check.
Standard library only.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from papertrail import ledger


class ArchiveError(Exception):
    """The record was not moved. The message says why, in plain words."""


@dataclass(frozen=True)
class Archived:
    lines: int
    target: str  # relative to the project, forward slashes
    fingerprint: str


def _target(folder: Path, now: datetime) -> Path:
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"ledger-{stamp}.jsonl"
    n = 2
    while target.exists():  # two archives in the same second
        target = folder / f"ledger-{stamp}-{n}.jsonl"
        n += 1
    return target


def archive(root: Path, now: datetime | None = None) -> Archived:
    """Move the record into .papertrail/archive/. Raises ArchiveError and moves nothing if it cannot."""
    now = now or datetime.now(timezone.utc)
    source = root / ".papertrail" / "ledger.jsonl"
    if not source.is_file() or source.stat().st_size == 0:
        raise ArchiveError("there is no record to archive")
    # The recorder takes this lock to write; holding it means no line is added mid-move.
    with ledger._file_lock(source.parent / "ledger.lock"):
        try:
            entries = ledger.read(source)
            ok, broken_at = ledger.verify_chain(source)
        except (ValueError, KeyError, OSError):
            raise ArchiveError("the record cannot be read, so it may be damaged") from None
        if not entries:
            raise ArchiveError("there is no record to archive")
        if not ok:
            raise ArchiveError(
                f"the record's fingerprints do not check (it is torn at line {broken_at}), "
                "so it may have been edited"
            )
        folder = source.parent / "archive"
        folder.mkdir(parents=True, exist_ok=True)
        target = _target(folder, now)
        os.replace(source, target)
    return Archived(
        lines=len(entries),
        target=target.relative_to(root).as_posix(),
        fingerprint=entries[-1]["hash"],
    )


def describe(done: Archived) -> list[str]:
    """What happened, in plain words."""
    lines = "1 line" if done.lines == 1 else f"{done.lines} lines"
    return [
        f"Moved the record ({lines}) to {done.target}.",
        f"Fingerprint of the archived record: {done.fingerprint}",
        "Nothing was deleted. The next line Paper Trail records starts a new record.",
    ]


__all__ = ["ArchiveError", "Archived", "archive", "describe"]
