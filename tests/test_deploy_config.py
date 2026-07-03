"""Production deploy smoke checks (#727 / P0.16).

The production deploy job referenced a missing ecosystem.production.config.js
and exported a wrong uv PATH ($HOME/.cargo/bin, unescaped), so a fresh
production host aborted under `set -e`. These guard against regressions.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO = Path(__file__).resolve().parents[1]
DEPLOY_YML = REPO / ".github" / "workflows" / "deploy.yml"
PROD_ECOSYSTEM = REPO / "ecosystem.production.config.js"


def test_production_ecosystem_config_exists():
    assert PROD_ECOSYSTEM.is_file(), (
        "ecosystem.production.config.js must exist — deploy.yml runs "
        "`pm2 start ecosystem.production.config.js`"
    )


def test_deploy_uses_correct_uv_path():
    text = DEPLOY_YML.read_text()
    # The broken cargo path must be gone...
    assert "cargo/bin" not in text, "deploy.yml still exports the wrong uv PATH (cargo/bin)"
    # ...and every uv PATH export uses the escaped ~/.local/bin (expands on the host).
    assert 'export PATH="\\$HOME/.local/bin:\\$PATH"' in text


def test_no_dangling_ecosystem_reference():
    """Every ecosystem.*.config.js file the workflow starts must exist."""
    import re

    text = DEPLOY_YML.read_text()
    for name in set(re.findall(r"ecosystem\.[\w.]*config\.js", text)):
        assert (REPO / name).is_file(), f"deploy.yml references missing {name}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_production_config_loads_with_two_apps():
    """Smoke-test: the config parses and defines backend + frontend apps."""
    result = subprocess.run(
        ["node", "-e",
         "const c=require('./ecosystem.production.config.js');"
         "if(!c.apps||c.apps.length!==2){process.exit(1)}"
         "process.stdout.write(c.apps.map(a=>a.name).join(','))"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    names = result.stdout.strip().split(",")
    assert len(names) == 2 and all(names)
