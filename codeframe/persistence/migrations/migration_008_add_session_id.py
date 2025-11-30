"""Add session_id column to token_usage table.

This migration adds SDK session tracking support to the token_usage table,
enabling conversation-level token aggregation for Claude Agent SDK integration.

Migration: 008
Created: 2025-11-30
Sprint: SDK Migration Phase 1
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codeframe.persistence.database import Database

logger = logging.getLogger(__name__)


async def upgrade(db: "Database") -> None:
    """Add session_id column to token_usage table.

    Args:
        db: Database instance

    Raises:
        Exception: If migration fails
    """
    logger.info("Running migration 008: Add session_id to token_usage")

    try:
        # Add session_id column
        await db.execute(
            """
            ALTER TABLE token_usage
            ADD COLUMN session_id TEXT DEFAULT NULL
            """
        )

        logger.info("✓ Added session_id column to token_usage table")

    except Exception as e:
        logger.error(f"Migration 008 failed: {e}")
        raise


async def downgrade(db: "Database") -> None:
    """Remove session_id column from token_usage table.

    Note: SQLite doesn't support DROP COLUMN easily, so this would require
    table recreation. For now, we leave the column in place on downgrade.

    Args:
        db: Database instance
    """
    logger.info("Downgrade for migration 008 not implemented (SQLite limitation)")
    logger.info("The session_id column will remain but can be ignored")
