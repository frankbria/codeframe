"""Migration 005: Add performance indexes to context_items table.

This migration adds performance indexes to the context_items table to support
the 007-context-management feature:

Indexes added:
- idx_context_agent_tier: Composite index on (agent_id, tier) for fast hot context loading
- idx_context_importance: Index on importance_score DESC for tier reassignment queries
- idx_context_last_accessed: Index on last_accessed DESC for age-based sorting

These indexes optimize the most common query patterns:
1. Loading HOT context for an agent (agent_id + tier filter)
2. Reassigning tiers based on importance scores (importance_score ordering)
3. Finding stale items for archival (last_accessed ordering)
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class AddContextIndexes(Migration):
    """Add performance indexes to context_items table."""

    def __init__(self):
        super().__init__(
            version="005", description="Add performance indexes to context_items table"
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if context_items table exists and indexes don't exist.
        """
        cursor = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='context_items'
            """
        )
        table_row = cursor.fetchone()

        if not table_row:
            logger.info("context_items table doesn't exist yet, skipping migration")
            return False

        # Check if indexes already exist
        cursor = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='index' AND name IN (
                'idx_context_agent_tier',
                'idx_context_importance',
                'idx_context_last_accessed'
            )
            """
        )
        existing_indexes = cursor.fetchall()

        if len(existing_indexes) >= 3:
            logger.info("Context indexes already exist, skipping migration")
            return False

        logger.info(f"Found {len(existing_indexes)}/3 indexes, migration can be applied")
        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        Creates performance indexes on context_items table.
        """
        cursor = conn.cursor()

        # Create composite index on agent_id and tier
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_context_agent_tier
            ON context_items(agent_id, tier)
        """
        )
        logger.info("Created index: idx_context_agent_tier")

        # Create index on importance_score for sorting
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_context_importance
            ON context_items(importance_score DESC)
        """
        )
        logger.info("Created index: idx_context_importance")

        # Create index on last_accessed for age-based queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_context_last_accessed
            ON context_items(last_accessed DESC)
        """
        )
        logger.info("Created index: idx_context_last_accessed")

        conn.commit()
        logger.info("Migration 005 completed successfully")

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        Drops the performance indexes from context_items table.
        """
        cursor = conn.cursor()

        # Drop all three indexes
        cursor.execute("DROP INDEX IF EXISTS idx_context_agent_tier")
        logger.info("Dropped index: idx_context_agent_tier")

        cursor.execute("DROP INDEX IF EXISTS idx_context_importance")
        logger.info("Dropped index: idx_context_importance")

        cursor.execute("DROP INDEX IF EXISTS idx_context_last_accessed")
        logger.info("Dropped index: idx_context_last_accessed")

        conn.commit()
        logger.info("Migration 005 rollback completed successfully")


# Migration instance for auto-discovery
migration = AddContextIndexes()
