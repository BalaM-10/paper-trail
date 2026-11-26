"""Tests for papertrail.recorder — Task 4 (revised)."""

import hashlib
from pathlib import Path

import pytest

from papertrail import ledger
from papertrail.recorder import record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ledger(tmp_path: Path) -> Path:
    return tmp_path / ".papertrail" / "ledger.jsonl"


def _last_entry(tmp_path: Path) -> dict:
    entries = ledger.read(_ledger(tmp_path))
    assert entries, "ledger is empty"
    return entries[-1]


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# AC2.1a — fs_write payload stores relative path
# ---------------------------------------------------------------------------

def test_fs_write_payload_relative_path(tmp_path):
    """AC2.1a: fs_write payload → ledger entry with relative tool_input.path."""
    abs_path = str(tmp_path / "papertrail" / "ledger.py")
    payload = {
        "session_id": "sess-a",
        "hook_event_name": "PostToolUse",
        "tool_name": "fs_write",
        "tool_input": {"path": abs_path, "text": "hello"},
        "tool_response": "ok",
    }
    record(payload, tmp_path, Path.home())

    entry = _last_entry(tmp_path)
    assert entry["kind"] == "tool"
    stored_path = entry["data"]["tool_input"]["path"]
    assert not Path(stored_path).is_absolute(), f"Path is still absolute: {stored_path!r}"
    assert stored_path == "papertrail/ledger.py"


# ---------------------------------------------------------------------------
# AC2.1b — execute_pwsh: command starting with absolute root → "." prefix
# ---------------------------------------------------------------------------

def test_execute_pwsh_command_root_replaced_by_dot(tmp_path):
    """
    AC2.1b: command beginning with the absolute root has the root replaced
    with "." by sanitise; the arguments after the root are kept verbatim.
    """
    abs_cmd = str(tmp_path) + "\\some\\script.ps1 --clean"
    payload = {
        "session_id": "sess-b",
        "hook_event_name": "PostToolUse",
        "tool_name": "execute_pwsh",
        "tool_input": {"command": abs_cmd, "description": "run script"},
        "tool_response": "",
    }
    record(payload, tmp_path, Path.home())

    entry = _last_entry(tmp_path)
    stored_cmd = entry["data"]["tool_input"]["command"]

    # Root must be gone.
    assert str(tmp_path).lower() not in stored_cmd.lower(), (
        f"Root path not redacted in command: {stored_cmd!r}"
    )
    # sanitise() replaces the root with ".", so the result starts with ".".
    assert stored_cmd.startswith("."), (
        f"Expected stored command to start with '.', got: {stored_cmd!r}"
    )
    # The arguments after the root path must still be present.
    assert "--clean" in stored_cmd, (
        f"Arguments were stripped from command: {stored_cmd!r}"
    )


# ---------------------------------------------------------------------------
# AC2.1c — bad payload → record() raises; caller appends error entry
# ---------------------------------------------------------------------------

def test_bad_payload_raises_and_error_entry_appended(tmp_path):
    """AC2.1c: tool_input that is not a dict causes record() to raise; error appended."""
    bad_payload = {
        "session_id": "sess-c",
        "hook_event_name": "PostToolUse",
        "tool_name": "fs_write",
        "tool_input": "not-a-dict",
        "tool_response": "ok",
    }
    lp = _ledger(tmp_path)
    try:
        record(bad_payload, tmp_path, Path.home())
    except Exception as exc:
        lp.parent.mkdir(parents=True, exist_ok=True)
        ledger.append(lp, bad_payload.get("session_id", "unknown"),
                      "error", {"error": str(exc), "raw": str(bad_payload)[:500]})
    entry = _last_entry(tmp_path)
    assert entry["kind"] == "error"
    assert entry["session_id"] == "sess-c"


# ---------------------------------------------------------------------------
# AC2.1d — no session_id → "unknown"; ledger dir created if absent
# ---------------------------------------------------------------------------

