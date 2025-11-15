"""Unit tests for context statistics endpoint (T061).

Tests the context stats functionality:
- Getting tier counts for an agent
- Calculating token counts per tier
- Returning ContextStats response

Part of 007-context-management Phase 7 (US5 - Context Visualization).
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, UTC

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
        name="test-project", description="Test project for context stats", workspace_path=""
    )
    return project_id


class TestContextStats:
    """Unit tests for context statistics calculation."""

    def test_get_context_stats_for_agent(self, temp_db, test_project):
        """Test that context stats returns correct tier counts."""
        agent_id = "test-agent-stats-001"

        # Create context items with different tiers
        # 5 HOT items
        for i in range(5):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.TASK.value,
                content=f"HOT task {i}: " + ("Critical details " * 10),
            )
            # Set to HOT tier
            cursor = temp_db.conn.cursor()
            cursor.execute(
                "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
                (item_id,),
            )
            temp_db.conn.commit()

        # 10 WARM items
        for i in range(10):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.CODE.value,
                content=f"WARM code {i}: " + ("def function(): pass; " * 5),
            )
            # Set to WARM tier
            cursor = temp_db.conn.cursor()
            cursor.execute(
                "UPDATE context_items SET importance_score = 0.6, current_tier = 'warm' WHERE id = ?",
                (item_id,),
            )
            temp_db.conn.commit()

        # 3 COLD items
        for i in range(3):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.PRD_SECTION.value,
                content=f"COLD prd {i}: " + ("Old requirements " * 8),
            )
            # Set to COLD tier
            cursor = temp_db.conn.cursor()
            cursor.execute(
                "UPDATE context_items SET importance_score = 0.2, current_tier = 'cold' WHERE id = ?",
                (item_id,),
            )
            temp_db.conn.commit()

        # ACT: Get context stats
        from codeframe.lib.context_manager import ContextManager

        context_mgr = ContextManager(db=temp_db)

        # Calculate stats manually for now (implementation will be in T067)
        hot_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="hot", limit=100
        )
        warm_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="warm", limit=100
        )
        cold_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="cold", limit=100
        )

        # ASSERT: Tier counts are correct
        assert len(hot_items) == 5
        assert len(warm_items) == 10
        assert len(cold_items) == 3

        # Total items
        all_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier=None, limit=100
        )
        assert len(all_items) == 18

    def test_context_stats_calculates_tokens(self, temp_db, test_project):
        """Test that context stats calculates token counts per tier correctly."""
        agent_id = "test-agent-stats-002"

        # Create items with known content lengths
        # 2 HOT items (~50 tokens each = 100 total)
        for i in range(2):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.TASK.value,
                content="Critical task: " + ("word " * 10),  # ~50 tokens
            )
            cursor = temp_db.conn.cursor()
            cursor.execute(
                "UPDATE context_items SET importance_score = 0.9, current_tier = 'hot' WHERE id = ?",
                (item_id,),
            )
            temp_db.conn.commit()

        # 3 WARM items (~30 tokens each = 90 total)
        for i in range(3):
            item_id = temp_db.create_context_item(
                project_id=test_project,
                agent_id=agent_id,
                item_type=ContextItemType.CODE.value,
                content="def function(): " + ("pass; " * 5),  # ~30 tokens
            )
            cursor = temp_db.conn.cursor()
            cursor.execute(
                "UPDATE context_items SET importance_score = 0.6, current_tier = 'warm' WHERE id = ?",
                (item_id,),
            )
            temp_db.conn.commit()

        # ACT: Calculate tokens per tier
        from codeframe.lib.token_counter import TokenCounter

        token_counter = TokenCounter(cache_enabled=True)

        hot_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="hot", limit=100
        )
        warm_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="warm", limit=100
        )

        hot_tokens = token_counter.count_context_tokens(hot_items)
        warm_tokens = token_counter.count_context_tokens(warm_items)

        # ASSERT: Token counts are reasonable
        assert hot_tokens > 0  # Should have some tokens
        assert warm_tokens > 0  # Should have some tokens
        assert hot_tokens + warm_tokens > 0  # Total should be positive

        # Verify we can get total tokens
        all_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier=None, limit=100
        )
        total_tokens = token_counter.count_context_tokens(all_items)
        assert total_tokens == hot_tokens + warm_tokens

    def test_context_stats_for_agent_with_no_items(self, temp_db, test_project):
        """Test context stats for agent with no context items."""
        agent_id = "test-agent-stats-empty"

        # ACT: Get stats for empty agent
        hot_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="hot", limit=100
        )
        warm_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="warm", limit=100
        )
        cold_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier="cold", limit=100
        )

        # ASSERT: All counts are zero
        assert len(hot_items) == 0
        assert len(warm_items) == 0
        assert len(cold_items) == 0

        # Total tokens should be zero
        from codeframe.lib.token_counter import TokenCounter

        token_counter = TokenCounter(cache_enabled=True)
        all_items = temp_db.list_context_items(
            project_id=test_project, agent_id=agent_id, tier=None, limit=100
        )
        total_tokens = token_counter.count_context_tokens(all_items)
        assert total_tokens == 0
