"""Integration tests for worker agent context storage (T026).

Tests the end-to-end workflow:
1. Worker agent saves context items
2. Items persist to database
3. Worker agent loads context items
4. Access tracking updates correctly

Part of 007-context-management MVP (Phase 3 - User Story 1).
"""

import pytest
import tempfile
from pathlib import Path

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.persistence.database import Database
from codeframe.core.models import ContextItemType, ContextTier


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
def worker_agent(temp_db):
    """Create worker agent with test database."""
    agent = WorkerAgent(
        agent_id="test-worker-001",
        agent_type="backend",
        db=temp_db
    )
    return agent


class TestWorkerContextStorageIntegration:
    """Integration tests for worker agent context storage."""

    def test_worker_saves_and_loads_context(self, worker_agent, temp_db):
        """Test complete workflow: save → load → verify.

        This is the core MVP test - verifies agents gain basic memory.
        """
        # ARRANGE: Create some context items
        task_content = "Implement user authentication with JWT"
        code_content = "def authenticate_user(username, password): ..."
        error_content = "AuthenticationError: Invalid credentials"

        # ACT: Save context items
        task_id = worker_agent.save_context_item(
            ContextItemType.TASK,
            task_content
        )
        code_id = worker_agent.save_context_item(
            ContextItemType.CODE,
            code_content
        )
        error_id = worker_agent.save_context_item(
            ContextItemType.ERROR,
            error_content
        )

        # ASSERT: Items were created with IDs
        assert task_id > 0
        assert code_id > 0
        assert error_id > 0

        # ACT: Load all context (default HOT tier)
        # Note: For MVP, all items are WARM tier, so load all tiers
        loaded_items = worker_agent.load_context(tier=None)

        # ASSERT: All items loaded
        assert len(loaded_items) == 3

        # ASSERT: Content matches
        contents = [item["content"] for item in loaded_items]
        assert task_content in contents
        assert code_content in contents
        assert error_content in contents

        # ASSERT: Access count incremented (load_context updates it)
        for item in loaded_items:
            assert item["access_count"] >= 1  # At least 1 from load_context

    def test_context_persists_across_sessions(self, temp_db):
        """Test that context survives agent restart (database persistence)."""
        # ARRANGE: Create first agent and save context
        agent1 = WorkerAgent(
            agent_id="test-worker-002",
            agent_type="backend",
            db=temp_db
        )

        content = "This is persistent context"
        item_id = agent1.save_context_item(ContextItemType.TASK, content)

        # ACT: Create new agent instance (simulates restart)
        agent2 = WorkerAgent(
            agent_id="test-worker-002",  # Same agent ID
            agent_type="backend",
            db=temp_db
        )

        # Load context with new agent instance
        loaded_items = agent2.load_context(tier=None)

        # ASSERT: Context still exists
        assert len(loaded_items) >= 1
        assert any(item["content"] == content for item in loaded_items)
        assert any(item["id"] == item_id for item in loaded_items)

    def test_get_context_item_by_id(self, worker_agent):
        """Test retrieving specific context item by ID."""
        # ARRANGE: Save a context item
        content = "Specific item to retrieve"
        item_id = worker_agent.save_context_item(
            ContextItemType.CODE,
            content
        )

        # ACT: Retrieve by ID
        item = worker_agent.get_context_item(item_id)

        # ASSERT: Item retrieved correctly
        assert item is not None
        assert item["id"] == item_id
        assert item["content"] == content
        assert item["item_type"] == ContextItemType.CODE.value
        assert item["access_count"] >= 1  # Updated by get_context_item

    def test_get_nonexistent_item_returns_none(self, worker_agent):
        """Test that retrieving non-existent item returns None."""
        # ACT: Try to get item that doesn't exist
        item = worker_agent.get_context_item(99999)

        # ASSERT: Returns None
        assert item is None

    def test_access_tracking_updates(self, worker_agent):
        """Test that access_count increments on each load."""
        # ARRANGE: Save a context item
        item_id = worker_agent.save_context_item(
            ContextItemType.TASK,
            "Test access tracking"
        )

        # ACT: Load context multiple times
        worker_agent.load_context(tier=None)  # First load
        worker_agent.load_context(tier=None)  # Second load
        worker_agent.load_context(tier=None)  # Third load

        # Get the item to check access count
        item = worker_agent.get_context_item(item_id)

        # ASSERT: Access count incremented (3 loads + 1 get = 4 total)
        assert item["access_count"] >= 4

    def test_multiple_item_types(self, worker_agent):
        """Test saving and loading different context item types."""
        # ARRANGE: Create items of all types
        items_to_create = [
            (ContextItemType.TASK, "Task description"),
            (ContextItemType.CODE, "def example(): pass"),
            (ContextItemType.ERROR, "ValueError: invalid input"),
            (ContextItemType.TEST_RESULT, "Tests passed: 10/10"),
            (ContextItemType.PRD_SECTION, "User Story: As a user..."),
        ]

        # ACT: Save all items
        created_ids = []
        for item_type, content in items_to_create:
            item_id = worker_agent.save_context_item(item_type, content)
            created_ids.append(item_id)

        # Load all items
        loaded_items = worker_agent.load_context(tier=None)

        # ASSERT: All types present
        loaded_types = {item["item_type"] for item in loaded_items}
        expected_types = {item_type.value for item_type, _ in items_to_create}
        assert loaded_types == expected_types

        # ASSERT: All IDs present
        loaded_ids = {item["id"] for item in loaded_items}
        assert loaded_ids == set(created_ids)

    def test_tier_filtering_works(self, worker_agent, temp_db):
        """Test that tier filtering works (even though all items are WARM in MVP)."""
        # ARRANGE: Save some items (all will be WARM tier in MVP)
        worker_agent.save_context_item(ContextItemType.TASK, "Task 1")
        worker_agent.save_context_item(ContextItemType.TASK, "Task 2")

        # ACT: Load with tier filter
        warm_items = worker_agent.load_context(tier=ContextTier.WARM)
        hot_items = worker_agent.load_context(tier=ContextTier.HOT)

        # ASSERT: WARM tier has items (MVP assigns all to WARM)
        assert len(warm_items) >= 2

        # ASSERT: HOT tier is empty (no items assigned to HOT in MVP)
        assert len(hot_items) == 0

    def test_empty_content_raises_error(self, worker_agent):
        """Test that saving empty content raises ValueError."""
        # ACT & ASSERT: Empty content should raise error
        with pytest.raises(ValueError, match="Content cannot be empty"):
            worker_agent.save_context_item(ContextItemType.TASK, "")

        # Whitespace-only should also raise error
        with pytest.raises(ValueError, match="Content cannot be empty"):
            worker_agent.save_context_item(ContextItemType.TASK, "   \n\t  ")

    def test_multiple_agents_isolated_context(self, temp_db):
        """Test that different agents have isolated context."""
        # ARRANGE: Create two different agents
        agent1 = WorkerAgent(
            agent_id="agent-001",
            agent_type="backend",
            db=temp_db
        )
        agent2 = WorkerAgent(
            agent_id="agent-002",
            agent_type="frontend",
            db=temp_db
        )

        # ACT: Each agent saves context
        agent1.save_context_item(ContextItemType.TASK, "Agent 1 task")
        agent2.save_context_item(ContextItemType.TASK, "Agent 2 task")

        # Load context for each agent
        agent1_items = agent1.load_context(tier=None)
        agent2_items = agent2.load_context(tier=None)

        # ASSERT: Each agent only sees their own context
        assert len(agent1_items) == 1
        assert len(agent2_items) == 1
        assert agent1_items[0]["content"] == "Agent 1 task"
        assert agent2_items[0]["content"] == "Agent 2 task"
        assert agent1_items[0]["agent_id"] == "agent-001"
        assert agent2_items[0]["agent_id"] == "agent-002"


