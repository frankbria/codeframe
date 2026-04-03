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
        """Simulate a pre-migration blocker row with no created_by value."""
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
