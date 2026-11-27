"""Restore the sample project's starting files for a fresh demo run."""
from pathlib import Path

CACHE_BYTES = b"\x00FAKE_BUILD_OUTPUT\x00"
NOTES_TEXT = "Project notes\n\nSee src/main.py for the entry point.\n"


def restore(folder: Path) -> list[str]:
    """Write the starting files into `folder`. Returns their relative paths."""
    folder = Path(folder)
    (folder / "cache").mkdir(parents=True, exist_ok=True)
    (folder / "cache" / "output.bin").write_bytes(CACHE_BYTES)
    # Newline fixed, so the file (and its fingerprint) is the same on every system.
    (folder / "notes.txt").write_text(NOTES_TEXT, encoding="utf-8", newline="\n")
    return ["cache/output.bin", "notes.txt"]


def main() -> None:
    restored = restore(Path(__file__).parent)
    print("Restored: " + ", ".join(restored))


if __name__ == "__main__":
    main()
