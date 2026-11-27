"""What the record must never hold, defined once.

The record may not hold an absolute path, the user name or the machine name.
This module is the only place that says what those look like. The recorder
(`ledger.append`) uses `scrub` to remove them. The tool that publishes the
record (`sample/export_build_record.py`) uses `find` to look for them. Both use
the same patterns, so anything `scrub` has cleaned passes `find`.

What `scrub` does, in this order:

1. The project folder becomes ".", the home folder becomes "~". The rest of the
   path is kept. Backslash, forward slash, doubled backslashes (text inside
   JSON text) and any letter case are recognised.
2. Any other absolute path keeps only its last part, behind the marker
   "[path]": `C:\\Program Files\\nodejs\\node.exe` becomes `[path]/node.exe`.
   Recognised: drive paths, UNC paths (`\\\\server\\share`), `file:///`
   addresses, and POSIX paths that start in a system or user folder.
3. The user name becomes "[user]" and the machine name "[machine]", in any
   letter case, and so do Windows short names made from them (`NAME~1`).

Text that holds none of these is returned unchanged. Standard library only:
the hooks import this through the ledger.
"""

import getpass
import os
import re
import socket
from pathlib import Path

PATH_MARKER = "[path]"
USER_MARKER = "[user]"
MACHINE_MARKER = "[machine]"
USER_LABEL = "the user name"
MACHINE_LABEL = "the machine name"

#: Folders that start a POSIX path we treat as absolute.
POSIX_FOLDERS = (
    "Users", "home", "root", "var", "tmp", "private", "Volumes", "opt", "etc",
    "usr", "mnt", "srv", "media", "Library", "Applications", "proc", "dev",
)

# A path ends at white space, a quote, or a character that closes or separates text.
_REST = r"""[^\s"'<>|`,;)\]}]*"""
# (not after a letter, and not right after one of our own markers, which end in "]")
_DRIVE_START = r"(?<![A-Za-z\]])[A-Za-z]:[\\/]"
# \\server\share, or the same inside JSON text (\\\\server\\share)
_UNC_START = r"(?<![\\\w\]])(?:\\{4}[\w.$-]+\\{1,2}|\\{2}[\w.$-]+\\)[\w.$-]+"
_POSIX_START = r"(?:^|(?<=[\s\"'=(:,;>|{]))/(?:" + "|".join(POSIX_FOLDERS) + r")/"
# file:/// followed by anything absolute (not "./", not an already cleaned marker)
_FILE_START = r"file:///(?![./\\\s\"'\[<>])"

PATH_RE = re.compile(
    rf"(?P<file>{_FILE_START}[^\s\"'<>|`,;)\]}}]+)"
    rf"|(?P<drive>{_DRIVE_START}{_REST})"
    rf"|(?P<unc>{_UNC_START}{_REST})"
    rf"|(?P<posix>{_POSIX_START}{_REST})"
)
_FILE_DRIVE = re.compile(_DRIVE_START)
_MARKERS = re.compile(r"(\[(?:user|machine|path)\])")

WHAT_DRIVE = "a drive path"
WHAT_NETWORK = "a network path"
WHAT_FOLDER = "a path under a user or system folder"


# ---------------------------------------------------------------------------
# The names
# ---------------------------------------------------------------------------

def identity_terms() -> dict[str, str]:
    """Names that must not appear, lower case, each with its label. Three letters or more."""
    users = [getpass.getuser(), os.environ.get("USERNAME", ""), os.environ.get("USER", ""), Path.home().name]
    hosts = [socket.gethostname(), os.environ.get("COMPUTERNAME", ""), os.environ.get("HOSTNAME", "")]
    hosts += [h.split(".")[0] for h in hosts]
    terms: dict[str, str] = {}
    for label, names in ((USER_LABEL, users), (MACHINE_LABEL, hosts)):
        for name in names:
            name = name.strip().lower()
            if len(name) >= 3:
                terms.setdefault(name, label)
    return terms


