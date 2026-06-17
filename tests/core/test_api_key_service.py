"""Direct unit tests for codeframe.core.api_key_service.ApiKeyService.

Covers the create/list/revoke/rotate/get surface against a real (tmp) SQLite
Database — main paths plus error cases (invalid scopes, wrong owner, not-found,
and the rotate-keeps-old-key-on-failure safety path). No live API calls.

Issue #654 (P6.8.1): test coverage hardening for untested core modules.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from codeframe.auth.api_keys import SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN
from codeframe.core.api_key_service import (
    ApiKeyService,
    ApiKeyInfo,
    CreatedApiKey,
)
from codeframe.platform_store.database import Database


pytestmark = pytest.mark.v2


# Two distinct users so ownership / isolation can be exercised.
USER_A = 1
USER_B = 2


@pytest.fixture
def db(tmp_path):
    """Initialized Database with two seeded users."""
    database = Database(tmp_path / "test.db")
    database.initialize()
    # initialize() seeds the bootstrap admin as user 1; OR REPLACE keeps the
    # seed deterministic for these tests.
    database.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES
            (?, 'a@example.com', 'User A', '!DISABLED!', 1, 0, 1, 1),
            (?, 'b@example.com', 'User B', '!DISABLED!', 1, 0, 1, 1)
        """,
        (USER_A, USER_B),
    )
    database.conn.commit()
    return database


@pytest.fixture
def service(db):
    return ApiKeyService(db)


# --- create_api_key ---------------------------------------------------------


class TestCreateApiKey:
    def test_create_with_default_scopes(self, service, db):
        result = service.create_api_key(user_id=USER_A, name="Default")

        assert isinstance(result, CreatedApiKey)
        assert result.key.startswith("cf_live_")
        assert result.prefix == result.key[:12]
        assert result.id  # non-empty UUID
        # created_at is RFC3339-ish (parseable)
        datetime.fromisoformat(result.created_at)

        # Persisted with the default scopes and active.
        record = db.api_keys.get_by_id(result.id)
        assert record is not None
        assert record["scopes"] == [SCOPE_READ, SCOPE_WRITE]
        assert record["is_active"] is True
        assert record["user_id"] == USER_A

    def test_create_with_custom_scopes(self, service, db):
        result = service.create_api_key(
            user_id=USER_A, name="ReadOnly", scopes=[SCOPE_READ]
        )
        record = db.api_keys.get_by_id(result.id)
        assert record["scopes"] == [SCOPE_READ]

    def test_create_with_admin_scope(self, service, db):
        result = service.create_api_key(
            user_id=USER_A, name="Admin", scopes=[SCOPE_ADMIN]
        )
        assert db.api_keys.get_by_id(result.id)["scopes"] == [SCOPE_ADMIN]

    def test_create_with_expiry(self, service, db):
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        result = service.create_api_key(
            user_id=USER_A, name="Expiring", expires_at=expires
        )
        record = db.api_keys.get_by_id(result.id)
        assert record["expires_at"] is not None

    def test_key_hash_is_persisted_but_not_returned(self, service, db):
        """The full key is returned once; the stored hash never leaves the DB."""
        result = service.create_api_key(user_id=USER_A, name="Hashed")
        record = db.api_keys.get_by_id(result.id)
        assert record["key_hash"].startswith("$sha256$")
        # The CreatedApiKey dataclass exposes no hash field.
        assert not hasattr(result, "key_hash")

    def test_invalid_scopes_raise_value_error(self, service):
        with pytest.raises(ValueError, match="Invalid scopes"):
            service.create_api_key(user_id=USER_A, name="Bad", scopes=["bogus"])

    def test_empty_scopes_raise_value_error(self, service):
        # validate_scopes() rejects an empty list.
        with pytest.raises(ValueError, match="Invalid scopes"):
            service.create_api_key(user_id=USER_A, name="Empty", scopes=[])


# --- list_api_keys ----------------------------------------------------------


