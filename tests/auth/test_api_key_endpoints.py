"""Tests for API key management endpoints.

Following TDD: tests written first, implementation follows.
"""

import os
import pytest
import jwt
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from codeframe.persistence.database import Database
from codeframe.auth.api_keys import generate_api_key, SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN


@pytest.fixture
def db(tmp_path):
    """Create test database."""
    from codeframe.auth.manager import reset_auth_engine

    db_path = tmp_path / "test_api_key_endpoints.db"

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
               (2, 'bob@example.com', 'Bob', '!DISABLED!', 1, 0, 1, 1)
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
def client(db):
    """Create test client.

    Database is configured via DATABASE_PATH environment variable
    set by the db fixture.
    """
    from codeframe.ui.server import app

    client = TestClient(app)
    return client


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


class TestCreateApiKey:
    """Tests for POST /api/auth/api-keys endpoint."""

    def test_create_api_key_success(self, client, db):
        """Create API key with valid JWT returns key details."""
        token = create_jwt_token(user_id=1)

        response = client.post(
            "/api/auth/api-keys",
            json={"name": "My New Key", "scopes": ["read", "write"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.json()

        assert "key" in data  # Full key shown only once
        assert "id" in data
        assert "prefix" in data
        assert "created_at" in data
        assert data["key"].startswith("cf_live_")
        assert data["prefix"] == data["key"][:12]

    def test_create_api_key_requires_jwt(self, client, db):
        """Create API key requires JWT authentication (not API key)."""
        # First create an API key to try using it
        _, key_hash, prefix = generate_api_key()
        db.api_keys.create(
            user_id=1,
            name="Existing Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN],
            expires_at=None,
        )

        # Try to create new key using API key auth
        full_key = f"cf_live_{prefix[8:]}{'a' * 28}"  # Fake but right format

        response = client.post(
            "/api/auth/api-keys",
            json={"name": "New Key", "scopes": ["read"]},
            headers={"X-API-Key": full_key},
        )

        # Should fail - API key creation requires JWT
        assert response.status_code == 401

    def test_create_api_key_no_auth(self, client):
        """Create API key without authentication returns 401."""
        response = client.post(
            "/api/auth/api-keys",
            json={"name": "My Key", "scopes": ["read"]},
        )

        assert response.status_code == 401

    def test_create_api_key_invalid_scopes(self, client):
        """Create API key with invalid scopes returns 422 (validation error)."""
        token = create_jwt_token(user_id=1)

        response = client.post(
            "/api/auth/api-keys",
            json={"name": "My Key", "scopes": ["invalid_scope"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422  # FastAPI validation error

    def test_create_api_key_with_expiration(self, client, db):
        """Create API key with expiration date."""
        token = create_jwt_token(user_id=1)
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        response = client.post(
            "/api/auth/api-keys",
            json={"name": "Expiring Key", "scopes": ["read"], "expires_at": expires},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201


class TestListApiKeys:
    """Tests for GET /api/auth/api-keys endpoint."""

    def test_list_api_keys_success(self, client, db):
        """List API keys returns user's keys."""
        # Create some keys for user 1
        for i, name in enumerate(["Key A", "Key B"]):
            _, key_hash, prefix = generate_api_key()
            db.api_keys.create(
                user_id=1,
                name=name,
                key_hash=key_hash,
                prefix=prefix,
                scopes=[SCOPE_READ],
                expires_at=None,
            )

        token = create_jwt_token(user_id=1)
        response = client.get(
            "/api/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        assert {k["name"] for k in data} == {"Key A", "Key B"}

    def test_list_api_keys_no_hash_exposed(self, client, db):
        """List API keys does not expose key hashes."""
        _, key_hash, prefix = generate_api_key()
        db.api_keys.create(
            user_id=1,
            name="My Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None,
        )

        token = create_jwt_token(user_id=1)
        response = client.get(
            "/api/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()

        for key in data:
            assert "key_hash" not in key
            assert "key" not in key  # Full key also not exposed

    def test_list_api_keys_with_api_key_auth(self, client, db):
        """List API keys works with API key authentication."""
        full_key, key_hash, prefix = generate_api_key()
        db.api_keys.create(
            user_id=1,
            name="Auth Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None,
        )

        response = client.get(
            "/api/auth/api-keys",
            headers={"X-API-Key": full_key},
        )

        assert response.status_code == 200

    def test_list_api_keys_no_auth(self, client):
        """List API keys without authentication returns 401."""
        response = client.get("/api/auth/api-keys")
        assert response.status_code == 401


class TestRevokeApiKey:
    """Tests for DELETE /api/auth/api-keys/{key_id} endpoint."""

    def test_revoke_api_key_success(self, client, db):
        """Revoke API key successfully."""
        _, key_hash, prefix = generate_api_key()
        key_id = db.api_keys.create(
            user_id=1,
            name="To Revoke",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None,
        )

        token = create_jwt_token(user_id=1)
        response = client.delete(
            f"/api/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

        # Verify key is revoked
        record = db.api_keys.get_by_id(key_id)
        assert record["is_active"] is False

    def test_revoke_api_key_not_owner(self, client, db):
        """Cannot revoke another user's API key."""
        _, key_hash, prefix = generate_api_key()
        key_id = db.api_keys.create(
            user_id=1,  # User 1 owns this key
            name="User 1 Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None,
        )

        # User 2 tries to revoke
        token = create_jwt_token(user_id=2)
        response = client.delete(
            f"/api/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404  # Not found (from user's perspective)

        # Verify key is still active
        record = db.api_keys.get_by_id(key_id)
        assert record["is_active"] is True

    def test_revoke_api_key_not_found(self, client):
        """Revoke non-existent API key returns 404."""
        token = create_jwt_token(user_id=1)
        response = client.delete(
            "/api/auth/api-keys/nonexistent-id",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    def test_revoke_api_key_no_auth(self, client, db):
        """Revoke API key without authentication returns 401."""
        _, key_hash, prefix = generate_api_key()
        key_id = db.api_keys.create(
            user_id=1,
            name="Some Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None,
        )

        response = client.delete(f"/api/auth/api-keys/{key_id}")
        assert response.status_code == 401


class TestApiKeyUsageAfterRevoke:
    """Tests for using revoked API keys."""

    def test_revoked_key_cannot_authenticate(self, client, db):
        """Revoked API key cannot be used for authentication."""
        full_key, key_hash, prefix = generate_api_key()
        key_id = db.api_keys.create(
            user_id=1,
            name="To Revoke",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None,
        )

        # Verify key works before revocation
        response = client.get(
            "/api/auth/api-keys",
            headers={"X-API-Key": full_key},
        )
        assert response.status_code == 200

        # Revoke the key
        db.api_keys.revoke(key_id, user_id=1)

        # Verify key no longer works
        response = client.get(
            "/api/auth/api-keys",
            headers={"X-API-Key": full_key},
        )
        assert response.status_code == 401
