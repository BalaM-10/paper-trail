"""Tests for papertrail/archive.py and `python -m papertrail archive` (AC3.1 to AC3.7)."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from papertrail import archive as archive_mod
from papertrail import ledger
from papertrail.archive import ArchiveError

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 3, 1, 9, 5, 7, tzinfo=timezone.utc)


def _record(tmp_path: Path, n: int = 3) -> Path:
    path = tmp_path / ".papertrail" / "ledger.jsonl"
    for i in range(n):
        ledger.append(path, "s", "tool", {"tool_name": "read_file", "tool_input": {"path": f"f{i}.py"}})
    return path


def test_the_record_moves_unchanged_and_nothing_is_left_behind(tmp_path):
    path = _record(tmp_path)
    before = path.read_bytes()
    last_hash = ledger.read(path)[-1]["hash"]
    done = archive_mod.archive(tmp_path, NOW)
    target = tmp_path / ".papertrail" / "archive" / "ledger-20260301T090507Z.jsonl"
    assert done.target == ".papertrail/archive/ledger-20260301T090507Z.jsonl"
    assert (done.lines, done.fingerprint) == (3, last_hash)
    assert target.read_bytes() == before  # byte for byte
    assert not path.exists()
    assert ledger.verify_chain(target) == (True, None)


def test_the_next_entry_starts_a_new_record(tmp_path):
    path = _record(tmp_path)
    archive_mod.archive(tmp_path, NOW)
    entry = ledger.append(path, "s2", "tool", {"tool_name": "read_file", "tool_input": {"path": "x"}})
    assert (entry["seq"], entry["prev_hash"]) == (1, "0" * 64)
    assert ledger.verify_chain(path) == (True, None)
    assert len(ledger.read(path)) == 1
    assert len(list((tmp_path / ".papertrail" / "archive").glob("ledger-*.jsonl"))) == 1


def test_two_archives_in_the_same_second_do_not_overwrite_each_other(tmp_path):
    _record(tmp_path, 2)
    first = archive_mod.archive(tmp_path, NOW)
    _record(tmp_path, 4)
    second = archive_mod.archive(tmp_path, NOW)
    assert first.target != second.target
    assert second.target.endswith("-2.jsonl")
    folder = tmp_path / ".papertrail" / "archive"
    assert sorted(len(ledger.read(p)) for p in folder.glob("ledger-*.jsonl")) == [2, 4]


def test_other_files_in_the_project_folder_are_left_alone(tmp_path):
    _record(tmp_path)
    keep = tmp_path / ".papertrail" / "statements" / "s-1.json"
    keep.parent.mkdir()
    keep.write_text("{}", encoding="utf-8")
    archive_mod.archive(tmp_path, NOW)
    assert keep.read_text(encoding="utf-8") == "{}"
    assert not (tmp_path / ".papertrail" / "ledger.lock").exists()  # the lock is released


def test_it_refuses_a_torn_record_and_moves_nothing(tmp_path):
    path = _record(tmp_path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[1]["data"]["tool_input"]["path"] = "edited.py"
    path.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ArchiveError, match="torn at line 2"):
        archive_mod.archive(tmp_path, NOW)
    assert path.read_bytes() == before
    assert not (tmp_path / ".papertrail" / "archive").exists()
    assert not (tmp_path / ".papertrail" / "ledger.lock").exists()


@pytest.mark.parametrize("content", ["not json at all\n", "{\"seq\": 1}\n"])
def test_it_refuses_a_record_it_cannot_read(tmp_path, content):
    path = tmp_path / ".papertrail" / "ledger.jsonl"
    path.parent.mkdir()
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ArchiveError):
        archive_mod.archive(tmp_path, NOW)
    assert path.read_text(encoding="utf-8") == content


@pytest.mark.parametrize("make", ["missing", "empty"])
def test_it_refuses_when_there_is_no_record(tmp_path, make):
    if make == "empty":
        (tmp_path / ".papertrail").mkdir()
        (tmp_path / ".papertrail" / "ledger.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ArchiveError, match="no record to archive"):
        archive_mod.archive(tmp_path, NOW)


def test_it_holds_the_write_lock_while_it_moves(tmp_path, monkeypatch):
    _record(tmp_path)
    seen = {}
    real_replace = os.replace

    def watching(src, dst):
        seen["locked"] = (tmp_path / ".papertrail" / "ledger.lock").exists()
        real_replace(src, dst)

    monkeypatch.setattr(archive_mod.os, "replace", watching)
    archive_mod.archive(tmp_path, NOW)
    assert seen["locked"] is True


def test_the_words_are_plain(tmp_path):
    _record(tmp_path, 1)
    text = "\n".join(archive_mod.describe(archive_mod.archive(tmp_path, NOW)))
    assert "Moved the record (1 line) to .papertrail/archive/ledger-20260301T090507Z.jsonl." in text
    assert "Nothing was deleted." in text and "starts a new record" in text
    assert str(tmp_path) not in text


# ---------------------------------------------------------------------------
# the command line
# ---------------------------------------------------------------------------

def _cli(args: list[str], root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PAPERTRAIL_ROOT": str(root)}
    return subprocess.run([sys.executable, "-m", "papertrail", *args], capture_output=True, text=True,
                          env=env, cwd=str(ROOT), timeout=60)


def test_cli_archive_says_what_it_did(tmp_path):
    _record(tmp_path, 4)
    result = _cli(["archive"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Moved the record (4 lines) to .papertrail/archive/ledger-" in result.stdout
    assert "Fingerprint of the archived record:" in result.stdout
    assert "Nothing was deleted." in result.stdout
    assert not (tmp_path / ".papertrail" / "ledger.jsonl").exists()


def test_cli_archive_refuses_with_status_1(tmp_path):
    result = _cli(["archive"], tmp_path)
    assert result.returncode == 1
    assert "Did not archive: there is no record to archive. Nothing was moved." in result.stdout
    path = _record(tmp_path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["kind"] = "witness"
    path.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n", encoding="utf-8")
    torn = _cli(["archive"], tmp_path)
    assert torn.returncode == 1 and "torn at line 1" in torn.stdout and path.exists()


def test_cli_archive_takes_no_arguments(tmp_path):
    assert _cli(["archive", "now"], tmp_path).returncode == 1


def test_cli_archive_uses_the_current_folder_without_papertrail_root(tmp_path):
    _record(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "PAPERTRAIL_ROOT"}
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run([sys.executable, "-m", "papertrail", "archive"], capture_output=True, text=True,
                            env=env, cwd=str(tmp_path), timeout=60)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".papertrail" / "archive").is_dir()
