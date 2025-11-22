"""Migration 007: Sprint 10 Review & Polish

Changes:
1. Create code_reviews table for Review Agent findings
2. Create token_usage table for cost tracking
3. Add quality gate columns to tasks table (quality_gate_status, quality_gate_failures, requires_human_approval)
4. Add checkpoint metadata columns (name, description, database_backup_path, context_snapshot_path, metadata)
5. Create indexes for performance optimization

Date: 2025-11-21
Sprint: 015-review-polish
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class Sprint10ReviewPolish(Migration):
    """Add Sprint 10 Review & Polish features."""

    def __init__(self):
        super().__init__(version="007", description="Sprint 10 Review & Polish")

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if code_reviews table does not exist.
        """
        cursor = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='code_reviews'
            """
        )
        row = cursor.fetchone()

        if row:
            logger.info("code_reviews table already exists, skipping migration")
            return False

        logger.info("code_reviews table not found, migration can be applied")
        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration."""
        cursor = conn.cursor()

        # 1. Create code_reviews table
        logger.info("Migration 007: Creating code_reviews table")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                agent_id TEXT NOT NULL,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                file_path TEXT NOT NULL,
                line_number INTEGER,
                severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info')),
                category TEXT NOT NULL CHECK(category IN ('security', 'performance', 'quality', 'maintainability', 'style')),
                message TEXT NOT NULL,
                recommendation TEXT,
                code_snippet TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("✓ Created code_reviews table")

        # 2. Create code_reviews indexes
        logger.info("Migration 007: Creating indexes for code_reviews")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reviews_task
            ON code_reviews(task_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reviews_severity
            ON code_reviews(severity, created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reviews_project
            ON code_reviews(project_id, created_at)
        """)
        logger.info("✓ Created code_reviews indexes")

        # 3. Create token_usage table
        logger.info("Migration 007: Creating token_usage table")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                agent_id TEXT NOT NULL,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                model_name TEXT NOT NULL,
                input_tokens INTEGER NOT NULL CHECK(input_tokens >= 0),
                output_tokens INTEGER NOT NULL CHECK(output_tokens >= 0),
                estimated_cost_usd REAL NOT NULL CHECK(estimated_cost_usd >= 0),
                actual_cost_usd REAL CHECK(actual_cost_usd >= 0),
                call_type TEXT CHECK(call_type IN ('task_execution', 'code_review', 'coordination', 'other')),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("✓ Created token_usage table")

        # 4. Create token_usage indexes
        logger.info("Migration 007: Creating indexes for token_usage")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_token_usage_agent
            ON token_usage(agent_id, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_token_usage_project
            ON token_usage(project_id, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_token_usage_task
            ON token_usage(task_id)
        """)
        logger.info("✓ Created token_usage indexes")

        # 5. Add quality gate columns to tasks table
        logger.info("Migration 007: Adding quality gate columns to tasks table")

        # Check if columns already exist before adding
        cursor.execute("PRAGMA table_info(tasks)")
        columns = {row[1] for row in cursor.fetchall()}

        try:
            if 'quality_gate_status' not in columns:
                cursor.execute("""
                    ALTER TABLE tasks ADD COLUMN quality_gate_status TEXT
                    CHECK(quality_gate_status IN ('pending', 'running', 'passed', 'failed'))
                    DEFAULT 'pending'
                """)
                logger.info("✓ Added quality_gate_status column")
            else:
                logger.info("⊘ quality_gate_status column already exists, skipping")

            if 'quality_gate_failures' not in columns:
                cursor.execute("""
                    ALTER TABLE tasks ADD COLUMN quality_gate_failures JSON
                """)
                logger.info("✓ Added quality_gate_failures column")
            else:
                logger.info("⊘ quality_gate_failures column already exists, skipping")

            if 'requires_human_approval' not in columns:
                cursor.execute("""
                    ALTER TABLE tasks ADD COLUMN requires_human_approval BOOLEAN DEFAULT FALSE
                """)
                logger.info("✓ Added requires_human_approval column")
            else:
                logger.info("⊘ requires_human_approval column already exists, skipping")

        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                logger.warning("⚠ tasks table does not exist, skipping quality gate columns")
            else:
                raise

        # 6. Add checkpoint metadata columns
        logger.info("Migration 007: Adding checkpoint metadata columns")

        cursor.execute("PRAGMA table_info(checkpoints)")
        checkpoint_columns = {row[1] for row in cursor.fetchall()}

        try:
            if 'name' not in checkpoint_columns:
                cursor.execute("ALTER TABLE checkpoints ADD COLUMN name TEXT")
                logger.info("✓ Added name column to checkpoints")
            else:
                logger.info("⊘ name column already exists in checkpoints, skipping")

            if 'description' not in checkpoint_columns:
                cursor.execute("ALTER TABLE checkpoints ADD COLUMN description TEXT")
                logger.info("✓ Added description column to checkpoints")
            else:
                logger.info("⊘ description column already exists in checkpoints, skipping")

            if 'database_backup_path' not in checkpoint_columns:
                cursor.execute("ALTER TABLE checkpoints ADD COLUMN database_backup_path TEXT")
                logger.info("✓ Added database_backup_path column to checkpoints")
            else:
                logger.info("⊘ database_backup_path column already exists, skipping")

            if 'context_snapshot_path' not in checkpoint_columns:
                cursor.execute("ALTER TABLE checkpoints ADD COLUMN context_snapshot_path TEXT")
                logger.info("✓ Added context_snapshot_path column to checkpoints")
            else:
                logger.info("⊘ context_snapshot_path column already exists, skipping")

            if 'metadata' not in checkpoint_columns:
                cursor.execute("ALTER TABLE checkpoints ADD COLUMN metadata JSON")
                logger.info("✓ Added metadata column to checkpoints")
            else:
                logger.info("⊘ metadata column already exists in checkpoints, skipping")

        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                logger.warning("⚠ checkpoints table does not exist, skipping metadata columns")
            else:
                raise

        # 7. Create checkpoint index
        logger.info("Migration 007: Creating index for checkpoints")
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoints_project
                ON checkpoints(project_id, created_at DESC)
            """)
            logger.info("✓ Created checkpoints index")
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                logger.warning("⚠ checkpoints table does not exist, skipping index creation")
            else:
                raise

        conn.commit()
        logger.info("Migration 007 completed successfully")

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration."""
        cursor = conn.cursor()

        logger.info("Migration 007: Rolling back changes")

        # Drop indexes
        cursor.execute("DROP INDEX IF EXISTS idx_reviews_task")
        cursor.execute("DROP INDEX IF EXISTS idx_reviews_severity")
        cursor.execute("DROP INDEX IF EXISTS idx_reviews_project")
        cursor.execute("DROP INDEX IF EXISTS idx_token_usage_agent")
        cursor.execute("DROP INDEX IF EXISTS idx_token_usage_project")
        cursor.execute("DROP INDEX IF EXISTS idx_token_usage_task")
        cursor.execute("DROP INDEX IF EXISTS idx_checkpoints_project")
        logger.info("✓ Dropped indexes")

        # Drop tables
        cursor.execute("DROP TABLE IF EXISTS code_reviews")
        cursor.execute("DROP TABLE IF EXISTS token_usage")
        logger.info("✓ Dropped code_reviews and token_usage tables")

        # Cannot drop columns in SQLite (requires table recreation)
        logger.warning(
            "⚠ Cannot drop quality gate columns from tasks table (SQLite limitation). "
            "Columns will remain but be unused."
        )
        logger.warning(
            "⚠ Cannot drop metadata columns from checkpoints table (SQLite limitation). "
            "Columns will remain but be unused."
        )

        conn.commit()
        logger.info("Migration 007 rollback completed")


# Migration instance for auto-discovery
migration = Sprint10ReviewPolish()
