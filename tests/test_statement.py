"""Tests for papertrail.statement — Task 3."""

import json
from pathlib import Path

import pytest

from papertrail.statement import parse, AGENT_KEYS, PROMOTED_KEYS, FILE_LISTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_stmt(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / 'statement.json'
    p.write_text(json.dumps(data), encoding='utf-8')
    return p


_VALID_PROMOTED = {
    'summary': 'Did some work.',
    'files_read':     ['src/main.py'],
    'files_created':  ['dist/out.bin'],
    'files_modified': ['README.md'],
    'files_deleted':  ['tmp/scratch.txt'],
    'session_id':     'sess-abc',
    'ts':             '2026-01-01T00:00:00.000000Z',
    'witness_seq':    7,
}


# ---------------------------------------------------------------------------
# AC4.4a — valid eight-field file parses correctly
# ---------------------------------------------------------------------------

def test_parse_valid_returns_all_eight_keys(tmp_path):
    """AC4.4a: parsing a valid eight-field file returns a dict with all eight keys."""
    p = _write_stmt(tmp_path, _VALID_PROMOTED)
    result = parse(p)
    assert set(result.keys()) >= PROMOTED_KEYS
    assert result['summary'] == 'Did some work.'
    assert result['files_read'] == ['src/main.py']
    assert result['witness_seq'] == 7


# ---------------------------------------------------------------------------
# AC4.4b — missing each required key raises ValueError naming that key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('missing_key', sorted(PROMOTED_KEYS))
def test_parse_missing_key_raises(tmp_path, missing_key):
    """AC4.4b: parsing a file missing each required key raises ValueError naming it."""
    data = {k: v for k, v in _VALID_PROMOTED.items() if k != missing_key}
    p = _write_stmt(tmp_path, data)
    with pytest.raises(ValueError, match=missing_key):
        parse(p)


# ---------------------------------------------------------------------------
# AC4.4c — absolute path in any file list raises ValueError naming the path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('file_list_key', sorted(FILE_LISTS))
@pytest.mark.parametrize('abs_path', [
    'C:/Users/test/file.txt',
    r'C:\Users\test\file.txt',
    '/usr/local/bin/python',
])
def test_parse_absolute_path_raises(tmp_path, file_list_key, abs_path):
    """AC4.4c: absolute path in any file list raises ValueError naming the path."""
    data = {**_VALID_PROMOTED, file_list_key: [abs_path]}
    p = _write_stmt(tmp_path, data)
    with pytest.raises(ValueError, match=re_escape_partial(abs_path)):
        parse(p)


def re_escape_partial(s: str) -> str:
    """Return a pattern that matches the offending path in the error message.

    The error message contains repr(p), so backslashes are doubled.
    We match on the first two characters (drive letter + colon, or leading
    slash) which are unambiguous and repr-stable.
    """
    import re
    # For Windows paths like "C:/..." or "C:\\...", match "C:" in the message.
    # For Unix paths like "/usr/...", match the leading slash.
    # repr() of "C:\\" is "'C:\\\\...'" so we match the literal drive prefix.
    if len(s) >= 2 and s[1] == ':':
        return re.escape(s[:2])   # e.g. "C:"
    return re.escape(s[0])        # leading slash


# ---------------------------------------------------------------------------
# Extra: back-slash paths are normalised, not rejected
# ---------------------------------------------------------------------------

def test_parse_normalises_backslash_paths(tmp_path):
    """Relative back-slash paths are normalised to forward slashes."""
    data = {**_VALID_PROMOTED, 'files_read': ['src\\utils\\helper.py']}
    p = _write_stmt(tmp_path, data)
    result = parse(p)
    assert result['files_read'] == ['src/utils/helper.py']


# ---------------------------------------------------------------------------
# Extra: duplicate paths within a list raise ValueError
# ---------------------------------------------------------------------------

def test_parse_duplicate_path_raises(tmp_path):
    """Duplicate paths within a list raise ValueError."""
    data = {**_VALID_PROMOTED, 'files_read': ['src/main.py', 'src/main.py']}
    p = _write_stmt(tmp_path, data)
    with pytest.raises(ValueError, match='duplicate'):
        parse(p)
