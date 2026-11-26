"""Tests for papertrail.ledger — Task 1."""

import hashlib
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from papertrail.ledger import append, read, sanitise, verify_chain, _compute_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ZEROS = '0' * 64


def _make_chain(ledger_path: Path, n: int, session_id: str = 'sess-test') -> list[dict]:
    """Append n entries and return them."""
    return [append(ledger_path, session_id, 'tool', {'seq_label': i}) for i in range(n)]


# ---------------------------------------------------------------------------
# AC1.1 — append / hash chain
# ---------------------------------------------------------------------------

def test_first_entry_seq_and_prev_hash(tmp_path):
    """AC1.1a: first entry seq=1, prev_hash = 64 zeros."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    entry = append(ledger, 'sess-1', 'tool', {'x': 1})
    assert entry['seq'] == 1
    assert entry['prev_hash'] == _ZEROS


def test_second_entry_links_to_first(tmp_path):
    """AC1.1b: second entry seq=2, prev_hash = first entry's hash."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    e1 = append(ledger, 'sess-1', 'tool', {'x': 1})
    e2 = append(ledger, 'sess-1', 'tool', {'x': 2})
    assert e2['seq'] == 2
    assert e2['prev_hash'] == e1['hash']


def test_hash_equals_sha256_of_canonical_json(tmp_path):
    """AC1.1c: hash equals SHA-256 of canonical JSON without hash field."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    entry = append(ledger, 'sess-1', 'tool', {'x': 1})
    without_hash = {k: v for k, v in entry.items() if k != 'hash'}
    canonical = json.dumps(without_hash, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False).encode('utf-8')
    expected = hashlib.sha256(canonical).hexdigest()
    assert entry['hash'] == expected


def test_absolute_path_in_data_is_sanitised(tmp_path):
    """AC1.1d: absolute path under project root is stored as relative "." form."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    abs_path = str(tmp_path / 'subdir' / 'file.txt')
    entry = append(ledger, 'sess-1', 'tool', {'path': abs_path})

    stored_path = entry['data']['path']
    # Must start with "." (root replaced) and must not contain the raw tmp_path
    assert stored_path.startswith('.'), f"Expected '.' prefix, got: {stored_path!r}"

    # The raw ledger line must not contain str(tmp_path) or the home dir string.
    line = ledger.read_text(encoding='utf-8').strip()
    assert str(tmp_path).replace('\\', '/').lower() not in line.lower(), \
        "tmp_path leaked into the ledger line"
    home_str = str(Path.home()).replace('\\', '/').lower()
    assert home_str not in line.lower(), "home dir leaked into the ledger line"


def test_absolute_path_sanitised_regardless_of_cwd(tmp_path, monkeypatch):
    """AC1.1d (cwd variant): result is the same regardless of working directory."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    abs_path = str(tmp_path / 'subdir' / 'file.txt')

    # Change cwd to something completely unrelated (drive root always exists on Windows).
    import os
    drive_root = os.path.splitdrive(str(tmp_path))[0] + '\\'
    monkeypatch.chdir(drive_root)

    entry = append(ledger, 'sess-1', 'tool', {'path': abs_path})

    stored_path = entry['data']['path']
    assert stored_path.startswith('.'), \
        f"cwd change broke sanitisation, got: {stored_path!r}"

    line = ledger.read_text(encoding='utf-8').strip()
    assert str(tmp_path).replace('\\', '/').lower() not in line.lower(), \
        "tmp_path leaked into ledger when cwd was changed"


# ---------------------------------------------------------------------------
# AC1.2 — read
# ---------------------------------------------------------------------------

def test_read_returns_entries_in_order(tmp_path):
    """AC1.2a: read returns entries in append order."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    entries = _make_chain(ledger, 5)
    result = read(ledger)
    assert [e['seq'] for e in result] == [1, 2, 3, 4, 5]


def test_read_absent_file_returns_empty(tmp_path):
    """AC1.2b: read on absent file returns []."""
    ledger = tmp_path / 'nonexistent.jsonl'
    assert read(ledger) == []


# ---------------------------------------------------------------------------
# AC1.3 — verify_chain
# ---------------------------------------------------------------------------

def test_verify_chain_passes_on_untouched_chain(tmp_path):
    """AC1.3a: unmodified chain passes."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    _make_chain(ledger, 5)
    ok, bad_seq = verify_chain(ledger)
    assert ok is True
    assert bad_seq is None


def test_verify_chain_fails_on_data_mutation(tmp_path):
    """AC1.3b: mutating data of an entry breaks the chain at that entry's seq."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    _make_chain(ledger, 3)

    lines = ledger.read_text(encoding='utf-8').splitlines()
    # Mutate entry seq=2 (index 1)
    entry = json.loads(lines[1])
    entry['data']['injected'] = 'tamper'
    lines[1] = json.dumps(entry, separators=(',', ':'))
    ledger.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    ok, bad_seq = verify_chain(ledger)
    assert ok is False
    assert bad_seq == 2


