"""Tests for API key generation, verification, and utility functions.

Following TDD: tests written first, implementation follows.
"""

import pytest
import re

# Import the module under test (will fail until implemented)
from codeframe.auth.api_keys import (
    generate_api_key,
    verify_api_key,
    extract_prefix,
    validate_scopes,
    SCOPE_READ,
    SCOPE_WRITE,
    SCOPE_ADMIN,
)


class TestGenerateApiKey:
    """Tests for API key generation."""

    def test_generate_api_key_returns_tuple(self):
        """generate_api_key() returns (full_key, key_hash, prefix) tuple."""
        result = generate_api_key()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_generate_api_key_format_live(self):
        """Generated key has format cf_live_{32_hex_chars}."""
        full_key, key_hash, prefix = generate_api_key()
        # Format: cf_live_{32 hex chars}
        pattern = r"^cf_live_[a-f0-9]{32}$"
        assert re.match(pattern, full_key), f"Key {full_key} doesn't match expected format"

    def test_generate_api_key_format_test(self):
        """Generated key for test environment has format cf_test_{32_hex_chars}."""
        full_key, key_hash, prefix = generate_api_key(environment="test")
        pattern = r"^cf_test_[a-f0-9]{32}$"
        assert re.match(pattern, full_key), f"Key {full_key} doesn't match expected format"

    def test_generate_api_key_hash_is_sha256(self):
        """Generated key_hash is a valid SHA256 hash."""
        full_key, key_hash, prefix = generate_api_key()
        # SHA256 hashes start with $sha256$
        assert key_hash.startswith("$sha256$"), f"Hash {key_hash} doesn't look like SHA256"
        # $sha256$ prefix (8 chars) + 64 hex chars = 72 characters
        assert len(key_hash) == 72

    def test_generate_api_key_prefix_format(self):
        """Prefix is first 12 characters of key: cf_{env}_xxxx."""
        full_key, key_hash, prefix = generate_api_key()
        # Prefix should be cf_live_xxxx (12 chars)
        assert len(prefix) == 12
        assert prefix == full_key[:12]
        assert prefix.startswith("cf_live_")

    def test_generate_api_key_uniqueness(self):
        """Each call generates a unique key."""
        key1, _, _ = generate_api_key()
        key2, _, _ = generate_api_key()
        assert key1 != key2

    def test_generate_api_key_hash_uniqueness(self):
        """Even with same key, hash should differ (bcrypt uses random salt)."""
        # Generate two keys
        _, hash1, _ = generate_api_key()
        _, hash2, _ = generate_api_key()
        # Different keys should have different hashes
        assert hash1 != hash2


class TestVerifyApiKey:
    """Tests for API key verification."""

    def test_verify_api_key_correct(self):
        """verify_api_key() returns True for correct key."""
        full_key, key_hash, prefix = generate_api_key()
        assert verify_api_key(full_key, key_hash) is True

    def test_verify_api_key_incorrect(self):
        """verify_api_key() returns False for incorrect key."""
        full_key, key_hash, prefix = generate_api_key()
        wrong_key = "cf_live_0000000000000000000000000000"
        assert verify_api_key(wrong_key, key_hash) is False

    def test_verify_api_key_empty_key(self):
        """verify_api_key() returns False for empty key."""
        full_key, key_hash, prefix = generate_api_key()
        assert verify_api_key("", key_hash) is False

    def test_verify_api_key_malformed_hash(self):
        """verify_api_key() handles malformed hash gracefully."""
        full_key, _, _ = generate_api_key()
        # Should return False, not raise exception
        assert verify_api_key(full_key, "not-a-bcrypt-hash") is False


class TestExtractPrefix:
    """Tests for prefix extraction."""

    def test_extract_prefix_returns_first_12_chars(self):
        """extract_prefix() returns first 12 characters."""
        full_key, _, expected_prefix = generate_api_key()
        result = extract_prefix(full_key)
        assert result == expected_prefix
        assert len(result) == 12

    def test_extract_prefix_live_environment(self):
        """extract_prefix() works for live environment keys."""
        full_key = "cf_live_abcdef0123456789abcdef01"
        prefix = extract_prefix(full_key)
        assert prefix == "cf_live_abcd"

    def test_extract_prefix_test_environment(self):
        """extract_prefix() works for test environment keys."""
        full_key = "cf_test_abcdef0123456789abcdef01"
        prefix = extract_prefix(full_key)
        assert prefix == "cf_test_abcd"

    def test_extract_prefix_short_key_raises(self):
        """extract_prefix() raises ValueError for key shorter than 12 chars."""
        with pytest.raises(ValueError, match="too short"):
            extract_prefix("cf_live_")


class TestValidateScopes:
    """Tests for scope validation."""

    def test_validate_scopes_valid_single(self):
        """validate_scopes() returns True for single valid scope."""
        assert validate_scopes([SCOPE_READ]) is True
        assert validate_scopes([SCOPE_WRITE]) is True
        assert validate_scopes([SCOPE_ADMIN]) is True

    def test_validate_scopes_valid_multiple(self):
        """validate_scopes() returns True for multiple valid scopes."""
        assert validate_scopes([SCOPE_READ, SCOPE_WRITE]) is True
        assert validate_scopes([SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]) is True

    def test_validate_scopes_invalid(self):
        """validate_scopes() returns False for invalid scope."""
        assert validate_scopes(["invalid_scope"]) is False
        assert validate_scopes([SCOPE_READ, "invalid"]) is False

    def test_validate_scopes_empty_list(self):
        """validate_scopes() returns False for empty list."""
        assert validate_scopes([]) is False

    def test_validate_scopes_duplicates(self):
        """validate_scopes() returns True even with duplicates."""
        assert validate_scopes([SCOPE_READ, SCOPE_READ]) is True


class TestScopeConstants:
    """Tests for scope constant values."""

    def test_scope_read_value(self):
        """SCOPE_READ has expected value."""
        assert SCOPE_READ == "read"

    def test_scope_write_value(self):
        """SCOPE_WRITE has expected value."""
        assert SCOPE_WRITE == "write"

    def test_scope_admin_value(self):
        """SCOPE_ADMIN has expected value."""
        assert SCOPE_ADMIN == "admin"
