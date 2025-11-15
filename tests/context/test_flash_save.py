"""Unit tests for flash save functionality (T047).

Tests the flash save workflow:
- Checkpoint creation in database
- COLD item archival
- HOT item retention
- Token count reduction tracking
- Threshold validation

Part of 007-context-management Phase 6 (US4 - Flash Save).
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
def test_project(temp_db):
    """Create a test project for context items."""
    project_id = temp_db.create_project(
        name="test-project", description="Test project for flash save", workspace_path=""
    )
    return project_id


@pytest.fixture
def context_manager(temp_db):
    """Create context manager with test database."""
    return ContextManager(db=temp_db)


class TestFlashSave:
    """Unit tests for flash save functionality."""

    def test_flash_save_creates_checkpoint(self, temp_db, test_project, context_manager):
        """Test that flash save creates a checkpoint record in DB."""
        agent_id = "test-agent-flash-001"

        # Create some context items
        for i in range(10):
            temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.TASK.value,
                content=f"Task {i} " * 100,  # Make it long enough
            )

        # ACT: Trigger flash save
        result = context_manager.flash_save(test_project, agent_id)

        # ASSERT: Checkpoint created
        assert result is not None
        assert "checkpoint_id" in result
        assert result["checkpoint_id"] > 0

        # Verify checkpoint exists in database
        checkpoint = temp_db.get_checkpoint(result["checkpoint_id"])
        assert checkpoint is not None
        assert checkpoint["agent_id"] == agent_id

    def test_flash_save_archives_cold_items(self, temp_db, test_project, context_manager):
        """Test that COLD tier items are archived during flash save."""
        agent_id = "test-agent-flash-002"

        # Create HOT item
        hot_item_id = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.TASK.value,
            content="Critical task " * 50,
        )
        # Manually set to HOT tier
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
            (hot_item_id,),
        )

        # Create COLD item
        cold_item_id = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.PRD_SECTION.value,
            content="Old PRD section " * 50,
        )
        # Manually set to COLD tier
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.2, current_tier = 'cold' WHERE id = ?",
            (cold_item_id,),
        )
        temp_db.conn.commit()

        # ACT: Trigger flash save
        result = context_manager.flash_save(test_project, agent_id)

        # ASSERT: COLD item archived (deleted)
        cold_item_after = temp_db.get_context_item(cold_item_id)
        assert cold_item_after is None  # Should be deleted

        # HOT item still exists
        hot_item_after = temp_db.get_context_item(hot_item_id)
        assert hot_item_after is not None

    def test_flash_save_retains_hot_items(self, temp_db, test_project, context_manager):
        """Test that HOT tier items are still accessible after flash save."""
        agent_id = "test-agent-flash-003"

        # Create multiple HOT items
        hot_item_ids = []
        for i in range(5):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.TASK.value,
                content=f"Critical task {i} " * 50,
            )
            hot_item_ids.append(item_id)

            # Manually set to HOT tier
            cursor = temp_db.conn.cursor()
            cursor.execute(
                "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
                (item_id,),
            )
            temp_db.conn.commit()

        # ACT: Trigger flash save
        context_manager.flash_save(test_project, agent_id)

        # ASSERT: All HOT items still accessible
        hot_items_after = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="hot"
        )
        assert len(hot_items_after) == 5
        hot_ids_after = [item["id"] for item in hot_items_after]
        for item_id in hot_item_ids:
            assert item_id in hot_ids_after

    def test_flash_save_calculates_reduction(self, temp_db, test_project, context_manager):
        """Test that token count before/after is tracked."""
        agent_id = "test-agent-flash-004"

        # Create items with different tiers
        for i in range(10):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.TASK.value,
                content=f"Task {i} " * 100,
            )

            # Set half to HOT, half to COLD
            cursor = temp_db.conn.cursor()
            if i < 5:
                cursor.execute(
                    "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
                    (item_id,),
                )
            else:
                cursor.execute(
                    "UPDATE context_items SET importance_score = 0.2, current_tier = 'cold' WHERE id = ?",
                    (item_id,),
                )
            temp_db.conn.commit()

        # ACT: Trigger flash save
        result = context_manager.flash_save(test_project, agent_id)

        # ASSERT: Reduction calculated
        assert "tokens_before" in result
        assert "tokens_after" in result
        assert "reduction_percentage" in result

        # Verify reduction is positive (COLD items removed)
        assert result["tokens_after"] < result["tokens_before"]
        assert result["reduction_percentage"] > 0

    def test_flash_save_below_threshold_fails(self, temp_db, test_project, context_manager):
        """Test that flash save fails if below threshold (unless force=True)."""
        agent_id = "test-agent-flash-005"

        # Create only 1 small item (well below threshold)
        temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.TASK.value,
            content="Small task",
        )

        # ACT: Try flash save without force (should not trigger)
        should_save = context_manager.should_flash_save(test_project, agent_id, force=False)

        # ASSERT: Should not trigger flash save
        assert should_save is False

        # ACT: Try flash save with force=True
        should_save_forced = context_manager.should_flash_save(test_project, agent_id, force=True)

        # ASSERT: Should trigger when forced
        assert should_save_forced is True
