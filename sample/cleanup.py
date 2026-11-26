"""Clear the build cache."""
from pathlib import Path

here = Path(__file__).parent
cache_file = here / "cache" / "output.bin"
notes_file = here / "notes.txt"

if cache_file.exists():
    cache_file.unlink()
print("Cleared build cache: removed cache/output.bin")

if notes_file.exists():
    notes_file.unlink()