def test_no_session_id_uses_unknown(tmp_path):
    """AC2.1d: payload with no session_id → 'unknown' used, entry appended."""
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "fs_write",
        "tool_input": {"path": "README.md", "text": "hi"},
        "tool_response": "written",
    }
    entry = record(payload, tmp_path, Path.home())
    assert entry["session_id"] == "unknown"
    assert entry["kind"] == "tool"


def test_ledger_dir_created_if_absent(tmp_path):
    """Ledger directory is created automatically when missing."""
    deep_root = tmp_path / "nested" / "project"
    payload = {
        "session_id": "sess-d",
        "hook_event_name": "PostToolUse",
        "tool_name": "fs_write",
        "tool_input": {"path": "a.txt", "text": "x"},
        "tool_response": "ok",
    }
    entry = record(payload, deep_root, Path.home())
    assert (deep_root / ".papertrail" / "ledger.jsonl").exists()
    assert entry["kind"] == "tool"


# ---------------------------------------------------------------------------
# Content keys — text is stored as digest, never verbatim
# ---------------------------------------------------------------------------

def test_text_value_stored_as_digest(tmp_path):
    """fs_write text starting with '//' is stored as size+sha256, never as text."""
    text = "// generated code\nconst x = 1;\n"
    payload = {
        "session_id": "sess-e",
        "hook_event_name": "PostToolUse",
        "tool_name": "fs_write",
        "tool_input": {"path": "src/app.ts", "text": text},
        "tool_response": "ok",
    }
    record(payload, tmp_path, Path.home())

    entry = _last_entry(tmp_path)
    stored = entry["data"]["tool_input"]["text"]

    # Must be a digest object, not the raw text.
    assert isinstance(stored, dict), f"Expected digest dict, got: {stored!r}"
    assert "size" in stored and "sha256" in stored
    assert "text" not in stored, "Raw text must not be stored"
    assert stored["size"] == len(text.encode("utf-8"))
    assert stored["sha256"] == _sha256(text)


def test_long_value_stored_as_digest(tmp_path):
    """Any string value > 2000 characters is stored as a digest."""
    long_val = "x" * 2001
    payload = {
        "session_id": "sess-f",
        "hook_event_name": "PostToolUse",
        "tool_name": "execute_pwsh",
        "tool_input": {"command": "echo hi", "description": long_val},
        "tool_response": "",
    }
    record(payload, tmp_path, Path.home())

    entry = _last_entry(tmp_path)
    stored = entry["data"]["tool_input"]["description"]
    assert isinstance(stored, dict)
    assert stored["size"] == len(long_val.encode("utf-8"))


# ---------------------------------------------------------------------------
# tool_response truncation
# ---------------------------------------------------------------------------

def test_long_tool_response_is_truncated(tmp_path):
    """A 5000-character tool_response is truncated to 2000 chars with truncated=True."""
    response = "a" * 5000
    payload = {
        "session_id": "sess-g",
        "hook_event_name": "PostToolUse",
        "tool_name": "execute_pwsh",
        "tool_input": {"command": "echo hi"},
        "tool_response": response,
    }
    record(payload, tmp_path, Path.home())

    entry = _last_entry(tmp_path)
    stored = entry["data"]["tool_response"]

    assert isinstance(stored, dict), f"Expected truncation dict, got: {stored!r}"
    assert stored["truncated"] is True
    assert len(stored["value"]) == 2000
    assert stored["value"] == "a" * 2000


def test_short_tool_response_stored_verbatim(tmp_path):
    """A short tool_response is stored as a plain string."""
    payload = {
        "session_id": "sess-h",
        "hook_event_name": "PostToolUse",
        "tool_name": "fs_write",
        "tool_input": {"path": "x.txt", "text": "hi"},
        "tool_response": "Written successfully.",
    }
    record(payload, tmp_path, Path.home())

    entry = _last_entry(tmp_path)
    stored = entry["data"]["tool_response"]
    assert isinstance(stored, str)
    assert stored == "Written successfully."
