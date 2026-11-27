"""The test workflow in .github/workflows/tests.yml (read as text, no YAML package)."""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "tests.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_runs_on_all_three_systems():
    text = _text()
    match = re.search(r"os:\s*\[([^\]]+)\]", text)
    assert match, "no os matrix found"
    systems = {s.strip() for s in match.group(1).split(",")}
    assert systems == {"ubuntu-latest", "windows-latest", "macos-latest"}
    assert "runs-on: ${{ matrix.os }}" in text


def test_one_system_failing_does_not_hide_the_others():
    assert re.search(r"fail-fast:\s*false", _text())


def test_runs_on_push_and_pull_request():
    text = _text()
    assert re.search(r"^on:\s*\n\s+push:", text, re.M)
    assert re.search(r"^\s+pull_request:", text, re.M)


def test_uses_the_pinned_versions():
    text = _text()
    assert 'python-version: "3.11"' in text
    assert re.search(r"node-version:\s*20\b", text)


def test_runs_the_python_and_web_checks():
    text = _text()
    for command in (
        "pip install -r requirements.txt",
        "python -m pytest tests/ -q",
        "npm ci",
        "npx vitest run",
        "npm run build",
    ):
        assert f"run: {command}" in text, command


def test_web_steps_run_in_the_web_folder():
    text = _text()
    for command in ("npm ci", "npx vitest run", "npm run build"):
        step = re.search(rf"run: {re.escape(command)}\n(\s+)working-directory: web", text)
        assert step, f"{command} must run in web/"


def test_nothing_secret_is_used():
    assert "secrets." not in _text()