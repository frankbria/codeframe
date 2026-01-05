"""Tests for CLI auth module - JWT token storage and retrieval.

TDD approach: Write tests first, then implement.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from codeframe.cli.auth import (
    get_credentials_path,
    store_token,
    get_token,
    clear_token,
    is_authenticated,
)


class TestCredentialsPath:
    """Tests for get_credentials_path function."""

    def test_returns_path_object(self):
        """get_credentials_path should return a Path object."""
        path = get_credentials_path()
        assert isinstance(path, Path)

    def test_path_in_user_home(self):
        """Credentials should be stored in user's home directory."""
        path = get_credentials_path()
        home = Path.home()
        assert str(path).startswith(str(home))

    def test_path_contains_codeframe_dir(self):
        """Credentials should be in .codeframe directory."""
        path = get_credentials_path()
        assert ".codeframe" in str(path)

    def test_filename_is_credentials_json(self):
        """Credentials file should be named credentials.json."""
        path = get_credentials_path()
        assert path.name == "credentials.json"


class TestStoreToken:
    """Tests for store_token function."""

    def test_store_token_creates_file(self, tmp_path):
        """store_token should create credentials file."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            store_token("test-jwt-token")

        assert creds_path.exists()

    def test_store_token_content_format(self, tmp_path):
        """Stored token should be in JSON format with 'access_token' key."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            store_token("test-jwt-token-123")

        with open(creds_path) as f:
            data = json.load(f)

        assert "access_token" in data
        assert data["access_token"] == "test-jwt-token-123"

    def test_store_token_creates_parent_dirs(self, tmp_path):
        """store_token should create parent directories if they don't exist."""
        creds_path = tmp_path / "nested" / "dir" / "credentials.json"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            store_token("test-token")

        assert creds_path.exists()

    def test_store_token_overwrites_existing(self, tmp_path):
        """store_token should overwrite existing token."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        # Store initial token
        with open(creds_path, "w") as f:
            json.dump({"access_token": "old-token"}, f)

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            store_token("new-token")

        with open(creds_path) as f:
            data = json.load(f)

        assert data["access_token"] == "new-token"

    def test_store_token_secure_permissions(self, tmp_path):
        """Credentials file should have restricted permissions (600)."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            store_token("secret-token")

        # Check file permissions (only owner read/write)
        mode = creds_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestGetToken:
    """Tests for get_token function."""

    def test_get_token_returns_stored_token(self, tmp_path):
        """get_token should return previously stored token."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        with open(creds_path, "w") as f:
            json.dump({"access_token": "my-jwt-token"}, f)

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            token = get_token()

        assert token == "my-jwt-token"

    def test_get_token_returns_none_if_no_file(self, tmp_path):
        """get_token should return None if credentials file doesn't exist."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            token = get_token()

        assert token is None

    def test_get_token_returns_none_if_invalid_json(self, tmp_path):
        """get_token should return None if credentials file has invalid JSON."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        with open(creds_path, "w") as f:
            f.write("not valid json {{{")

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            token = get_token()

        assert token is None

    def test_get_token_returns_none_if_missing_key(self, tmp_path):
        """get_token should return None if JSON doesn't have access_token key."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        with open(creds_path, "w") as f:
            json.dump({"some_other_key": "value"}, f)

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            token = get_token()

        assert token is None

    def test_get_token_prefers_env_variable(self, tmp_path):
        """get_token should prefer CODEFRAME_TOKEN environment variable."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        with open(creds_path, "w") as f:
            json.dump({"access_token": "file-token"}, f)

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch.dict(os.environ, {"CODEFRAME_TOKEN": "env-token"}):
                token = get_token()

        assert token == "env-token"


class TestClearToken:
    """Tests for clear_token function."""

    def test_clear_token_removes_file(self, tmp_path):
        """clear_token should remove credentials file."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        with open(creds_path, "w") as f:
            json.dump({"access_token": "to-be-deleted"}, f)

        assert creds_path.exists()

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            clear_token()

        assert not creds_path.exists()

    def test_clear_token_noop_if_no_file(self, tmp_path):
        """clear_token should not raise error if file doesn't exist."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            # Should not raise
            clear_token()


class TestIsAuthenticated:
    """Tests for is_authenticated function."""

    def test_is_authenticated_true_with_token(self, tmp_path):
        """is_authenticated should return True if token exists."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            assert is_authenticated() is True

    def test_is_authenticated_false_without_token(self, tmp_path):
        """is_authenticated should return False if no token."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            assert is_authenticated() is False

    def test_is_authenticated_true_with_env_token(self):
        """is_authenticated should return True with CODEFRAME_TOKEN env var."""
        with patch.dict(os.environ, {"CODEFRAME_TOKEN": "env-token"}):
            assert is_authenticated() is True
