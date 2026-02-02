"""Tests for dual authentication (API key + JWT) dependency.

Following TDD: tests written first, implementation follows.
"""

import os
import pytest
import jwt
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from fastapi import HTTPException

from codeframe.persistence.database import Database
from codeframe.auth.api_keys import generate_api_key, SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN


@pytest.fixture
def db(tmp_path):
    """Create test database."""
    from codeframe.auth.manager import reset_auth_engine

    db_path = tmp_path / "test_dual_auth.db"

    # Set DATABASE_PATH so auth engine uses the same database
    original_db_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(db_path)

    # Reset auth engine to pick up new DATABASE_PATH
    reset_auth_engine()

    db = Database(db_path)
    db.initialize()

    # Create test users
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (1, 'alice@example.com', 'Alice', '!DISABLED!', 1, 0, 1, 1),
               (2, 'inactive@example.com', 'Inactive', '!DISABLED!', 0, 0, 1, 1)
        """
    )
    db.conn.commit()

    yield db

    # Restore original DATABASE_PATH
    if original_db_path is not None:
        os.environ["DATABASE_PATH"] = original_db_path
    elif "DATABASE_PATH" in os.environ:
        del os.environ["DATABASE_PATH"]

    reset_auth_engine()


@pytest.fixture
def api_key_for_user_1(db):
    """Create an API key for user 1."""
    full_key, key_hash, prefix = generate_api_key()
    key_id = db.api_keys.create(
        user_id=1,
        name="Test Key",
        key_hash=key_hash,
        prefix=prefix,
        scopes=[SCOPE_READ, SCOPE_WRITE],
        expires_at=None,
    )
    return full_key, key_id


@pytest.fixture
def admin_api_key(db):
    """Create an admin-scoped API key for user 1."""
    full_key, key_hash, prefix = generate_api_key()
    key_id = db.api_keys.create(
        user_id=1,
        name="Admin Key",
        key_hash=key_hash,
        prefix=prefix,
        scopes=[SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN],
        expires_at=None,
    )
    return full_key, key_id


@pytest.fixture
def read_only_api_key(db):
    """Create a read-only API key for user 1."""
    full_key, key_hash, prefix = generate_api_key()
    key_id = db.api_keys.create(
        user_id=1,
        name="Read-Only Key",
        key_hash=key_hash,
        prefix=prefix,
        scopes=[SCOPE_READ],
        expires_at=None,
    )
    return full_key, key_id


def create_jwt_token(user_id: int, secret: str = "CHANGE-ME-IN-PRODUCTION") -> str:
    """Create a JWT token for testing."""
    from codeframe.auth.manager import JWT_ALGORITHM, JWT_AUDIENCE, JWT_LIFETIME_SECONDS

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "aud": JWT_AUDIENCE,
        "exp": now + timedelta(seconds=JWT_LIFETIME_SECONDS),
        "iat": now,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


class TestGetApiKeyAuth:
    """Tests for API key authentication extraction."""

    @pytest.mark.asyncio
    async def test_api_key_auth_valid(self, db, api_key_for_user_1):
        """Valid API key returns auth dict."""
        from codeframe.auth.dependencies import get_api_key_auth

        full_key, _ = api_key_for_user_1

        # Create mock request with X-API-Key header
        mock_request = MagicMock()
        mock_request.state.db = db

        result = await get_api_key_auth(api_key=full_key, request=mock_request)

        assert result is not None
        assert result["type"] == "api_key"
        assert result["user_id"] == 1
        assert result["scopes"] == [SCOPE_READ, SCOPE_WRITE]

    @pytest.mark.asyncio
    async def test_api_key_auth_no_header(self, db):
        """No API key header returns None."""
        from codeframe.auth.dependencies import get_api_key_auth

        mock_request = MagicMock()
        mock_request.state.db = db

        result = await get_api_key_auth(api_key=None, request=mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_api_key_auth_invalid_key(self, db):
        """Invalid API key returns None."""
        from codeframe.auth.dependencies import get_api_key_auth

        mock_request = MagicMock()
        mock_request.state.db = db

        result = await get_api_key_auth(api_key="cf_live_invalid_key_000000000", request=mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_api_key_auth_revoked_key(self, db, api_key_for_user_1):
        """Revoked API key returns None."""
        from codeframe.auth.dependencies import get_api_key_auth

        full_key, key_id = api_key_for_user_1
        db.api_keys.revoke(key_id, user_id=1)

        mock_request = MagicMock()
        mock_request.state.db = db

        result = await get_api_key_auth(api_key=full_key, request=mock_request)
        assert result is None


class TestRequireAuth:
    """Tests for dual authentication requirement."""

    @pytest.mark.asyncio
    async def test_require_auth_with_api_key(self, db, api_key_for_user_1):
        """API key authentication works."""
        from codeframe.auth.dependencies import require_auth

        full_key, _ = api_key_for_user_1
        api_key_auth = {
            "type": "api_key",
            "user_id": 1,
            "scopes": [SCOPE_READ, SCOPE_WRITE],
            "key_id": "test-key-id",
        }

        result = await require_auth(api_key_auth=api_key_auth, jwt_user=None)

        assert result["type"] == "api_key"
        assert result["user_id"] == 1

    @pytest.mark.asyncio
    async def test_require_auth_with_jwt(self):
        """JWT authentication works."""
        from codeframe.auth.dependencies import require_auth
        from codeframe.auth.models import User

        # Create mock user
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_user.email = "alice@example.com"

        result = await require_auth(api_key_auth=None, jwt_user=mock_user)

        assert result["type"] == "jwt"
        assert result["user_id"] == 1
        # JWT users get all scopes
        assert SCOPE_ADMIN in result["scopes"]

    @pytest.mark.asyncio
    async def test_require_auth_no_credentials(self):
        """No credentials raises 401."""
        from codeframe.auth.dependencies import require_auth

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(api_key_auth=None, jwt_user=None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_auth_prefers_api_key(self):
        """When both present, API key takes precedence."""
        from codeframe.auth.dependencies import require_auth
        from codeframe.auth.models import User

        api_key_auth = {
            "type": "api_key",
            "user_id": 1,
            "scopes": [SCOPE_READ],
            "key_id": "test-key-id",
        }

        mock_user = MagicMock(spec=User)
        mock_user.id = 2  # Different user

        result = await require_auth(api_key_auth=api_key_auth, jwt_user=mock_user)

        # Should use API key auth, not JWT
        assert result["type"] == "api_key"
        assert result["user_id"] == 1


class TestRequireScope:
    """Tests for scope-based authorization."""

    @pytest.mark.asyncio
    async def test_require_scope_has_scope(self):
        """Principal with required scope passes."""
        from codeframe.auth.dependencies import require_scope

        auth = {
            "type": "api_key",
            "user_id": 1,
            "scopes": [SCOPE_READ, SCOPE_WRITE],
        }

        # Should not raise
        checker = require_scope(SCOPE_WRITE)
        result = await checker(auth=auth)
        assert result == auth

    @pytest.mark.asyncio
    async def test_require_scope_missing_scope(self):
        """Principal without required scope raises 403."""
        from codeframe.auth.dependencies import require_scope

        auth = {
            "type": "api_key",
            "user_id": 1,
            "scopes": [SCOPE_READ],  # Only read, not write
        }

        checker = require_scope(SCOPE_WRITE)
        with pytest.raises(HTTPException) as exc_info:
            await checker(auth=auth)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_scope_admin_has_all(self):
        """Admin scope implies all other scopes."""
        from codeframe.auth.dependencies import require_scope

        auth = {
            "type": "api_key",
            "user_id": 1,
            "scopes": [SCOPE_ADMIN],
        }

        # Admin should pass any scope check
        for scope in [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]:
            checker = require_scope(scope)
            result = await checker(auth=auth)
            assert result == auth


class TestScopeHierarchy:
    """Tests for scope hierarchy logic."""

    def test_has_scope_direct_match(self):
        """Direct scope match returns True."""
        from codeframe.auth.scopes import has_scope

        auth = {"scopes": [SCOPE_READ]}
        assert has_scope(auth, SCOPE_READ) is True

    def test_has_scope_admin_grants_all(self):
        """Admin scope grants all permissions."""
        from codeframe.auth.scopes import has_scope

        auth = {"scopes": [SCOPE_ADMIN]}
        assert has_scope(auth, SCOPE_READ) is True
        assert has_scope(auth, SCOPE_WRITE) is True
        assert has_scope(auth, SCOPE_ADMIN) is True

    def test_has_scope_write_grants_read(self):
        """Write scope grants read permission."""
        from codeframe.auth.scopes import has_scope

        auth = {"scopes": [SCOPE_WRITE]}
        assert has_scope(auth, SCOPE_READ) is True
        assert has_scope(auth, SCOPE_WRITE) is True
        assert has_scope(auth, SCOPE_ADMIN) is False

    def test_has_scope_read_only(self):
        """Read scope only grants read permission."""
        from codeframe.auth.scopes import has_scope

        auth = {"scopes": [SCOPE_READ]}
        assert has_scope(auth, SCOPE_READ) is True
        assert has_scope(auth, SCOPE_WRITE) is False
        assert has_scope(auth, SCOPE_ADMIN) is False
