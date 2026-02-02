"""Tests for API key CLI commands.

Following TDD: tests written first, implementation follows.
"""

import os
import pytest
from typer.testing import CliRunner
from unittest.mock import patch

from codeframe.cli.app import app
from codeframe.persistence.database import Database
from codeframe.auth.api_keys import generate_api_key, SCOPE_READ, SCOPE_WRITE

# Mark all tests in this module as v2 tests
pytestmark = pytest.mark.v2


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def db(tmp_path):
    """Create test database."""
    from codeframe.auth.manager import reset_auth_engine

    db_path = tmp_path / "test_cli_api_keys.db"

    # Set DATABASE_PATH
    original_db_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(db_path)

    reset_auth_engine()

    db = Database(db_path)
    db.initialize()

    # Create test user
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (1, 'test@example.com', 'Test User', '!DISABLED!', 1, 0, 1, 1)
        """
    )
    db.conn.commit()

    yield db

    # Restore
    if original_db_path is not None:
        os.environ["DATABASE_PATH"] = original_db_path
    elif "DATABASE_PATH" in os.environ:
        del os.environ["DATABASE_PATH"]

    reset_auth_engine()


class TestApiKeyCreate:
    """Tests for `cf auth api-key-create` command."""

    def test_api_key_create_success(self, runner, db):
        """Create API key displays key and warning."""
        with patch("codeframe.cli.auth_commands.get_db_for_cli") as mock_get_db:
            mock_get_db.return_value = db

            result = runner.invoke(
                app,
                ["auth", "api-key-create", "--name", "My Test Key", "--user-id", "1"],
            )

            assert result.exit_code == 0
            assert "cf_live_" in result.output
            assert "Save this key" in result.output or "shown again" in result.output.lower()

    def test_api_key_create_with_scopes(self, runner, db):
        """Create API key with custom scopes."""
        with patch("codeframe.cli.auth_commands.get_db_for_cli") as mock_get_db:
            mock_get_db.return_value = db

            result = runner.invoke(
                app,
                ["auth", "api-key-create", "--name", "Read Only Key", "--user-id", "1", "--scopes", "read"],
            )

            assert result.exit_code == 0
            assert "cf_live_" in result.output

    def test_api_key_create_requires_name(self, runner, db):
        """Create API key requires --name option."""
        result = runner.invoke(
            app,
            ["auth", "api-key-create", "--user-id", "1"],
        )

        # Should fail due to missing required option
        assert result.exit_code != 0


class TestApiKeyList:
    """Tests for `cf auth api-key-list` command."""

    def test_api_key_list_empty(self, runner, db):
        """List API keys when none exist."""
        with patch("codeframe.cli.auth_commands.get_db_for_cli") as mock_get_db:
            mock_get_db.return_value = db

            result = runner.invoke(
                app,
                ["auth", "api-key-list", "--user-id", "1"],
            )

            assert result.exit_code == 0
            assert "No API keys" in result.output or "0" in result.output or result.output.strip() == ""

    def test_api_key_list_shows_keys(self, runner, db):
        """List API keys shows existing keys."""
        # Create some keys first
        _, hash1, prefix1 = generate_api_key()
        _, hash2, prefix2 = generate_api_key()

        db.api_keys.create(
            user_id=1,
            name="Key One",
            key_hash=hash1,
            prefix=prefix1,
            scopes=[SCOPE_READ],
            expires_at=None,
        )
        db.api_keys.create(
            user_id=1,
            name="Key Two",
            key_hash=hash2,
            prefix=prefix2,
            scopes=[SCOPE_WRITE],
            expires_at=None,
        )

        with patch("codeframe.cli.auth_commands.get_db_for_cli") as mock_get_db:
            mock_get_db.return_value = db

            result = runner.invoke(
                app,
                ["auth", "api-key-list", "--user-id", "1"],
            )

            assert result.exit_code == 0
            assert "Key One" in result.output
            assert "Key Two" in result.output

    def test_api_key_list_hides_hash(self, runner, db):
        """List API keys does not show key hash."""
        _, key_hash, prefix = generate_api_key()
        db.api_keys.create(
            user_id=1,
            name="Secret Key",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None,
        )

        with patch("codeframe.cli.auth_commands.get_db_for_cli") as mock_get_db:
            mock_get_db.return_value = db

            result = runner.invoke(
                app,
                ["auth", "api-key-list", "--user-id", "1"],
            )

            assert result.exit_code == 0
            # Hash should not appear in output
            assert "$sha256$" not in result.output


class TestApiKeyRevoke:
    """Tests for `cf auth api-key-revoke` command."""

    def test_api_key_revoke_success(self, runner, db):
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

        with patch("codeframe.cli.auth_commands.get_db_for_cli") as mock_get_db:
            mock_get_db.return_value = db

            result = runner.invoke(
                app,
                ["auth", "api-key-revoke", key_id, "--user-id", "1", "--yes"],
            )

            assert result.exit_code == 0
            assert "revoked" in result.output.lower() or "success" in result.output.lower()

            # Verify key is revoked
            record = db.api_keys.get_by_id(key_id)
            assert record["is_active"] is False

    def test_api_key_revoke_prompts_confirmation(self, runner, db):
        """Revoke API key prompts for confirmation without --yes."""
        _, key_hash, prefix = generate_api_key()
        key_id = db.api_keys.create(
            user_id=1,
            name="To Revoke",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ],
            expires_at=None,
        )

        with patch("codeframe.cli.auth_commands.get_db_for_cli") as mock_get_db:
            mock_get_db.return_value = db

            # Provide 'n' to decline confirmation
            result = runner.invoke(
                app,
                ["auth", "api-key-revoke", key_id, "--user-id", "1"],
                input="n\n",
            )

            # Key should still be active
            record = db.api_keys.get_by_id(key_id)
            assert record["is_active"] is True

    def test_api_key_revoke_not_found(self, runner, db):
        """Revoke non-existent API key shows error."""
        with patch("codeframe.cli.auth_commands.get_db_for_cli") as mock_get_db:
            mock_get_db.return_value = db

            result = runner.invoke(
                app,
                ["auth", "api-key-revoke", "nonexistent-id", "--user-id", "1", "--yes"],
            )

            assert result.exit_code != 0 or "not found" in result.output.lower()


class TestApiKeyRotate:
    """Tests for `cf auth api-key-rotate` command."""

    def test_api_key_rotate_creates_new_key(self, runner, db):
        """Rotate API key creates new key with same name/scopes."""
        _, key_hash, prefix = generate_api_key()
        key_id = db.api_keys.create(
            user_id=1,
            name="To Rotate",
            key_hash=key_hash,
            prefix=prefix,
            scopes=[SCOPE_READ, SCOPE_WRITE],
            expires_at=None,
        )

        with patch("codeframe.cli.auth_commands.get_db_for_cli") as mock_get_db:
            mock_get_db.return_value = db

            result = runner.invoke(
                app,
                ["auth", "api-key-rotate", key_id, "--user-id", "1"],
            )

            assert result.exit_code == 0
            assert "cf_live_" in result.output  # New key shown

            # Old key should be revoked
            old_record = db.api_keys.get_by_id(key_id)
            assert old_record["is_active"] is False

            # New key should exist with same scopes
            keys = db.api_keys.list_user_keys(user_id=1)
            active_keys = [k for k in keys if k["is_active"]]
            assert len(active_keys) == 1
            assert active_keys[0]["scopes"] == [SCOPE_READ, SCOPE_WRITE]
