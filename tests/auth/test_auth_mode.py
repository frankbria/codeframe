"""Tests for env-gated auth mode (issue #336).

Auth is controlled by CODEFRAME_AUTH_REQUIRED:
- default ON ("true")
- read at request time (os.getenv per call) so tests can monkeypatch
- truthy: "1/true/yes/on" (case-insensitive); falsy: "0/false/no/off"
- when disabled, require_auth returns a synthetic auth dict instead of raising
"""

from types import SimpleNamespace

import pytest

from codeframe.auth.dependencies import auth_required, require_auth
from codeframe.auth.api_keys import SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN

pytestmark = pytest.mark.v2


class TestAuthRequiredHelper:
    def test_default_is_on(self, monkeypatch):
        monkeypatch.delenv("CODEFRAME_AUTH_REQUIRED", raising=False)
        assert auth_required() is True

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on", "ON"])
    def test_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", value)
        assert auth_required() is True

    @pytest.mark.parametrize("value", ["0", "false", "FALSE", "No", "off", "OFF"])
    def test_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", value)
        assert auth_required() is False

    def test_unknown_value_defaults_to_on(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "maybe")
        assert auth_required() is True

    def test_read_at_request_time(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        assert auth_required() is False
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        assert auth_required() is True


class TestRequireAuthBypass:
    @pytest.mark.asyncio
    async def test_disabled_returns_synthetic_dict(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        result = await require_auth(api_key_auth=None, jwt_user=None)
        assert result["type"] == "disabled"
        assert result["user_id"] is None
        assert result["scopes"] == [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]

    @pytest.mark.asyncio
    async def test_enabled_no_creds_raises_401(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await require_auth(api_key_auth=None, jwt_user=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_disabled_still_prefers_api_key(self, monkeypatch):
        """If real credentials are present, they win even when auth disabled."""
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        api_key_auth = {"type": "api_key", "user_id": 7, "scopes": [SCOPE_READ]}
        result = await require_auth(api_key_auth=api_key_auth, jwt_user=None)
        assert result["type"] == "api_key"
        assert result["user_id"] == 7


class _FakeState:
    pass


class _FakeRequest:
    """Minimal request stub with a settable ``state`` for require_auth (#754)."""

    def __init__(self):
        self.state = _FakeState()


class TestRequireAuthPublishesPrincipal:
    """require_auth must publish the principal to request.state.user (#754)."""

    @pytest.mark.asyncio
    async def test_sets_state_user_for_api_key(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        req = _FakeRequest()
        api_key_auth = {"type": "api_key", "user_id": 7, "scopes": [SCOPE_READ]}
        result = await require_auth(request=req, api_key_auth=api_key_auth, jwt_user=None)
        assert req.state.user is result
        assert req.state.user["user_id"] == 7

    @pytest.mark.asyncio
    async def test_sets_state_user_for_jwt(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        req = _FakeRequest()
        jwt_user = SimpleNamespace(id=42)
        result = await require_auth(request=req, api_key_auth=None, jwt_user=jwt_user)
        assert req.state.user is result
        assert req.state.user["user_id"] == 42

    @pytest.mark.asyncio
    async def test_sets_state_user_for_disabled(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        req = _FakeRequest()
        await require_auth(request=req, api_key_auth=None, jwt_user=None)
        assert req.state.user["type"] == "disabled"

    @pytest.mark.asyncio
    async def test_published_principal_enables_per_user_rate_key(self, monkeypatch):
        """End-to-end: require_auth's write drives the rate-limit key func (#754)."""
        from codeframe.lib.rate_limiter import get_rate_limit_key

        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        req = _FakeRequest()
        req.client = SimpleNamespace(host="10.0.0.1")
        req.headers = {}
        req.url = SimpleNamespace(path="/api/v2/tasks")

        # Before auth resolves, no principal → keyed by IP.
        assert get_rate_limit_key(req) == "ip:10.0.0.1"

        await require_auth(
            request=req,
            api_key_auth={"type": "api_key", "user_id": 99, "scopes": [SCOPE_READ]},
            jwt_user=None,
        )
        # After auth resolves, keyed per user.
        assert get_rate_limit_key(req) == "user:99"
