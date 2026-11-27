"""Cross-language hash fixture: Python side.

The browser test in web/src/__tests__/chainCheck.test.ts loads the same file
and must produce the same hash.
"""

import json
from pathlib import Path

from papertrail.ledger import _compute_hash

FIXTURE = Path(__file__).parent / "fixtures" / "hash_fixture.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_python_hash_matches_fixture():
    data = _load()
    assert _compute_hash(data["entry"]) == data["expected_hash"]


def test_fixture_covers_required_character_classes():
    values = _load()["entry"]["data"].values()
    joined = "".join(values)
    assert '"' in joined          # double quote
    assert "\\" in joined         # backslash
    assert "\n" in joined         # newline
    assert "\t" in joined         # tab
    assert "\x01" in joined       # control character U+0001
    assert any(ord(c) > 0xFFFF for c in joined)   # emoji (non-BMP)
    assert any(127 < ord(c) <= 0xFFFF for c in joined)  # accented letter
