"""Extract and record tool-call data from a hook payload into the ledger."""

import hashlib
from pathlib import Path

from papertrail import ledger

# Keys whose values are filesystem paths and should be normalised via to_relative.
_PATH_KEYS: frozenset[str] = frozenset({
    "path", "cwd", "file_path", "filePath", "target", "directory",
})

# Keys whose string values are file contents and must never be stored verbatim.
_CONTENT_KEYS: frozenset[str] = frozenset({
    "text", "content", "contents", "new_str", "old_str",
})

# Strings longer than this are replaced with a size/sha256 digest.
_MAX_VALUE_LEN = 2000
# tool_response is truncated (not digested) at this length.
_MAX_RESPONSE_LEN = 2000


def _digest(value: str) -> dict:
    """Return {"size": <UTF-8 bytes>, "sha256": <hex>} for a string."""
    encoded = value.encode("utf-8")
    return {
        "size":   len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _process_input_value(key: str, value: str, root: Path, home: Path):
    """
    Return the stored form for one tool_input string value.

    - Content keys  → digest (size + sha256), never stored verbatim.
    - Values > 2000 chars → digest.
    - Path keys     → to_relative().
    - Everything else → sanitise() only; no path guessing.
    """
    if key in _CONTENT_KEYS or len(value) > _MAX_VALUE_LEN:
        return _digest(value)
    if key in _PATH_KEYS:
        return ledger.to_relative(value, root)
    return ledger.sanitise(value, root, home)


def record(payload: dict, root: Path, home: Path) -> dict:
    """
    Extract tool call fields from a parsed PostToolUse payload, normalise
    paths and sanitise strings, append a "tool" ledger entry, and return it.

    Raises on ledger failure (the caller is responsible for error handling).

    Field extraction uses .get() with safe defaults throughout so malformed
    payloads never raise a KeyError.
    """
    session_id: str      = payload.get("session_id", "unknown")
    tool_name: str       = payload.get("tool_name", "")
    tool_input: dict     = payload.get("tool_input") or {}
    tool_response        = payload.get("tool_response", "")
    hook_event_name: str = payload.get("hook_event_name", "")

    ledger_path = root / ".papertrail" / "ledger.jsonl"

    # Process each tool_input value.
    normalised_input: dict = {}
    for key, value in tool_input.items():
        if not isinstance(value, str):
            normalised_input[key] = value
        else:
            normalised_input[key] = _process_input_value(key, value, root, home)

    # Sanitise and truncate tool_response.
    if isinstance(tool_response, str):
        sanitised = ledger.sanitise(tool_response, root, home)
        if len(sanitised) > _MAX_RESPONSE_LEN:
            stored_response = {"value": sanitised[:_MAX_RESPONSE_LEN], "truncated": True}
        else:
            stored_response = sanitised
    else:
        stored_response = tool_response

    data = {
        "tool_name":       tool_name,
        "hook_event_name": hook_event_name,
        "tool_input":      normalised_input,
        "tool_response":   stored_response,
    }

    return ledger.append(ledger_path, session_id, "tool", data)
