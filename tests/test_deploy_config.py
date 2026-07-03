"""Production deploy smoke checks (#727 / P0.16).

The production deploy job referenced a missing ecosystem.production.config.js
and exported a wrong uv PATH ($HOME/.cargo/bin, unescaped), so a fresh
production host aborted under `set -e`. These guard against regressions.
"""

import re
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
    text = DEPLOY_YML.read_text()
    for name in set(re.findall(r"ecosystem\.[\w.]*config\.js", text)):
        assert (REPO / name).is_file(), f"deploy.yml references missing {name}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_production_config_is_valid_javascript():
    """Smoke-test: the config parses as valid JS. `node --check` is syntax-only
    (no execution / module resolution), so it doesn't need the root npm deps
    that only exist on the deploy host, yet still catches a broken config."""
    result = subprocess.run(
        ["node", "--check", "ecosystem.production.config.js"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_production_config_defines_two_apps():
    """The config must define backend + frontend apps. Checked statically so it
    needs no node/npm deps: both app blocks reference the venv python and next."""
    text = PROD_ECOSYSTEM.read_text()
    assert ".venv/bin/python" in text  # backend app
    assert "web-ui/node_modules/.bin/next" in text  # frontend app
    assert text.count("name:") == 2  # exactly two pm2 apps
