"""Append-only, hash-chained ledger for Paper Trail."""

import contextlib
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Privacy sanitisation
# ---------------------------------------------------------------------------

def _make_path_re(path: str) -> str:
    """Split on both / and \\, escape each segment, rejoin with separator pattern."""
    parts = re.split(r'[/\\]', path)
    return r'[/\\]'.join(re.escape(p) for p in parts if p)


_BOUNDARY = r'(?=[/\\"\'<>\s]|$)'


def sanitise(value: str, root: Path, home: Path) -> str:
    """
    Replace all occurrences of root with "." and home with "~".

    root is replaced before home. Matching is case-insensitive and
    slash-style-insensitive. A match is only recognised when followed
    by /, \\, ", whitespace, > or end of string.
    """
    root_pattern = re.compile(_make_path_re(str(root)) + _BOUNDARY, re.IGNORECASE)
    home_pattern = re.compile(_make_path_re(str(home)) + _BOUNDARY, re.IGNORECASE)

    result = root_pattern.sub('.', value)
    result = home_pattern.sub('~', result)
    return result


def _sanitise_data(data: dict, root: Path, home: Path) -> dict:
    """Recurse over every string leaf of data and apply sanitise. Return new dict."""
    def _walk(obj):
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(item) for item in obj]
        if isinstance(obj, str):
            return sanitise(obj, root, home)
        return obj

    return _walk(data)


# ---------------------------------------------------------------------------
# Path normalisation
# ---------------------------------------------------------------------------

def to_relative(path: str, root: Path) -> str:
    """
    Absolute path under root  →  relative forward-slash form.
    Already relative          →  normalise separators to forward slash.
    Absolute outside root     →  pass through sanitise() and return as-is.
    """
    p = Path(path)
    if p.is_absolute():
        try:
            return p.relative_to(root).as_posix()
        except ValueError:
            return sanitise(path, root, Path.home())
    # Already relative: just normalise separators.
    return path.replace('\\', '/')


# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _file_lock(lock_path: Path):
    deadline = time.monotonic() + 5.0
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                age = 999
            if age > 10:
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Could not acquire {lock_path} within 5 s")
            time.sleep(0.1)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------------

def _compute_hash(entry_without_hash: dict) -> str:
    canonical = json.dumps(
        entry_without_hash,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def append(ledger_path: Path, session_id: str, kind: str, data: dict) -> dict:
    """
    Acquire exclusive lock, read last line for seq/hash, build and write new
    entry, flush, release lock. Return the written entry.

    Calls _sanitise_data() on every string leaf of data before hashing.
    """
    # Create parent dirs before acquiring the lock (os.open needs the dir to exist).
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = ledger_path.parent / 'ledger.lock'

    with _file_lock(lock_path):
        # Parent dirs already created above.

        # 2. Read last line for prev_hash and seq.
        prev_hash = '0' * 64
        seq = 0
        if ledger_path.exists():
            with open(ledger_path, 'rb') as f:
                # Efficiently find the last non-empty line.
                f.seek(0, 2)
                file_size = f.tell()
                if file_size > 0:
                    # Read backwards to find last newline.
                    pos = file_size - 1
                    buf = b''
                    while pos >= 0:
                        chunk_size = min(4096, pos + 1)
                        pos -= chunk_size
                        f.seek(pos + 1)
                        chunk = f.read(chunk_size)
                        buf = chunk + buf
                        # Look for newline in buf (from the right, skip trailing newline)
                        stripped = buf.rstrip(b'\n\r')
                        idx = stripped.rfind(b'\n')
                        if idx != -1:
                            last_line = stripped[idx + 1:]
                            if last_line:
                                break
                        if pos < 0:
                            last_line = stripped
                            break
                    else:
                        last_line = buf.rstrip(b'\n\r')

                    if last_line:
                        last_entry = json.loads(last_line)
                        prev_hash = last_entry['hash']
                        seq = last_entry['seq']

        # 3. Build entry.
        # root is derived from the ledger path itself so the result is
        # independent of the caller's working directory.
        seq += 1
        root = ledger_path.parent.parent  # folder containing .papertrail/
        sanitised_data = _sanitise_data(data, root, Path.home())
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'

        entry_without_hash: dict = {
            'seq': seq,
            'ts': ts,
            'session_id': session_id,
            'kind': kind,
            'data': sanitised_data,
            'prev_hash': prev_hash,
        }
        hash_value = _compute_hash(entry_without_hash)
        entry = {**entry_without_hash, 'hash': hash_value}

        # 4. Append to file.
        with open(ledger_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, separators=(',', ':')) + '\n')
            f.flush()

        return entry


def read(ledger_path: Path) -> list[dict]:
    """Return entries in append order. Empty list if file absent."""
    if not ledger_path.exists():
        return []
    with open(ledger_path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def verify_chain(ledger_path: Path) -> tuple[bool, int | None]:
    """
    Check every entry's hash and prev_hash linkage, and that seq is a
    gap-free sequence starting at 1 with no repeats.
    Return (True, None) on success; (False, seq) at the first broken entry.
    """
    entries = read(ledger_path)
    expected_prev = '0' * 64
    expected_seq = 1

    for entry in entries:
        # Check seq.
        if entry['seq'] != expected_seq:
            return (False, entry['seq'])

        # Recompute hash.
        entry_without_hash = {k: v for k, v in entry.items() if k != 'hash'}
        expected_hash = _compute_hash(entry_without_hash)

        if entry['hash'] != expected_hash:
            return (False, entry['seq'])

        if entry['prev_hash'] != expected_prev:
            return (False, entry['seq'])

        expected_prev = entry['hash']
        expected_seq += 1

    return (True, None)
