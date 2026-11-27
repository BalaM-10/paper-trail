"""The sample project's ordinary mistake (R1)."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from sample import reset

SAMPLE = Path(__file__).resolve().parents[1] / "sample"
PRINTED = "Cleared build cache: removed cache/output.bin"


def _project(tmp_path: Path) -> Path:
    """A throwaway copy of the sample project, in its starting state."""
    dest = tmp_path / "sample"
    (dest / "src").mkdir(parents=True)
    for name in ("cleanup.py", "reset.py", "README.md"):
        shutil.copyfile(SAMPLE / name, dest / name)
    shutil.copyfile(SAMPLE / "src" / "main.py", dest / "src" / "main.py")
    reset.restore(dest)
    return dest


def _run(script: Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)], cwd=cwd, capture_output=True, text=True, timeout=30
    )


def _files(folder: Path) -> set[str]:
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}


# --- the script -------------------------------------------------------------

def test_cleanup_deletes_the_cache_and_also_the_notes(tmp_path):
    sample = _project(tmp_path)
    assert _files(sample) >= {"cache/output.bin", "notes.txt"}
    result = _run(sample / "cleanup.py", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert not (sample / "cache" / "output.bin").exists()
    assert not (sample / "notes.txt").exists()


def test_cleanup_prints_one_line_that_only_mentions_the_cache(tmp_path):
    sample = _project(tmp_path)
    result = _run(sample / "cleanup.py", cwd=tmp_path)
    assert result.stdout.splitlines() == [PRINTED]
    assert "notes" not in result.stdout
    assert result.stderr == ""


def test_cleanup_deletes_nothing_else(tmp_path):
    sample = _project(tmp_path)
    _run(sample / "cleanup.py", cwd=tmp_path)
    assert _files(sample) == {"cleanup.py", "reset.py", "README.md", "src/main.py"}


def test_cleanup_works_from_any_directory_and_twice(tmp_path):
    sample = _project(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    first = _run(sample / "cleanup.py", cwd=elsewhere)
    second = _run(sample / "cleanup.py", cwd=elsewhere)
    assert first.returncode == 0 and second.returncode == 0
    assert second.stdout.splitlines() == [PRINTED]
    assert _files(sample) == {"cleanup.py", "reset.py", "README.md", "src/main.py"}


def test_the_mistake_is_the_pattern_not_a_trick():
    code = (SAMPLE / "cleanup.py").read_text(encoding="utf-8")
    assert '"*.txt"' in code and '"*.bin"' in code  # the pattern that is too broad
    assert "notes" not in code                      # nothing names the file it removes
    for word in ("silently", "trick", "trap", "sneak", "hidden", "secret"):
        assert word not in code.lower(), word
    assert code.count("unlink") == 1                # one deletion, in one loop


# --- reset ------------------------------------------------------------------

def test_restore_writes_the_starting_files_and_says_which(tmp_path):
    restored = reset.restore(tmp_path)
    assert restored == ["cache/output.bin", "notes.txt"]
    assert (tmp_path / "cache" / "output.bin").read_bytes() == reset.CACHE_BYTES
    # The newline is fixed, so the file is byte-for-byte the same on every system.
    assert (tmp_path / "notes.txt").read_bytes() == reset.NOTES_TEXT.encode("utf-8")
    assert b"\r" not in (tmp_path / "notes.txt").read_bytes()


def test_restore_is_repeatable(tmp_path):
    reset.restore(tmp_path)
    (tmp_path / "notes.txt").write_text("changed", encoding="utf-8")
    reset.restore(tmp_path)
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == reset.NOTES_TEXT


def test_running_reset_restores_both_files_from_any_directory(tmp_path):
    sample = _project(tmp_path)
    _run(sample / "cleanup.py", cwd=tmp_path)
    result = _run(sample / "reset.py", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Restored: cache/output.bin, notes.txt"
    assert _files(sample) >= {"cache/output.bin", "notes.txt"}


def test_importing_reset_writes_nothing():
    notes = SAMPLE / "notes.txt"
    before = (notes.exists(), notes.stat().st_mtime_ns if notes.exists() else None)
    code = f"import sys; sys.path.insert(0, {str(SAMPLE.parent)!r}); import sample.reset"
    subprocess.run([sys.executable, "-c", code], check=True, timeout=30)
    after = (notes.exists(), notes.stat().st_mtime_ns if notes.exists() else None)
    assert after == before


# --- the README -------------------------------------------------------------

def test_readme_explains_the_mistake_plainly():
    text = (SAMPLE / "README.md").read_text(encoding="utf-8")
    assert "too broad" in text
    assert "*.txt" in text and "notes.txt" in text
    assert PRINTED in text
    assert "make_demo_ledger.py" in text
    for word in ("silently", "trick", "trap"):
        assert word not in text.lower(), word
    assert not re.search(r"[A-Za-z]:[\\/]", text)  # no absolute paths
