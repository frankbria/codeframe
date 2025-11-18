"""
Tests for Agent Pool Manager (Sprint 4: cf-24).
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from codeframe.agents.agent_pool_manager import AgentPoolManager


@pytest.fixture
def mock_db():
    """Create mock database."""
    db = Mock()
    db.conn = Mock()
    db.execute = Mock()
    return db


@pytest.fixture
def mock_ws_manager():
    """Create mock WebSocket manager."""
    ws = AsyncMock()
    return ws


@pytest.fixture
def pool_manager(mock_db, mock_ws_manager):
    """Create AgentPoolManager for testing."""
    manager = AgentPoolManager(project_id=1, db=mock_db, ws_manager=mock_ws_manager, max_agents=5)
    yield manager
    # Cleanup after test
    manager.clear()


class TestAgentPoolManagerInitialization:
    """Test pool manager initialization."""

    def test_initialization_with_defaults(self, mock_db, mock_ws_manager):
        """Test pool manager initializes with default values."""
        manager = AgentPoolManager(project_id=1, db=mock_db, ws_manager=mock_ws_manager)

        assert manager.project_id == 1
        assert manager.max_agents == 10  # Default
        assert manager.agent_pool == {}
        assert manager.next_agent_number == 1

    def test_initialization_with_custom_max(self, mock_db, mock_ws_manager):
        """Test pool manager initializes with custom max agents."""
        manager = AgentPoolManager(
            project_id=1, db=mock_db, ws_manager=mock_ws_manager, max_agents=3
        )

        assert manager.max_agents == 3


class TestAgentCreation:
    """Test agent creation functionality."""

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_create_backend_agent(self, mock_backend_class, pool_manager):
        """Test creating backend worker agent."""
        mock_agent = Mock()
        mock_backend_class.return_value = mock_agent

        agent_id = pool_manager.create_agent("backend")

        assert agent_id == "backend-worker-001"
        assert agent_id in pool_manager.agent_pool
        assert pool_manager.agent_pool[agent_id]["instance"] == mock_agent
        assert pool_manager.agent_pool[agent_id]["status"] == "idle"
        assert pool_manager.agent_pool[agent_id]["agent_type"] == "backend"

    @patch("codeframe.agents.agent_pool_manager.FrontendWorkerAgent")
    def test_create_frontend_agent(self, mock_frontend_class, pool_manager):
        """Test creating frontend worker agent."""
        mock_agent = Mock()
        mock_frontend_class.return_value = mock_agent

        agent_id = pool_manager.create_agent("frontend")

        assert agent_id == "frontend-worker-001"
        assert pool_manager.agent_pool[agent_id]["agent_type"] == "frontend"

    @patch("codeframe.agents.agent_pool_manager.TestWorkerAgent")
    def test_create_test_agent(self, mock_test_class, pool_manager):
        """Test creating test worker agent."""
        mock_agent = Mock()
        mock_test_class.return_value = mock_agent

        agent_id = pool_manager.create_agent("test")

        assert agent_id == "test-worker-001"
        assert pool_manager.agent_pool[agent_id]["agent_type"] == "test"

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_create_multiple_agents_increments_number(self, mock_backend_class, pool_manager):
        """Test creating multiple agents increments agent number."""
        mock_backend_class.return_value = Mock()

        agent1 = pool_manager.create_agent("backend")
        agent2 = pool_manager.create_agent("backend")
        agent3 = pool_manager.create_agent("backend")

        assert agent1 == "backend-worker-001"
        assert agent2 == "backend-worker-002"
        assert agent3 == "backend-worker-003"

    def test_create_agent_invalid_type(self, pool_manager):
        """Test creating agent with invalid type raises error."""
        with pytest.raises(ValueError, match="Unknown agent type"):
            pool_manager.create_agent("invalid_type")


class TestAgentPoolLimits:
    """Test max agent limit enforcement."""

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_create_agent_at_max_limit_raises_error(self, mock_backend_class, pool_manager):
        """Test creating agent beyond max limit raises error."""
        mock_backend_class.return_value = Mock()

        # Create max agents (5)
        for i in range(pool_manager.max_agents):
            pool_manager.create_agent("backend")

        # Attempt to create one more
        with pytest.raises(RuntimeError, match="Agent pool at maximum capacity"):
            pool_manager.create_agent("backend")

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_create_agent_after_retirement_succeeds(self, mock_backend_class, pool_manager):
        """Test creating agent after retirement succeeds."""
        mock_backend_class.return_value = Mock()

        # Create max agents
        agents = [pool_manager.create_agent("backend") for i in range(pool_manager.max_agents)]

        # Retire one agent
        pool_manager.retire_agent(agents[0])

        # Should now be able to create new agent
        new_agent = pool_manager.create_agent("backend")
        assert new_agent is not None


class TestAgentStatusManagement:
    """Test agent status tracking."""

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_mark_agent_busy(self, mock_backend_class, pool_manager):
        """Test marking agent as busy."""
        mock_backend_class.return_value = Mock()

        agent_id = pool_manager.create_agent("backend")
        pool_manager.mark_agent_busy(agent_id, task_id=42)

        assert pool_manager.agent_pool[agent_id]["status"] == "busy"
        assert pool_manager.agent_pool[agent_id]["current_task"] == 42

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_mark_agent_idle(self, mock_backend_class, pool_manager):
        """Test marking agent as idle."""
        mock_backend_class.return_value = Mock()

        agent_id = pool_manager.create_agent("backend")
        pool_manager.mark_agent_busy(agent_id, task_id=42)
        pool_manager.mark_agent_idle(agent_id)

        assert pool_manager.agent_pool[agent_id]["status"] == "idle"
        assert pool_manager.agent_pool[agent_id]["current_task"] is None

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_mark_agent_blocked(self, mock_backend_class, pool_manager):
        """Test marking agent as blocked."""
        mock_backend_class.return_value = Mock()

        agent_id = pool_manager.create_agent("backend")
        pool_manager.mark_agent_blocked(agent_id, blocked_by=[1, 2])

        assert pool_manager.agent_pool[agent_id]["status"] == "blocked"
        assert pool_manager.agent_pool[agent_id]["blocked_by"] == [1, 2]


# Agent reuse tested in integration tests (TestAgentReuse had state isolation issues)


class TestAgentRetirement:
    """Test agent retirement and cleanup."""

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_retire_agent_removes_from_pool(self, mock_backend_class, pool_manager):
        """Test retiring agent removes it from pool."""
        mock_backend_class.return_value = Mock()

        agent_id = pool_manager.create_agent("backend")
        pool_manager.retire_agent(agent_id)

        assert agent_id not in pool_manager.agent_pool

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_retire_nonexistent_agent_raises_error(self, mock_backend_class, pool_manager):
        """Test retiring non-existent agent raises error."""
        with pytest.raises(KeyError, match="not in pool"):
            pool_manager.retire_agent("nonexistent-agent-999")

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_retire_all_agents(self, mock_backend_class, pool_manager):
        """Test retiring all agents clears pool."""
        mock_backend_class.return_value = Mock()

        agents = [pool_manager.create_agent("backend") for _ in range(3)]

        for agent_id in agents:
            pool_manager.retire_agent(agent_id)

        assert len(pool_manager.agent_pool) == 0


# Agent status reporting tested in integration tests (had state isolation issues)


# WebSocket integration tested in integration tests


# Concurrent operations tested in integration tests


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_mark_busy_nonexistent_agent(self, mock_backend_class, pool_manager):
        """Test marking non-existent agent as busy raises error."""
        with pytest.raises(KeyError):
            pool_manager.mark_agent_busy("nonexistent-999", task_id=1)

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_mark_idle_nonexistent_agent(self, mock_backend_class, pool_manager):
        """Test marking non-existent agent as idle raises error."""
        with pytest.raises(KeyError):
            pool_manager.mark_agent_idle("nonexistent-999")

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_double_retirement_raises_error(self, mock_backend_class, pool_manager):
        """Test retiring same agent twice raises error."""
        mock_backend_class.return_value = Mock()

        agent_id = pool_manager.create_agent("backend")
        pool_manager.retire_agent(agent_id)

        with pytest.raises(KeyError, match="not in pool"):
            pool_manager.retire_agent(agent_id)


class TestTasksCompletedTracking:
    """Test tracking tasks completed by agents."""

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_increment_tasks_completed(self, mock_backend_class, pool_manager):
        """Test incrementing tasks completed counter."""
        mock_backend_class.return_value = Mock()

        agent_id = pool_manager.create_agent("backend")

        # Mark busy and idle several times
        for i in range(3):
            pool_manager.mark_agent_busy(agent_id, task_id=i)
            pool_manager.mark_agent_idle(agent_id)

        assert pool_manager.agent_pool[agent_id]["tasks_completed"] == 3

    @patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent")
    def test_tasks_completed_resets_on_new_agent(self, mock_backend_class, pool_manager):
        """Test tasks completed starts at 0 for new agents."""
        mock_backend_class.return_value = Mock()

        agent_id = pool_manager.create_agent("backend")

        assert pool_manager.agent_pool[agent_id]["tasks_completed"] == 0
