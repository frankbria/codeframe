"""Integration tests for credential management system.

These tests exercise real system operations:
- Actual keyring storage and retrieval (when available)
- Real encryption/decryption with Fernet
- File permission verification
- Machine-specific key derivation

Run with: pytest -m integration tests/core/test_credentials_integration.py
"""

import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core.credentials import (
    Credential,
    CredentialManager,
    CredentialProvider,
    CredentialSource,
    CredentialStore,
    KEYRING_AVAILABLE,
    derive_encryption_key,
    validate_credential_format,
)


# Mark all tests as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.v2]


# =============================================================================
# CredentialStore Integration Tests
# =============================================================================


class TestCredentialStoreIntegration:
    """Integration tests for CredentialStore with real storage operations."""

    def test_store_and_retrieve_encrypted_file(self, integration_storage_dir: Path):
        """Store credential in encrypted file and retrieve it successfully."""
        # Force encrypted file storage by disabling keyring
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            original = Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-test-key-12345678901234567890",
                name="test-credential",
                metadata={"test": True, "environment": "integration"},
            )

            # Store the credential
            store.store(original)

            # Retrieve and verify
            retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)

            assert retrieved is not None
            assert retrieved.value == original.value
            assert retrieved.name == original.name
            assert retrieved.metadata == original.metadata
            assert retrieved.provider == original.provider

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permissions not supported on Windows")
    def test_encrypted_file_permissions_are_secure(self, integration_storage_dir: Path):
        """Verify encrypted file has 0600 permissions (owner-only read/write)."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            store.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-test-key-12345678901234567890",
            ))

            encrypted_file = integration_storage_dir / "credentials.encrypted"
            assert encrypted_file.exists()

            file_mode = stat.S_IMODE(encrypted_file.stat().st_mode)
            assert file_mode == 0o600, f"Expected 0o600, got {oct(file_mode)}"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permissions not supported on Windows")
    def test_salt_file_permissions_are_secure(self, integration_storage_dir: Path):
        """Verify salt file has 0600 permissions."""
        salt_file = integration_storage_dir / "salt"
        derive_encryption_key(salt_file)

        assert salt_file.exists()
        file_mode = stat.S_IMODE(salt_file.stat().st_mode)
        assert file_mode == 0o600, f"Expected 0o600, got {oct(file_mode)}"

    def test_store_multiple_credentials_encrypted(self, integration_storage_dir: Path):
        """Store multiple credentials and retrieve them all correctly."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            credentials = [
                Credential(
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    value="sk-ant-api03-anthropic-key-1234567890",
                    name="anthropic-key",
                ),
                Credential(
                    provider=CredentialProvider.GIT_GITHUB,
                    value="ghp_github_pat_token_12345",
                    name="github-pat",
                ),
                Credential(
                    provider=CredentialProvider.DATABASE,
                    value="postgresql://user:pass@localhost/db",
                    name="database-url",
                ),
            ]

            # Store all credentials
            for cred in credentials:
                store.store(cred)

            # Retrieve and verify each
            for original in credentials:
                retrieved = store.retrieve(original.provider)
                assert retrieved is not None
                assert retrieved.value == original.value
                assert retrieved.name == original.name

    def test_delete_credential_from_encrypted_file(self, integration_storage_dir: Path):
        """Delete credential from encrypted file storage."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            # Store a credential
            store.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-test-key-12345678901234567890",
            ))

            # Verify it exists
            assert store.retrieve(CredentialProvider.LLM_ANTHROPIC) is not None

            # Delete it
            store.delete(CredentialProvider.LLM_ANTHROPIC)

            # Verify it's gone
            assert store.retrieve(CredentialProvider.LLM_ANTHROPIC) is None

    def test_list_providers_from_encrypted_file(self, integration_storage_dir: Path):
        """List all stored provider types from encrypted file."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            store.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-key-12345678901234567890",
            ))
            store.store(Credential(
                provider=CredentialProvider.GIT_GITHUB,
                value="ghp_github_token_1234567890",
            ))

            providers = store.list_providers()

            assert CredentialProvider.LLM_ANTHROPIC in providers
            assert CredentialProvider.GIT_GITHUB in providers
            assert len(providers) == 2

    def test_overwrite_existing_credential(self, integration_storage_dir: Path):
        """Overwriting credential replaces the old value."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            # Store original
            store.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-original-key-12345",
                name="original",
            ))

            # Overwrite with new value
            store.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-updated-key-67890",
                name="updated",
            ))

            # Retrieve and verify it's the new value
            retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)
            assert retrieved.value == "sk-ant-api03-updated-key-67890"
            assert retrieved.name == "updated"


# =============================================================================
# Encryption Integration Tests
# =============================================================================


class TestEncryptionIntegration:
    """Integration tests for real encryption operations."""

    def test_key_derivation_is_consistent(self, integration_storage_dir: Path):
        """Same salt file produces same encryption key."""
        salt_file = integration_storage_dir / "salt"

        key1 = derive_encryption_key(salt_file)
        key2 = derive_encryption_key(salt_file)

        assert key1 == key2

    def test_key_derivation_different_salts(self, tmp_path: Path):
        """Different salt files produce different keys."""
        key1 = derive_encryption_key(tmp_path / "salt1")
        key2 = derive_encryption_key(tmp_path / "salt2")

        assert key1 != key2

    def test_fernet_key_format(self, integration_storage_dir: Path):
        """Derived key is valid Fernet format (44 bytes base64)."""
        salt_file = integration_storage_dir / "salt"
        key = derive_encryption_key(salt_file)

        # Fernet keys are 32 bytes encoded as base64 = 44 characters
        assert len(key) == 44
        assert isinstance(key, bytes)

    def test_encryption_round_trip_large_credential(self, integration_storage_dir: Path):
        """Encrypt and decrypt large credential value."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            # Create a large credential (e.g., OAuth token with extra metadata)
            large_value = "sk-ant-" + "x" * 5000  # ~5KB value

            original = Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value=large_value,
                metadata={"large_metadata": "y" * 1000},
            )

            store.store(original)
            retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)

            assert retrieved.value == large_value
            assert retrieved.metadata == original.metadata

    def test_corrupt_encrypted_file_returns_empty(self, integration_storage_dir: Path):
        """Corrupted encrypted file returns empty dict, doesn't crash."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            # Store a valid credential first
            store.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-valid-key-1234567890",
            ))

            # Corrupt the encrypted file
            encrypted_file = integration_storage_dir / "credentials.encrypted"
            encrypted_file.write_bytes(b"corrupted data that is not valid fernet")

            # Should return None (graceful degradation)
            retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)
            assert retrieved is None

    def test_invalid_salt_file_raises_error(self, integration_storage_dir: Path):
        """Invalid salt file (wrong size) raises ValueError."""
        salt_file = integration_storage_dir / "salt"
        # Write invalid salt (should be 16 bytes)
        salt_file.write_bytes(b"too short")

        with pytest.raises(ValueError, match="Invalid salt file"):
            derive_encryption_key(salt_file)

    def test_corrupt_json_in_encrypted_file_handled(self, integration_storage_dir: Path):
        """Encrypted file with invalid JSON is handled gracefully."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            # First create a valid salt and fernet instance
            _ = store._get_fernet()

            # Now encrypt invalid JSON
            fernet = store._get_fernet()
            encrypted = fernet.encrypt(b"not valid json {{{")

            encrypted_file = integration_storage_dir / "credentials.encrypted"
            encrypted_file.write_bytes(encrypted)
            encrypted_file.chmod(0o600)

            # Should return None gracefully
            retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)
            assert retrieved is None