class TestMVPDemonstration:
    """Demonstration tests showing MVP value delivery."""

    def test_mvp_demo_agent_saves_task_and_retrieves(self, worker_agent):
        """MVP Demo: Agent saves task description → retrieves it later.

        This demonstrates the core value: agents now have memory.

        Before MVP: Agents had no memory, lost context between operations.
        After MVP: Agents can save and retrieve important context.
        """
        # SCENARIO: Agent starts a new task
        task_description = (
            "Implement user authentication system:\n"
            "- JWT token-based auth\n"
            "- Password hashing with bcrypt\n"
            "- Email verification\n"
            "- Rate limiting on login attempts"
        )

        # Agent saves the task description
        task_id = worker_agent.save_context_item(
            ContextItemType.TASK,
            task_description
        )

        print(f"\n✓ Agent saved task (ID: {task_id})")

        # ... Agent works on the task ...

        # Later: Agent retrieves the task description
        loaded_context = worker_agent.load_context(tier=None)

        # Agent can now reference the original task
        task_item = next(
            (item for item in loaded_context if item["id"] == task_id),
            None
        )

        print(f"✓ Agent retrieved task: {task_item['content'][:50]}...")

        # VERIFY: Agent has access to the full task context
        assert task_item is not None
        assert "JWT token-based auth" in task_item["content"]
        assert "Email verification" in task_item["content"]

        print("✓ MVP Value Delivered: Agent now has persistent memory!")
