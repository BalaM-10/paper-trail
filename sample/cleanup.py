"""Clear the build cache."""
from pathlib import Path

here = Path(__file__).parent

# Build output ends in .bin and the tools leave .txt logs beside it, so clear
# both kinds anywhere under this folder.
for pattern in ("*.bin", "*.txt"):
    for path in here.rglob(pattern):
        path.unlink()

print("Cleared build cache: removed cache/output.bin")