class TestListApiKeys:
    def test_empty_when_no_keys(self, service):
        assert service.list_api_keys(user_id=USER_A) == []

    def test_lists_multiple_keys(self, service):
        service.create_api_key(user_id=USER_A, name="One")
        service.create_api_key(user_id=USER_A, name="Two")

        keys = service.list_api_keys(user_id=USER_A)
        assert len(keys) == 2
        assert all(isinstance(k, ApiKeyInfo) for k in keys)
        assert {k.name for k in keys} == {"One", "Two"}

    def test_isolated_per_user(self, service):
        service.create_api_key(user_id=USER_A, name="A-key")
        service.create_api_key(user_id=USER_B, name="B-key")

        a_keys = service.list_api_keys(user_id=USER_A)
        assert [k.name for k in a_keys] == ["A-key"]

    def test_includes_revoked_keys(self, service):
        created = service.create_api_key(user_id=USER_A, name="Soon-revoked")
        service.revoke_api_key(created.id, user_id=USER_A)

        keys = service.list_api_keys(user_id=USER_A)
        assert len(keys) == 1
        assert keys[0].is_active is False

    def test_listing_does_not_leak_hash(self, service):
        service.create_api_key(user_id=USER_A, name="NoLeak")
        info = service.list_api_keys(user_id=USER_A)[0]
        # ApiKeyInfo has no hash attribute and the dict source excludes it.
        assert not hasattr(info, "key_hash")


# --- revoke_api_key ---------------------------------------------------------


class TestRevokeApiKey:
    def test_revoke_active_key(self, service, db):
        created = service.create_api_key(user_id=USER_A, name="Revoke me")

        assert service.revoke_api_key(created.id, user_id=USER_A) is True
        assert db.api_keys.get_by_id(created.id)["is_active"] is False

    def test_revoke_unknown_key_returns_false(self, service):
        assert service.revoke_api_key("does-not-exist", user_id=USER_A) is False

    def test_revoke_other_users_key_returns_false(self, service, db):
        created = service.create_api_key(user_id=USER_A, name="A-owned")

        # User B may not revoke User A's key.
        assert service.revoke_api_key(created.id, user_id=USER_B) is False
        assert db.api_keys.get_by_id(created.id)["is_active"] is True


# --- rotate_api_key ---------------------------------------------------------


class TestRotateApiKey:
    def test_rotate_creates_new_and_revokes_old(self, service, db):
        original = service.create_api_key(
            user_id=USER_A, name="Rotating", scopes=[SCOPE_READ]
        )

        rotated = service.rotate_api_key(original.id, user_id=USER_A)

        assert isinstance(rotated, CreatedApiKey)
        assert rotated.id != original.id
        assert rotated.key != original.key
        # Old key is now inactive; new key is active with carried-over name/scopes.
        assert db.api_keys.get_by_id(original.id)["is_active"] is False
        new_record = db.api_keys.get_by_id(rotated.id)
        assert new_record["is_active"] is True
        assert new_record["name"] == "Rotating"
        assert new_record["scopes"] == [SCOPE_READ]

    def test_rotate_unknown_key_returns_none(self, service):
        assert service.rotate_api_key("nope", user_id=USER_A) is None

    def test_rotate_other_users_key_returns_none(self, service, db):
        created = service.create_api_key(user_id=USER_A, name="A-owned")

        assert service.rotate_api_key(created.id, user_id=USER_B) is None
        # Untouched.
        assert db.api_keys.get_by_id(created.id)["is_active"] is True

    def test_rotate_keeps_old_key_when_creation_fails(self, service, db):
        """If new-key creation raises, the old key must remain active."""
        created = service.create_api_key(user_id=USER_A, name="Safety")

        with patch.object(
            service, "create_api_key", side_effect=ValueError("boom")
        ):
            with pytest.raises(ValueError, match="boom"):
                service.rotate_api_key(created.id, user_id=USER_A)

        assert db.api_keys.get_by_id(created.id)["is_active"] is True


# --- get_api_key ------------------------------------------------------------


class TestGetApiKey:
    def test_get_existing_key(self, service):
        created = service.create_api_key(user_id=USER_A, name="Fetch me")

        info = service.get_api_key(created.id)
        assert isinstance(info, ApiKeyInfo)
        assert info.id == created.id
        assert info.name == "Fetch me"
        assert info.prefix == created.prefix
        assert info.is_active is True

    def test_get_unknown_key_returns_none(self, service):
        assert service.get_api_key("missing") is None
