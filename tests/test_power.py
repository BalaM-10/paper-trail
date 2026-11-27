"""power/paper-trail follows the layout in Kiro's documentation for Powers."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWER = ROOT / "power" / "paper-trail"


def _json(name: str) -> dict:
    return json.loads((POWER / name).read_text(encoding="utf-8"))


def test_the_manifest_has_the_documented_fields():
    plugin = _json("plugin.json")
    assert plugin["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", plugin["name"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", plugin["version"])
    assert plugin["description"].strip()
    assert plugin["author"]["name"].strip()
    assert plugin["keywords"] and all(isinstance(k, str) and k for k in plugin["keywords"])


def test_the_power_and_the_package_agree_on_the_version():
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert _json("plugin.json")["version"] == project["version"]


def test_mcp_json_has_the_paper_trail_server():
    mcp = _json("mcp.json")
    server = mcp["mcpServers"]["paper-trail"]
    assert server["type"] == "stdio"
    assert server["command"] == "python"
    assert server["args"] == ["-m", "papertrail.mcp_server"]
    assert "env" not in server  # no secrets, no absolute paths


def test_it_matches_the_server_that_init_writes():
    packaged = json.loads((ROOT / "papertrail" / "assets" / "mcp-server.json").read_text(encoding="utf-8"))
    server = _json("mcp.json")["mcpServers"]["paper-trail"]
    assert (server["command"], server["args"]) == (packaged["command"], packaged["args"])


SKILLS = sorted(p for p in (POWER / "skills").iterdir() if p.is_dir())


def test_there_are_two_skills():
    assert [p.name for p in SKILLS] == ["check-my-work", "install"]


@pytest.mark.parametrize("folder", SKILLS, ids=lambda p: p.name)
def test_each_skill_has_front_matter_that_names_its_folder(folder):
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, "SKILL.md must start with front matter"
    fields = dict(line.split(": ", 1) for line in match.group(1).splitlines())
    assert fields["name"] == folder.name
    assert fields["description"].strip()


def test_the_power_holds_only_what_a_power_can_hold():
    """Documented components: plugin.json, skills/, mcp.json. No hooks, no steering."""
    top = {p.name for p in POWER.iterdir()}
    assert top == {"plugin.json", "mcp.json", "skills"}


def test_the_install_skill_tells_the_agent_to_run_init():
    text = (POWER / "skills" / "install" / "SKILL.md").read_text(encoding="utf-8")
    assert "python -m papertrail init" in text
    assert "python -m papertrail doctor" in text


def test_the_check_skill_names_real_tools():
    text = (POWER / "skills" / "check-my-work" / "SKILL.md").read_text(encoding="utf-8")
    server = (ROOT / "papertrail" / "mcp_server.py").read_text(encoding="utf-8")
    for tool in re.findall(r"`([a-z_]+)`", text):
        if tool in {"list_sessions", "verify_statement", "print_session", "check_chain"}:
            assert f"def {tool}(" in server
    for tool in ("list_sessions", "verify_statement", "print_session", "check_chain"):
        assert f"`{tool}`" in text
