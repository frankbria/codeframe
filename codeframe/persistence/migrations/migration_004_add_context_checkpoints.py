"""Migration 004: Add context_checkpoints table for flash save functionality.

This migration adds the context_checkpoints table to support the 007-context-management feature:

New table: context_checkpoints
- Stores flash save checkpoint data for agent context management
- Tracks context state snapshots including items count, archived count, and token metrics
- Enables context recovery and historical tracking

Table schema:
- id: Auto-increment primary key
- agent_id: FK to agents table
- checkpoint_data: JSON serialized context state
- items_count: Total items before flash save
- items_archived: Number of COLD items archived
- hot_items_retained: Number of HOT items kept
- token_count: Total tokens before flash save
- created_at: Checkpoint timestamp
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class AddContextCheckpoints(Migration):
    """Add context_checkpoints table for flash save feature."""

    def __init__(self):
        super().__init__(
            version="004",
            description="Add context_checkpoints table for flash save feature"
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if context_checkpoints table does not exist.
        """
        cursor = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='context_checkpoints'
            """
        )
        row = cursor.fetchone()

        if row:
            logger.info("context_checkpoints table already exists, skipping migration")
            return False

        logger.info("context_checkpoints table not found, migration can be applied")
        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        Creates context_checkpoints table with indexes.
        """
        cursor = conn.cursor()

        # Create context_checkpoints table
        cursor.execute("""
            CREATE TABLE context_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                checkpoint_data TEXT NOT NULL,
                items_count INTEGER NOT NULL,
                items_archived INTEGER NOT NULL,
                hot_items_retained INTEGER NOT NULL,
                token_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
            )
        """)
        logger.info("Created context_checkpoints table")

        # Create performance index
        cursor.execute("""
            CREATE INDEX idx_checkpoints_agent_created
            ON context_checkpoints(agent_id, created_at DESC)
        """)
        logger.info("Created index: idx_checkpoints_agent_created")

        conn.commit()
        logger.info("Migration 004 completed successfully")

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        Drops context_checkpoints table and its indexes.
        """
        cursor = conn.cursor()

        # Check if table exists and has data
        try:
            cursor.execute("SELECT COUNT(*) FROM context_checkpoints")
            checkpoint_count = cursor.fetchone()[0]
            logger.warning(f"Rollback will remove {checkpoint_count} checkpoints")
        except sqlite3.OperationalError:
            checkpoint_count = 0
            logger.info("context_checkpoints table doesn't exist")

        # Drop index and table
        cursor.execute("DROP INDEX IF EXISTS idx_checkpoints_agent_created")
        logger.info("Dropped index: idx_checkpoints_agent_created")

        cursor.execute("DROP TABLE IF EXISTS context_checkpoints")
        logger.info("Dropped context_checkpoints table")

        conn.commit()
        logger.info("Migration 004 rollback completed successfully")


# Migration instance for auto-discovery
migration = AddContextCheckpoints()
