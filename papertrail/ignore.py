"""Which files the witness leaves out: the project's .gitignore plus a built-in list.

Standard library only, because the hooks import this through `witness`.

What is read from `.gitignore` (the project's top-level file only):
- blank lines and lines starting with `#` are skipped;
- `!` at the start negates a line; the last line that matches a path decides;
- a `/` at the start or inside a pattern anchors it to the project folder, a
  pattern without one matches a name at any depth;
- a `/` at the end matches folders only;
- `*`, `?` and `[...]` never match `/`; `**` matches any number of folders;
- `\\#`, `\\!` and `\\ ` stand for the plain character;
- a file inside an ignored folder stays ignored, as in git.

Nested `.gitignore` files, `.git/info/exclude` and the global ignore file are not
read. See .kiro/specs/paper-trail-ignore/design.md.
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

#: The value of the `ignore` field in a snapshot record: the snapshot follows the
#: rule above. The record never holds a pattern or a skipped path.
RULE_NAME = "gitignore"

#: Common caches and editor files for Python, Node and editors. They are placed
#: before the project's own lines, so a line such as `!.cache/` brings one back.
BUILTIN: tuple[str, ...] = (
    # Python
    ".pytest_cache/", ".hypothesis/", ".mypy_cache/", ".ruff_cache/", ".tox/",
    ".nox/", ".eggs/", "*.egg-info/", "htmlcov/", ".ipynb_checkpoints/", "venv/",
    "*.pyc", "*.pyo", ".coverage", ".coverage.*",
    # Node
    ".cache/", ".parcel-cache/", ".turbo/", ".next/", ".nyc_output/",
    "*.tsbuildinfo", ".eslintcache",
    # Editors and the operating system
    ".idea/", ".vs/", "*.swp", "*.swo", "*~", ".DS_Store", "Thumbs.db",
)


@dataclass(frozen=True)
class _Rule:
    regex: "re.Pattern[str]"
    negated: bool
    folders_only: bool


def _class(pattern: str, start: int) -> tuple[str, int] | None:
    """A `[...]` class starting at pattern[start]. Returns (regex, next index) or None if unclosed."""
    i = start + 1
    if i < len(pattern) and pattern[i] in "!^":
        i += 1
    first = i
    while i < len(pattern):
        if pattern[i] == "]" and i > first:
            body = pattern[start + 1:i]
            negate = body[:1] in ("!", "^")
            if negate:
                body = body[1:]
            body = body.replace("\\", "\\\\").replace("[", "\\[")
            return f"[{'^' if negate else ''}{body}]", i + 1
        i += 1
    return None


def _segment(seg: str) -> str:
    """The regular expression for one path segment of a pattern."""
    out: list[str] = []
    i = 0
    while i < len(seg):
        c = seg[i]
        if c == "\\" and i + 1 < len(seg):
            out.append(re.escape(seg[i + 1]))
            i += 2
        elif c == "*":
            while i < len(seg) and seg[i] == "*":
                i += 1
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            found = _class(seg, i)
            if found is None:
                out.append(re.escape(c))
                i += 1
            else:
                out.append(found[0])
                i = found[1]
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def _parse(line: str, ignore_case: bool) -> _Rule | None:
    """One line of a .gitignore as a rule, or None when it holds no rule."""
    line = line.rstrip("\r\n")
    if not line or line.startswith("#"):
        return None
    while line.endswith(" ") and not line.endswith("\\ "):
        line = line[:-1]
    negated = line.startswith("!")
    if negated:
        line = line[1:]
    folders_only = line.endswith("/")
    line = line.rstrip("/")
    if not line:
        return None
    anchored = "/" in line
    line = line.lstrip("/")
    parts = line.split("/")
    rx = ""
    for i, seg in enumerate(parts):
        last = i == len(parts) - 1
        if seg == "**":
            rx += (".*" if len(parts) == 1 else ".+") if last else "(?:.*/)?"
        else:
            rx += _segment(seg) + ("" if last else "/")
    prefix = "" if anchored else "(?:.*/)?"
    flags = re.DOTALL | (re.IGNORECASE if ignore_case else 0)
    try:
        return _Rule(re.compile(f"^{prefix}{rx}$", flags), negated, folders_only)
    except re.error:
        return None


class Matcher:
    """Answers "is this path ignored?" for paths relative to the project folder, with `/`."""

    def __init__(self, lines: list[str] | tuple[str, ...] = (), ignore_case: bool = False) -> None:
        rules = (_parse(line, ignore_case) for line in lines)
        self._rules: tuple[_Rule, ...] = tuple(r for r in rules if r is not None)

    @classmethod
    def load(cls, root: Path) -> "Matcher":
        """The built-in list followed by the project's top-level .gitignore, if it has one."""
        lines: list[str] = list(BUILTIN)
        try:
            text = (Path(root) / ".gitignore").read_bytes().decode("utf-8-sig", errors="replace")
            lines += text.split("\n")
        except OSError:
            pass
        return cls(lines, ignore_case=sys.platform == "win32")

    def matches(self, path: str, is_dir: bool = False) -> bool:
        """The decision for this path alone. The caller knows no folder above it is ignored."""
        result = False
        for rule in self._rules:
            if rule.folders_only and not is_dir:
                continue
            if rule.regex.match(path):
                result = not rule.negated
        return result

    def is_ignored(self, path: str, is_dir: bool = False) -> bool:
        """True if the path, or any folder above it, is ignored."""
        path = path.replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        parts = [p for p in path.split("/") if p]
        for i in range(1, len(parts)):
            if self.matches("/".join(parts[:i]), True):
                return True
        return bool(parts) and self.matches("/".join(parts), is_dir)
