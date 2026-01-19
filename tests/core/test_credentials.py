"""Tests for credential management system.

Tests the credential storage, retrieval, and validation functionality.
Uses TDD - these tests are written before implementation.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Mark all tests in this file as v2
pytestmark = pytest.mark.v2


class TestCredentialProvider:
    """Tests for CredentialProvider enum."""

    def test_provider_types_exist(self):
        """All expected provider types are defined."""
        from codeframe.core.credentials import CredentialProvider

        assert CredentialProvider.LLM_ANTHROPIC
        assert CredentialProvider.LLM_OPENAI
        assert CredentialProvider.GIT_GITHUB
        assert CredentialProvider.GIT_GITLAB
        assert CredentialProvider.CICD_GENERIC
        assert CredentialProvider.DATABASE

    def test_provider_has_env_var_mapping(self):
        """Each provider maps to expected environment variable name."""
        from codeframe.core.credentials import CredentialProvider

        # LLM providers should map to their API key env vars
        assert CredentialProvider.LLM_ANTHROPIC.env_var == "ANTHROPIC_API_KEY"
        assert CredentialProvider.LLM_OPENAI.env_var == "OPENAI_API_KEY"
        assert CredentialProvider.GIT_GITHUB.env_var == "GITHUB_TOKEN"
        assert CredentialProvider.GIT_GITLAB.env_var == "GITLAB_TOKEN"

    def test_provider_has_display_name(self):
        """Each provider has a human-readable display name."""
        from codeframe.core.credentials import CredentialProvider

        assert CredentialProvider.LLM_ANTHROPIC.display_name == "Anthropic (Claude)"
        assert CredentialProvider.LLM_OPENAI.display_name == "OpenAI (GPT)"
        assert CredentialProvider.GIT_GITHUB.display_name == "GitHub"


class TestCredential:
    """Tests for Credential model."""

    def test_credential_creation_minimal(self):
        """Credential can be created with minimal required fields."""
        from codeframe.core.credentials import Credential, CredentialProvider

        cred = Credential(
            provider=CredentialProvider.LLM_ANTHROPIC,
            value="sk-ant-test-key",
        )

        assert cred.provider == CredentialProvider.LLM_ANTHROPIC
        assert cred.value == "sk-ant-test-key"
        assert cred.name is None
        assert cred.metadata == {}
        assert cred.created_at is not None
        assert cred.expires_at is None

    def test_credential_creation_full(self):
        """Credential can be created with all fields."""
        from codeframe.core.credentials import Credential, CredentialProvider

        created = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        expires = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        cred = Credential(
            provider=CredentialProvider.GIT_GITHUB,
            name="main-account",
            value="ghp_test_token",
            metadata={"scopes": ["repo", "workflow"]},
            created_at=created,
            expires_at=expires,
        )

        assert cred.name == "main-account"
        assert cred.metadata == {"scopes": ["repo", "workflow"]}
        assert cred.created_at == created
        assert cred.expires_at == expires

    def test_credential_is_expired(self):
        """Credential correctly reports expiration status."""
        from codeframe.core.credentials import Credential, CredentialProvider

        # Not expired
        future = datetime.now(timezone.utc) + timedelta(days=30)
        cred_valid = Credential(
            provider=CredentialProvider.LLM_ANTHROPIC,
            value="test",
            expires_at=future,
        )
        assert cred_valid.is_expired is False

        # Expired
        past = datetime.now(timezone.utc) - timedelta(days=1)
        cred_expired = Credential(
            provider=CredentialProvider.LLM_ANTHROPIC,
            value="test",
            expires_at=past,
        )
        assert cred_expired.is_expired is True

        # No expiration set (never expires)
        cred_no_expiry = Credential(
            provider=CredentialProvider.LLM_ANTHROPIC,
            value="test",
        )
        assert cred_no_expiry.is_expired is False

    def test_credential_masked_value(self):
        """Credential masks value for display."""
        from codeframe.core.credentials import Credential, CredentialProvider

        cred = Credential(
            provider=CredentialProvider.LLM_ANTHROPIC,
            value="sk-ant-api03-abcdefghijklmnop",
        )

        masked = cred.masked_value
        assert masked.startswith("sk-a")
        assert masked.endswith("...mnop")
        assert "abcdefghijklmnop" not in masked

    def test_credential_masked_value_short(self):
        """Short credentials are fully masked."""
        from codeframe.core.credentials import Credential, CredentialProvider

        cred = Credential(
            provider=CredentialProvider.LLM_ANTHROPIC,
            value="abc",
        )

        assert cred.masked_value == "***"

    def test_credential_to_dict_excludes_value(self):
        """Credential serialization excludes actual value by default."""
        from codeframe.core.credentials import Credential, CredentialProvider

        cred = Credential(
            provider=CredentialProvider.LLM_ANTHROPIC,
            value="secret-key",
        )

        data = cred.to_safe_dict()
        assert "value" not in data
        assert data["provider"] == "LLM_ANTHROPIC"
        assert "masked_value" in data


class TestCredentialStore:
    """Tests for CredentialStore low-level storage."""

    def test_store_with_keyring_available(self):
        """Store uses keyring when available."""
        from codeframe.core.credentials import (
            CredentialStore,
            Credential,
            CredentialProvider,
        )

        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()

            store = CredentialStore()

            cred = Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="test-key",
            )

            store.store(cred)

            mock_keyring.set_password.assert_called_once()
            args = mock_keyring.set_password.call_args
            assert "codeframe" in args[0][0].lower()
            assert "LLM_ANTHROPIC" in args[0][1]
            # Value should be encrypted/encoded
            assert args[0][2] is not None

    def test_store_fallback_to_encrypted_file(self):
        """Store falls back to encrypted file when keyring unavailable."""
        from codeframe.core.credentials import (
            CredentialStore,
            Credential,
            CredentialProvider,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                # Simulate keyring not working
                mock_keyring.get_keyring.return_value = MagicMock()
                mock_keyring.set_password.side_effect = Exception("Keyring not available")

                store = CredentialStore(storage_dir=Path(tmpdir))

                cred = Credential(
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    value="test-key",
                )

                store.store(cred)

                # Should have created encrypted file
                encrypted_file = Path(tmpdir) / "credentials.encrypted"
                assert encrypted_file.exists()
                # File should have secure permissions
                assert (encrypted_file.stat().st_mode & 0o777) == 0o600

    def test_retrieve_from_keyring(self):
        """Retrieve gets credential from keyring."""
        from codeframe.core.credentials import (
            CredentialStore,
            CredentialProvider,
        )

        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()

            store = CredentialStore()

            # First store a credential
            stored_data = {
                "provider": "LLM_ANTHROPIC",
                "value": "test-key",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            mock_keyring.get_password.return_value = json.dumps(stored_data)

            cred = store.retrieve(CredentialProvider.LLM_ANTHROPIC)

            assert cred is not None
            assert cred.value == "test-key"

    def test_retrieve_returns_none_when_not_found(self):
        """Retrieve returns None when credential doesn't exist."""
        from codeframe.core.credentials import (
            CredentialStore,
            CredentialProvider,
        )

        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()
            mock_keyring.get_password.return_value = None

            store = CredentialStore()
            cred = store.retrieve(CredentialProvider.LLM_ANTHROPIC)

            assert cred is None

    def test_delete_removes_credential(self):
        """Delete removes credential from storage."""
        from codeframe.core.credentials import (
            CredentialStore,
            CredentialProvider,
        )

        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()

            store = CredentialStore()
            store.delete(CredentialProvider.LLM_ANTHROPIC)

            mock_keyring.delete_password.assert_called_once()

    def test_list_providers_returns_configured_providers(self):
        """List returns all configured provider types."""
        from codeframe.core.credentials import (
            CredentialStore,
            Credential,
            CredentialProvider,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                mock_keyring.get_keyring.return_value = MagicMock()
                mock_keyring.set_password.side_effect = Exception("No keyring")

                store = CredentialStore(storage_dir=Path(tmpdir))

                # Store a couple credentials
                store.store(
                    Credential(
                        provider=CredentialProvider.LLM_ANTHROPIC,
                        value="key1",
                    )
                )
                store.store(
                    Credential(
                        provider=CredentialProvider.GIT_GITHUB,
                        value="token1",
                    )
                )

                providers = store.list_providers()
                assert CredentialProvider.LLM_ANTHROPIC in providers
                assert CredentialProvider.GIT_GITHUB in providers


class TestCredentialManager:
    """Tests for CredentialManager high-level API."""

    def test_get_credential_env_var_priority(self):
        """Environment variable takes priority over stored credential."""
        from codeframe.core.credentials import (
            CredentialManager,
            CredentialProvider,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                mock_keyring.get_keyring.return_value = MagicMock()

                manager = CredentialManager()
                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)

                assert value == "env-key"
                # Should not have called keyring since env var was set
                mock_keyring.get_password.assert_not_called()

    def test_get_credential_falls_back_to_store(self):
        """Falls back to stored credential when env var not set."""
        from codeframe.core.credentials import (
            CredentialManager,
            CredentialProvider,
        )

        # Ensure env var is not set
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                mock_keyring.get_keyring.return_value = MagicMock()
                stored_data = {
                    "provider": "LLM_ANTHROPIC",
                    "value": "stored-key",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                mock_keyring.get_password.return_value = json.dumps(stored_data)

                manager = CredentialManager()
                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)

                assert value == "stored-key"

    def test_get_credential_returns_none_when_not_found(self):
        """Returns None when credential not found anywhere."""
        from codeframe.core.credentials import (
            CredentialManager,
            CredentialProvider,
        )

        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                mock_keyring.get_keyring.return_value = MagicMock()
                mock_keyring.get_password.return_value = None

                manager = CredentialManager()
                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)

                assert value is None

    def test_set_credential_stores_securely(self):
        """Set credential stores it securely."""
        from codeframe.core.credentials import (
            CredentialManager,
            CredentialProvider,
        )

        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()

            manager = CredentialManager()
            manager.set_credential(
                CredentialProvider.LLM_ANTHROPIC,
                "new-api-key",
                metadata={"source": "cli"},
            )

            mock_keyring.set_password.assert_called_once()

    def test_delete_credential_removes_from_store(self):
        """Delete removes credential from store."""
        from codeframe.core.credentials import (
            CredentialManager,
            CredentialProvider,
        )

        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()

            manager = CredentialManager()
            manager.delete_credential(CredentialProvider.LLM_ANTHROPIC)

            mock_keyring.delete_password.assert_called_once()

    def test_list_credentials_shows_all_sources(self):
        """List shows credentials from both env and store."""
        from codeframe.core.credentials import (
            CredentialManager,
            CredentialProvider,
            CredentialInfo,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                mock_keyring.get_keyring.return_value = MagicMock()
                # Simulate stored GitHub credential
                stored_data = {
                    "provider": "GIT_GITHUB",
                    "value": "ghp_token",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                mock_keyring.get_password.side_effect = lambda service, key: (
                    json.dumps(stored_data) if "GIT_GITHUB" in key else None
                )

                manager = CredentialManager()
                credentials = manager.list_credentials()

                # Should include both env-based and stored
                providers = [c.provider for c in credentials]
                assert CredentialProvider.LLM_ANTHROPIC in providers

    def test_get_credential_source_returns_env_or_stored(self):
        """Reports whether credential comes from env or storage."""
        from codeframe.core.credentials import (
            CredentialManager,
            CredentialProvider,
            CredentialSource,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                mock_keyring.get_keyring.return_value = MagicMock()

                manager = CredentialManager()
                source = manager.get_credential_source(CredentialProvider.LLM_ANTHROPIC)

                assert source == CredentialSource.ENVIRONMENT

    def test_rotate_credential_atomic(self):
        """Rotate stores new before deleting old."""
        from codeframe.core.credentials import (
            CredentialManager,
            CredentialProvider,
        )

        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()
            stored_data = {
                "provider": "LLM_ANTHROPIC",
                "value": "old-key",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            mock_keyring.get_password.return_value = json.dumps(stored_data)

            manager = CredentialManager()
            manager.rotate_credential(
                CredentialProvider.LLM_ANTHROPIC,
                "new-key",
            )

            # Should have stored new key
            mock_keyring.set_password.assert_called()


class TestEncryption:
    """Tests for encrypted file storage."""

    def test_encryption_key_derived_from_machine_id(self):
        """Encryption key is derived from machine-specific data."""
        from codeframe.core.credentials import derive_encryption_key

        with tempfile.TemporaryDirectory() as tmpdir:
            salt_file = Path(tmpdir) / "salt"

            key1 = derive_encryption_key(salt_file)
            # Same salt should give same key
            key2 = derive_encryption_key(salt_file)

            assert key1 == key2
            assert len(key1) == 44  # Fernet key is 44 bytes base64 encoded

    def test_different_salt_different_key(self):
        """Different salt files produce different keys."""
        from codeframe.core.credentials import derive_encryption_key

        with tempfile.TemporaryDirectory() as tmpdir:
            key1 = derive_encryption_key(Path(tmpdir) / "salt1")
            key2 = derive_encryption_key(Path(tmpdir) / "salt2")

            assert key1 != key2

    def test_encrypted_storage_round_trip(self):
        """Data can be encrypted and decrypted correctly."""
        from codeframe.core.credentials import (
            CredentialStore,
            Credential,
            CredentialProvider,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                mock_keyring.get_keyring.return_value = MagicMock()
                mock_keyring.set_password.side_effect = Exception("No keyring")
                mock_keyring.get_password.side_effect = Exception("No keyring")

                store = CredentialStore(storage_dir=Path(tmpdir))

                original = Credential(
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    value="secret-api-key-12345",
                    metadata={"test": "data"},
                )

                store.store(original)
                retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)

                assert retrieved is not None
                assert retrieved.value == original.value
                assert retrieved.metadata == original.metadata


class TestFilePermissions:
    """Tests for secure file handling."""

    def test_encrypted_file_has_600_permissions(self):
        """Encrypted credential file has owner-only permissions."""
        from codeframe.core.credentials import (
            CredentialStore,
            Credential,
            CredentialProvider,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                mock_keyring.get_keyring.return_value = MagicMock()
                mock_keyring.set_password.side_effect = Exception("No keyring")

                store = CredentialStore(storage_dir=Path(tmpdir))
                store.store(
                    Credential(
                        provider=CredentialProvider.LLM_ANTHROPIC,
                        value="key",
                    )
                )

                encrypted_file = Path(tmpdir) / "credentials.encrypted"
                mode = encrypted_file.stat().st_mode & 0o777
                assert mode == 0o600

    def test_salt_file_has_600_permissions(self):
        """Salt file has owner-only permissions."""
        from codeframe.core.credentials import derive_encryption_key

        with tempfile.TemporaryDirectory() as tmpdir:
            salt_file = Path(tmpdir) / "salt"
            derive_encryption_key(salt_file)

            mode = salt_file.stat().st_mode & 0o777
            assert mode == 0o600


class TestValidation:
    """Tests for credential format validation."""

    def test_validate_anthropic_key_format(self):
        """Validates Anthropic API key format."""
        from codeframe.core.credentials import validate_credential_format, CredentialProvider

        # Valid format
        assert validate_credential_format(CredentialProvider.LLM_ANTHROPIC, "sk-ant-api03-abc123") is True

        # Invalid - too short
        assert validate_credential_format(CredentialProvider.LLM_ANTHROPIC, "sk") is False

        # Invalid - empty
        assert validate_credential_format(CredentialProvider.LLM_ANTHROPIC, "") is False

    def test_validate_github_token_format(self):
        """Validates GitHub token format."""
        from codeframe.core.credentials import validate_credential_format, CredentialProvider

        # Valid classic PAT
        assert validate_credential_format(CredentialProvider.GIT_GITHUB, "ghp_xxxxxxxxxxxx") is True

        # Valid fine-grained PAT
        assert validate_credential_format(CredentialProvider.GIT_GITHUB, "github_pat_xxx") is True

        # Invalid - too short
        assert validate_credential_format(CredentialProvider.GIT_GITHUB, "gh") is False

    def test_validate_openai_key_format(self):
        """Validates OpenAI API key format."""
        from codeframe.core.credentials import validate_credential_format, CredentialProvider

        # Valid format
        assert validate_credential_format(CredentialProvider.LLM_OPENAI, "sk-proj-abc123xyz") is True

        # Invalid - too short
        assert validate_credential_format(CredentialProvider.LLM_OPENAI, "sk") is False
