"""Migration 006: MVP Completion (Sprint 9)

Changes:
1. Add commit_sha column to tasks table
2. Create lint_results table
3. Create composite index on context_items(project_id, agent_id, current_tier)
4. Create partial index on tasks.commit_sha

Performance Impact:
- Composite index (idx_context_project_agent) improves multi-agent context queries
- Verified via EXPLAIN QUERY PLAN - index used for project_id + agent_id + current_tier queries
- Benchmark: Queries on 1000+ context items show measurable speedup vs table scan
- Enables efficient context filtering for multiple concurrent agents

Date: 2025-11-15
Sprint: 009-mvp-completion
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class MVPCompletion(Migration):
    """Add Sprint 9 MVP completion features."""

    def __init__(self):
        super().__init__(version="006", description="MVP Completion (Sprint 9)")

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if lint_results table does not exist.
        """
        cursor = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='lint_results'
            """
        )
        row = cursor.fetchone()

        if row:
            logger.info("lint_results table already exists, skipping migration")
            return False

        logger.info("lint_results table not found, migration can be applied")
        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration."""
        cursor = conn.cursor()

        logger.info("Migration 006: Adding commit_sha to tasks table")
        try:
            cursor.execute("ALTER TABLE tasks ADD COLUMN commit_sha TEXT")
            logger.info("✓ Added commit_sha column")
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "duplicate column name" in error_msg:
                logger.info("⊘ Column commit_sha already exists, skipping")
            elif "no such table" in error_msg:
                logger.warning("⚠ tasks table does not exist, skipping commit_sha column addition")
            else:
                raise

        logger.info("Migration 006: Creating lint_results table")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS lint_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                linter TEXT NOT NULL CHECK(linter IN ('ruff', 'eslint', 'other')),
                error_count INTEGER NOT NULL DEFAULT 0,
                warning_count INTEGER NOT NULL DEFAULT 0,
                files_linted INTEGER NOT NULL DEFAULT 0,
                output TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """
        )
        logger.info("✓ Created lint_results table")

        logger.info("Migration 006: Creating indexes on lint_results")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lint_results_task
            ON lint_results(task_id)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lint_results_created
            ON lint_results(created_at DESC)
        """
        )
        logger.info("✓ Created lint_results indexes")

        logger.info("Migration 006: Creating composite index on context_items")
        try:
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_context_project_agent
                ON context_items(project_id, agent_id, current_tier)
                """
            )
            logger.info("✓ Created composite index idx_context_project_agent")
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                logger.warning(
                    "⚠ context_items table does not exist, skipping composite index creation"
                )
            else:
                raise

        logger.info("Migration 006: Creating partial index on tasks.commit_sha")
        try:
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_commit_sha
                ON tasks(commit_sha)
                WHERE commit_sha IS NOT NULL
                """
            )
            logger.info("✓ Created partial index on tasks.commit_sha")
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "no such table" in error_msg:
                logger.warning("⚠ tasks table does not exist, skipping partial index creation")
            elif "no such column" in error_msg:
                logger.warning(
                    "⚠ commit_sha column does not exist, skipping partial index creation"
                )
            else:
                raise

        conn.commit()
        logger.info("Migration 006 completed successfully")

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration."""
        cursor = conn.cursor()

        logger.info("Migration 006: Rolling back changes")

        # Drop indexes
        cursor.execute("DROP INDEX IF EXISTS idx_context_project_agent")
        cursor.execute("DROP INDEX IF EXISTS idx_lint_results_task")
        cursor.execute("DROP INDEX IF EXISTS idx_lint_results_created")
        cursor.execute("DROP INDEX IF EXISTS idx_tasks_commit_sha")
        logger.info("✓ Dropped indexes")

        # Drop lint_results table
        cursor.execute("DROP TABLE IF EXISTS lint_results")
        logger.info("✓ Dropped lint_results table")

        # Cannot drop column in SQLite (requires table recreation)
        logger.warning(
            "⚠ Cannot drop commit_sha column from tasks table (SQLite limitation). "
            "Column will remain but be unused."
        )

        conn.commit()
        logger.info("Migration 006 rollback completed")


# Migration instance for auto-discovery
migration = MVPCompletion()
