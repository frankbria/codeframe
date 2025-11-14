"""Unit tests for ContextManager (T036).

Tests the ContextManager class methods:
- recalculate_scores_for_agent()

Part of 007-context-management Phase 4 (US2 - Importance Scoring).
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, UTC

from codeframe.persistence.database import Database
from codeframe.lib.context_manager import ContextManager
from codeframe.core.models import ContextItemType


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
def context_manager(temp_db):
    """Create context manager with test database."""
    return ContextManager(db=temp_db)


class TestContextManager:
    """Unit tests for ContextManager class."""

    def test_recalculate_scores_updates_all_items(self, temp_db, context_manager):
        """Test that recalculate_scores_for_agent updates all agent items."""
        agent_id = "test-agent-001"

        # Create 3 context items
        item_ids = []
        for i in range(3):
            item_id = temp_db.create_context_item(
                agent_id=agent_id,
                item_type=ContextItemType.TASK.value,
                content=f"Task {i}"
            )
            item_ids.append(item_id)

        # Get initial scores
        initial_scores = []
        for item_id in item_ids:
            item = temp_db.get_context_item(item_id)
            initial_scores.append(item['importance_score'])

        # Age one item to make score change detectable
        cursor = temp_db.conn.cursor()
        one_day_ago = datetime.now(UTC) - timedelta(days=1)
        cursor.execute(
            "UPDATE context_items SET created_at = ? WHERE id = ?",
            (one_day_ago.isoformat(), item_ids[0])
        )
        temp_db.conn.commit()

        # ACT: Recalculate scores
        updated_count = context_manager.recalculate_scores_for_agent(agent_id)

        # ASSERT: All 3 items updated
        assert updated_count == 3

        # Verify at least one score changed (the aged item)
        item_0_after = temp_db.get_context_item(item_ids[0])
        assert item_0_after['importance_score'] < initial_scores[0]

    def test_recalculate_scores_returns_count(self, temp_db, context_manager):
        """Test that recalculate_scores_for_agent returns correct count."""
        agent_id = "test-agent-002"

        # Create 5 items
        for i in range(5):
            temp_db.create_context_item(
                agent_id=agent_id,
                item_type=ContextItemType.CODE.value,
                content=f"def function_{i}(): pass"
            )

        # ACT: Recalculate
        updated_count = context_manager.recalculate_scores_for_agent(agent_id)

        # ASSERT: Returns count of 5
        assert updated_count == 5

    def test_recalculate_scores_with_empty_agent(self, context_manager):
        """Test recalculation with agent that has no context items."""
        agent_id = "nonexistent-agent"

        # ACT: Recalculate for empty agent
        updated_count = context_manager.recalculate_scores_for_agent(agent_id)

        # ASSERT: Returns 0
        assert updated_count == 0

    def test_recalculate_scores_only_affects_target_agent(self, temp_db, context_manager):
        """Test that recalculation only updates items for specified agent."""
        agent_1 = "agent-001"
        agent_2 = "agent-002"

        # Create items for both agents
        agent_1_item_id = temp_db.create_context_item(
            agent_id=agent_1,
            item_type=ContextItemType.TASK.value,
            content="Agent 1 task"
        )
        agent_2_item_id = temp_db.create_context_item(
            agent_id=agent_2,
            item_type=ContextItemType.TASK.value,
            content="Agent 2 task"
        )

        # Get initial scores
        agent_1_before = temp_db.get_context_item(agent_1_item_id)
        agent_2_before = temp_db.get_context_item(agent_2_item_id)

        # Age agent_1's item
        cursor = temp_db.conn.cursor()
        one_day_ago = datetime.now(UTC) - timedelta(days=1)
        cursor.execute(
            "UPDATE context_items SET created_at = ? WHERE id = ?",
            (one_day_ago.isoformat(), agent_1_item_id)
        )
        temp_db.conn.commit()

        # ACT: Recalculate only for agent_1
        updated_count = context_manager.recalculate_scores_for_agent(agent_1)

        # ASSERT: Only 1 item updated
        assert updated_count == 1

        # Agent 1's score changed
        agent_1_after = temp_db.get_context_item(agent_1_item_id)
        assert agent_1_after['importance_score'] < agent_1_before['importance_score']

        # Agent 2's score unchanged
        agent_2_after = temp_db.get_context_item(agent_2_item_id)
        assert agent_2_after['importance_score'] == agent_2_before['importance_score']

    def test_context_manager_initialization(self, temp_db):
        """Test ContextManager initialization."""
        # ACT
        manager = ContextManager(db=temp_db)

        # ASSERT
        assert manager.db is temp_db
