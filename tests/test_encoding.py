"""Text files are UTF-8 without a byte-order mark (a BOM once broke package.json)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {".py", ".md", ".json", ".jsonl", ".txt", ".ts", ".tsx", ".css", ".html", ".yml", ".yaml"}
SKIP = {"node_modules", "dist", ".git", ".hypothesis", ".pytest_cache", "__pycache__", ".papertrail", ".venv"}
BOM = b"\xef\xbb\xbf"


def _text_files() -> list[Path]:
    found = []
    for path in ROOT.rglob("*"):
        if path.suffix.lower() not in SUFFIXES or not path.is_file():
            continue
        if SKIP & set(path.relative_to(ROOT).parts):
            continue
        found.append(path)
    return found


def test_no_file_starts_with_a_byte_order_mark():
    assert _text_files(), "found nothing to check"
    with_bom = [p.relative_to(ROOT).as_posix() for p in _text_files() if p.read_bytes().startswith(BOM)]
    assert with_bom == []


def test_every_text_file_is_valid_utf8():
    bad = []
    for path in _text_files():
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            bad.append(path.relative_to(ROOT).as_posix())
    assert bad == []