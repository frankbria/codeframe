"""Tests for the notifications endpoints in settings_v2 (issue #560).

Covers:
- GET returns defaults when no config exists
- PUT persists URL + enabled flag and GET reads it back
- PUT with empty URL clears the value
- POST /test returns 400 when no URL configured
- POST /test surfaces the underlying webhook status code
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace():
    temp_dir = Path(tempfile.mkdtemp())
    ws_path = temp_dir / "ws"
    ws_path.mkdir(parents=True, exist_ok=True)
    from codeframe.core.workspace import create_or_load_workspace

    ws = create_or_load_workspace(ws_path)
    try:
        yield ws
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client(workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import settings_v2

    app = FastAPI()
    app.include_router(settings_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    return TestClient(app)


# Note on the "workspace_path contract" suggestion raised by reviewers:
# `get_v2_workspace` does not strictly fail when ``workspace_path`` is
# absent — it falls back to default-workspace resolution. So a test
# asserting 400/422 on missing query param wouldn't reflect reality.
# That contract is a router-wide concern; it's not specific to #560 and
# would need a fix in the dependency itself, not in this endpoint's tests.


class TestGetNotificationSettings:
    def test_returns_defaults_when_no_config(self, client):
        r = client.get("/api/v2/settings/notifications")
        assert r.status_code == 200
        data = r.json()
        assert data == {"webhook_url": None, "webhook_enabled": False}


class TestUpdateNotificationSettings:
    def test_persists_url_and_flag(self, client):
        r = client.put(
            "/api/v2/settings/notifications",
            json={
                "webhook_url": "https://hooks.example.com/abc",
                "webhook_enabled": True,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["webhook_url"] == "https://hooks.example.com/abc"
        assert data["webhook_enabled"] is True

    def test_roundtrip_get_after_put(self, client):
        client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "https://x.test/h", "webhook_enabled": False},
        )
        r = client.get("/api/v2/settings/notifications")
        data = r.json()
        assert data["webhook_url"] == "https://x.test/h"
        assert data["webhook_enabled"] is False

    def test_empty_url_clears_value(self, client):
        client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "https://x.test/h", "webhook_enabled": True},
        )
        client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "", "webhook_enabled": True},
        )
        r = client.get("/api/v2/settings/notifications")
        assert r.json()["webhook_url"] is None

    def test_whitespace_url_normalized_to_none(self, client):
        r = client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "   ", "webhook_enabled": True},
        )
        assert r.json()["webhook_url"] is None

    def test_rejects_file_scheme_url(self, client):
        """SSRF guard — file:// must be rejected (CVE-class issue)."""
        r = client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "file:///etc/passwd", "webhook_enabled": True},
        )
        assert r.status_code == 400

    def test_rejects_ftp_scheme_url(self, client):
        r = client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "ftp://example.com/h", "webhook_enabled": True},
        )
        assert r.status_code == 400

    def test_rejects_url_without_host(self, client):
        r = client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "http://", "webhook_enabled": True},
        )
        assert r.status_code == 400

    def test_accepts_https(self, client):
        r = client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "https://hooks.example.com/h", "webhook_enabled": True},
        )
        assert r.status_code == 200

    def test_accepts_http(self, client):
        """Plain http is allowed for public endpoints. Uses a global IP literal
        (no DNS lookup) so the test is hermetic — TEST-NET ranges count as
        private under ipaddress, so a real routable global IP is used."""
        r = client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "http://8.8.8.8:9876/h", "webhook_enabled": True},
        )
        assert r.status_code == 200

    # --- SSRF host validation (#656) ---------------------------------------

    def test_rejects_metadata_ip(self, client):
        """Cloud IMDS (169.254.169.254) must be rejected — the core SSRF target."""
        r = client.put(
            "/api/v2/settings/notifications",
            json={
                "webhook_url": "http://169.254.169.254/latest/meta-data/",
                "webhook_enabled": True,
            },
        )
        assert r.status_code == 400

    def test_rejects_localhost(self, client):
        """A DNS name resolving to loopback → blocked. getaddrinfo is mocked so
        the test doesn't depend on how the CI image resolves ``localhost``
        (some return ::1, some 127.0.0.1, hardened ones not at all)."""
        with patch(
            "codeframe.core.notifications_config.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("127.0.0.1", 0))],
        ):
            r = client.put(
                "/api/v2/settings/notifications",
                json={
                    "webhook_url": "http://localhost:9876/h",
                    "webhook_enabled": True,
                },
            )
        assert r.status_code == 400

    def test_rejects_ipv4_mapped_ipv6_metadata(self, client):
        """::ffff:169.254.169.254 must be unwrapped to its IPv4 and rejected —
        the trickiest case, easy to silently break in a refactor."""
        r = client.put(
            "/api/v2/settings/notifications",
            json={
                "webhook_url": "http://[::ffff:169.254.169.254]/h",
                "webhook_enabled": True,
            },
        )
        assert r.status_code == 400

    def test_rejects_loopback_ip(self, client):
        r = client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "http://127.0.0.1:8000/h", "webhook_enabled": True},
        )
        assert r.status_code == 400

    def test_rejects_rfc1918_ip(self, client):
        r = client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "http://10.0.0.5/h", "webhook_enabled": True},
        )
        assert r.status_code == 400

    def test_rejects_ipv6_loopback(self, client):
        r = client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "http://[::1]:8000/h", "webhook_enabled": True},
        )
        assert r.status_code == 400

    def test_allows_private_host_when_opted_in(self, client, monkeypatch):
        """CODEFRAME_ALLOW_PRIVATE_WEBHOOKS=1 is the documented escape hatch."""
        monkeypatch.setenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", "1")
        for host in ("http://127.0.0.1:8000/h", "http://10.0.0.5/h"):
            r = client.put(
                "/api/v2/settings/notifications",
                json={"webhook_url": host, "webhook_enabled": True},
            )
            assert r.status_code == 200, host


