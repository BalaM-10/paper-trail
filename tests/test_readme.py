"""The README only names things that exist (AC4.1 to AC4.5)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
SKIP_DIRS = {"node_modules", ".git", "dist", ".hypothesis", ".pytest_cache", "__pycache__"}


def _backticked() -> list[str]:
    return re.findall(r"`([^`\n]+)`", README)


def _exists_somewhere(name: str) -> bool:
    return any(not (SKIP_DIRS & set(p.relative_to(ROOT).parts)) for p in ROOT.rglob(name))


def _is_path(token: str) -> bool:
    if any(c in token for c in "<>$\\ ") or token.startswith(("http", "-", "python", "npm", "npx")):
        return False
    if token.startswith(".papertrail"):  # runtime data, not in the repository
        return False
    if "/" in token:
        return True
    return bool(re.fullmatch(r"[\w.-]+\.(py|md|json|yml|jsonl|toml)", token)) or token == "LICENSE"


PATHS = sorted({t for t in _backticked() if _is_path(t)})


def test_the_readme_names_some_paths():
    assert len(PATHS) >= 15


@pytest.mark.parametrize("token", PATHS)
def test_every_path_in_the_readme_exists(token):
    if "/" in token:
        assert (ROOT / token.rstrip("/")).exists(), token
    else:
        assert _exists_somewhere(token), token


def test_markdown_links_point_at_real_places():
    for target in re.findall(r"\]\(([^)]+)\)", README):
        if not target.startswith("http"):
            assert (ROOT / target).exists(), target


def test_every_script_the_readme_runs_exists():
    for script in re.findall(r"python (\S+\.py)", README):
        assert (ROOT / script).is_file(), script


def test_every_subcommand_the_readme_uses_exists():
    main = (ROOT / "papertrail" / "__main__.py").read_text(encoding="utf-8")
    commands = set(re.findall(r'cmd == "([a-z-]+)"', main))
    used = re.findall(r"python -m papertrail ([a-z][\w-]*)", README)
    assert {"init", "doctor", "verify", "print", "check-chain", "serve"} <= set(used)
    for word in used:
        assert word in commands, word


def test_the_install_command_is_the_one_init_takes():
    assert "python -m papertrail init C:\\path\\to\\your\\project" in README
    assert "--force" in README
    main = (ROOT / "papertrail" / "__main__.py").read_text(encoding="utf-8")
    assert "init <project_folder> [--force]" in main
    install = (ROOT / "papertrail" / "install.py").read_text(encoding="utf-8")
    assert "Left alone" in install and "Left alone" in " ".join(README.split())


def test_the_top_has_the_question_then_the_explanation_then_install_then_verdicts():
    order = [
        README.index("**Did the agent do what it said?**"),
        README.index("## In 30 seconds"),
        README.index("## Install in one command"),
        README.index("## The verdicts"),
    ]
    assert order == sorted(order)
    assert README.index("# Paper Trail") < order[0]
    verdicts = README[README.index("## The verdicts"): README.index("## Try the demo")]
    for word in ("SUPPORTED", "CONTRADICTED", "UNVERIFIED", "NO STATEMENT"):
        assert f"| {word} |" in verdicts


def test_the_explanation_names_the_five_parts():
    part = README[README.index("## In 30 seconds"): README.index("## Install in one command")]
    for word in ("Record", "Witness", "Statement", "Verdict", "Printout"):
        assert f"**{word}.**" in part


def test_built_with_kiro_names_what_was_used():
    section = README[README.index("## Built with Kiro"): README.index("## Running the tests")]
    for spec in sorted(p.name for p in (ROOT / ".kiro" / "specs").iterdir() if p.is_dir()):
        assert f"`{spec}`" in section, spec
    for hook in sorted(p.name for p in (ROOT / ".kiro" / "hooks").glob("*.json")):
        assert f"`{hook}`" in section, hook
    for steering in sorted(p.name for p in (ROOT / ".kiro" / "steering").glob("*.md")):
        assert f"`{steering}`" in section, steering
    server = (ROOT / "papertrail" / "mcp_server.py").read_text(encoding="utf-8")
    tools = re.findall(r"@server\.tool\(\)\s*\n\s*def (\w+)\(", server)
    assert len(tools) == 5
    for tool in tools:
        assert f"`{tool}`" in section, tool
    # the files named as property-based tests really use Hypothesis
    for name in re.findall(r"`(tests/test_\w+\.py)`", section):
        assert "@given" in (ROOT / name).read_text(encoding="utf-8"), name


def test_windows_comes_first_and_the_license_is_named():
    assert "```powershell" in README
    assert "Windows, macOS or Linux" in README
    assert "MIT" in README.split("## License")[1]
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")


def test_readme_is_plain_utf8_without_a_byte_order_mark():
    raw = (ROOT / "README.md").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "\u2014" not in README  # no em-dash chains
