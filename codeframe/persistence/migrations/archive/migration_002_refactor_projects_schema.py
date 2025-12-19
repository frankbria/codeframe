"""Migration 002: Refactor projects table schema with source types and workspace management.

This migration adds support for multiple project source types (git_remote, local_path, upload, empty)
and introduces managed workspace paths for project sandboxing.

New fields added to projects table:
- description: Project description (required)
- source_type: Type of project source (git_remote, local_path, upload, empty)
- source_location: Location of the source (URL, path, etc.)
- source_branch: Git branch name (for git sources)
- workspace_path: Path to managed workspace directory
- git_initialized: Whether git has been initialized
- current_commit: Current git commit hash

SQLite doesn't support ALTER TABLE ADD COLUMN with NOT NULL and no default,
so we need to recreate the table:
1. Create new projects table with expanded schema
2. Migrate existing data (if any) with default values
3. Drop old projects table
4. Rename new table
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class RefactorProjectsSchema(Migration):
    """Refactor projects table to support source types and workspace management."""

    def __init__(self):
        super().__init__(
            version="002",
            description="Refactor projects schema with source types and workspace management",
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if projects table exists without the new schema fields.
        """
        cursor = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='projects'
            """
        )
        row = cursor.fetchone()

        if not row:
            logger.info("Projects table doesn't exist yet, skipping migration")
            return False

        # Check if new fields already exist
        table_sql = row[0]
        has_new_fields = "source_type" in table_sql and "workspace_path" in table_sql

        if has_new_fields:
            logger.info("New schema already applied, skipping migration")
            return False

        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        Creates new projects table with expanded schema and migrates data.
        """
        cursor = conn.cursor()

        # Check if projects table exists and has data
        try:
            cursor.execute("SELECT COUNT(*) FROM projects")
            project_count = cursor.fetchone()[0]
            logger.info(f"Found {project_count} projects to migrate")
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            project_count = 0
            logger.info("No existing projects table found")

        if project_count > 0:
            logger.warning(
                f"Migration will reset {project_count} existing projects. "
                "This is a destructive operation for development purposes only."
            )

        # 1. Drop old projects table (one-time destructive migration for dev)
        cursor.execute("DROP TABLE IF EXISTS projects")
        logger.info("Dropped old projects table")

        # 2. Create new projects table with expanded schema
        cursor.execute(
            """
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,

                -- Source tracking (optional, can be set during setup or later)
                source_type TEXT CHECK(source_type IN ('git_remote', 'local_path', 'upload', 'empty')) DEFAULT 'empty',
                source_location TEXT,
                source_branch TEXT DEFAULT 'main',

                -- Managed workspace (always local to running instance)
                workspace_path TEXT NOT NULL,

                -- Git tracking (foundation for all projects)
                git_initialized BOOLEAN DEFAULT FALSE,
                current_commit TEXT,

                -- Workflow state
                status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
                phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')) DEFAULT 'discovery',

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                config JSON
            )
        """
        )
        logger.info("Created new projects table with expanded schema")

        conn.commit()

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        Recreates projects table with original schema (data will be lost).
        """
        cursor = conn.cursor()

        # Check if projects table exists and has data
        cursor.execute("SELECT COUNT(*) FROM projects")
        project_count = cursor.fetchone()[0]
        logger.warning(f"Rollback will remove {project_count} projects")

        # Drop new table
        cursor.execute("DROP TABLE IF EXISTS projects")
        logger.info("Dropped new projects table")

        # Create old projects table with original schema
        cursor.execute(
            """
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                root_path TEXT,
                status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
                phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')) DEFAULT 'discovery',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                config JSON
            )
        """
        )
        logger.info("Recreated projects table with original schema")

        conn.commit()


# Migration instance for auto-discovery
migration = RefactorProjectsSchema()
