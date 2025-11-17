"""Integration test for flash save workflow (T058).

Tests the end-to-end flash save workflow:
1. Create 150 context items (mix of HOT/WARM/COLD)
2. Trigger flash save
3. Verify COLD items archived
4. Verify HOT items still loadable
5. Verify token reduction >= 30%

Part of 007-context-management Phase 6 (US4 - Flash Save).
"""

import pytest
import tempfile
from pathlib import Path

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
        name="test-project", description="Test project for flash save workflow", workspace_path=""
    )
    return project_id


@pytest.fixture
def context_manager(temp_db):
    """Create context manager with test database."""
    return ContextManager(db=temp_db)


class TestFlashSaveWorkflow:
    """Integration tests for complete flash save workflow."""

    def test_flash_save_workflow_with_150_items(self, temp_db, test_project, context_manager):
        """Test full flash save workflow with 150 items (mix of HOT/WARM/COLD).

        Workflow:
        1. Create 150 context items with varying tiers
        2. Verify token count is substantial
        3. Trigger flash save
        4. Verify COLD items archived (deleted)
        5. Verify HOT and WARM items still loadable
        6. Verify token reduction >= 30%
        """
        agent_id = "test-agent-workflow-001"

        # STEP 1: Create 150 context items
        # Distribution: 30 HOT, 70 WARM, 50 COLD
        item_ids = []

        # Create HOT items (30)
        for i in range(30):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.TASK.value,
                content=f"Critical task {i}: " + ("Important details " * 50),  # ~500 tokens each
            )
            item_ids.append(item_id)

            # Manually set to HOT tier
            cursor = temp_db.conn.cursor()
            cursor.execute(
                "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
                (item_id,),
            )
            temp_db.conn.commit()

        # Create WARM items (70)
        for i in range(70):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.CODE.value,
                content=f"Code snippet {i}: " + ("def function(): pass; " * 30),  # ~300 tokens each
            )
            item_ids.append(item_id)

            # Manually set to WARM tier
            cursor = temp_db.conn.cursor()
            cursor.execute(
                "UPDATE context_items SET importance_score = 0.6, current_tier = 'warm' WHERE id = ?",
                (item_id,),
            )
            temp_db.conn.commit()

        # Create COLD items (50)
        for i in range(50):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.PRD_SECTION.value,
                content=f"Old PRD section {i}: "
                + ("Old requirements text " * 40),  # ~400 tokens each
            )
            item_ids.append(item_id)

            # Manually set to COLD tier
            cursor = temp_db.conn.cursor()
            cursor.execute(
                "UPDATE context_items SET importance_score = 0.2, current_tier = 'cold' WHERE id = ?",
                (item_id,),
            )
            temp_db.conn.commit()

        # STEP 2: Verify token count is substantial
        all_items_before = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier=None, limit=200
        )
        assert len(all_items_before) == 150

        # Get tokens before (from flash save result)
        # Expected: ~30 * 500 + 70 * 300 + 50 * 400 = 15k + 21k + 20k = ~56k tokens

        # STEP 3: Trigger flash save
        result = context_manager.flash_save(test_project, agent_id)

        # ASSERT: Flash save completed successfully
        assert "checkpoint_id" in result
        assert result["checkpoint_id"] > 0

        # STEP 4: Verify COLD items archived (deleted)
        cold_items_after = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="cold", limit=100
        )
        assert len(cold_items_after) == 0  # All COLD items deleted

        # STEP 5: Verify HOT and WARM items still loadable
        hot_items_after = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="hot", limit=100
        )
        assert len(hot_items_after) == 30  # All HOT items retained

        warm_items_after = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="warm", limit=100
        )
        assert len(warm_items_after) == 70  # All WARM items retained

        # Total remaining items = 30 HOT + 70 WARM = 100
        all_items_after = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier=None, limit=200
        )
        assert len(all_items_after) == 100

        # STEP 6: Verify token reduction >= 30%
        assert result["tokens_before"] > 0
        assert result["tokens_after"] > 0
        assert result["tokens_after"] < result["tokens_before"]

        # Calculate actual reduction
        reduction_percentage = result["reduction_percentage"]
        assert reduction_percentage >= 30.0  # At least 30% reduction

        # Verify metrics
        assert result["items_archived"] == 50  # 50 COLD items
        assert result["hot_items_retained"] == 30
        assert result["warm_items_retained"] == 70

    def test_flash_save_creates_recoverable_checkpoint(
        self, temp_db, test_project, context_manager
    ):
        """Test that checkpoint contains full context state and is recoverable."""
        agent_id = "test-agent-workflow-002"

        # Create some context items
        for i in range(10):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.TASK.value,
                content=f"Task {i} " * 100,
            )

            # Set different tiers
            cursor = temp_db.conn.cursor()
            if i < 3:
                cursor.execute(
                    "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
                    (item_id,),
                )
            elif i < 7:
                cursor.execute(
                    "UPDATE context_items SET importance_score = 0.6, current_tier = 'warm' WHERE id = ?",
                    (item_id,),
                )
            else:
                cursor.execute(
                    "UPDATE context_items SET importance_score = 0.2, current_tier = 'cold' WHERE id = ?",
                    (item_id,),
                )
            temp_db.conn.commit()

        # Trigger flash save
        result = context_manager.flash_save(test_project, agent_id)

        # Verify checkpoint exists and contains data
        checkpoint = temp_db.get_checkpoint(result["checkpoint_id"])
        assert checkpoint is not None
        assert checkpoint["agent_id"] == agent_id

        # Verify checkpoint data is not empty
        import json

        checkpoint_data = json.loads(checkpoint["checkpoint_data"])
        assert "context_items" in checkpoint_data
        assert len(checkpoint_data["context_items"]) == 10  # All items before archival

        # Verify checkpoint metadata
        assert checkpoint["items_count"] == 10
        assert checkpoint["items_archived"] == 3  # 3 COLD items (indices 7, 8, 9)
        assert checkpoint["hot_items_retained"] == 3