def test_verify_chain_fails_on_hash_mutation(tmp_path):
    """AC1.3c: mutating the hash field of an entry breaks the chain."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    _make_chain(ledger, 3)

    lines = ledger.read_text(encoding='utf-8').splitlines()
    # Corrupt hash of entry seq=1 (index 0)
    entry = json.loads(lines[0])
    entry['hash'] = 'a' * 64
    lines[0] = json.dumps(entry, separators=(',', ':'))
    ledger.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    ok, bad_seq = verify_chain(ledger)
    assert ok is False
    # seq=1 fails because stored hash != recomputed hash,
    # OR seq=2 fails because prev_hash != seq=1's (now wrong) hash.
    assert bad_seq in (1, 2)


def test_verify_chain_fails_on_seq_gap(tmp_path):
    """AC1.3d: a gap in seq numbers is detected."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    _make_chain(ledger, 4)

    lines = ledger.read_text(encoding='utf-8').splitlines()
    # Remove entry seq=2 (index 1)
    del lines[1]
    ledger.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    ok, bad_seq = verify_chain(ledger)
    assert ok is False
    assert bad_seq == 3  # seq=3 found where seq=2 expected


def test_verify_chain_fails_on_seq_repeat(tmp_path):
    """AC1.3e: a repeated seq number is detected."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    entries = _make_chain(ledger, 3)

    lines = ledger.read_text(encoding='utf-8').splitlines()
    # Duplicate the second line (seq=2 appears twice)
    lines.insert(2, lines[1])
    ledger.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    ok, bad_seq = verify_chain(ledger)
    assert ok is False
    # The third line is seq=2 again, so it fails at seq=2 (the duplicate).
    assert bad_seq == 2


def test_verify_chain_fails_on_prev_hash_mismatch(tmp_path):
    """AC1.3f: prev_hash pointing to wrong predecessor is detected."""
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'
    _make_chain(ledger, 3)

    lines = ledger.read_text(encoding='utf-8').splitlines()
    # Corrupt prev_hash of entry seq=3 (index 2)
    entry = json.loads(lines[2])
    entry['prev_hash'] = 'b' * 64
    # Recompute hash so the hash itself is consistent with the corrupted entry.
    entry_without_hash = {k: v for k, v in entry.items() if k != 'hash'}
    entry['hash'] = _compute_hash(entry_without_hash)
    lines[2] = json.dumps(entry, separators=(',', ':'))
    ledger.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    ok, bad_seq = verify_chain(ledger)
    assert ok is False
    assert bad_seq == 3


# ---------------------------------------------------------------------------
# AC1.5 — sanitise
# ---------------------------------------------------------------------------

_ROOT_BACKSLASH = r'c:\Work\Projects\paper-trail'
_ROOT_FORWARD   = r'c:/Work/Projects/paper-trail'
# Use a fake home that won't interfere with the root patterns.
_FAKE_HOME = Path(r'c:\Users\testuser')


def test_sanitise_root_backslash(tmp_path):
    """AC1.5a: root with back-slashes is redacted to '.'."""
    root = Path(_ROOT_BACKSLASH)
    value = _ROOT_BACKSLASH + r'\papertrail\ledger.py'
    result = sanitise(value, root, _FAKE_HOME)
    assert result.startswith('.')
    assert _ROOT_BACKSLASH.lower() not in result.lower()


def test_sanitise_root_forward_slash(tmp_path):
    """AC1.5b: root with forward-slashes is redacted to '.'."""
    root = Path(_ROOT_FORWARD)
    value = _ROOT_FORWARD + '/papertrail/ledger.py'
    result = sanitise(value, root, _FAKE_HOME)
    assert result.startswith('.')
    assert _ROOT_FORWARD.lower() not in result.lower()


def test_sanitise_mixed_separators(tmp_path):
    """AC1.5c: mixed separators in value are still redacted."""
    root = Path(_ROOT_BACKSLASH)
    value = _ROOT_BACKSLASH.replace('\\', '/') + '/papertrail/ledger.py'
    result = sanitise(value, root, _FAKE_HOME)
    assert result.startswith('.')


def test_sanitise_preserves_surrounding_text(tmp_path):
    """AC1.5d: text before and after the matched path is preserved."""
    root = Path(_ROOT_BACKSLASH)
    value = 'Error in ' + _ROOT_BACKSLASH + r'\some\file.py line 10'
    result = sanitise(value, root, _FAKE_HOME)
    assert result.startswith('Error in .')
    assert 'line 10' in result


# ---------------------------------------------------------------------------
# Hypothesis — AC8.2: mutating any entry breaks the chain
# ---------------------------------------------------------------------------

@given(st.lists(
    st.fixed_dictionaries({'key': st.text(max_size=20), 'val': st.integers()}),
    min_size=1,
    max_size=10,
))
@settings(max_examples=200)
def test_hypothesis_mutate_any_entry_breaks_chain(tmp_path_factory, data_list):
    """AC8.2a-b: mutate any single entry's data → verify_chain returns (False, _)."""
    tmp_path = tmp_path_factory.mktemp('hyp')
    ledger = tmp_path / '.papertrail' / 'ledger.jsonl'

    # Build chain.
    for item in data_list:
        append(ledger, 'sess-hyp', 'tool', item)

    # Pick an entry to mutate (always the last for determinism).
    lines = ledger.read_text(encoding='utf-8').splitlines()
    idx = len(lines) - 1
    entry = json.loads(lines[idx])
    entry['data']['__mutated__'] = True
    lines[idx] = json.dumps(entry, separators=(',', ':'))
    ledger.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    ok, bad_seq = verify_chain(ledger)
    assert ok is False
    assert bad_seq is not None
