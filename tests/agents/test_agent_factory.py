"""Tests for AgentFactory."""

import pytest
from pathlib import Path

from codeframe.agents.factory import AgentFactory
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import AgentMaturity


class TestAgentFactory:
    """Test suite for AgentFactory."""

    @pytest.fixture
    def factory(self):
        """Create AgentFactory instance."""
        return AgentFactory()

    def test_factory_initialization(self, factory):
        """Test factory initializes and loads definitions."""
        assert factory is not None
        assert factory.loader is not None
        assert factory.definitions_dir.exists()

    def test_list_available_agents(self, factory):
        """Test listing available agent types."""
        agents = factory.list_available_agents()

        assert isinstance(agents, list)
        assert len(agents) > 0

        # Check for expected built-in agents
        assert "backend-worker" in agents
        assert "backend-architect" in agents
        assert "frontend-specialist" in agents
        assert "test-engineer" in agents
        assert "code-reviewer" in agents

    def test_create_backend_worker_agent(self, factory):
        """Test creating a backend worker agent."""
        agent = factory.create_agent(
            agent_type="backend-worker", agent_id="test-backend-001", provider="claude"
        )

        assert isinstance(agent, WorkerAgent)
        assert agent.agent_id == "test-backend-001"
        assert agent.agent_type == "backend"
        assert agent.provider == "claude"
        assert agent.maturity == AgentMaturity.D1
        assert agent.system_prompt is not None
        assert len(agent.system_prompt) > 0

        # Check that definition metadata is attached
        assert hasattr(agent, "definition")
        assert hasattr(agent, "capabilities")
        assert isinstance(agent.capabilities, list)

    def test_create_backend_architect_agent(self, factory):
        """Test creating a backend architect agent."""
        agent = factory.create_agent(
            agent_type="backend-architect", agent_id="test-architect-001", provider="claude"
        )

        assert isinstance(agent, WorkerAgent)
        assert agent.agent_id == "test-architect-001"
        assert agent.agent_type == "backend"
        assert agent.provider == "claude"
        assert agent.maturity == AgentMaturity.D2  # Defined in YAML

        # Check capabilities from YAML
        assert "RESTful and GraphQL API design" in agent.capabilities
        assert "Database schema design and optimization" in agent.capabilities

    def test_create_frontend_specialist_agent(self, factory):
        """Test creating a frontend specialist agent."""
        agent = factory.create_agent(
            agent_type="frontend-specialist", agent_id="test-frontend-001", provider="claude"
        )

        assert isinstance(agent, WorkerAgent)
        assert agent.agent_type == "frontend"
        assert agent.maturity == AgentMaturity.D2

        # Check capabilities
        assert "React, Vue, Angular expertise" in agent.capabilities
        assert "Component-based architecture" in agent.capabilities

    def test_create_test_engineer_agent(self, factory):
        """Test creating a test engineer agent."""
        agent = factory.create_agent(
            agent_type="test-engineer", agent_id="test-tester-001", provider="claude"
        )

        assert isinstance(agent, WorkerAgent)
        assert agent.agent_type == "test"
        assert agent.maturity == AgentMaturity.D2

        # Check capabilities
        assert "Unit and integration testing" in agent.capabilities
        assert "Test-driven development (TDD)" in agent.capabilities

    def test_create_code_reviewer_agent(self, factory):
        """Test creating a code reviewer agent."""
        agent = factory.create_agent(
            agent_type="code-reviewer", agent_id="test-reviewer-001", provider="claude"
        )

        assert isinstance(agent, WorkerAgent)
        assert agent.agent_type == "review"
        assert agent.maturity == AgentMaturity.D3  # Higher maturity

        # Check capabilities
        assert "Code quality assessment" in agent.capabilities
        assert "Security vulnerability detection" in agent.capabilities

    def test_get_agent_capabilities(self, factory):
        """Test getting capabilities for an agent type."""
        capabilities = factory.get_agent_capabilities("backend-architect")

        assert isinstance(capabilities, list)
        assert len(capabilities) > 0
        assert "RESTful and GraphQL API design" in capabilities
        assert "Database schema design and optimization" in capabilities

    def test_get_agent_capabilities_unknown_type(self, factory):
        """Test getting capabilities for unknown agent type raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            factory.get_agent_capabilities("nonexistent-agent")

        assert "not found" in str(exc_info.value)
        assert "Available agents" in str(exc_info.value)

    def test_create_agent_unknown_type(self, factory):
        """Test creating agent with unknown type raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            factory.create_agent(
                agent_type="nonexistent-agent", agent_id="test-001", provider="claude"
            )

        assert "not found" in str(exc_info.value)

    def test_create_agent_with_custom_maturity(self, factory):
        """Test creating agent with custom maturity override."""
        agent = factory.create_agent(
            agent_type="backend-worker",
            agent_id="test-001",
            provider="claude",
            maturity=AgentMaturity.D4,  # Override default D1
        )

        assert agent.maturity == AgentMaturity.D4

    def test_get_agent_definition(self, factory):
        """Test getting full agent definition."""
        definition = factory.get_agent_definition("backend-architect")

        assert definition.name == "backend-architect"
        assert definition.type == "backend"
        assert definition.maturity == AgentMaturity.D2
        assert len(definition.system_prompt) > 0
        assert len(definition.capabilities) > 0
        assert "backend" in definition.metadata.get("tags", [])

    def test_get_agents_by_type(self, factory):
        """Test getting all agents of a specific type category."""
        backend_agents = factory.get_agents_by_type("backend")

        assert isinstance(backend_agents, list)
        assert len(backend_agents) >= 2  # At least backend-worker and backend-architect
        assert "backend-worker" in backend_agents
        assert "backend-architect" in backend_agents

    def test_backward_compatibility_with_existing_code(self):
        """Test that existing code using BackendWorkerAgent still works."""
        # This tests backward compatibility - existing code should still function
        from codeframe.agents.backend_worker_agent import BackendWorkerAgent
        from codeframe.persistence.database import Database
        from codeframe.indexing.codebase_index import CodebaseIndex

        # Create minimal dependencies
        db = Database(":memory:")
        db.initialize()
        project_id = db.create_project("test", "Test project")

        # Create a simple codebase index
        index = CodebaseIndex(Path("."))

        # BackendWorkerAgent should still work as before
        agent = BackendWorkerAgent(
            db=db, codebase_index=index, provider="claude", project_root=".", use_sdk=False
        )

        assert agent is not None
        assert agent.db == db

        db.close()

    def test_agent_has_system_prompt(self, factory):
        """Test that created agents have system_prompt attribute."""
        agent = factory.create_agent(
            agent_type="backend-worker", agent_id="test-001", provider="claude"
        )

        assert hasattr(agent, "system_prompt")
        assert agent.system_prompt is not None
        assert len(agent.system_prompt) > 50  # Should be substantial

    def test_agent_has_capabilities_attribute(self, factory):
        """Test that created agents have capabilities attribute."""
        agent = factory.create_agent(
            agent_type="test-engineer", agent_id="test-001", provider="claude"
        )

        assert hasattr(agent, "capabilities")
        assert isinstance(agent.capabilities, list)
        assert len(agent.capabilities) > 0

    def test_agent_has_tools_attribute(self, factory):
        """Test that created agents have tools attribute."""
        agent = factory.create_agent(
            agent_type="backend-architect", agent_id="test-001", provider="claude"
        )

        assert hasattr(agent, "tools")
        assert isinstance(agent.tools, list)
        # Backend-architect should have tools defined
        assert len(agent.tools) > 0
        assert "database_query" in agent.tools

    def test_agent_has_constraints_attribute(self, factory):
        """Test that created agents have constraints attribute."""
        agent = factory.create_agent(
            agent_type="code-reviewer", agent_id="test-001", provider="claude"
        )

        assert hasattr(agent, "constraints")
        assert isinstance(agent.constraints, dict)
        # Code-reviewer should have constraints defined
        assert "max_tokens" in agent.constraints
        assert "temperature" in agent.constraints

    def test_reload_definitions(self, factory):
        """Test reloading definitions."""
        initial_count = len(factory.list_available_agents())

        # Reload definitions
        factory.reload_definitions()

        # Should have same count (no new files added)
        reloaded_count = len(factory.list_available_agents())
        assert reloaded_count == initial_count

    def test_worker_agent_maintains_backward_compatibility(self):
        """Test that WorkerAgent can still be instantiated directly."""
        # Old way - should still work
        agent = WorkerAgent(
            agent_id="old-style-001",
            agent_type="backend",
            provider="claude",
            maturity=AgentMaturity.D1,
        )

        assert agent.agent_id == "old-style-001"
        assert agent.agent_type == "backend"
        assert agent.provider == "claude"
        assert agent.maturity == AgentMaturity.D1
        # system_prompt is optional, so should be None
        assert agent.system_prompt is None

    def test_worker_agent_with_system_prompt(self):
        """Test that WorkerAgent can be instantiated with system_prompt."""
        custom_prompt = "You are a custom agent with specific instructions."

        agent = WorkerAgent(
            agent_id="custom-001",
            agent_type="custom",
            provider="claude",
            maturity=AgentMaturity.D2,
            system_prompt=custom_prompt,
        )

        assert agent.system_prompt == custom_prompt
