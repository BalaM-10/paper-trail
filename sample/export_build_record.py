"""Publish this project's own record as the "How this was built" roll.

    python sample/export_build_record.py [--source PATH] [--dest PATH]

Copies .papertrail/ledger.jsonl to web/public/demo/build-ledger.jsonl, byte for
byte, so the fingerprints still check on the page. Before copying it reads every
record and refuses if any text in it holds an absolute path, the user name of
this machine or its name. When it refuses it copies nothing and lists each
finding. It never changes the source: the record is append-only.
"""

import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # run as a script from any folder
    sys.path.insert(0, str(ROOT))

from papertrail import ledger  # noqa: E402

DEFAULT_SOURCE = ROOT / ".papertrail" / "ledger.jsonl"
DEFAULT_DEST = ROOT / "web" / "public" / "demo" / "build-ledger.jsonl"
REQUIRED_KEYS = ("seq", "ts", "session_id", "kind", "data", "prev_hash", "hash")

# A letter that stands alone, then ":" and a slash. "https://" and "file:///" do not match,
# because the letter before ":" there belongs to a longer word.
DRIVE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
NETWORK_PATH = re.compile(r"(?<![\\\w])\\\\[\w.$-]+\\[\w.$-]+")
FOLDER_PATH = re.compile(r"(?:^|[\s\"'=(:,;])/(?:Users|home|root|var|tmp|private|Volumes)/")

SNIPPET = 20  # characters kept either side of a match


@dataclass(frozen=True)
class Finding:
    line: int
    seq: object
    kind: str
    field: str
    what: str
    text: str


def identity_terms() -> dict[str, str]:
    """Names that must not appear: the user name and the machine name, lower case."""
    users = [getpass.getuser(), os.environ.get("USERNAME", ""), os.environ.get("USER", ""), Path.home().name]
    hosts = [socket.gethostname(), os.environ.get("COMPUTERNAME", ""), os.environ.get("HOSTNAME", "")]
    hosts += [h.split(".")[0] for h in hosts]
    terms: dict[str, str] = {}
    for label, names in (("the user name", users), ("the machine name", hosts)):
        for name in names:
            name = name.strip().lower()
            if len(name) >= 3:
                terms.setdefault(name, label)
    return terms


def _snippet(text: str, start: int, end: int) -> str:
    piece = text[max(0, start - SNIPPET): end + SNIPPET]
    return " ".join(piece.split())


def _scan_text(text: str, terms: dict[str, str]) -> list[tuple[str, str]]:
    """(what, snippet) for each kind of thing found in one piece of text."""
    found: list[tuple[str, str]] = []
    for what, pattern in (
        ("a drive path", DRIVE_PATH),
        ("a network path", NETWORK_PATH),
        ("a path under a user or system folder", FOLDER_PATH),
    ):
        match = pattern.search(text)
        if match:
            found.append((what, _snippet(text, match.start(), match.end())))
    lowered = text.lower()
    for term, label in terms.items():
        at = lowered.find(term)
        if at >= 0:
            found.append((label, _snippet(text, at, at + len(term))))
    return found


def _walk(value: object, field: str):
    """Every string in a JSON value, keys included, with the name of where it sits."""
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, dict):
        for key, inner in value.items():
            yield f"{field}.{key} (name)" if field else f"{key} (name)", str(key)
            yield from _walk(inner, f"{field}.{key}" if field else str(key))
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            yield from _walk(inner, f"{field}[{i}]")


def scan(lines: list[str], terms: dict[str, str]) -> list[Finding]:
    """Everything in the records that must not be published. Each (line, field, kind of thing) once."""
    findings: list[Finding] = []
    seen: set[tuple[int, str, str]] = set()

    def add(number: int, record: dict, field: str, what: str, text: str) -> None:
        key = (number, field, what)
        if key not in seen:
            seen.add(key)
            findings.append(Finding(number, record.get("seq"), str(record.get("kind")), field, what, text))

    for number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            record = {}
        if isinstance(record, dict):
            for field, text in _walk(record, ""):
                for what, snippet in _scan_text(text, terms):
                    add(number, record, field, what, snippet)
        # the raw line too: this catches a name inside escaped text
        lowered = raw.lower()
        for term, label in terms.items():
            at = lowered.find(term)
            if at >= 0 and not any(f.line == number and f.what == label for f in findings):
                add(number, record if isinstance(record, dict) else {}, "(the line as written)", label,
                    _snippet(raw, at, at + len(term)))
    return findings


def _lines(source: Path) -> list[str]:
    return [line.rstrip("\r") for line in source.read_bytes().decode("utf-8").split("\n")]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(source: Path, terms: dict[str, str] | None = None) -> tuple[list[str], list[Finding]]:
    """(problems, findings). Both empty means the record can be published."""
    if not source.is_file():
        return [f"The record is missing: {source.name} was not found."], []
    try:
        lines = [line for line in _lines(source) if line.strip()]
    except UnicodeDecodeError:
        return ["The record is not valid UTF-8 text."], []
    if not lines:
        return ["The record is empty: there is nothing to publish."], []
    for number, raw in enumerate(lines, start=1):
        try:
            record = json.loads(raw)
        except ValueError:
            return [f"Line {number} is not a record (it is not JSON)."], []
        if not isinstance(record, dict) or any(k not in record for k in REQUIRED_KEYS):
            return [f"Line {number} is not a record (a required field is missing)."], []
    ok, broken = ledger.verify_chain(source)
    if not ok:
        return [
            f"The record is torn at line {broken}. A published record must have fingerprints that check."
        ], []
    return [], scan(lines, identity_terms() if terms is None else terms)


def export(source: Path, dest: Path, terms: dict[str, str] | None = None) -> tuple[list[str], list[Finding]]:
    """Scan, then copy. Returns (problems, findings); both empty means it was copied."""
    problems, findings = check(source, terms)
    if problems or findings:
        return problems, findings
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + ".tmp")
    try:
        shutil.copyfile(source, temporary)
        if _sha(temporary) != _sha(source):
            return ["The copy does not match the original, so it was thrown away."], []
        os.replace(temporary, dest)
    finally:
        if temporary.exists():
            temporary.unlink()
    return [], []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish the build record for the web page.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # a snippet may hold characters the console cannot show
        sys.stdout.reconfigure(errors="replace")

    if args.source.resolve() == args.dest.resolve():
        print("Refusing: the source and the destination are the same file.")
        return 1

    problems, findings = export(args.source, args.dest)
    if problems:
        print("Refusing to publish. Nothing was copied.")
        for problem in problems:
            print(f"  {problem}")
        return 1
    if findings:
        print(f"Refusing to publish: {len(findings)} {'problem' if len(findings) == 1 else 'problems'} found. Nothing was copied.")
        print("A published record must not hold an absolute path, a user name or a machine name.")
        print()
        for f in findings:
            print(f"  line {f.line} ({f.kind}) {f.field}: {f.what}: ...{f.text}...")
        print()
        print(f"{len(findings)} {'finding' if len(findings) == 1 else 'findings'} in total. The record is append-only, so it cannot be edited.")
        return 1

    entries = ledger.read(args.dest)
    print(f"Copied {len(entries)} lines to {args.dest.name}.")
    print(f"Fingerprint of the record: {entries[-1]['hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
