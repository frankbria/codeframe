"""Unit tests for checkpoint creation and retrieval (T049).

Tests the checkpoint functionality:
- Creating checkpoints with JSON data
- Listing checkpoints for an agent
- Checkpoint metadata (items_count, token_count, etc.)

Part of 007-context-management Phase 6 (US4 - Flash Save).
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, UTC

from codeframe.persistence.database import Database


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = Database(db_path)
    db.initialize()

    yield db

    db.close()
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def test_project(temp_db):
    """Create a test project for context items."""
    project_id = temp_db.create_project(
        name="test-project",
        description="Test project for checkpoint restore",
        workspace_path=""
    )
    return project_id


class TestCheckpointRestore:
    """Unit tests for checkpoint creation and retrieval."""

    def test_create_checkpoint_with_data(self, temp_db, test_project):
        """Test that checkpoint stores JSON state correctly."""
        agent_id = "test-agent-checkpoint-001"

        # Create checkpoint data (JSON-serializable state)
        checkpoint_data = {
            "context_items": [
                {"id": 1, "content": "Task 1", "tier": "HOT"},
                {"id": 2, "content": "Task 2", "tier": "WARM"},
                {"id": 3, "content": "Task 3", "tier": "COLD"}
            ],
            "metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "reason": "flash_save_triggered"
            }
        }

        # ACT: Create checkpoint
        checkpoint_id = temp_db.create_checkpoint(
            agent_id=agent_id,
            checkpoint_data=json.dumps(checkpoint_data),
            items_count=10,
            items_archived=5,
            hot_items_retained=3,
            token_count=5000
        )

        # ASSERT: Checkpoint created
        assert checkpoint_id > 0

        # Retrieve and verify checkpoint
        checkpoint = temp_db.get_checkpoint(checkpoint_id)
        assert checkpoint is not None
        assert checkpoint["agent_id"] == agent_id

        # Verify JSON data can be deserialized
        retrieved_data = json.loads(checkpoint["checkpoint_data"])
        assert "context_items" in retrieved_data
        assert len(retrieved_data["context_items"]) == 3
        assert retrieved_data["metadata"]["reason"] == "flash_save_triggered"

    def test_list_checkpoints_for_agent(self, temp_db, test_project):
        """Test that pagination works for listing checkpoints."""
        agent_id = "test-agent-checkpoint-002"

        # Create multiple checkpoints
        checkpoint_ids = []
        for i in range(15):
            checkpoint_data = {
                "checkpoint_number": i,
                "items": []
            }

            checkpoint_id = temp_db.create_checkpoint(
                agent_id=agent_id,
                checkpoint_data=json.dumps(checkpoint_data),
                items_count=10 + i,
                items_archived=5 + i,
                hot_items_retained=3,
                token_count=5000 + (i * 100)
            )
            checkpoint_ids.append(checkpoint_id)

        # ACT: List checkpoints with default limit (10)
        checkpoints_page1 = temp_db.list_checkpoints(agent_id, limit=10)

        # ASSERT: Returns first 10 checkpoints (most recent first)
        assert len(checkpoints_page1) == 10

        # ACT: List with limit=5
        checkpoints_page2 = temp_db.list_checkpoints(agent_id, limit=5)

        # ASSERT: Returns 5 most recent
        assert len(checkpoints_page2) == 5

        # Verify all returned checkpoints belong to this agent
        assert all(cp["agent_id"] == agent_id for cp in checkpoints_page2)

        # Verify IDs are from our created set
        returned_ids = [cp["id"] for cp in checkpoints_page2]
        assert all(cid in checkpoint_ids for cid in returned_ids)

    def test_checkpoint_includes_metrics(self, temp_db, test_project):
        """Test that checkpoint includes metrics (items_count, token_count, etc.)."""
        agent_id = "test-agent-checkpoint-003"

        # Create checkpoint with specific metrics
        checkpoint_data = {"state": "saved"}
        checkpoint_id = temp_db.create_checkpoint(
            agent_id=agent_id,
            checkpoint_data=json.dumps(checkpoint_data),
            items_count=50,
            items_archived=20,
            hot_items_retained=15,
            token_count=12000
        )

        # ACT: Retrieve checkpoint
        checkpoint = temp_db.get_checkpoint(checkpoint_id)

        # ASSERT: Metrics are present
        assert checkpoint["items_count"] == 50
        assert checkpoint["items_archived"] == 20
        assert checkpoint["hot_items_retained"] == 15
        assert checkpoint["token_count"] == 12000

        # Verify created_at timestamp exists
        assert "created_at" in checkpoint
        assert checkpoint["created_at"] is not None

    def test_list_checkpoints_for_nonexistent_agent(self, temp_db):
        """Test listing checkpoints for agent with no checkpoints."""
        agent_id = "nonexistent-agent"

        # ACT: List checkpoints
        checkpoints = temp_db.list_checkpoints(agent_id, limit=10)

        # ASSERT: Returns empty list
        assert checkpoints == []
        assert len(checkpoints) == 0

    def test_get_nonexistent_checkpoint(self, temp_db):
        """Test retrieving checkpoint that doesn't exist."""
        # ACT: Get checkpoint with invalid ID
        checkpoint = temp_db.get_checkpoint(999999)

        # ASSERT: Returns None
        assert checkpoint is None