def _name_patterns(terms: dict[str, str]) -> list[tuple[re.Pattern[str], str]]:
    """(pattern, marker) for each name and for the Windows short name made from it."""
    out: list[tuple[re.Pattern[str], str]] = []
    shorts: list[tuple[re.Pattern[str], str]] = []
    for term, label in sorted(terms.items(), key=lambda item: -len(item[0])):
        marker = USER_MARKER if label == USER_LABEL else MACHINE_MARKER
        short = re.sub(r"[^A-Za-z0-9]", "", term)[:6]
        if len(short) >= 2:  # NAME~1: the 8.3 form Windows uses for long folder names
            shorts.append((re.compile(re.escape(short) + r"~\d+", re.IGNORECASE), marker))
        out.append((re.compile(re.escape(term), re.IGNORECASE), marker))
    return shorts + out  # the short form first: "ALICE~1" is one name, not "ALICE" and "~1"


# ---------------------------------------------------------------------------
# Looking
# ---------------------------------------------------------------------------

def _kind(match: re.Match[str]) -> str:
    if match.lastgroup == "drive":
        return WHAT_DRIVE
    if match.lastgroup == "unc":
        return WHAT_NETWORK
    if match.lastgroup == "file":
        return WHAT_DRIVE if _FILE_DRIVE.match(match.group(0)[len("file:///"):]) else WHAT_FOLDER
    return WHAT_FOLDER


def find(text: str, terms: dict[str, str] | None = None) -> list[tuple[str, int, int]]:
    """(what, start, end) for everything in `text` that must not be recorded."""
    terms = identity_terms() if terms is None else terms
    found = [(_kind(m), m.start(), m.end()) for m in PATH_RE.finditer(text)]
    names = _name_patterns(terms)
    offset = 0
    for piece in _MARKERS.split(text):
        if not _MARKERS.fullmatch(piece):  # our own markers are not findings
            taken: list[tuple[int, int]] = []
            for pattern, marker in names:
                label = USER_LABEL if marker == USER_MARKER else MACHINE_LABEL
                for m in pattern.finditer(piece):
                    if any(m.start() < b and a < m.end() for a, b in taken):  # inside a longer finding
                        continue
                    taken.append((m.start(), m.end()))
                    found.append((label, offset + m.start(), offset + m.end()))
        offset += len(piece)
    return sorted(found, key=lambda item: item[1])


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

def _folder_pattern(path: str) -> re.Pattern[str] | None:
    """The folder, whichever slash style and however many backslashes, any case."""
    parts = [re.escape(p) for p in re.split(r"[/\\]+", path) if p]
    if not parts:  # "/" or "": nothing to name
        return None
    return re.compile(r"[/\\]+".join(parts) + r"""(?=[/\\"'<>\s]|$)""", re.IGNORECASE)


def _shorten(match: re.Match[str]) -> str:
    token = match.group(0)
    prefix = ""
    if match.lastgroup == "file":
        prefix, token = "file:///", token[len("file:///"):]
    ending = re.search(r"[\\/]*$", token).group(0)
    core = token[: len(token) - len(ending)]
    parts = [p for p in re.split(r"[\\/]+", core) if p]
    if parts and re.fullmatch(r"[A-Za-z]:", parts[0]):
        parts = parts[1:]
    punctuation = ""
    if parts:  # "y.txt." ends a sentence: the full stop is not part of the name
        punctuation = re.search(r"[.:!?]*$", parts[-1]).group(0)
        parts[-1] = parts[-1][: len(parts[-1]) - len(punctuation)]
        if not parts[-1]:
            parts.pop()
    last = parts[-1] if parts else ""
    kept = PATH_MARKER + (f"/{last}" if last else "")
    # A colon followed by a slash would look like a drive again.
    tail = ending if ending else punctuation
    return prefix + kept + tail


def scrub(text: str, root: Path, home: Path, terms: dict[str, str] | None = None) -> str:
    """`text` with the project folder, the home folder, other absolute paths and names removed."""
    terms = identity_terms() if terms is None else terms
    result = text
    for folder, marker in ((root, "."), (home, "~")):
        pattern = _folder_pattern(str(folder))
        if pattern is not None:
            result = pattern.sub(marker, result)
    result = PATH_RE.sub(_shorten, result)
    names = _name_patterns(terms)
    if not names:
        return result
    pieces = _MARKERS.split(result)
    for i, piece in enumerate(pieces):
        if not _MARKERS.fullmatch(piece):
            for pattern, marker in names:
                piece = pattern.sub(marker, piece)
            pieces[i] = piece
    return "".join(pieces)
