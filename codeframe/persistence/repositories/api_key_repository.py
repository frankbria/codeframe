"""Repository for API key database operations.

Handles CRUD operations for API keys used for programmatic server access.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import logging

from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class APIKeyRepository(BaseRepository):
    """Repository for API key operations."""

    def create(
        self,
        user_id: int,
        name: str,
        key_hash: str,
        prefix: str,
        scopes: List[str],
        expires_at: Optional[datetime] = None,
    ) -> str:
        """Create a new API key record.

        Args:
            user_id: Owner user ID
            name: Human-readable name for the key
            key_hash: SHA256 or bcrypt hash of the full key
            prefix: First 12 chars for efficient lookup
            scopes: List of permission scopes
            expires_at: Optional expiration timestamp

        Returns:
            Generated key ID (UUID)
        """
        key_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Normalize expires_at to UTC for consistent string comparison
        expires_at_utc = None
        if expires_at:
            if expires_at.tzinfo is None:
                # Treat naive datetime as UTC
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            expires_at_utc = expires_at.astimezone(timezone.utc).isoformat()

        self._execute(
            """
            INSERT INTO api_keys (
                id, user_id, name, key_hash, prefix, scopes,
                created_at, expires_at, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                key_id,
                user_id,
                name,
                key_hash,
                prefix,
                json.dumps(scopes),
                now,
                expires_at_utc,
            ),
        )
        self._commit()

        logger.debug(f"Created API key {key_id} for user {user_id}")
        return key_id

    def get_by_id(self, key_id: str) -> Optional[Dict[str, Any]]:
        """Get an API key by its ID.

        Args:
            key_id: The key's UUID

        Returns:
            Key record dict or None if not found
        """
        row = self._fetchone(
            """
            SELECT id, user_id, name, key_hash, prefix, scopes,
                   created_at, last_used_at, expires_at, is_active
            FROM api_keys
            WHERE id = ?
            """,
            (key_id,),
        )

        if row is None:
            return None

        return self._row_to_api_key(row)

    def get_by_prefix(self, prefix: str) -> Optional[Dict[str, Any]]:
        """Get an active API key by its prefix.

        Only returns active, non-expired keys for authentication.

        Args:
            prefix: The key prefix (first 12 characters)

        Returns:
            Key record dict or None if not found/inactive
        """
        now = datetime.now(timezone.utc).isoformat()

        row = self._fetchone(
            """
            SELECT id, user_id, name, key_hash, prefix, scopes,
                   created_at, last_used_at, expires_at, is_active
            FROM api_keys
            WHERE prefix = ?
              AND is_active = 1
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (prefix, now),
        )

        if row is None:
            return None

        return self._row_to_api_key(row)

    def list_user_keys(self, user_id: int) -> List[Dict[str, Any]]:
        """List all API keys for a user (active and inactive).

        Does NOT include key_hash for security.

        Args:
            user_id: The user's ID

        Returns:
            List of key records (without key_hash)
        """
        rows = self._fetchall(
            """
            SELECT id, user_id, name, prefix, scopes,
                   created_at, last_used_at, expires_at, is_active
            FROM api_keys
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        )

        return [self._row_to_api_key_safe(row) for row in rows]

    def update_last_used(self, key_id: str) -> None:
        """Update the last_used_at timestamp.

        Called after successful authentication.

        Args:
            key_id: The key's UUID
        """
        now = datetime.now(timezone.utc).isoformat()

        self._execute(
            """
            UPDATE api_keys
            SET last_used_at = ?
            WHERE id = ?
            """,
            (now, key_id),
        )
        self._commit()

    def revoke(self, key_id: str, user_id: int) -> bool:
        """Revoke an API key (soft delete).

        Args:
            key_id: The key's UUID
            user_id: The user attempting to revoke (must be owner)

        Returns:
            True if revoked, False if not found or not owned
        """
        cursor = self._execute(
            """
            UPDATE api_keys
            SET is_active = 0
            WHERE id = ? AND user_id = ?
            """,
            (key_id, user_id),
        )
        self._commit()

        return cursor.rowcount > 0

    def delete(self, key_id: str, user_id: int) -> bool:
        """Hard delete an API key.

        Args:
            key_id: The key's UUID
            user_id: The user attempting to delete (must be owner)

        Returns:
            True if deleted, False if not found or not owned
        """
        cursor = self._execute(
            """
            DELETE FROM api_keys
            WHERE id = ? AND user_id = ?
            """,
            (key_id, user_id),
        )
        self._commit()

        return cursor.rowcount > 0

    def _row_to_api_key(self, row) -> Dict[str, Any]:
        """Convert database row to API key dict (includes hash)."""
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "key_hash": row["key_hash"],
            "prefix": row["prefix"],
            "scopes": json.loads(row["scopes"]),
            "created_at": self._ensure_rfc3339(row["created_at"]),
            "last_used_at": self._ensure_rfc3339(row["last_used_at"]) if row["last_used_at"] else None,
            "expires_at": self._ensure_rfc3339(row["expires_at"]) if row["expires_at"] else None,
            "is_active": bool(row["is_active"]),
        }

    def _row_to_api_key_safe(self, row) -> Dict[str, Any]:
        """Convert database row to API key dict (excludes hash for listing)."""
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "prefix": row["prefix"],
            "scopes": json.loads(row["scopes"]),
            "created_at": self._ensure_rfc3339(row["created_at"]),
            "last_used_at": self._ensure_rfc3339(row["last_used_at"]) if row["last_used_at"] else None,
            "expires_at": self._ensure_rfc3339(row["expires_at"]) if row["expires_at"] else None,
            "is_active": bool(row["is_active"]),
        }
