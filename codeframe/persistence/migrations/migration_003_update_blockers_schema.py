"""Migration 003: Update blockers table schema for human-in-the-loop functionality.

This migration updates the blockers table to support the 049-human-in-loop feature:

New fields added to blockers table:
- agent_id: Agent that created the blocker (required)
- answer: User's answer to the blocker question (replaces resolution)
- status: Current blocker status (PENDING, RESOLVED, EXPIRED)
- blocker_type: Type of blocker (SYNC or ASYNC, replaces severity)

SQLite doesn't support complex ALTER TABLE operations,
so we need to recreate the table:
1. Create new blockers table with updated schema
2. Migrate existing data with field mapping
3. Drop old blockers table
4. Rename new table
5. Create performance indexes
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class UpdateBlockersSchema(Migration):
    """Update blockers table for human-in-the-loop feature."""

    def __init__(self):
        super().__init__(
            version="003",
            description="Update blockers schema for human-in-the-loop feature"
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if blockers table exists without the new schema fields.
        """
        cursor = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='blockers'
            """
        )
        row = cursor.fetchone()

        if not row:
            logger.info("Blockers table doesn't exist yet, skipping migration")
            return False

        # Check if new fields already exist
        table_sql = row[0]
        has_new_fields = "agent_id" in table_sql and "status" in table_sql and "answer" in table_sql

        if has_new_fields:
            logger.info("New schema already applied, skipping migration")
            return False

        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        Creates new blockers table with updated schema and migrates data.
        """
        cursor = conn.cursor()

        # Check if blockers table exists and has data
        try:
            cursor.execute("SELECT COUNT(*) FROM blockers")
            blocker_count = cursor.fetchone()[0]
            logger.info(f"Found {blocker_count} blockers to migrate")
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            blocker_count = 0
            logger.info("No existing blockers table found")

        # 1. Create new blockers table with updated schema
        cursor.execute("""
            CREATE TABLE blockers_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                project_id INTEGER NOT NULL,
                task_id INTEGER,
                blocker_type TEXT NOT NULL CHECK(blocker_type IN ('SYNC', 'ASYNC')),
                question TEXT NOT NULL,
                answer TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'RESOLVED', 'EXPIRED')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)
        logger.info("Created new blockers table with updated schema")

        # 2. Migrate existing data (if any) with field mapping
        if blocker_count > 0:
            cursor.execute("""
                INSERT INTO blockers_new
                    (id, agent_id, project_id, task_id, blocker_type, question, answer, status, created_at, resolved_at)
                SELECT
                    b.id,
                    COALESCE(
                        (SELECT a.id FROM agents a JOIN tasks t ON t.id = b.task_id WHERE a.id = t.current_task_id LIMIT 1),
                        'unknown-agent'
                    ) as agent_id,
                    COALESCE(
                        (SELECT t.project_id FROM tasks t WHERE t.id = b.task_id),
                        (SELECT MIN(id) FROM projects)
                    ) as project_id,
                    b.task_id,
                    UPPER(COALESCE(b.severity, 'async')) as blocker_type,
                    COALESCE(b.question, b.reason, 'No question provided') as question,
                    b.resolution as answer,
                    CASE
                        WHEN b.resolved_at IS NOT NULL THEN 'RESOLVED'
                        ELSE 'PENDING'
                    END as status,
                    b.created_at,
                    b.resolved_at
                FROM blockers b
            """)
            logger.info(f"Migrated {blocker_count} existing blockers")

        # 3. Drop old blockers table
        cursor.execute("DROP TABLE IF EXISTS blockers")
        logger.info("Dropped old blockers table")

        # 4. Rename new table
        cursor.execute("ALTER TABLE blockers_new RENAME TO blockers")
        logger.info("Renamed blockers_new to blockers")

        # 5. Create performance indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_blockers_status_created
            ON blockers(status, created_at)
        """)
        logger.info("Created index: idx_blockers_status_created")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_blockers_agent_status
            ON blockers(agent_id, status)
        """)
        logger.info("Created index: idx_blockers_agent_status")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_blockers_task_id
            ON blockers(task_id)
        """)
        logger.info("Created index: idx_blockers_task_id")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_blockers_project_status
            ON blockers(project_id, status)
        """)
        logger.info("Created index: idx_blockers_project_status")

        conn.commit()
        logger.info("Migration 003 completed successfully")

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        Recreates blockers table with original schema (data will be lost).
        """
        cursor = conn.cursor()

        # Check if blockers table exists and has data
        try:
            cursor.execute("SELECT COUNT(*) FROM blockers")
            blocker_count = cursor.fetchone()[0]
            logger.warning(f"Rollback will remove {blocker_count} blockers")
        except sqlite3.OperationalError:
            blocker_count = 0

        # Drop new table and indexes
        cursor.execute("DROP INDEX IF EXISTS idx_blockers_status_created")
        cursor.execute("DROP INDEX IF EXISTS idx_blockers_agent_status")
        cursor.execute("DROP INDEX IF EXISTS idx_blockers_task_id")
        cursor.execute("DROP TABLE IF EXISTS blockers")
        logger.info("Dropped new blockers table and indexes")

        # Create old blockers table with original schema
        cursor.execute("""
            CREATE TABLE blockers (
                id INTEGER PRIMARY KEY,
                task_id INTEGER REFERENCES tasks(id),
                severity TEXT CHECK(severity IN ('sync', 'async')),
                reason TEXT,
                question TEXT,
                resolution TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
            )
        """)
        logger.info("Recreated blockers table with original schema")

        conn.commit()


# Migration instance for auto-discovery
migration = UpdateBlockersSchema()
