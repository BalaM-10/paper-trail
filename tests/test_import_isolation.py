"""The hook scripts rely on the core modules being standard-library only."""

import subprocess
import sys

import pytest

FORBIDDEN = ["fastapi", "uvicorn", "httpx", "mcp"]
CORE = [
    "papertrail.ledger",
    "papertrail.witness",
    "papertrail.session",
    "papertrail.recorder",
]


@pytest.mark.parametrize("module", CORE)
def test_core_module_does_not_import_optional_packages(module):
    code = (
        f"import {module}, sys; "
        f"bad = [m for m in {FORBIDDEN!r} if m in sys.modules]; "
        f"assert not bad, bad"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"Importing {module} pulled in optional packages:\n{result.stderr}"
    )
