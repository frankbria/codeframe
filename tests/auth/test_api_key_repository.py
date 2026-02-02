"""Tests for API key repository database operations.

Following TDD: tests written first, implementation follows.
"""

import pytest
from datetime import datetime, timedelta, timezone

from codeframe.persistence.database import Database
from codeframe.auth.api_keys import generate_api_key, SCOPE_READ, SCOPE_WRITE


@pytest.fixture
def db(tmp_path):
    """Create test database with API keys table."""
    db_path = tmp_path / "test_api_keys.db"
    db = Database(db_path)
    db.initialize()

    # Create a test user for API key ownership
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (1, 'test@example.com', 'Test User', '!DISABLED!', 1, 0, 1, 1),
               (2, 'other@example.com', 'Other User', '!DISABLED!', 1, 0, 1, 1)
        """
    )
    db.conn.commit()

    return db


class TestCreateApiKey:
    """Tests for creating API keys in the database."""

    def test_create_api_key_returns_id(self, db):
        """create_api_key() returns a valid key ID."""
        _, key_hash, prefix = generate_api_key()

        key_id = db.api_keys.create(
            user_id=1,
            name="My Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ, SCOPE_WRITE],
            expires_at=None
        )

        assert key_id is not None
        assert isinstance(key_id, str)

    def test_create_api_key_stores_correct_data(self, db):
        """create_api_key() stores all fields correctly."""
        _, key_hash, prefix = generate_api_key()
        expires = datetime.now(timezone.utc) + timedelta(days=30)

        key_id = db.api_keys.create(
            user_id=1,
            name="Production Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=expires
        )

        # Retrieve and verify
        record = db.api_keys.get_by_id(key_id)
        assert record is not None
        assert record["user_id"] == 1
        assert record["name"] == "Production Key"
        assert record["key_hash"] == key_hash
        assert record["prefix"] == prefix
        assert record["scopes"] == [SCOPE_READ]
        assert record["is_active"] is True

    def test_create_api_key_sets_created_at(self, db):
        """create_api_key() sets created_at timestamp."""
        _, key_hash, prefix = generate_api_key()

        before = datetime.now(timezone.utc)
        key_id = db.api_keys.create(
            user_id=1,
            name="Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )
        after = datetime.now(timezone.utc)

        record = db.api_keys.get_by_id(key_id)
        created = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
        assert before <= created <= after


class TestGetApiKeyByPrefix:
    """Tests for looking up API keys by prefix."""

    def test_get_by_prefix_returns_key(self, db):
        """get_by_prefix() returns the key record."""
        _, key_hash, prefix = generate_api_key()

        key_id = db.api_keys.create(
            user_id=1,
            name="Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        record = db.api_keys.get_by_prefix(prefix)
        assert record is not None
        assert record["id"] == key_id
        assert record["key_hash"] == key_hash

    def test_get_by_prefix_returns_none_for_unknown(self, db):
        """get_by_prefix() returns None for unknown prefix."""
        record = db.api_keys.get_by_prefix("cf_live_xxxx")
        assert record is None

    def test_get_by_prefix_excludes_inactive(self, db):
        """get_by_prefix() excludes inactive keys."""
        _, key_hash, prefix = generate_api_key()

        key_id = db.api_keys.create(
            user_id=1,
            name="Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        # Revoke the key
        db.api_keys.revoke(key_id, user_id=1)

        # Should not find inactive key
        record = db.api_keys.get_by_prefix(prefix)
        assert record is None


class TestListUserApiKeys:
    """Tests for listing a user's API keys."""

    def test_list_returns_user_keys(self, db):
        """list_user_keys() returns all keys for a user."""
        _, hash1, prefix1 = generate_api_key()
        _, hash2, prefix2 = generate_api_key()

        db.api_keys.create(
            user_id=1,
            name="Key One",
            key_hash=hash1,
            prefix=prefix1,
            scopes=[SCOPE_READ],
            expires_at=None
        )
        db.api_keys.create(
            user_id=1,
            name="Key Two",
            key_hash=hash2,
            prefix=prefix2,
            scopes=[SCOPE_WRITE],
            expires_at=None
        )

        keys = db.api_keys.list_user_keys(user_id=1)
        assert len(keys) == 2
        assert {k["name"] for k in keys} == {"Key One", "Key Two"}

    def test_list_excludes_other_users_keys(self, db):
        """list_user_keys() only returns keys for specified user."""
        _, hash1, prefix1 = generate_api_key()
        _, hash2, prefix2 = generate_api_key()

        db.api_keys.create(
            user_id=1,
            name="User 1 Key",
            key_hash=hash1,
            prefix=prefix1,
            scopes=[SCOPE_READ],
            expires_at=None
        )
        db.api_keys.create(
            user_id=2,
            name="User 2 Key",
            key_hash=hash2,
            prefix=prefix2,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        user1_keys = db.api_keys.list_user_keys(user_id=1)
        assert len(user1_keys) == 1
        assert user1_keys[0]["name"] == "User 1 Key"

    def test_list_excludes_key_hash(self, db):
        """list_user_keys() does not expose key_hash."""
        _, key_hash, prefix = generate_api_key()

        db.api_keys.create(
            user_id=1,
            name="Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        keys = db.api_keys.list_user_keys(user_id=1)
        assert "key_hash" not in keys[0]

    def test_list_includes_inactive_keys(self, db):
        """list_user_keys() includes inactive (revoked) keys."""
        _, key_hash, prefix = generate_api_key()

        key_id = db.api_keys.create(
            user_id=1,
            name="Revoked Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        db.api_keys.revoke(key_id, user_id=1)

        keys = db.api_keys.list_user_keys(user_id=1)
        assert len(keys) == 1
        assert keys[0]["is_active"] is False


class TestRevokeApiKey:
    """Tests for revoking API keys."""

    def test_revoke_sets_inactive(self, db):
        """revoke() sets is_active to False."""
        _, key_hash, prefix = generate_api_key()

        key_id = db.api_keys.create(
            user_id=1,
            name="Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        result = db.api_keys.revoke(key_id, user_id=1)
        assert result is True

        record = db.api_keys.get_by_id(key_id)
        assert record["is_active"] is False

    def test_revoke_requires_ownership(self, db):
        """revoke() fails if user doesn't own the key."""
        _, key_hash, prefix = generate_api_key()

        key_id = db.api_keys.create(
            user_id=1,
            name="Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        # Try to revoke as different user
        result = db.api_keys.revoke(key_id, user_id=2)
        assert result is False

        # Key should still be active
        record = db.api_keys.get_by_id(key_id)
        assert record["is_active"] is True

    def test_revoke_unknown_key_returns_false(self, db):
        """revoke() returns False for unknown key ID."""
        result = db.api_keys.revoke("nonexistent-id", user_id=1)
        assert result is False


class TestDeleteApiKey:
    """Tests for hard-deleting API keys."""

    def test_delete_removes_key(self, db):
        """delete() removes the key from database."""
        _, key_hash, prefix = generate_api_key()

        key_id = db.api_keys.create(
            user_id=1,
            name="Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        result = db.api_keys.delete(key_id, user_id=1)
        assert result is True

        record = db.api_keys.get_by_id(key_id)
        assert record is None

    def test_delete_requires_ownership(self, db):
        """delete() fails if user doesn't own the key."""
        _, key_hash, prefix = generate_api_key()

        key_id = db.api_keys.create(
            user_id=1,
            name="Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        # Try to delete as different user
        result = db.api_keys.delete(key_id, user_id=2)
        assert result is False

        # Key should still exist
        record = db.api_keys.get_by_id(key_id)
        assert record is not None


class TestUpdateLastUsed:
    """Tests for updating last_used_at timestamp."""

    def test_update_last_used_sets_timestamp(self, db):
        """update_last_used() sets last_used_at."""
        _, key_hash, prefix = generate_api_key()

        key_id = db.api_keys.create(
            user_id=1,
            name="Test Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None
        )

        # Initially last_used_at should be None
        record = db.api_keys.get_by_id(key_id)
        assert record["last_used_at"] is None

        # Update last used
        db.api_keys.update_last_used(key_id)

        # Now it should have a timestamp
        record = db.api_keys.get_by_id(key_id)
        assert record["last_used_at"] is not None
