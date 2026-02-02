"""API key generation, verification, and utility functions.

Provides utilities for creating and validating API keys for server authentication.
API keys follow the format: cf_{environment}_{32_hex_chars}

Security considerations:
- Keys are hashed using SHA256 (industry standard for high-entropy API keys)
- API keys have 128 bits of entropy from secrets.token_hex(16)
- SHA256 is appropriate here (vs bcrypt for passwords) because API keys
  are already high-entropy random strings, not human-chosen passwords
- Only the prefix is stored for efficient lookup
- Full key is shown only once during creation

This approach matches GitHub, Stripe, and other API key implementations.
"""

import hashlib
import hmac
import secrets
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Scope constants for API key permissions
SCOPE_READ = "read"
SCOPE_WRITE = "write"
SCOPE_ADMIN = "admin"

# All valid scopes
VALID_SCOPES = frozenset({SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN})

# Key format constants
KEY_PREFIX_LENGTH = 12  # cf_live_xxxx
KEY_RANDOM_BYTES = 16   # 16 bytes = 32 hex characters


def generate_api_key(environment: str = "live") -> Tuple[str, str, str]:
    """Generate a new API key with SHA256 hash.

    Args:
        environment: Environment identifier ('live' or 'test')

    Returns:
        Tuple of (full_key, key_hash, prefix):
        - full_key: The complete API key to give to the user (shown once)
        - key_hash: SHA256 hash of the key for storage (bcrypt-like format)
        - prefix: First 12 characters for efficient lookup

    Example:
        >>> key, hash, prefix = generate_api_key()
        >>> key
        'cf_live_a1b2c3d4e5f6789012345678abcdef01'
        >>> prefix
        'cf_live_a1b2'
    """
    # Generate 16 random bytes = 32 hex characters (128 bits entropy)
    random_part = secrets.token_hex(KEY_RANDOM_BYTES)

    # Construct the full key: cf_{environment}_{32_hex}
    full_key = f"cf_{environment}_{random_part}"

    # Hash using SHA256 - appropriate for high-entropy API keys
    # Format: $sha256${hex_digest} to distinguish from bcrypt hashes
    digest = hashlib.sha256(full_key.encode()).hexdigest()
    key_hash = f"$sha256${digest}"

    # Extract prefix for database lookup optimization
    prefix = full_key[:KEY_PREFIX_LENGTH]

    logger.debug(f"Generated API key with prefix {prefix}")

    return full_key, key_hash, prefix


def verify_api_key(key: str, key_hash: str) -> bool:
    """Verify an API key against its stored hash.

    Supports both SHA256 (preferred for API keys) and bcrypt hashes.

    Args:
        key: The full API key provided by the user
        key_hash: The stored hash (SHA256 or bcrypt format)

    Returns:
        True if the key matches the hash, False otherwise

    Note:
        Uses constant-time comparison to prevent timing attacks.
        Returns False (not exception) for invalid inputs.
    """
    if not key or not key_hash:
        return False

    try:
        if key_hash.startswith("$sha256$"):
            # SHA256 hash verification with constant-time comparison
            expected_digest = key_hash[8:]  # Remove "$sha256$" prefix
            actual_digest = hashlib.sha256(key.encode()).hexdigest()
            return hmac.compare_digest(expected_digest, actual_digest)

        elif key_hash.startswith("$2"):
            # Bcrypt hash (legacy or if we switch back)
            # Import here to avoid startup issues with bcrypt compatibility
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            return pwd_context.verify(key, key_hash)

        else:
            # Unknown hash format
            logger.warning(f"Unknown hash format: {key_hash[:10]}...")
            return False

    except Exception as e:
        # Handle malformed hashes gracefully
        logger.debug(f"API key verification failed: {e}")
        return False


def extract_prefix(key: str) -> str:
    """Extract the prefix from a full API key for database lookup.

    The prefix is the first 12 characters (cf_{env}_xxxx) which provides
    enough entropy for efficient indexed lookup while avoiding full key
    comparison in the database.

    Args:
        key: The full API key

    Returns:
        The 12-character prefix

    Raises:
        ValueError: If key is shorter than 12 characters
    """
    if len(key) < KEY_PREFIX_LENGTH:
        raise ValueError(f"API key too short: expected at least {KEY_PREFIX_LENGTH} chars")

    return key[:KEY_PREFIX_LENGTH]


def validate_scopes(scopes: list[str]) -> bool:
    """Validate that all scopes in the list are valid.

    Args:
        scopes: List of scope strings to validate

    Returns:
        True if all scopes are valid and list is non-empty, False otherwise
    """
    if not scopes:
        return False

    return all(scope in VALID_SCOPES for scope in scopes)
