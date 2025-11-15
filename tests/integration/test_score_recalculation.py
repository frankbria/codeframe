"""Integration test for score recalculation (T035).

Tests the end-to-end workflow:
1. Create context item with initial score
2. Mock time passage (make item old)
3. Trigger score recalculation
4. Verify score decreased due to age decay

Part of 007-context-management Phase 4 (US2 - Importance Scoring).
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, UTC
from unittest.mock import patch

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
def test_project(temp_db):
    """Create a test project for context items."""
    project_id = temp_db.create_project(
        name="test-project",
        description="Test project for context management",
        workspace_path=""
    )
    return project_id


@pytest.fixture
def context_manager(temp_db, test_project):
    """Create context manager with test database."""
    return ContextManager(db=temp_db)


class TestScoreRecalculationIntegration:
    """Integration tests for score recalculation workflow."""

    def test_score_recalculation_with_aged_item(self, temp_db, test_project, context_manager):
        """Test that score decreases when item ages.

        Workflow:
        1. Create item (gets fresh score based on current time)
        2. Manually set created_at to 7 days ago in database
        3. Trigger recalculation
        4. Verify score decreased due to age decay
        """
        agent_id = "test-agent-recalc-001"

        # STEP 1: Create a TASK item (high initial score)
        item_id = temp_db.create_context_item(project_id=test_project, agent_id=agent_id,
            item_type=ContextItemType.TASK.value,
            content="Implement user authentication"
        )

        # Get initial item
        item_before = temp_db.get_context_item(item_id)
        initial_score = item_before['importance_score']

        # Initial score should be high (TASK type=1.0, fresh age=1.0, no access=0.0)
        # Expected: 0.4 × 1.0 + 0.4 × 1.0 + 0.2 × 0.0 = 0.8
        assert initial_score >= 0.75

        # STEP 2: Mock item as created 7 days ago
        # Manually update created_at to simulate time passage
        seven_days_ago = datetime.now(UTC) - timedelta(days=7)
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "UPDATE context_items SET created_at = ? WHERE id = ?",
            (seven_days_ago.isoformat(), item_id)
        )
        temp_db.conn.commit()

        # STEP 3: Trigger score recalculation
        updated_count = context_manager.recalculate_scores_for_agent(test_project, agent_id)

        # ASSERT: Recalculation updated 1 item
        assert updated_count == 1

        # STEP 4: Verify score decreased
        item_after = temp_db.get_context_item(item_id)
        recalculated_score = item_after['importance_score']

        # Age decay for 7 days: e^(-0.5 × 7) = e^(-3.5) ≈ 0.03
        # Expected: 0.4 × 1.0 + 0.4 × 0.03 + 0.2 × 0.0 ≈ 0.41
        assert recalculated_score < initial_score  # Score decreased
        assert recalculated_score < 0.5  # Significantly decayed

    def test_score_recalculation_with_high_access_count(self, temp_db, test_project, context_manager):
        """Test that high access count boosts score even for older items."""
        agent_id = "test-agent-recalc-002"

        # Create item
        item_id = temp_db.create_context_item(project_id=test_project, agent_id=agent_id,
            item_type=ContextItemType.CODE.value,
            content="def authenticate_user(): ..."
        )

        # Simulate age (3 days old)
        three_days_ago = datetime.now(UTC) - timedelta(days=3)
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "UPDATE context_items SET created_at = ?, access_count = ? WHERE id = ?",
            (three_days_ago.isoformat(), 100, item_id)  # High access count
        )
        temp_db.conn.commit()

        # Get initial score (before recalculation)
        item_before = temp_db.get_context_item(item_id)
        initial_score = item_before['importance_score']

        # Recalculate
        context_manager.recalculate_scores_for_agent(test_project, agent_id)

        # Get recalculated score
        item_after = temp_db.get_context_item(item_id)
        recalculated_score = item_after['importance_score']

        # Age decay for 3 days: e^(-0.5 × 3) = e^(-1.5) ≈ 0.223
        # Access boost for 100 accesses: log(101) / 10 ≈ 0.46
        # Expected: 0.4 × 0.8 + 0.4 × 0.223 + 0.2 × 0.46 ≈ 0.51
        assert recalculated_score >= 0.45  # Access boost compensates for age
        assert recalculated_score < 0.7

    def test_recalculation_with_no_items(self, test_project, context_manager):
        """Test recalculation with no context items."""
        agent_id = "nonexistent-agent"

        # Recalculate for agent with no items
        updated_count = context_manager.recalculate_scores_for_agent(test_project, agent_id)

        # Should return 0 (no items updated)
        assert updated_count == 0

    def test_recalculation_with_multiple_items(self, temp_db, test_project, context_manager):
        """Test recalculation updates all items for an agent."""
        agent_id = "test-agent-recalc-003"

        # Create multiple items
        item_ids = []
        for i in range(5):
            item_id = temp_db.create_context_item(project_id=test_project, agent_id=agent_id,
                item_type=ContextItemType.TASK.value,
                content=f"Task {i}"
            )
            item_ids.append(item_id)

        # Recalculate all items
        updated_count = context_manager.recalculate_scores_for_agent(test_project, agent_id)

        # Should update all 5 items
        assert updated_count == 5

        # Verify all items have scores
        for item_id in item_ids:
            item = temp_db.get_context_item(item_id)
            assert 0.0 <= item['importance_score'] <= 1.0
