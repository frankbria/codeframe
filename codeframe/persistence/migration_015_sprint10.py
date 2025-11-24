"""Database migration for Sprint 10 (015-review-polish) features.

This migration adds:
- code_reviews table for Review Agent findings
- token_usage table for cost tracking
- Enhanced checkpoints table with metadata
- Quality gate columns on tasks table
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)


def upgrade(conn: sqlite3.Connection) -> None:
    """Apply Sprint 10 schema changes.

    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()

    # 1. Create code_reviews table
    logger.info("Creating code_reviews table...")
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

    # 2. Create code_reviews indexes
    logger.info("Creating indexes for code_reviews...")
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

    # 3. Create token_usage table
    logger.info("Creating token_usage table...")
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

    # 4. Create token_usage indexes
    logger.info("Creating indexes for token_usage...")
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

    # 5. Add quality gate columns to tasks table
    logger.info("Adding quality gate columns to tasks table...")

    # Check if columns already exist before adding
    cursor.execute("PRAGMA table_info(tasks)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'quality_gate_status' not in columns:
        cursor.execute("""
            ALTER TABLE tasks ADD COLUMN quality_gate_status TEXT
            CHECK(quality_gate_status IN ('pending', 'running', 'passed', 'failed'))
            DEFAULT 'pending'
        """)

    if 'quality_gate_failures' not in columns:
        cursor.execute("""
            ALTER TABLE tasks ADD COLUMN quality_gate_failures JSON
        """)

    if 'requires_human_approval' not in columns:
        cursor.execute("""
            ALTER TABLE tasks ADD COLUMN requires_human_approval BOOLEAN DEFAULT FALSE
        """)

    # 6. Add checkpoint metadata columns
    logger.info("Adding checkpoint metadata columns...")

    cursor.execute("PRAGMA table_info(checkpoints)")
    checkpoint_columns = {row[1] for row in cursor.fetchall()}

    if 'name' not in checkpoint_columns:
        cursor.execute("ALTER TABLE checkpoints ADD COLUMN name TEXT")

    if 'description' not in checkpoint_columns:
        cursor.execute("ALTER TABLE checkpoints ADD COLUMN description TEXT")

    if 'database_backup_path' not in checkpoint_columns:
        cursor.execute("ALTER TABLE checkpoints ADD COLUMN database_backup_path TEXT")

    if 'context_snapshot_path' not in checkpoint_columns:
        cursor.execute("ALTER TABLE checkpoints ADD COLUMN context_snapshot_path TEXT")

    if 'metadata' not in checkpoint_columns:
        cursor.execute("ALTER TABLE checkpoints ADD COLUMN metadata JSON")

    # 7. Create checkpoint index
    logger.info("Creating index for checkpoints...")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_checkpoints_project
        ON checkpoints(project_id, created_at DESC)
    """)

    conn.commit()
    logger.info("Sprint 10 migration completed successfully")


def downgrade(conn: sqlite3.Connection) -> None:
    """Rollback Sprint 10 schema changes.

    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()

    # Drop tables
    cursor.execute("DROP TABLE IF EXISTS code_reviews")
    cursor.execute("DROP TABLE IF EXISTS token_usage")

    # Note: SQLite doesn't support DROP COLUMN, so we can't cleanly remove
    # the quality gate columns from tasks table or checkpoint metadata columns
    # A full downgrade would require recreating the tables without those columns

    logger.warning("Sprint 10 downgrade: Dropped code_reviews and token_usage tables")
    logger.warning("Sprint 10 downgrade: Cannot remove columns from tasks and checkpoints (SQLite limitation)")

    conn.commit()
