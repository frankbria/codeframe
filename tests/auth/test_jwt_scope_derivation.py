"""JWT principals derive their scopes from the user record (issue #898 / P0.4).

``require_auth`` used to hand every JWT principal ``[read, write, admin]`` "for
backward compatibility", which made the whole ``require_scope(SCOPE_ADMIN)``
layer — credential storage, GitHub PAT storage, PR merge — decorative for
anything holding a browser session, and left ``users.is_superuser`` unread.

Admin now comes from ``is_superuser``; the auth-disabled synthetic principal is
deliberately unchanged (it is the local single-operator opt-out).
"""

import pytest

from codeframe.auth.api_keys import SCOPE_ADMIN, SCOPE_READ, SCOPE_WRITE
from codeframe.auth.dependencies import require_auth
from codeframe.auth.models import User
from codeframe.auth.scopes import has_scope

pytestmark = pytest.mark.v2


def _user(user_id: int = 1, *, is_superuser: bool) -> User:
    """A detached User row — require_auth only reads attributes off it."""
    return User(
        id=user_id,
        email="u@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=is_superuser,
        is_verified=True,
    )


class TestJwtScopeDerivation:
    @pytest.mark.asyncio
    async def test_non_superuser_jwt_gets_read_write_only(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        auth = await require_auth(jwt_user=_user(is_superuser=False), api_key_auth=None)

        assert auth["type"] == "jwt"
        assert auth["scopes"] == [SCOPE_READ, SCOPE_WRITE]
        assert has_scope(auth, SCOPE_WRITE) is True
        assert has_scope(auth, SCOPE_ADMIN) is False

    @pytest.mark.asyncio
    async def test_superuser_jwt_gets_admin(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        auth = await require_auth(jwt_user=_user(is_superuser=True), api_key_auth=None)

        assert auth["scopes"] == [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]
        assert has_scope(auth, SCOPE_ADMIN) is True

    @pytest.mark.asyncio
    async def test_api_key_scopes_still_win_over_jwt(self, monkeypatch):
        """A read-only key presented alongside a superuser JWT stays read-only."""
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        auth = await require_auth(
            jwt_user=_user(is_superuser=True),
            api_key_auth={"type": "api_key", "user_id": 1, "scopes": [SCOPE_READ]},
        )

        assert auth["type"] == "api_key"
        assert has_scope(auth, SCOPE_ADMIN) is False

    @pytest.mark.asyncio
    async def test_principal_without_the_flag_fails_closed(self, monkeypatch):
        """A principal object lacking ``is_superuser`` degrades to non-admin
        rather than raising — fail closed, never 500 and never escalate."""
        from types import SimpleNamespace

        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        auth = await require_auth(jwt_user=SimpleNamespace(id=42), api_key_auth=None)

        assert auth["user_id"] == 42
        assert has_scope(auth, SCOPE_ADMIN) is False

    @pytest.mark.asyncio
    async def test_auth_disabled_principal_keeps_admin(self, monkeypatch):
        """The local no-auth opt-out is unchanged — it has no user record to read."""
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        auth = await require_auth(jwt_user=None, api_key_auth=None)

        assert auth["type"] == "disabled"
        assert has_scope(auth, SCOPE_ADMIN) is True
