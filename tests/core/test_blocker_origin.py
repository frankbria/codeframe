"""Tests for blocker origin (created_by) field — issue #487."""

import pytest
from pathlib import Path

from codeframe.core.workspace import create_or_load_workspace
from codeframe.core import blockers
from codeframe.core.blockers import BlockerOrigin

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


class TestBlockerOriginEnum:
    def test_valid_values(self):
        assert BlockerOrigin.SYSTEM == "system"
        assert BlockerOrigin.AGENT == "agent"
        assert BlockerOrigin.HUMAN == "human"


class TestBlockerCreate:
    def test_invalid_origin_raises_value_error(self, workspace):
        with pytest.raises(ValueError):
            blockers.create(workspace, "A question?", created_by="invalid")

    def test_default_origin_is_human(self, workspace):
        b = blockers.create(workspace, "A question?")
        assert b.created_by == BlockerOrigin.HUMAN

    def test_agent_origin(self, workspace):
        b = blockers.create(workspace, "Agent question?", created_by="agent")
        assert b.created_by == BlockerOrigin.AGENT

    def test_system_origin(self, workspace):
        b = blockers.create(workspace, "Stall detected", created_by="system")
        assert b.created_by == BlockerOrigin.SYSTEM

    def test_origin_persisted_and_retrieved(self, workspace):
        created = blockers.create(workspace, "Test?", created_by="agent")
        fetched = blockers.get(workspace, created.id)
        assert fetched is not None
        assert fetched.created_by == BlockerOrigin.AGENT


class TestBlockerListIncludesOrigin:
    def test_list_all_includes_created_by(self, workspace):
        blockers.create(workspace, "Q1", created_by="human")
        blockers.create(workspace, "Q2", created_by="agent")
        result = blockers.list_all(workspace)
        assert len(result) == 2
        origins = {b.created_by for b in result}
        assert BlockerOrigin.HUMAN in origins
        assert BlockerOrigin.AGENT in origins


class TestExistingBlockersMigration:
    def test_blockers_without_created_by_default_to_human(self, workspace):
        """COALESCE fallback: rows inserted without created_by read back as HUMAN."""
        from codeframe.core.workspace import get_db_connection
        import uuid
        from datetime import datetime, timezone

        conn = get_db_connection(workspace)
        old_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO blockers (id, workspace_id, task_id, question, status, created_at)
            VALUES (?, ?, NULL, ?, 'OPEN', ?)
            """,
            (old_id, workspace.id, "Old question?", now),
        )
        conn.commit()
        conn.close()

        fetched = blockers.get(workspace, old_id)
        assert fetched is not None
        assert fetched.created_by == BlockerOrigin.HUMAN

    def test_alter_table_migration_adds_created_by_column(self, tmp_path: Path):
        """ALTER TABLE migration: initializing a DB without created_by column adds it."""
        import sqlite3
        from codeframe.core.workspace import _init_database, CODEFRAME_DIR, STATE_DB_NAME

        # Create a DB with the old blockers schema (no created_by column)
        repo = tmp_path / "old-repo"
        repo.mkdir()
        codeframe_dir = repo / CODEFRAME_DIR
        codeframe_dir.mkdir()
        db_path = codeframe_dir / STATE_DB_NAME

        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blockers (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                task_id TEXT,
                question TEXT NOT NULL,
                answer TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                created_at TEXT NOT NULL,
                answered_at TEXT
            )
        """)
        conn.commit()
        conn.close()

        # Confirm column is absent before migration
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(blockers)")
        columns_before = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert "created_by" not in columns_before

        # Run the full init (triggers the ALTER TABLE migration)
        _init_database(db_path)

        # Confirm column is present after migration
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(blockers)")
        columns_after = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert "created_by" in columns_after
