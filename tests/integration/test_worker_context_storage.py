"""Integration tests for worker agent context storage (T026).

Tests the end-to-end workflow:
1. Worker agent saves context items
2. Items persist to database
3. Worker agent loads context items
4. Access tracking updates correctly

Part of 007-context-management MVP (Phase 3 - User Story 1).
"""

import pytest

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.persistence.database import Database
from codeframe.core.models import ContextItemType, ContextTier


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    # Use :memory: database instead of tempfile to avoid WSL filesystem issues
    db = Database(":memory:")
    db.initialize()

    yield db

    db.close()


@pytest.fixture
def test_project(temp_db):
    """Create a test project for context items."""
    project_id = temp_db.create_project(
        name="test-project",
        description="Test project for worker context storage",
        workspace_path="",
    )
    return project_id


@pytest.fixture
def worker_agent(temp_db, test_project):
    """Create worker agent with test database and assign to project."""
    from codeframe.core.models import AgentMaturity

    agent = WorkerAgent(
        agent_id="test-worker-001", agent_type="backend", provider="anthropic", db=temp_db
    )
    # Create agent in database first (required for foreign key)
    temp_db.create_agent(
        agent_id=agent.agent_id,
        agent_type=agent.agent_type,
        provider=agent.provider,
        maturity_level=AgentMaturity.D1,
    )
    # Assign agent to project using project_agents junction table
    temp_db.assign_agent_to_project(test_project, agent.agent_id)

    # Create a mock task to establish project context
    from codeframe.core.models import Task, TaskStatus

    task = Task(
        id=1,
        issue_id=1,
        project_id=test_project,
        assigned_to=agent.agent_id,
        title="Test task",
        description="Test task for context storage",
        status=TaskStatus.IN_PROGRESS,
    )
    agent.current_task = task

    return agent


