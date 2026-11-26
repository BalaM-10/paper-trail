"""Tests for papertrail.witness — Task 2."""

import hashlib
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from papertrail.witness import EXCLUDE, diff, snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: bytes = b'hello') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# AC3.1 — snapshot
# ---------------------------------------------------------------------------

def test_snapshot_size_and_sha256(tmp_path):
    """AC3.1a: snapshot returns correct size and SHA-256 for a known file."""
    content = b'known content'
    _write(tmp_path / 'file.txt', content)

    snap = snapshot(tmp_path)

    assert 'file.txt' in snap
    assert snap['file.txt']['size'] == len(content)
    assert snap['file.txt']['sha256'] == _sha256(content)


def test_snapshot_excludes_dot_git(tmp_path):
    """AC3.1b: .git directory is absent from the snapshot."""
    _write(tmp_path / '.git' / 'HEAD', b'ref: refs/heads/main')
    _write(tmp_path / 'src' / 'main.py', b'print("hi")')

    snap = snapshot(tmp_path)

    assert not any(p.startswith('.git/') or p == '.git' for p in snap)
    assert 'src/main.py' in snap


def test_snapshot_excludes_node_modules(tmp_path):
    """AC3.1b (node_modules): node_modules directory is absent from snapshot."""
    _write(tmp_path / 'node_modules' / 'pkg' / 'index.js', b'module.exports={}')
    _write(tmp_path / 'src' / 'app.ts', b'export {}')

    snap = snapshot(tmp_path)

    assert not any('node_modules' in p for p in snap)
    assert 'src/app.ts' in snap


def test_snapshot_paths_are_forward_slash_relative(tmp_path):
    """AC3.1c: all paths use forward slashes and are relative."""
    _write(tmp_path / 'a' / 'b' / 'c.txt', b'x')

    snap = snapshot(tmp_path)

    for key in snap:
        assert '\\' not in key, f"Back-slash in path: {key!r}"
        assert not key.startswith('/'), f"Absolute path in snapshot: {key!r}"
        assert not key[1:3] == ':\\', f"Drive letter in snapshot: {key!r}"


# ---------------------------------------------------------------------------
# AC3.2 — diff
# ---------------------------------------------------------------------------

def test_diff_created(tmp_path):
    """AC3.2a: file in new but not old → created."""
    old: dict = {}
    new = {'a.txt': {'size': 1, 'sha256': 'aa'}}
    result = diff(old, new)
    assert result['created'] == ['a.txt']
    assert result['deleted'] == []
    assert result['modified'] == []


def test_diff_deleted(tmp_path):
    """AC3.2b: file in old but not new → deleted."""
    old = {'a.txt': {'size': 1, 'sha256': 'aa'}}
    new: dict = {}
    result = diff(old, new)
    assert result['deleted'] == ['a.txt']
    assert result['created'] == []
    assert result['modified'] == []


def test_diff_modified(tmp_path):
    """AC3.2c: file in both with different sha256 → modified."""
    old = {'a.txt': {'size': 1, 'sha256': 'aa'}}
    new = {'a.txt': {'size': 2, 'sha256': 'bb'}}
    result = diff(old, new)
    assert result['modified'] == ['a.txt']
    assert result['created'] == []
    assert result['deleted'] == []


def test_diff_unchanged(tmp_path):
    """AC3.2d: same path, same sha256 → not in any list."""
    snap = {'a.txt': {'size': 1, 'sha256': 'aa'}}
    result = diff(snap, snap)
    assert result['created'] == []
    assert result['deleted'] == []
    assert result['modified'] == []


def test_diff_identical_snapshots(tmp_path):
    """AC3.2e: two identical snapshots produce empty diff."""
    _write(tmp_path / 'x.txt', b'data')
    snap = snapshot(tmp_path)
    result = diff(snap, snap)
    assert result == {'created': [], 'deleted': [], 'modified': []}


# ---------------------------------------------------------------------------
# Hypothesis — AC8.3: diff of two arbitrary snapshots is correct
# ---------------------------------------------------------------------------

_snap_entry = st.fixed_dictionaries({
    'size': st.integers(min_value=0, max_value=10 ** 9),
    'sha256': st.text(alphabet='0123456789abcdef', min_size=64, max_size=64),
})

_path_key = st.text(
    alphabet='abcdefghijklmnopqrstuvwxyz_.',
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip('.') != '')

_snapshot_strategy = st.dictionaries(_path_key, _snap_entry, max_size=10)


@given(_snapshot_strategy, _snapshot_strategy)
@settings(max_examples=200)
def test_hypothesis_diff_properties(old, new):
    """AC8.3a-b: diff invariants hold for arbitrary snapshot pairs."""
    result = diff(old, new)

    created  = set(result['created'])
    deleted  = set(result['deleted'])
    modified = set(result['modified'])

    # AC8.3a: membership
    for p in created:
        assert p in new and p not in old
    for p in deleted:
        assert p in old and p not in new
    for p in modified:
        assert p in old and p in new
        assert old[p]['sha256'] != new[p]['sha256']

    # AC8.3b: no path appears in more than one list
    all_lists = [result['created'], result['deleted'], result['modified']]
    all_paths = [p for lst in all_lists for p in lst]
    assert len(all_paths) == len(set(all_paths)), "Path appears in multiple diff lists"