class TestNotificationWebhookTest:
    @pytest.fixture(autouse=True)
    def _public_dns(self):
        """Hermetic DNS: ``hooks.example.com`` must resolve to a public IP so
        the save-time check and the #746 dispatch-time guard in ``send_event``
        both pass without real lookups. IP-literal and scheme rejection tests
        in this class never reach getaddrinfo, so the stub is safe for all."""
        with patch(
            "codeframe.core.notifications_config.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
        ):
            yield

    def test_returns_400_when_no_url_configured(self, client):
        r = client.post("/api/v2/settings/notifications/test")
        assert r.status_code == 400

    def test_returns_400_when_url_present_but_empty(self, client):
        # PUT empty URL → /test should still 400 since nothing to call.
        client.put(
            "/api/v2/settings/notifications",
            json={"webhook_url": "", "webhook_enabled": True},
        )
        r = client.post("/api/v2/settings/notifications/test")
        assert r.status_code == 400

    def test_returns_status_code_on_success(self, client):
        client.put(
            "/api/v2/settings/notifications",
            json={
                "webhook_url": "https://hooks.example.com/abc",
                "webhook_enabled": True,
            },
        )
        # Mock aiohttp so we don't actually hit the network.
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_post_context = AsyncMock()
        mock_post_context.__aenter__.return_value = mock_response
        mock_post_context.__aexit__.return_value = None
        mock_session = MagicMock()
        mock_session.post.return_value = mock_post_context
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        with patch("aiohttp.ClientSession", return_value=mock_session):
            r = client.post("/api/v2/settings/notifications/test")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["status_code"] == 204

    def test_returns_error_on_5xx(self, client):
        client.put(
            "/api/v2/settings/notifications",
            json={
                "webhook_url": "https://hooks.example.com/abc",
                "webhook_enabled": True,
            },
        )
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_post_context = AsyncMock()
        mock_post_context.__aenter__.return_value = mock_response
        mock_post_context.__aexit__.return_value = None
        mock_session = MagicMock()
        mock_session.post.return_value = mock_post_context
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        with patch("aiohttp.ClientSession", return_value=mock_session):
            r = client.post("/api/v2/settings/notifications/test")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status_code"] == 500

    def test_rejects_unsafe_stored_url_at_test_time(self, client, workspace):
        """Defence-in-depth: even if a hand-edited config bypassed the PUT
        validation, /test must refuse to POST to an unsafe URL."""
        # Write directly to the config file to simulate a hand-edited bypass.
        path = workspace.state_dir / "notifications_config.json"
        path.write_text(
            '{"webhook_url": "file:///etc/passwd", "webhook_enabled": true}'
        )
        r = client.post("/api/v2/settings/notifications/test")
        assert r.status_code == 400

    def test_rejects_metadata_ip_at_test_time(self, client, workspace):
        """SSRF (#656): a hand-edited config pointing at IMDS must be refused
        by /test, not fired."""
        path = workspace.state_dir / "notifications_config.json"
        path.write_text(
            '{"webhook_url": "http://169.254.169.254/latest/meta-data/", '
            '"webhook_enabled": true}'
        )
        r = client.post("/api/v2/settings/notifications/test")
        assert r.status_code == 400

    def test_test_works_even_when_enabled_flag_is_false(self, client):
        """The Test button should still work when the user is verifying
        a URL before turning notifications on."""
        client.put(
            "/api/v2/settings/notifications",
            json={
                "webhook_url": "https://hooks.example.com/abc",
                "webhook_enabled": False,
            },
        )
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_post_context = AsyncMock()
        mock_post_context.__aenter__.return_value = mock_response
        mock_post_context.__aexit__.return_value = None
        mock_session = MagicMock()
        mock_session.post.return_value = mock_post_context
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        with patch("aiohttp.ClientSession", return_value=mock_session):
            r = client.post("/api/v2/settings/notifications/test")
        assert r.status_code == 200
        assert r.json()["ok"] is True