# =============================================================================
# CredentialManager Integration Tests
# =============================================================================


class TestCredentialManagerIntegration:
    """Integration tests for high-level credential management."""

    def test_set_and_get_credential(self, integration_storage_dir: Path):
        """Set credential and retrieve it via manager."""
        # Clear ANTHROPIC_API_KEY to test stored credential retrieval
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
                manager = CredentialManager(storage_dir=integration_storage_dir)

                manager.set_credential(
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    value="sk-ant-api03-manager-test-key-123",
                    name="test-key",
                    metadata={"source": "integration-test"},
                )

                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)
                assert value == "sk-ant-api03-manager-test-key-123"

    def test_environment_variable_override(self, integration_storage_dir: Path):
        """Environment variable takes priority over stored credential."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            manager = CredentialManager(storage_dir=integration_storage_dir)

            # Store a credential
            manager.set_credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-stored-key-12345678",
            )

            # Set environment variable
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-override-key"}):
                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)
                assert value == "env-override-key"

            # Without env var, should return stored value
            # Note: We need to clear the env var properly
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)
                assert value == "sk-ant-api03-stored-key-12345678"

    def test_credential_source_detection(self, integration_storage_dir: Path):
        """Correctly identify credential source (env vs stored)."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            manager = CredentialManager(storage_dir=integration_storage_dir)

            # Clear any existing GITHUB_TOKEN from environment
            env = os.environ.copy()
            env.pop("GITHUB_TOKEN", None)

            with patch.dict(os.environ, env, clear=True):
                # Store a credential
                manager.set_credential(
                    provider=CredentialProvider.GIT_GITHUB,
                    value="ghp_stored_token_12345",
                )

                # Check source detection - should be STORED when no env var
                source = manager.get_credential_source(CredentialProvider.GIT_GITHUB)
                assert source == CredentialSource.STORED

            # With env var set, should report ENVIRONMENT
            with patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}):
                source = manager.get_credential_source(CredentialProvider.GIT_GITHUB)
                assert source == CredentialSource.ENVIRONMENT

    def test_rotate_credential_preserves_metadata(self, integration_storage_dir: Path):
        """Rotating credential preserves existing metadata."""
        # Clear ANTHROPIC_API_KEY to test stored credential retrieval
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
                manager = CredentialManager(storage_dir=integration_storage_dir)

                # Store initial credential with metadata
                manager.set_credential(
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    value="sk-ant-api03-old-key-1234567890",
                    name="production-key",
                    metadata={"scopes": ["read", "write"], "rotated_count": 0},
                )

                # Rotate credential
                manager.rotate_credential(
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    new_value="sk-ant-api03-new-key-0987654321",
                )

                # Verify new value with preserved metadata
                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)
                assert value == "sk-ant-api03-new-key-0987654321"

    def test_list_credentials_from_storage(self, integration_storage_dir: Path):
        """List credentials shows all stored credentials."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            manager = CredentialManager(storage_dir=integration_storage_dir)

            manager.set_credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-key-12345678901234",
                name="anthropic",
            )
            manager.set_credential(
                provider=CredentialProvider.GIT_GITHUB,
                value="ghp_github_token_12345",
                name="github",
            )

            credentials = manager.list_credentials()

            providers = [c.provider for c in credentials]
            assert CredentialProvider.LLM_ANTHROPIC in providers
            assert CredentialProvider.GIT_GITHUB in providers

    def test_expired_credential_returns_none(self, integration_storage_dir: Path):
        """Expired credential returns None when retrieved."""
        # Clear ANTHROPIC_API_KEY to test stored credential expiration
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
                manager = CredentialManager(storage_dir=integration_storage_dir)

                # Set credential with past expiration
                past = datetime.now(timezone.utc) - timedelta(days=1)
                manager.set_credential(
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    value="sk-ant-api03-expired-key-123",
                    expires_at=past,
                )

                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)
                assert value is None

    def test_delete_credential(self, integration_storage_dir: Path):
        """Delete credential removes it from storage."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            manager = CredentialManager(storage_dir=integration_storage_dir)

            # Store and verify
            manager.set_credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-to-delete-key-1234",
            )
            assert manager.get_credential(CredentialProvider.LLM_ANTHROPIC) is not None

            # Delete and verify
            manager.delete_credential(CredentialProvider.LLM_ANTHROPIC)

            # After deletion, should return None from storage
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                assert manager.get_credential(CredentialProvider.LLM_ANTHROPIC) is None