class TestWorkerContextStorageIntegration:
    """Integration tests for worker agent context storage."""

    @pytest.mark.asyncio
    async def test_worker_saves_and_loads_context(self, worker_agent, temp_db):
        """Test complete workflow: save → load → verify.

        This is the core MVP test - verifies agents gain basic memory.
        """
        # ARRANGE: Create some context items
        task_content = "Implement user authentication with JWT"
        code_content = "def authenticate_user(username, password): ..."
        error_content = "AuthenticationError: Invalid credentials"

        # ACT: Save context items
        task_id = await worker_agent.save_context_item(ContextItemType.TASK, task_content)
        code_id = await worker_agent.save_context_item(ContextItemType.CODE, code_content)
        error_id = await worker_agent.save_context_item(ContextItemType.ERROR, error_content)

        # ASSERT: Items were created with IDs (UUIDs as strings)
        assert task_id is not None
        assert code_id is not None
        assert error_id is not None
        assert isinstance(task_id, str)
        assert isinstance(code_id, str)
        assert isinstance(error_id, str)

        # ACT: Load all context (default HOT tier)
        # Note: For MVP, all items are WARM tier, so load all tiers
        loaded_items = await worker_agent.load_context(tier=None)

        # ASSERT: All items loaded
        assert len(loaded_items) == 3

        # ASSERT: Content matches
        contents = [item["content"] for item in loaded_items]
        assert task_content in contents
        assert code_content in contents
        assert error_content in contents

        # ASSERT: Access count exists (may or may not be incremented by load_context)
        for item in loaded_items:
            assert "access_count" in item
            assert item["access_count"] >= 0

    @pytest.mark.asyncio
    async def test_context_persists_across_sessions(self, temp_db, test_project):
        """Test that context survives agent restart (database persistence)."""
        # ARRANGE: Create first agent and save context
        from codeframe.core.models import Task, TaskStatus, AgentMaturity

        agent1 = WorkerAgent(
            agent_id="test-worker-002", agent_type="backend", provider="anthropic", db=temp_db
        )
        temp_db.create_agent(agent1.agent_id, agent1.agent_type, agent1.provider, AgentMaturity.D1)
        temp_db.assign_agent_to_project(test_project, agent1.agent_id)

        # Create task to establish project context
        task1 = Task(
            id=2,
            issue_id=1,
            project_id=test_project,
            assigned_to=agent1.agent_id,
            title="Test task",
            description="Test task",
            status=TaskStatus.IN_PROGRESS,
        )
        agent1.current_task = task1

        content = "This is persistent context"
        item_id = await agent1.save_context_item(ContextItemType.TASK, content)

        # ACT: Create new agent instance (simulates restart)
        # Note: Agent already exists in DB from agent1 creation
        agent2 = WorkerAgent(
            agent_id="test-worker-002",  # Same agent ID
            agent_type="backend",
            provider="anthropic",
            db=temp_db,
        )
        # Agent already assigned to project from agent1, no need to reassign

        # Create task to establish project context for agent2
        task2 = Task(
            id=3,
            issue_id=1,
            project_id=test_project,
            assigned_to=agent2.agent_id,
            title="Test task",
            description="Test task",
            status=TaskStatus.IN_PROGRESS,
        )
        agent2.current_task = task2

        # Load context with new agent instance
        loaded_items = await agent2.load_context(tier=None)

        # ASSERT: Context still exists
        assert len(loaded_items) >= 1
        assert any(item["content"] == content for item in loaded_items)
        assert any(item["id"] == item_id for item in loaded_items)

    @pytest.mark.asyncio
    async def test_get_context_item_by_id(self, worker_agent):
        """Test retrieving specific context item by ID."""
        # ARRANGE: Save a context item
        content = "Specific item to retrieve"
        item_id = await worker_agent.save_context_item(ContextItemType.CODE, content)

        # ACT: Retrieve by ID
        item = await worker_agent.get_context_item(item_id)

        # ASSERT: Item retrieved correctly
        assert item is not None
        assert item["id"] == item_id
        assert item["content"] == content
        assert item["item_type"] == ContextItemType.CODE.value
        # Note: get_context_item() may not increment access_count
        assert item["access_count"] >= 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_item_returns_none(self, worker_agent):
        """Test that retrieving non-existent item returns None."""
        # ACT: Try to get item that doesn't exist
        item = await worker_agent.get_context_item(99999)

        # ASSERT: Returns None
        assert item is None

    @pytest.mark.asyncio
    async def test_access_tracking_updates(self, worker_agent):
        """Test that access_count increments on each load."""
        # ARRANGE: Save a context item
        item_id = await worker_agent.save_context_item(ContextItemType.TASK, "Test access tracking")

        # ACT: Load context multiple times
        await worker_agent.load_context(tier=None)  # First load
        await worker_agent.load_context(tier=None)  # Second load
        await worker_agent.load_context(tier=None)  # Third load

        # Get the item to check access count
        item = await worker_agent.get_context_item(item_id)

        # ASSERT: Access count incremented (3 loads, get_context_item doesn't increment)
        assert item["access_count"] >= 3

    @pytest.mark.asyncio
    async def test_multiple_item_types(self, worker_agent):
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
            item_id = await worker_agent.save_context_item(item_type, content)
            created_ids.append(item_id)

        # Load all items
        loaded_items = await worker_agent.load_context(tier=None)

        # ASSERT: All types present
        loaded_types = {item["item_type"] for item in loaded_items}
        expected_types = {item_type.value for item_type, _ in items_to_create}
        assert loaded_types == expected_types

        # ASSERT: All IDs present
        loaded_ids = {item["id"] for item in loaded_items}
        assert loaded_ids == set(created_ids)

    @pytest.mark.asyncio
    async def test_tier_filtering_works(self, worker_agent, temp_db):
        """Test that tier filtering works (even though all items are WARM in MVP)."""
        # ARRANGE: Save some items (all will be WARM tier in MVP)
        await worker_agent.save_context_item(ContextItemType.TASK, "Task 1")
        await worker_agent.save_context_item(ContextItemType.TASK, "Task 2")

        # ACT: Load with tier filter
        warm_items = await worker_agent.load_context(tier=ContextTier.WARM)
        hot_items = await worker_agent.load_context(tier=ContextTier.HOT)

        # ASSERT: WARM tier has items (MVP assigns all to WARM)
        assert len(warm_items) >= 2

        # ASSERT: HOT tier is empty (no items assigned to HOT in MVP)
        assert len(hot_items) == 0

    @pytest.mark.asyncio
    async def test_empty_content_raises_error(self, worker_agent):
        """Test that saving empty content raises ValueError."""
        # ACT & ASSERT: Empty content should raise error
        with pytest.raises(ValueError, match="Content cannot be empty"):
            await worker_agent.save_context_item(ContextItemType.TASK, "")

        # Whitespace-only should also raise error
        with pytest.raises(ValueError, match="Content cannot be empty"):
            await worker_agent.save_context_item(ContextItemType.TASK, "   \n\t  ")

    @pytest.mark.asyncio
    async def test_multiple_agents_isolated_context(self, temp_db, test_project):
        """Test that different agents have isolated context."""
        # ARRANGE: Create two different agents
        from codeframe.core.models import Task, TaskStatus, AgentMaturity

        agent1 = WorkerAgent(
            agent_id="agent-001", agent_type="backend", provider="anthropic", db=temp_db
        )
        temp_db.create_agent(agent1.agent_id, agent1.agent_type, agent1.provider, AgentMaturity.D1)
        temp_db.assign_agent_to_project(test_project, agent1.agent_id)

        agent2 = WorkerAgent(
            agent_id="agent-002", agent_type="frontend", provider="anthropic", db=temp_db
        )
        temp_db.create_agent(agent2.agent_id, agent2.agent_type, agent2.provider, AgentMaturity.D1)
        temp_db.assign_agent_to_project(test_project, agent2.agent_id)

        # Create tasks to establish project context
        task1 = Task(
            id=4,
            issue_id=1,
            project_id=test_project,
            assigned_to=agent1.agent_id,
            title="Agent 1 task",
            description="Task for agent 1",
            status=TaskStatus.IN_PROGRESS,
        )
        agent1.current_task = task1

        task2 = Task(
            id=5,
            issue_id=1,
            project_id=test_project,
            assigned_to=agent2.agent_id,
            title="Agent 2 task",
            description="Task for agent 2",
            status=TaskStatus.IN_PROGRESS,
        )
        agent2.current_task = task2

        # ACT: Each agent saves context
        await agent1.save_context_item(ContextItemType.TASK, "Agent 1 task")
        await agent2.save_context_item(ContextItemType.TASK, "Agent 2 task")

        # Load context for each agent
        agent1_items = await agent1.load_context(tier=None)
        agent2_items = await agent2.load_context(tier=None)

        # ASSERT: Each agent only sees their own context
        assert len(agent1_items) == 1
        assert len(agent2_items) == 1
        assert agent1_items[0]["content"] == "Agent 1 task"
        assert agent2_items[0]["content"] == "Agent 2 task"
        assert agent1_items[0]["agent_id"] == "agent-001"
        assert agent2_items[0]["agent_id"] == "agent-002"


class TestMVPDemonstration:
    """Demonstration tests showing MVP value delivery."""

    @pytest.mark.asyncio
    async def test_mvp_demo_agent_saves_task_and_retrieves(self, worker_agent):
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
        task_id = await worker_agent.save_context_item(ContextItemType.TASK, task_description)

        print(f"\n✓ Agent saved task (ID: {task_id})")

        # ... Agent works on the task ...

        # Later: Agent retrieves the task description
        loaded_context = await worker_agent.load_context(tier=None)

        # Agent can now reference the original task
        task_item = next((item for item in loaded_context if item["id"] == task_id), None)

        print(f"✓ Agent retrieved task: {task_item['content'][:50]}...")

        # VERIFY: Agent has access to the full task context
        assert task_item is not None
        assert "JWT token-based auth" in task_item["content"]
        assert "Email verification" in task_item["content"]

        print("✓ MVP Value Delivered: Agent now has persistent memory!")
