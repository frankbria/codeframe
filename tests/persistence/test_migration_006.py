"""
Unit tests for migration_006_mvp_completion.

Tests cover:
- T150: Migration upgrade
- T151: Migration downgrade
- T152: Migration idempotency
"""

import pytest
import sqlite3

from codeframe.persistence.migrations.archive.migration_006_mvp_completion import MVPCompletion


class TestMigration006Upgrade:
    """T150: Unit test for migration_006 upgrade"""

    def test_creates_lint_results_table(self, fresh_db):
        """Should create lint_results table with correct schema"""
        migration = MVPCompletion()

        # Verify table doesn't exist
        cursor = fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lint_results'"
        )
        assert cursor.fetchone() is None

        # Apply migration
        migration.apply(fresh_db)

        # Verify table exists
        cursor = fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lint_results'"
        )
        assert cursor.fetchone() is not None

        # Verify schema
        cursor = fresh_db.execute("PRAGMA table_info(lint_results)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert "id" in columns
        assert "task_id" in columns
        assert "linter" in columns
        assert "error_count" in columns
        assert "warning_count" in columns
        assert "files_linted" in columns
        assert "output" in columns
        assert "created_at" in columns

    def test_adds_commit_sha_to_tasks(self, fresh_db_with_tasks):
        """Should add commit_sha column to tasks table"""
        migration = MVPCompletion()

        # Verify column doesn't exist initially
        cursor = fresh_db_with_tasks.execute("PRAGMA table_info(tasks)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "commit_sha" not in columns

        # Apply migration
        migration.apply(fresh_db_with_tasks)

        # Verify column exists
        cursor = fresh_db_with_tasks.execute("PRAGMA table_info(tasks)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert "commit_sha" in columns
        assert columns["commit_sha"] == "TEXT"

    def test_creates_composite_index_on_context_items(self, fresh_db_with_context):
        """Should create composite index idx_context_project_agent"""
        migration = MVPCompletion()

        # Apply migration
        migration.apply(fresh_db_with_context)

        # Verify index exists
        cursor = fresh_db_with_context.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_context_project_agent'
            """
        )
        assert cursor.fetchone() is not None

        # Verify index is on correct columns
        cursor = fresh_db_with_context.execute(
            "SELECT sql FROM sqlite_master WHERE name='idx_context_project_agent'"
        )
        sql = cursor.fetchone()[0]
        assert "project_id" in sql.lower()
        assert "agent_id" in sql.lower()
        assert "current_tier" in sql.lower()

    def test_creates_lint_results_indexes(self, fresh_db):
        """Should create indexes on lint_results table"""
        migration = MVPCompletion()
        migration.apply(fresh_db)

        # Verify idx_lint_results_task exists
        cursor = fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_lint_results_task'"
        )
        assert cursor.fetchone() is not None

        # Verify idx_lint_results_created exists
        cursor = fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_lint_results_created'"
        )
        assert cursor.fetchone() is not None

    def test_creates_partial_index_on_commit_sha(self, fresh_db_with_tasks):
        """Should create partial index on tasks.commit_sha"""
        migration = MVPCompletion()
        migration.apply(fresh_db_with_tasks)

        # Verify index exists
        cursor = fresh_db_with_tasks.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_commit_sha'"
        )
        assert cursor.fetchone() is not None

        # Verify it's a partial index (WHERE clause)
        cursor = fresh_db_with_tasks.execute(
            "SELECT sql FROM sqlite_master WHERE name='idx_tasks_commit_sha'"
        )
        sql = cursor.fetchone()[0]
        assert "WHERE" in sql.upper()
        assert "IS NOT NULL" in sql.upper()


class TestMigration006Downgrade:
    """T151: Unit test for migration_006 downgrade"""

    def test_drops_lint_results_table(self, migrated_db):
        """Should drop lint_results table"""
        migration = MVPCompletion()

        # Verify table exists
        cursor = migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lint_results'"
        )
        assert cursor.fetchone() is not None

        # Rollback migration
        migration.rollback(migrated_db)

        # Verify table is dropped
        cursor = migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lint_results'"
        )
        assert cursor.fetchone() is None

    def test_drops_composite_index(self, migrated_db):
        """Should drop idx_context_project_agent index"""
        migration = MVPCompletion()

        # Verify index exists
        cursor = migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_context_project_agent'"
        )
        assert cursor.fetchone() is not None

        # Rollback migration
        migration.rollback(migrated_db)

        # Verify index is dropped
        cursor = migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_context_project_agent'"
        )
        assert cursor.fetchone() is None

    def test_drops_lint_results_indexes(self, migrated_db):
        """Should drop lint_results indexes"""
        migration = MVPCompletion()
        migration.rollback(migrated_db)

        # Verify idx_lint_results_task is dropped
        cursor = migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_lint_results_task'"
        )
        assert cursor.fetchone() is None

        # Verify idx_lint_results_created is dropped
        cursor = migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_lint_results_created'"
        )
        assert cursor.fetchone() is None

    def test_drops_partial_index_on_commit_sha(self, migrated_db):
        """Should drop partial index on tasks.commit_sha"""
        migration = MVPCompletion()
        migration.rollback(migrated_db)

        # Verify index is dropped
        cursor = migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_commit_sha'"
        )
        assert cursor.fetchone() is None


class TestMigration006Idempotency:
    """T152: Unit test for migration_006 idempotency"""

    def test_can_run_upgrade_twice_safely(self, fresh_db):
        """Should be safe to run migration twice (idempotent)"""
        migration = MVPCompletion()

        # Apply migration first time
        migration.apply(fresh_db)

        # Apply migration second time (should not raise error)
        migration.apply(fresh_db)

        # Verify table still exists
        cursor = fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lint_results'"
        )
        assert cursor.fetchone() is not None

    def test_can_run_downgrade_on_non_migrated_db(self, fresh_db):
        """Should be safe to run rollback on fresh database"""
        migration = MVPCompletion()

        # Run rollback on fresh db (should not raise error)
        migration.rollback(fresh_db)

        # Database should still be valid
        cursor = fresh_db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        assert len(tables) >= 0  # Should not crash


# Fixtures


@pytest.fixture
def fresh_db():
    """Create a fresh in-memory database"""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def fresh_db_with_tasks():
    """Create a fresh database with tasks table"""
    conn = sqlite3.connect(":memory:")

    # Create minimal tasks table
    conn.execute(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            description TEXT NOT NULL
        )
    """
    )

    yield conn
    conn.close()


@pytest.fixture
def fresh_db_with_context():
    """Create a fresh database with context_items table"""
    conn = sqlite3.connect(":memory:")

    # Create minimal context_items table
    conn.execute(
        """
        CREATE TABLE context_items (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            agent_id TEXT NOT NULL,
            current_tier TEXT NOT NULL
        )
    """
    )

    yield conn
    conn.close()


@pytest.fixture
def migrated_db():
    """Create a database with migration_006 already applied"""
    conn = sqlite3.connect(":memory:")

    # Create base tables
    conn.execute(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            description TEXT NOT NULL
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE context_items (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            agent_id TEXT NOT NULL,
            current_tier TEXT NOT NULL
        )
    """
    )

    # Apply migration
    migration = MVPCompletion()
    migration.apply(conn)

    yield conn
    conn.close()
