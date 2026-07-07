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
STAGING_ECOSYSTEM = REPO / "ecosystem.staging.config.js"
CADDYFILE = REPO / "deploy" / "Caddyfile.example"
STAGING_ENV = REPO / ".env.staging.example"
PROD_ENV = REPO / ".env.production.example"


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


# ---------------------------------------------------------------------------
# TLS reverse proxy (#747 / P1.20): app processes bind loopback; a
# TLS-terminating proxy is the sole public listener; documented origins are
# https/wss.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cfg", [PROD_ECOSYSTEM, STAGING_ECOSYSTEM], ids=["prod", "staging"])
def test_frontend_binds_loopback(cfg):
    """The Next.js frontend must bind 127.0.0.1, never 0.0.0.0 — the Caddy
    reverse proxy is the only process allowed to listen on public interfaces."""
    text = cfg.read_text()
    assert "-H 127.0.0.1" in text, f"{cfg.name}: frontend must bind 127.0.0.1"
    assert "-H 0.0.0.0" not in text, f"{cfg.name}: frontend must not bind 0.0.0.0"


def test_env_examples_bind_backend_loopback():
    """HOST in the deploy env templates must pin the backend to loopback."""
    for env in (STAGING_ENV, PROD_ENV):
        text = env.read_text()
        assert re.search(r"^HOST=127\.0\.0\.1$", text, re.MULTILINE), (
            f"{env.name}: HOST must be 127.0.0.1 (backend behind the proxy)"
        )
        assert "HOST=0.0.0.0" not in text, f"{env.name}: HOST must not be 0.0.0.0"


def test_env_examples_document_tls_origins():
    """Public-facing origins in the deploy templates must be https/wss, not
    plaintext http/ws (the whole point of #747)."""
    for env in (STAGING_ENV, PROD_ENV):
        text = env.read_text()
        for line in text.splitlines():
            if line.startswith("NEXT_PUBLIC_API_URL="):
                assert line.split("=", 1)[1].startswith("https://"), f"{env.name}: {line}"
            if line.startswith("NEXT_PUBLIC_WS_URL="):
                assert line.split("=", 1)[1].startswith("wss://"), f"{env.name}: {line}"


def test_caddyfile_example_exists_and_proxies_both_services():
    """A reverse-proxy config must ship and route to both loopback services."""
    assert CADDYFILE.is_file(), "deploy/Caddyfile.example must exist"
    text = CADDYFILE.read_text()
    assert "reverse_proxy" in text
    assert "127.0.0.1:14200" in text, "Caddyfile must proxy the backend"
    assert "127.0.0.1:14100" in text, "Caddyfile must proxy the frontend"
    # Backend paths (API/auth/websockets) must be routed to the backend.
    assert "/api/*" in text and "/auth/*" in text and "/ws/*" in text


@pytest.mark.skipif(shutil.which("caddy") is None, reason="caddy not available")
def test_caddyfile_example_is_valid():
    """If caddy is installed, the shipped config must pass `caddy validate`."""
    result = subprocess.run(
        ["caddy", "validate", "--config", str(CADDYFILE), "--adapter", "caddyfile"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_remote_setup_installs_proxy_and_binds_loopback_firewall():
    """Provisioning must install the proxy and stop exposing the app ports
    directly (only 80/443 should be public)."""
    text = (REPO / "scripts" / "remote-setup.sh").read_text()
    assert "caddy" in text.lower(), "remote-setup.sh must provision the reverse proxy"
    assert "for port in 80 443" in text, "remote-setup.sh firewall must allow HTTP/HTTPS (80/443)"
    # The raw app ports must no longer be opened to the world.
    assert "ufw allow 14100/tcp" not in text
    assert "ufw allow 14200/tcp" not in text
