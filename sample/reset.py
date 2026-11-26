"""Restore sample project files for a fresh demo run."""
from pathlib import Path

here = Path(__file__).parent
(here / "cache").mkdir(exist_ok=True)
(here / "cache" / "output.bin").write_bytes(b"\x00FAKE_BUILD_OUTPUT\x00")
(here / "notes.txt").write_text(
    "Project notes\n\nSee src/main.py for the entry point.\n",
    encoding="utf-8",
)
