"""Add session_id column to token_usage table.

This migration adds SDK session tracking support to the token_usage table,
enabling conversation-level token aggregation for Claude Agent SDK integration.

Migration: 008
Created: 2025-11-30
Sprint: SDK Migration Phase 1
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class AddSessionId(Migration):
    """Add session_id column to token_usage table."""

    def __init__(self):
        super().__init__(
            version="008",
            description="Add session_id to token_usage table for SDK session tracking",
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if token_usage table exists without session_id column.
        """
        cursor = conn.cursor()

        # Check if token_usage table exists
        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='token_usage'
            """
        )
        if not cursor.fetchone():
            logger.info("token_usage table doesn't exist yet, skipping migration")
            return False

        # Check if session_id column already exists
        cursor.execute("PRAGMA table_info(token_usage)")
        columns = [row[1] for row in cursor.fetchall()]

        if "session_id" in columns:
            logger.info("session_id column already exists, skipping migration")
            return False

        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        Adds session_id column to token_usage table.
        """
        cursor = conn.cursor()

        logger.info("Migration 008: Adding session_id to token_usage table")

        try:
            cursor.execute(
                """
                ALTER TABLE token_usage
                ADD COLUMN session_id TEXT DEFAULT NULL
                """
            )
            logger.info("✓ Added session_id column to token_usage table")

        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("session_id column already exists")
            else:
                raise

        conn.commit()
        logger.info("Migration 008 completed successfully")

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        Note: SQLite doesn't support DROP COLUMN easily, so this would require
        table recreation. For now, we leave the column in place on rollback.
        """
        logger.info("Rollback for migration 008 not implemented (SQLite limitation)")
        logger.info("The session_id column will remain but can be ignored")


# Migration instance for auto-discovery
migration = AddSessionId()
