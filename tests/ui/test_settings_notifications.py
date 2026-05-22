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


class TestNotificationWebhookTest:
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
