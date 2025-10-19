"""Migration 001: Remove hard-coded CHECK constraint on agent type.

This migration allows arbitrary agent types to be stored in the database,
enabling dynamic agent type definition from YAML configuration files.

SQLite doesn't support ALTER TABLE DROP CONSTRAINT, so we:
1. Create new table without constraint
2. Copy data from old table
3. Drop old table
4. Rename new table
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class RemoveAgentTypeConstraint(Migration):
    """Remove CHECK constraint on agents.type field."""

    def __init__(self):
        super().__init__(
            version="001",
            description="Remove hard-coded CHECK constraint on agent type"
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if agents table exists and has the old constraint.
        """
        cursor = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='agents'
            """
        )
        row = cursor.fetchone()

        if not row:
            logger.info("Agents table doesn't exist yet, skipping migration")
            return False

        # Check if constraint exists
        table_sql = row[0]
        has_constraint = "CHECK(type IN (" in table_sql

        if not has_constraint:
            logger.info("Constraint already removed, skipping migration")
            return False

        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        Creates new agents table without type constraint and migrates data.
        """
        cursor = conn.cursor()

        # Check if agents table exists and has data
        cursor.execute("SELECT COUNT(*) FROM agents")
        agent_count = cursor.fetchone()[0]
        logger.info(f"Found {agent_count} agents to migrate")

        # 1. Create new table without type constraint
        cursor.execute("""
            CREATE TABLE agents_new (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                provider TEXT,
                maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
                status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
                current_task_id INTEGER REFERENCES tasks(id),
                last_heartbeat TIMESTAMP,
                metrics JSON
            )
        """)
        logger.info("Created new agents table without type constraint")

        # 2. Copy data from old table
        cursor.execute("""
            INSERT INTO agents_new
            SELECT * FROM agents
        """)
        logger.info(f"Copied {agent_count} agents to new table")

        # 3. Drop old table
        cursor.execute("DROP TABLE agents")
        logger.info("Dropped old agents table")

        # 4. Rename new table
        cursor.execute("ALTER TABLE agents_new RENAME TO agents")
        logger.info("Renamed agents_new to agents")

        conn.commit()

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        Recreates agents table with type constraint.
        """
        cursor = conn.cursor()

        # Check if agents table exists and has data
        cursor.execute("SELECT COUNT(*) FROM agents")
        agent_count = cursor.fetchone()[0]
        logger.info(f"Found {agent_count} agents to rollback")

        # 1. Create old table with type constraint
        cursor.execute("""
            CREATE TABLE agents_old (
                id TEXT PRIMARY KEY,
                type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
                provider TEXT,
                maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
                status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
                current_task_id INTEGER REFERENCES tasks(id),
                last_heartbeat TIMESTAMP,
                metrics JSON
            )
        """)
        logger.info("Created agents table with type constraint")

        # 2. Copy data - this will fail if any agents have non-standard types
        try:
            cursor.execute("""
                INSERT INTO agents_old
                SELECT * FROM agents
            """)
            logger.info(f"Copied {agent_count} agents to old table")
        except sqlite3.IntegrityError as e:
            logger.error(f"Cannot rollback: agents table contains non-standard types: {e}")
            cursor.execute("DROP TABLE agents_old")
            raise ValueError(
                "Cannot rollback migration: agents table contains agent types "
                "not in ('lead', 'backend', 'frontend', 'test', 'review'). "
                "Please remove or update these agents before rolling back."
            )

        # 3. Drop new table
        cursor.execute("DROP TABLE agents")
        logger.info("Dropped new agents table")

        # 4. Rename old table
        cursor.execute("ALTER TABLE agents_old RENAME TO agents")
        logger.info("Renamed agents_old to agents")

        conn.commit()


# Migration instance for auto-discovery
migration = RemoveAgentTypeConstraint()
