"""Migration 010: Add pause functionality support.

This migration adds pause/resume support by:

1. Adding paused_at TIMESTAMP column to projects table (tracks when project was paused)

This enables:
- Project.pause() to record pause timestamp
- Project.resume() to check if project was previously paused
- Dashboard to show pause duration

Migration: 010
Created: 2025-12-17
Sprint: Pause Functionality Phase 1
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class PauseFunctionality(Migration):
    """Add pause functionality support."""

    def __init__(self):
        super().__init__(
            version="010",
            description="Add pause functionality support",
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if paused_at column does not exist in projects table.
        """
        cursor = conn.cursor()

        # Check if paused_at column already exists
        cursor.execute("PRAGMA table_info(projects)")
        columns = [row[1] for row in cursor.fetchall()]

        if "paused_at" in columns:
            logger.info("paused_at column already exists, skipping migration")
            return False

        logger.info("paused_at column not found, migration can be applied")
        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        Adds paused_at TIMESTAMP column to projects table.
        """
        cursor = conn.cursor()

        logger.info("Migration 010: Adding paused_at to projects table")

        try:
            cursor.execute(
                """
                ALTER TABLE projects
                ADD COLUMN paused_at TIMESTAMP NULL
                """
            )
            logger.info("Added paused_at column to projects table")

        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("paused_at column already exists")
            else:
                raise

        conn.commit()
        logger.info("Migration 010 completed successfully")

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        Note: SQLite doesn't support DROP COLUMN easily, so this requires
        recreating the projects table without the paused_at column.
        """
        cursor = conn.cursor()

        logger.warning("Rolling back migration 010: Removing paused_at column")

        cursor.execute("PRAGMA foreign_keys = OFF")

        try:
            # Step 1: Create new projects table without paused_at
            cursor.execute(
                """
                CREATE TABLE projects_new (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source_type TEXT CHECK(source_type IN ('git_remote', 'local_path', 'upload', 'empty')) DEFAULT 'empty',
                    source_location TEXT,
                    source_branch TEXT DEFAULT 'main',
                    workspace_path TEXT NOT NULL,
                    git_initialized BOOLEAN DEFAULT FALSE,
                    current_commit TEXT,
                    status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
                    phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')) DEFAULT 'discovery',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    config JSON
                )
                """
            )
            logger.info("Created projects_new table without paused_at")

            # Step 2: Copy data (excluding paused_at column)
            cursor.execute(
                """
                INSERT INTO projects_new (
                    id, name, description, source_type, source_location, source_branch,
                    workspace_path, git_initialized, current_commit, status, phase,
                    created_at, config
                )
                SELECT
                    id, name, description, source_type, source_location, source_branch,
                    workspace_path, git_initialized, current_commit, status, phase,
                    created_at, config
                FROM projects
                """
            )
            logger.info("Copied data to projects_new")

            # Step 3: Drop old table and rename new one
            cursor.execute("DROP TABLE projects")
            cursor.execute("ALTER TABLE projects_new RENAME TO projects")
            logger.info("Replaced projects table")

        finally:
            cursor.execute("PRAGMA foreign_keys = ON")

        conn.commit()
        logger.info("Migration 010 rollback completed")


# Migration instance for auto-discovery
migration = PauseFunctionality()
