"""Migration 009: Add project_agents junction table for many-to-many relationships.

This migration implements the multi-agent per project architecture by:

1. Creating project_agents junction table
2. Adding performance indexes (partial indexes for is_active = TRUE)
3. Migrating existing agent-project relationships (if agents table has project_id)
4. Removing project_id column from agents table (SQLite recreation pattern)
5. Adding created_at timestamp to agents table

This enables:
- Agents can work on multiple projects (reusable resources)
- Projects can have multiple agents working on them
- Historical tracking of agent assignments (soft delete pattern)
- Flexible role assignment per project

Migration: 009
Created: 2025-12-03
Sprint: Multi-Agent Architecture Phase 2
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class AddProjectAgentsJunctionTable(Migration):
    """Add project_agents junction table for many-to-many relationships."""

    def __init__(self):
        super().__init__(
            version="009",
            description="Add project_agents junction table for multi-agent per project"
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if agents table exists without project_agents table.
        """
        cursor = conn.cursor()

        # Check if project_agents table already exists
        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='project_agents'
            """
        )
        if cursor.fetchone():
            logger.info("project_agents table already exists, skipping migration")
            return False

        # Check if agents table exists
        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='agents'
            """
        )
        if not cursor.fetchone():
            logger.info("agents table doesn't exist yet, skipping migration")
            return False

        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        Creates project_agents table and migrates existing data if needed.
        """
        cursor = conn.cursor()

        # Step 1: Create project_agents junction table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS project_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unassigned_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                CHECK(unassigned_at IS NULL OR unassigned_at >= assigned_at)
            )
        """
        )
        logger.info("Created project_agents junction table")

        # Step 2: Create performance indexes
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_agents_project_active
            ON project_agents(project_id, is_active)
            WHERE is_active = TRUE
        """
        )
        logger.info("Created index: idx_project_agents_project_active")

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_agents_agent_active
            ON project_agents(agent_id, is_active)
            WHERE is_active = TRUE
        """
        )
        logger.info("Created index: idx_project_agents_agent_active")

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_agents_assigned_at
            ON project_agents(assigned_at)
        """
        )
        logger.info("Created index: idx_project_agents_assigned_at")

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_agents_unassigned
            ON project_agents(unassigned_at)
            WHERE unassigned_at IS NOT NULL
        """
        )
        logger.info("Created index: idx_project_agents_unassigned")

        # Step 3: Create unique constraint (partial index)
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_project_agents_unique_active
            ON project_agents(project_id, agent_id, is_active)
            WHERE is_active = TRUE
        """
        )
        logger.info("Created unique constraint: idx_project_agents_unique_active")

        # Step 4: Check if agents table has project_id column
        cursor.execute("PRAGMA table_info(agents)")
        columns = [row[1] for row in cursor.fetchall()]
        has_project_id = 'project_id' in columns

        if has_project_id:
            logger.info("Found project_id in agents table, migrating data...")

            # Step 4a: Migrate existing agent-project relationships
            cursor.execute(
                """
                INSERT INTO project_agents (project_id, agent_id, role, is_active)
                SELECT
                    project_id,
                    id,
                    'migrated',
                    TRUE
                FROM agents
                WHERE project_id IS NOT NULL
            """
            )
            migrated_count = cursor.rowcount
            logger.info(f"Migrated {migrated_count} existing agent-project relationships")

            # Step 4b: Recreate agents table WITHOUT project_id
            cursor.execute("PRAGMA foreign_keys = OFF")

            cursor.execute(
                """
                CREATE TABLE agents_new (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    provider TEXT,
                    maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
                    status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
                    current_task_id INTEGER REFERENCES tasks(id),
                    last_heartbeat TIMESTAMP,
                    metrics JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            logger.info("Created agents_new table without project_id")

            cursor.execute(
                """
                INSERT INTO agents_new (id, type, provider, maturity_level, status, current_task_id, last_heartbeat, metrics, created_at)
                SELECT
                    id, type, provider, maturity_level, status, current_task_id, last_heartbeat, metrics,
                    CURRENT_TIMESTAMP
                FROM agents
            """
            )
            logger.info("Copied data to agents_new")

            cursor.execute("DROP TABLE agents")
            cursor.execute("ALTER TABLE agents_new RENAME TO agents")
            logger.info("Replaced agents table with new schema")

            cursor.execute("PRAGMA foreign_keys = ON")

        else:
            logger.info("agents table doesn't have project_id, no data migration needed")

            # Still need to add created_at column if it doesn't exist
            cursor.execute("PRAGMA table_info(agents)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'created_at' not in columns:
                cursor.execute(
                    """
                    ALTER TABLE agents
                    ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                """
                )
                logger.info("Added created_at column to agents table")

        conn.commit()
        logger.info("Migration 009 completed successfully")

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        WARNING: This will lose multi-project assignments, keeping only one project per agent.
        """
        cursor = conn.cursor()

        logger.warning("Rolling back migration 009: Multi-project assignments will be lost")

        cursor.execute("PRAGMA foreign_keys = OFF")

        # Step 1: Recreate agents table WITH project_id
        cursor.execute(
            """
            CREATE TABLE agents_new (
                id TEXT PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                provider TEXT,
                maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
                status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
                current_task_id INTEGER REFERENCES tasks(id),
                last_heartbeat TIMESTAMP,
                metrics JSON
            )
        """
        )
        logger.info("Created agents_new table WITH project_id")

        # Step 2: Restore data with FIRST project assignment per agent
        cursor.execute(
            """
            INSERT INTO agents_new (id, project_id, type, provider, maturity_level, status, current_task_id, last_heartbeat, metrics)
            SELECT
                a.id,
                pa.project_id,
                a.type,
                a.provider,
                a.maturity_level,
                a.status,
                a.current_task_id,
                a.last_heartbeat,
                a.metrics
            FROM agents a
            LEFT JOIN (
                SELECT agent_id, project_id, MIN(assigned_at) AS first_assigned
                FROM project_agents
                WHERE is_active = TRUE
                GROUP BY agent_id
            ) pa ON a.id = pa.agent_id
        """
        )
        logger.info("Restored agents with first project assignment")

        cursor.execute("DROP TABLE agents")
        cursor.execute("ALTER TABLE agents_new RENAME TO agents")
        logger.info("Replaced agents table")

        # Step 3: Drop project_agents table and indexes
        cursor.execute("DROP INDEX IF EXISTS idx_project_agents_project_active")
        cursor.execute("DROP INDEX IF EXISTS idx_project_agents_agent_active")
        cursor.execute("DROP INDEX IF EXISTS idx_project_agents_assigned_at")
        cursor.execute("DROP INDEX IF EXISTS idx_project_agents_unassigned")
        cursor.execute("DROP INDEX IF EXISTS idx_project_agents_unique_active")
        cursor.execute("DROP TABLE IF EXISTS project_agents")
        logger.info("Dropped project_agents table and indexes")

        cursor.execute("PRAGMA foreign_keys = ON")

        conn.commit()
        logger.info("Migration 009 rollback completed")


# Migration instance for auto-discovery
migration = AddProjectAgentsJunctionTable()
