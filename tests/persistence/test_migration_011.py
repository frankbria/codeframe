"""Tests for migration 011: created_at NOT NULL constraint."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from codeframe.persistence.migrations.migration_011_created_at_not_null import (
    CreatedAtNotNull,
)


@pytest.fixture
def db_path():
    """Create a temporary database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def conn(db_path):
    """Create a database connection with base schema."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create base schema (tasks and issues tables with NULL allowed)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE issues (
            id INTEGER PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id),
            issue_number TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT,
            priority INTEGER,
            workflow_step INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            UNIQUE(project_id, issue_number)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id),
            issue_id INTEGER REFERENCES issues(id),
            task_number TEXT,
            parent_issue_number TEXT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT,
            assigned_to TEXT,
            depends_on TEXT,
            can_parallelize BOOLEAN DEFAULT FALSE,
            priority INTEGER,
            workflow_step INTEGER,
            requires_mcp BOOLEAN DEFAULT FALSE,
            estimated_tokens INTEGER,
            actual_tokens INTEGER,
            commit_sha TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            quality_gate_status TEXT DEFAULT 'pending',
            quality_gate_failures JSON,
            requires_human_approval BOOLEAN DEFAULT FALSE
        )
        """
    )

    # Create migrations table
    cursor.execute(
        """
        CREATE TABLE migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    yield conn
    conn.close()


class TestMigration011CanApply:
    """Tests for can_apply method."""

    def test_can_apply_when_null_values_exist(self, conn):
        """Migration should apply when NULL created_at values exist."""
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO projects (id, name) VALUES (1, 'test')"
        )
        cursor.execute(
            """
            INSERT INTO tasks (id, project_id, title, created_at)
            VALUES (1, 1, 'Test Task', NULL)
            """
        )
        conn.commit()

        migration = CreatedAtNotNull()
        assert migration.can_apply(conn) is True

    def test_can_apply_when_null_allowed(self, conn):
        """Migration should apply when created_at allows NULL (no data)."""
        migration = CreatedAtNotNull()
        # Fresh table with no data but NULL constraint not set
        assert migration.can_apply(conn) is True

    def test_can_apply_false_after_migration(self, conn):
        """Migration should not apply if already applied."""
        migration = CreatedAtNotNull()
        migration.apply(conn)

        # After migration, NOT NULL constraint exists
        assert migration.can_apply(conn) is False


class TestMigration011Apply:
    """Tests for apply method."""

    def test_backfills_null_created_at_in_tasks(self, conn):
        """Migration should backfill NULL created_at values in tasks."""
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (id, name) VALUES (1, 'test')")
        cursor.execute(
            """
            INSERT INTO tasks (id, project_id, title, created_at)
            VALUES (1, 1, 'Task with NULL', NULL)
            """
        )
        cursor.execute(
            """
            INSERT INTO tasks (id, project_id, title, created_at)
            VALUES (2, 1, 'Task with value', '2025-01-01 00:00:00')
            """
        )
        conn.commit()

        migration = CreatedAtNotNull()
        migration.apply(conn)

        # Check that NULL was backfilled
        cursor.execute("SELECT id, created_at FROM tasks ORDER BY id")
        rows = cursor.fetchall()
        assert rows[0]["created_at"] is not None  # Was NULL, now backfilled
        assert rows[1]["created_at"] == "2025-01-01 00:00:00"  # Unchanged

    def test_backfills_null_created_at_in_issues(self, conn):
        """Migration should backfill NULL created_at values in issues."""
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (id, name) VALUES (1, 'test')")
        cursor.execute(
            """
            INSERT INTO issues (id, project_id, issue_number, title, created_at)
            VALUES (1, 1, '1.0', 'Issue with NULL', NULL)
            """
        )
        conn.commit()

        migration = CreatedAtNotNull()
        migration.apply(conn)

        cursor.execute("SELECT created_at FROM issues WHERE id = 1")
        row = cursor.fetchone()
        assert row["created_at"] is not None

    def test_adds_not_null_constraint_to_tasks(self, conn):
        """Migration should add NOT NULL constraint to tasks.created_at."""
        migration = CreatedAtNotNull()
        migration.apply(conn)

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(tasks)")
        for row in cursor.fetchall():
            if row[1] == "created_at":
                assert row[3] == 1, "created_at should have NOT NULL constraint"
                return

        pytest.fail("created_at column not found in tasks table")

    def test_adds_not_null_constraint_to_issues(self, conn):
        """Migration should add NOT NULL constraint to issues.created_at."""
        migration = CreatedAtNotNull()
        migration.apply(conn)

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(issues)")
        for row in cursor.fetchall():
            if row[1] == "created_at":
                assert row[3] == 1, "created_at should have NOT NULL constraint"
                return

        pytest.fail("created_at column not found in issues table")

    def test_creates_backup_tables(self, conn):
        """Migration should retain old tables as backups."""
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (id, name) VALUES (1, 'test')")
        cursor.execute(
            """
            INSERT INTO tasks (id, project_id, title)
            VALUES (1, 1, 'Test Task')
            """
        )
        conn.commit()

        migration = CreatedAtNotNull()
        migration.apply(conn)

        # Check that backup tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks_backup_011'"
        )
        assert cursor.fetchone() is not None, "tasks_backup_011 should exist"

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='issues_backup_011'"
        )
        assert cursor.fetchone() is not None, "issues_backup_011 should exist"

    def test_preserves_existing_data(self, conn):
        """Migration should preserve all existing task data."""
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (id, name) VALUES (1, 'test')")
        cursor.execute(
            "INSERT INTO issues (id, project_id, issue_number, title) VALUES (1, 1, '1.0', 'Issue')"
        )
        cursor.execute(
            """
            INSERT INTO tasks (id, project_id, issue_id, task_number, title, status, priority)
            VALUES (1, 1, 1, '1.0.1', 'Test Task', 'pending', 2)
            """
        )
        conn.commit()

        migration = CreatedAtNotNull()
        migration.apply(conn)

        cursor.execute("SELECT * FROM tasks WHERE id = 1")
        row = cursor.fetchone()
        assert row["task_number"] == "1.0.1"
        assert row["title"] == "Test Task"
        assert row["status"] == "pending"
        assert row["priority"] == 2


class TestMigration011Rollback:
    """Tests for rollback method."""

    def test_rollback_restores_from_backup(self, conn):
        """Rollback should restore from backup tables."""
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (id, name) VALUES (1, 'test')")
        cursor.execute(
            """
            INSERT INTO tasks (id, project_id, title, created_at)
            VALUES (1, 1, 'Test Task', NULL)
            """
        )
        conn.commit()

        migration = CreatedAtNotNull()
        migration.apply(conn)

        # Verify backup exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks_backup_011'"
        )
        assert cursor.fetchone() is not None

        # Rollback
        migration.rollback(conn)

        # Backup should be gone (restored)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks_backup_011'"
        )
        assert cursor.fetchone() is None

        # Original data should be preserved
        cursor.execute("SELECT title FROM tasks WHERE id = 1")
        row = cursor.fetchone()
        assert row["title"] == "Test Task"

    def test_rollback_removes_not_null_constraint(self, conn):
        """Rollback should remove NOT NULL constraint."""
        migration = CreatedAtNotNull()
        migration.apply(conn)
        migration.rollback(conn)

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(tasks)")
        for row in cursor.fetchall():
            if row[1] == "created_at":
                assert row[3] == 0, "created_at should allow NULL after rollback"
                return


class TestMigration011CleanupBackups:
    """Tests for cleanup_backups static method."""

    def test_cleanup_removes_backup_tables(self, conn):
        """cleanup_backups should remove backup tables."""
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (id, name) VALUES (1, 'test')")
        conn.commit()

        migration = CreatedAtNotNull()
        migration.apply(conn)

        # Verify backups exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_backup_011'"
        )
        backups = cursor.fetchall()
        assert len(backups) == 2

        # Cleanup
        CreatedAtNotNull.cleanup_backups(conn)

        # Verify backups removed
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_backup_011'"
        )
        backups = cursor.fetchall()
        assert len(backups) == 0

    def test_cleanup_is_safe_when_no_backups(self, conn):
        """cleanup_backups should not fail if backups don't exist."""
        # Just call cleanup without applying migration
        CreatedAtNotNull.cleanup_backups(conn)  # Should not raise


class TestMigration011Integration:
    """Integration tests for full migration cycle."""

    def test_full_migration_cycle(self, conn):
        """Test apply -> rollback -> apply cycle."""
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (id, name) VALUES (1, 'test')")
        cursor.execute(
            """
            INSERT INTO tasks (id, project_id, title, created_at)
            VALUES (1, 1, 'Test Task', NULL)
            """
        )
        conn.commit()

        migration = CreatedAtNotNull()

        # Apply
        migration.apply(conn)
        cursor.execute("SELECT created_at FROM tasks WHERE id = 1")
        assert cursor.fetchone()["created_at"] is not None

        # Rollback
        migration.rollback(conn)

        # Apply again (backups are gone, so full recreation path)
        migration.apply(conn)
        cursor.execute("SELECT created_at FROM tasks WHERE id = 1")
        assert cursor.fetchone()["created_at"] is not None

    def test_migration_metadata(self, db_path):
        """Test migration has correct metadata."""
        migration = CreatedAtNotNull()
        assert migration.version == "011"
        assert "created_at" in migration.description.lower()
        assert "NOT NULL" in migration.description.upper()
