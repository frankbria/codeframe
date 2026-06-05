"""Tests for env-gated auth mode (issue #336).

Auth is controlled by CODEFRAME_AUTH_REQUIRED:
- default ON ("true")
- read at request time (os.getenv per call) so tests can monkeypatch
- truthy: "1/true/yes/on" (case-insensitive); falsy: "0/false/no/off"
- when disabled, require_auth returns a synthetic auth dict instead of raising
"""

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
