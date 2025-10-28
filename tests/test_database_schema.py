"""Tests for database schema changes (project refactoring)."""
import pytest
from pathlib import Path
from codeframe.persistence.database import Database


def test_projects_table_has_new_columns():
    """Verify projects table has new schema columns."""
    db_path = ":memory:"
    db = Database(db_path)
    db.initialize()

    # Get table schema
    cursor = db.conn.cursor()
    cursor.execute("PRAGMA table_info(projects)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    # Verify new columns exist
    assert "description" in columns, "Missing description column"
    assert "source_type" in columns, "Missing source_type column"
    assert "source_location" in columns, "Missing source_location column"
    assert "source_branch" in columns, "Missing source_branch column"
    assert "workspace_path" in columns, "Missing workspace_path column"
    assert "git_initialized" in columns, "Missing git_initialized column"
    assert "current_commit" in columns, "Missing current_commit column"

    # Verify old columns removed
    assert "root_path" not in columns, "root_path should be removed"


def test_source_type_check_constraint():
    """Verify source_type has CHECK constraint."""
    db_path = ":memory:"
    db = Database(db_path)
    db.initialize()

    # Try to insert invalid source_type
    cursor = db.conn.cursor()
    with pytest.raises(Exception) as exc_info:
        cursor.execute("""
            INSERT INTO projects (name, description, source_type, workspace_path)
            VALUES ('test', 'desc', 'invalid_type', '/tmp/test')
        """)
        db.conn.commit()

    assert "CHECK constraint failed" in str(exc_info.value)


def test_description_not_null():
    """Verify description is required (NOT NULL)."""
    db_path = ":memory:"
    db = Database(db_path)
    db.initialize()

    cursor = db.conn.cursor()
    with pytest.raises(Exception) as exc_info:
        cursor.execute("""
            INSERT INTO projects (name, workspace_path)
            VALUES ('test', '/tmp/test')
        """)
        db.conn.commit()

    assert "NOT NULL constraint failed" in str(exc_info.value)
