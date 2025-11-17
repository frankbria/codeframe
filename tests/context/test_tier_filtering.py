"""Tests for tier-based context filtering (T038).

Tests the database list_context_items() method with tier filtering:
- Filter by specific tier (HOT, WARM, COLD)
- Verify correct items returned
- Test tier=None returns all items

Part of 007-context-management Phase 5 (US3 - Automatic Tier Assignment).
"""

import pytest
import tempfile
from pathlib import Path

from codeframe.persistence.database import Database
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
        name="test-project", description="Test project for context management", workspace_path=""
    )
    return project_id


class TestTierFiltering:
    """Test tier-based filtering in list_context_items()."""

    def test_filter_by_hot_tier(self, temp_db, test_project):
        """Test filtering returns only HOT tier items."""
        agent_id = "test-agent-hot"

        # Create items with different scores (will auto-assign tiers)
        # HOT items (score >= 0.8)
        hot_item_1 = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.TASK.value,
            content="Fresh critical task",
        )

        # Manually set high score to ensure HOT tier
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
            (hot_item_1,),
        )
        temp_db.conn.commit()

        # WARM item (score 0.4-0.8)
        warm_item = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.CODE.value,
            content="Some code",
        )
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.6, current_tier = 'warm' WHERE id = ?",
            (warm_item,),
        )
        temp_db.conn.commit()

        # ACT: Filter by HOT tier
        hot_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="HOT"
        )

        # ASSERT: Only HOT items returned
        assert len(hot_items) == 1
        assert hot_items[0]["id"] == hot_item_1
        assert hot_items[0]["current_tier"] == "hot"

    def test_filter_by_warm_tier(self, temp_db, test_project):
        """Test filtering returns only WARM tier items."""
        agent_id = "test-agent-warm"

        # Create HOT item
        hot_item = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.TASK.value,
            content="Critical task",
        )
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
            (hot_item,),
        )

        # Create WARM items
        warm_item_1 = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.CODE.value,
            content="Some code",
        )
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.6, current_tier = 'warm' WHERE id = ?",
            (warm_item_1,),
        )

        warm_item_2 = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.ERROR.value,
            content="Error log",
        )
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.5, current_tier = 'warm' WHERE id = ?",
            (warm_item_2,),
        )
        temp_db.conn.commit()

        # ACT: Filter by WARM tier
        warm_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="WARM"
        )

        # ASSERT: Only WARM items returned
        assert len(warm_items) == 2
        warm_ids = [item["id"] for item in warm_items]
        assert warm_item_1 in warm_ids
        assert warm_item_2 in warm_ids
        assert all(item["current_tier"] == "warm" for item in warm_items)

    def test_filter_by_cold_tier(self, temp_db, test_project):
        """Test filtering returns only COLD tier items."""
        agent_id = "test-agent-cold"

        # Create HOT item
        hot_item = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.TASK.value,
            content="Critical task",
        )
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
            (hot_item,),
        )

        # Create COLD item
        cold_item = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.PRD_SECTION.value,
            content="Old PRD section",
        )
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.2, current_tier = 'cold' WHERE id = ?",
            (cold_item,),
        )
        temp_db.conn.commit()

        # ACT: Filter by COLD tier
        cold_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="COLD"
        )

        # ASSERT: Only COLD items returned
        assert len(cold_items) == 1
        assert cold_items[0]["id"] == cold_item
        assert cold_items[0]["current_tier"] == "cold"

    def test_tier_none_returns_all_items(self, temp_db, test_project):
        """Test that tier=None returns all items regardless of tier."""
        agent_id = "test-agent-all"

        # Create items in all tiers
        hot_item = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.TASK.value,
            content="HOT item",
        )
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
            (hot_item,),
        )

        warm_item = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.CODE.value,
            content="WARM item",
        )
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.6, current_tier = 'warm' WHERE id = ?",
            (warm_item,),
        )

        cold_item = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.PRD_SECTION.value,
            content="COLD item",
        )
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.2, current_tier = 'cold' WHERE id = ?",
            (cold_item,),
        )
        temp_db.conn.commit()

        # ACT: Get all items (tier=None)
        all_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier=None
        )

        # ASSERT: All 3 items returned
        assert len(all_items) == 3
        all_ids = [item["id"] for item in all_items]
        assert hot_item in all_ids
        assert warm_item in all_ids
        assert cold_item in all_ids

    def test_empty_tier_filter(self, temp_db, test_project):
        """Test filtering by tier with no matching items."""
        agent_id = "test-agent-empty"

        # Create only HOT item
        hot_item = temp_db.create_context_item(
            project_id=test_project,
            agent_id=agent_id,
            item_type=ContextItemType.TASK.value,
            content="HOT item",
        )
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
            (hot_item,),
        )
        temp_db.conn.commit()

        # ACT: Filter by COLD tier (no COLD items exist)
        cold_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="COLD"
        )

        # ASSERT: Empty list returned
        assert len(cold_items) == 0
        assert cold_items == []
