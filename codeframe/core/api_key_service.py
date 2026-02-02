"""Core business logic for API key management.

This service is used by both CLI commands and REST API endpoints,
ensuring consistent behavior across interfaces.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from codeframe.auth.api_keys import (
    generate_api_key,
    validate_scopes,
    SCOPE_READ,
    SCOPE_WRITE,
)
from codeframe.persistence.database import Database

logger = logging.getLogger(__name__)


@dataclass
class ApiKeyInfo:
    """API key information (without sensitive data)."""

    id: str
    name: str
    prefix: str
    scopes: List[str]
    created_at: str
    last_used_at: Optional[str]
    expires_at: Optional[str]
    is_active: bool


@dataclass
class CreatedApiKey:
    """Result of creating an API key (includes full key shown once)."""

    key: str  # Full key - shown only once
    id: str
    prefix: str
    created_at: str


class ApiKeyService:
    """Service for API key operations.

    Encapsulates business logic for creating, listing, and revoking API keys.
    Used by both CLI and REST API to ensure consistent behavior.
    """

    def __init__(self, db: Database):
        """Initialize with database connection.

        Args:
            db: Initialized Database instance
        """
        self.db = db

    def create_api_key(
        self,
        user_id: int,
        name: str,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> CreatedApiKey:
        """Create a new API key for a user.

        Args:
            user_id: Owner user ID
            name: Human-readable name for the key
            scopes: Permission scopes (defaults to read, write)
            expires_at: Optional expiration timestamp

        Returns:
            CreatedApiKey with the full key (shown only once)

        Raises:
            ValueError: If scopes are invalid
        """
        if scopes is None:
            scopes = [SCOPE_READ, SCOPE_WRITE]

        if not validate_scopes(scopes):
            raise ValueError(f"Invalid scopes: {scopes}. Valid scopes: read, write, admin")

        # Generate the key
        full_key, key_hash, prefix = generate_api_key()

        # Store in database
        key_id = self.db.api_keys.create(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            scopes=scopes,
            expires_at=expires_at,
        )

        logger.info(f"API key created for user {user_id}: {prefix}...")

        return CreatedApiKey(
            key=full_key,
            id=key_id,
            prefix=prefix,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def list_api_keys(self, user_id: int) -> List[ApiKeyInfo]:
        """List all API keys for a user.

        Args:
            user_id: The user's ID

        Returns:
            List of API key info (without hashes)
        """
        keys = self.db.api_keys.list_user_keys(user_id=user_id)

        return [
            ApiKeyInfo(
                id=k["id"],
                name=k["name"],
                prefix=k["prefix"],
                scopes=k["scopes"],
                created_at=k["created_at"],
                last_used_at=k.get("last_used_at"),
                expires_at=k.get("expires_at"),
                is_active=k["is_active"],
            )
            for k in keys
        ]

    def revoke_api_key(self, key_id: str, user_id: int) -> bool:
        """Revoke an API key.

        Args:
            key_id: The API key ID to revoke
            user_id: The user attempting to revoke (must be owner)

        Returns:
            True if revoked, False if not found or not owned
        """
        success = self.db.api_keys.revoke(key_id, user_id=user_id)

        if success:
            logger.info(f"API key revoked by user {user_id}: {key_id}")

        return success

    def rotate_api_key(self, key_id: str, user_id: int) -> Optional[CreatedApiKey]:
        """Rotate an API key (revoke old, create new with same config).

        Args:
            key_id: The API key ID to rotate
            user_id: The user attempting to rotate (must be owner)

        Returns:
            New CreatedApiKey, or None if old key not found/owned
        """
        # Get the old key's configuration
        old_key = self.db.api_keys.get_by_id(key_id)
        if old_key is None or old_key["user_id"] != user_id:
            return None

        # Create new key with same configuration
        new_key = self.create_api_key(
            user_id=user_id,
            name=old_key["name"],
            scopes=old_key["scopes"],
            expires_at=None,  # New key starts fresh
        )

        # Revoke the old key
        self.db.api_keys.revoke(key_id, user_id=user_id)

        logger.info(f"API key rotated by user {user_id}: {key_id} -> {new_key.id}")

        return new_key

    def get_api_key(self, key_id: str) -> Optional[ApiKeyInfo]:
        """Get a single API key's info.

        Args:
            key_id: The API key ID

        Returns:
            ApiKeyInfo or None if not found
        """
        key = self.db.api_keys.get_by_id(key_id)
        if key is None:
            return None

        return ApiKeyInfo(
            id=key["id"],
            name=key["name"],
            prefix=key["prefix"],
            scopes=key["scopes"],
            created_at=key["created_at"],
            last_used_at=key.get("last_used_at"),
            expires_at=key.get("expires_at"),
            is_active=key["is_active"],
        )
