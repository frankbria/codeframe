"""Migration 011: Backfill NULL created_at and add NOT NULL constraint.

This migration ensures data integrity by:

1. Backfilling NULL created_at values in tasks table with CURRENT_TIMESTAMP
2. Backfilling NULL created_at values in issues table with CURRENT_TIMESTAMP
3. Recreating tables with NOT NULL constraint on created_at

This prevents data quality issues where created_at is unexpectedly NULL.

Migration: 011
Created: 2025-12-18
Sprint: Type Safety Improvements
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class CreatedAtNotNull(Migration):
    """Backfill NULL created_at and add NOT NULL constraint."""

    def __init__(self):
        super().__init__(
            version="011",
            description="Backfill NULL created_at and add NOT NULL constraint",
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if there are NULL created_at values or columns allow NULL.
        """
        cursor = conn.cursor()

        # Check for NULL values in tasks
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE created_at IS NULL")
        null_tasks = cursor.fetchone()[0]

        # Check for NULL values in issues
        cursor.execute("SELECT COUNT(*) FROM issues WHERE created_at IS NULL")
        null_issues = cursor.fetchone()[0]

        if null_tasks > 0 or null_issues > 0:
            logger.info(
                f"Found {null_tasks} tasks and {null_issues} issues with NULL created_at"
            )
            return True

        # Check if NOT NULL constraint already exists by examining table schema
        # SQLite doesn't have a direct way to check constraints, so we look for notnull flag
        cursor.execute("PRAGMA table_info(tasks)")
        for row in cursor.fetchall():
            if row[1] == "created_at" and row[3] == 0:  # notnull flag is 0 (allows NULL)
                logger.info("tasks.created_at allows NULL, migration can be applied")
                return True

        cursor.execute("PRAGMA table_info(issues)")
        for row in cursor.fetchall():
            if row[1] == "created_at" and row[3] == 0:  # notnull flag is 0 (allows NULL)
                logger.info("issues.created_at allows NULL, migration can be applied")
                return True

        logger.info("NOT NULL constraint already exists, skipping migration")
        return False

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        Backfills NULL values and recreates tables with NOT NULL constraint.
        """
        cursor = conn.cursor()

        logger.info("Migration 011: Backfilling NULL created_at values")

        # Step 1: Backfill NULL created_at in tasks
        cursor.execute(
            """
            UPDATE tasks
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """
        )
        tasks_updated = cursor.rowcount
        logger.info(f"Backfilled {tasks_updated} tasks with NULL created_at")

        # Step 2: Backfill NULL created_at in issues
        cursor.execute(
            """
            UPDATE issues
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """
        )
        issues_updated = cursor.rowcount
        logger.info(f"Backfilled {issues_updated} issues with NULL created_at")

        conn.commit()

        # Step 3: Recreate tasks table with NOT NULL constraint
        logger.info("Recreating tasks table with NOT NULL constraint on created_at")
        cursor.execute("PRAGMA foreign_keys = OFF")

        try:
            # Create new tasks table with NOT NULL
            cursor.execute(
                """
                CREATE TABLE tasks_new (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER REFERENCES projects(id),
                    issue_id INTEGER REFERENCES issues(id),
                    task_number TEXT,
                    parent_issue_number TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT CHECK(status IN ('pending', 'assigned', 'in_progress', 'blocked', 'completed', 'failed')),
                    assigned_to TEXT,
                    depends_on TEXT,
                    can_parallelize BOOLEAN DEFAULT FALSE,
                    priority INTEGER CHECK(priority BETWEEN 0 AND 4),
                    workflow_step INTEGER,
                    requires_mcp BOOLEAN DEFAULT FALSE,
                    estimated_tokens INTEGER,
                    actual_tokens INTEGER,
                    commit_sha TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
                """
            )

            # Copy data
            cursor.execute(
                """
                INSERT INTO tasks_new
                SELECT * FROM tasks
                """
            )

            # Drop old table and rename
            cursor.execute("DROP TABLE tasks")
            cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")

            # Recreate indexes
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_issue_number
                ON tasks(parent_issue_number)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_pending_priority
                ON tasks(project_id, status, priority, created_at)
                """
            )

            logger.info("Recreated tasks table with NOT NULL constraint")

            # Step 4: Recreate issues table with NOT NULL constraint
            logger.info("Recreating issues table with NOT NULL constraint on created_at")

            cursor.execute(
                """
                CREATE TABLE issues_new (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER REFERENCES projects(id),
                    issue_number TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT CHECK(status IN ('pending', 'in_progress', 'completed', 'failed')),
                    priority INTEGER CHECK(priority BETWEEN 0 AND 4),
                    workflow_step INTEGER,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    UNIQUE(project_id, issue_number)
                )
                """
            )

            # Copy data
            cursor.execute(
                """
                INSERT INTO issues_new
                SELECT * FROM issues
                """
            )

            # Drop old table and rename
            cursor.execute("DROP TABLE issues")
            cursor.execute("ALTER TABLE issues_new RENAME TO issues")

            # Recreate indexes
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_issues_number
                ON issues(project_id, issue_number)
                """
            )

            logger.info("Recreated issues table with NOT NULL constraint")

        finally:
            cursor.execute("PRAGMA foreign_keys = ON")

        conn.commit()
        logger.info("Migration 011 completed successfully")

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        Recreates tables allowing NULL in created_at (original schema).
        Note: This does not restore NULL values - they remain backfilled.
        """
        cursor = conn.cursor()

        logger.warning("Rolling back migration 011: Removing NOT NULL constraint")
        cursor.execute("PRAGMA foreign_keys = OFF")

        try:
            # Recreate tasks table without NOT NULL
            cursor.execute(
                """
                CREATE TABLE tasks_new (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER REFERENCES projects(id),
                    issue_id INTEGER REFERENCES issues(id),
                    task_number TEXT,
                    parent_issue_number TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT CHECK(status IN ('pending', 'assigned', 'in_progress', 'blocked', 'completed', 'failed')),
                    assigned_to TEXT,
                    depends_on TEXT,
                    can_parallelize BOOLEAN DEFAULT FALSE,
                    priority INTEGER CHECK(priority BETWEEN 0 AND 4),
                    workflow_step INTEGER,
                    requires_mcp BOOLEAN DEFAULT FALSE,
                    estimated_tokens INTEGER,
                    actual_tokens INTEGER,
                    commit_sha TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
                """
            )

            cursor.execute("INSERT INTO tasks_new SELECT * FROM tasks")
            cursor.execute("DROP TABLE tasks")
            cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")

            # Recreate indexes
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_issue_number
                ON tasks(parent_issue_number)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_pending_priority
                ON tasks(project_id, status, priority, created_at)
                """
            )

            # Recreate issues table without NOT NULL
            cursor.execute(
                """
                CREATE TABLE issues_new (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER REFERENCES projects(id),
                    issue_number TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT CHECK(status IN ('pending', 'in_progress', 'completed', 'failed')),
                    priority INTEGER CHECK(priority BETWEEN 0 AND 4),
                    workflow_step INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    UNIQUE(project_id, issue_number)
                )
                """
            )

            cursor.execute("INSERT INTO issues_new SELECT * FROM issues")
            cursor.execute("DROP TABLE issues")
            cursor.execute("ALTER TABLE issues_new RENAME TO issues")

            # Recreate indexes
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_issues_number
                ON issues(project_id, issue_number)
                """
            )

        finally:
            cursor.execute("PRAGMA foreign_keys = ON")

        conn.commit()
        logger.info("Migration 011 rollback completed")


# Migration instance for auto-discovery
migration = CreatedAtNotNull()