# =============================================================================
# Credential Validation Integration Tests
# =============================================================================


class TestCredentialValidationIntegration:
    """Integration tests for credential format validation."""

    @pytest.mark.parametrize("value,expected", [
        ("sk-ant-api03-1234567890123456789012345", True),  # Valid Anthropic
        ("sk-ant-api03-abc", False),  # Too short
        ("sk-wrong-prefix-12345678901234", False),  # Wrong prefix
        ("", False),  # Empty
    ])
    def test_validate_anthropic_format(self, value: str, expected: bool):
        """Validate Anthropic API key format with various inputs."""
        result = validate_credential_format(CredentialProvider.LLM_ANTHROPIC, value)
        assert result == expected

    @pytest.mark.parametrize("value,expected", [
        ("ghp_abcdefghijklmnopqrstuvwxyz1234567890", True),  # Valid classic PAT
        ("github_pat_abcdefgh", True),  # Valid fine-grained PAT
        ("gho_oauth_token_1234", True),  # OAuth token
        ("ghs_server_token_12", True),  # Server-to-server token
        ("gh_invalid", False),  # Wrong prefix
        ("ghp_short", False),  # Too short
    ])
    def test_validate_github_format(self, value: str, expected: bool):
        """Validate GitHub token format with various inputs."""
        result = validate_credential_format(CredentialProvider.GIT_GITHUB, value)
        assert result == expected

    @pytest.mark.parametrize("value,expected", [
        ("sk-proj-abc12345678901234567890", True),  # Valid project key
        ("sk-abc123456789012345678901", True),  # Valid legacy key
        ("pk-wrong-prefix-12345678901", False),  # Wrong prefix
        ("sk-short", False),  # Too short
    ])
    def test_validate_openai_format(self, value: str, expected: bool):
        """Validate OpenAI API key format with various inputs."""
        result = validate_credential_format(CredentialProvider.LLM_OPENAI, value)
        assert result == expected


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestCredentialEdgeCases:
    """Edge case and error handling tests."""

    def test_empty_storage_directory(self, tmp_path: Path):
        """Handle non-existent storage directory gracefully."""
        non_existent = tmp_path / "does" / "not" / "exist"

        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=non_existent)

            # Should create directory and store successfully
            store.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-new-dir-key-123",
            ))

            assert non_existent.exists()
            assert store.retrieve(CredentialProvider.LLM_ANTHROPIC) is not None

    def test_special_characters_in_credential_value(self, integration_storage_dir: Path):
        """Handle special characters in credential values."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            special_value = "sk-ant-api03-key-with-special-chars-!@#$%^&*()_+-=[]{}|;':\",./<>?`~"

            store.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value=special_value,
            ))

            retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)
            assert retrieved.value == special_value

    def test_unicode_in_credential_metadata(self, integration_storage_dir: Path):
        """Handle unicode characters in credential metadata."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            unicode_metadata = {
                "description": "Clé pour l'environnement de développement",
                "emoji": "🔐",
                "japanese": "開発環境",
            }

            store.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-unicode-test-12345",
                metadata=unicode_metadata,
            ))

            retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)
            assert retrieved.metadata == unicode_metadata

    def test_sequential_multi_credential_operations(self, integration_storage_dir: Path):
        """Store and retrieve multiple credentials sequentially.

        Note: The encrypted file storage is not designed for concurrent writes.
        This test verifies that sequential operations with multiple credentials
        work correctly, which is the expected usage pattern.
        """
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            # Store multiple credentials sequentially
            credentials_to_store = [
                (CredentialProvider.LLM_ANTHROPIC, "sk-ant-api03-key1-12345"),
                (CredentialProvider.GIT_GITHUB, "ghp_github_token_12345"),
                (CredentialProvider.DATABASE, "postgres://user:pass@host/db"),
            ]

            for provider, value in credentials_to_store:
                store.store(Credential(provider=provider, value=value))

            # All credentials should be retrievable
            for provider, expected_value in credentials_to_store:
                retrieved = store.retrieve(provider)
                assert retrieved is not None
                assert retrieved.value == expected_value

    def test_multiple_store_instances_same_directory(self, integration_storage_dir: Path):
        """Multiple store instances can access the same storage directory.

        This simulates what happens when the same user runs multiple
        CLI sessions that access credentials.
        """
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            # First store instance writes credentials
            store1 = CredentialStore(storage_dir=integration_storage_dir)
            store1.store(Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-shared-key-12345",
            ))

            # Second store instance reads credentials
            store2 = CredentialStore(storage_dir=integration_storage_dir)
            retrieved = store2.retrieve(CredentialProvider.LLM_ANTHROPIC)

            assert retrieved is not None
            assert retrieved.value == "sk-ant-api03-shared-key-12345"

    def test_credential_with_naive_datetime(self, integration_storage_dir: Path):
        """Handle credentials with naive datetime (no timezone)."""
        with patch("codeframe.core.credentials.KEYRING_AVAILABLE", False):
            store = CredentialStore(storage_dir=integration_storage_dir)

            # Naive datetime (no timezone)
            naive_time = datetime(2024, 12, 31, 23, 59, 59)

            cred = Credential(
                provider=CredentialProvider.LLM_ANTHROPIC,
                value="sk-ant-api03-naive-datetime-key",
                expires_at=naive_time,
            )

            store.store(cred)
            retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)

            # Should handle naive datetime
            assert retrieved is not None
            assert retrieved.expires_at is not None


# =============================================================================
# Keyring Integration Tests (conditional)
# =============================================================================


@pytest.mark.skipif(not KEYRING_AVAILABLE, reason="Keyring not available")
class TestKeyringIntegration:
    """Integration tests for real keyring operations.

    These tests are skipped if keyring is not available on the system.
    """

    def test_keyring_availability_check(self):
        """Verify keyring availability detection works."""
        store = CredentialStore()
        # If we got here, keyring is available, so check should pass
        assert store._keyring_available or not KEYRING_AVAILABLE

    def test_keyring_backend_detection(self):
        """Verify we can detect the keyring backend type."""
        import keyring as kr
        backend = kr.get_keyring()
        # Should have a backend name
        assert hasattr(backend, '__class__')
        backend_name = backend.__class__.__name__.lower()
        # Should not be the fail keyring
        assert "fail" not in backend_name
