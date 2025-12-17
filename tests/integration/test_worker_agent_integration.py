"""
Integration tests for WorkerAgent.execute_task() with real API.

These tests require a valid ANTHROPIC_API_KEY environment variable.
They are skipped if the API key is not set.

Test coverage:
- End-to-end execution with real Anthropic API
- Token usage recording in database
- Different model configurations
"""

import os
import pytest

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.persistence.database import Database
from codeframe.core.models import Task, TaskStatus, AgentMaturity


# Skip all tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY environment variable required for integration tests",
)


@pytest.fixture
def temp_database(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_state.db"
    db = Database(str(db_path))
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def project_id(temp_database):
    """Create a test project and return its ID."""
    return temp_database.create_project(
        name="IntegrationTestProject",
        description="Project for WorkerAgent integration tests",
        workspace_path="/tmp/integration_test",
        status="active",
    )


@pytest.fixture
def agent(temp_database):
    """Create a WorkerAgent with real database connection."""
    return WorkerAgent(
        agent_id="integration-test-001",
        agent_type="backend",
        provider="anthropic",
        maturity=AgentMaturity.D1,
        system_prompt="You are a helpful assistant. Respond concisely.",
        db=temp_database,
    )


@pytest.fixture
def simple_task(project_id):
    """Create a simple task for testing."""
    return Task(
        id=1,
        project_id=project_id,
        task_number="INT-1",
        title="Simple Test Task",
        description="Respond with 'Hello, World!' and nothing else.",
        status=TaskStatus.IN_PROGRESS,
        assigned_to="integration-test-001",
        priority=1,
    )


class TestRealApiExecution:
    """Test real API calls (requires ANTHROPIC_API_KEY)."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_execute_simple_task_with_real_api(self, agent, simple_task):
        """Test executing a simple task with the real Anthropic API."""
        result = await agent.execute_task(simple_task)

        assert result["status"] == "completed"
        assert result["output"]  # Should have some output
        assert "usage" in result
        assert result["usage"]["input_tokens"] > 0
        assert result["usage"]["output_tokens"] > 0
        assert result["model"] == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_execute_with_haiku_model(self, agent, simple_task):
        """Test execution with Claude Haiku (faster, cheaper)."""
        result = await agent.execute_task(simple_task, model_name="claude-haiku-4")

        assert result["status"] == "completed"
        assert result["model"] == "claude-haiku-4"
        assert result["usage"]["input_tokens"] > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_current_task_set_after_execution(self, agent, simple_task):
        """Test that current_task is set correctly after execution."""
        await agent.execute_task(simple_task)

        assert agent.current_task == simple_task
        assert agent.current_task.project_id == simple_task.project_id


class TestTokenUsageDatabase:
    """Test that token usage is properly recorded in the database."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_token_usage_recorded_in_database(
        self, temp_database, project_id, simple_task
    ):
        """Test that token usage is saved to the database after execution."""
        agent = WorkerAgent(
            agent_id="db-test-agent",
            agent_type="backend",
            provider="anthropic",
            db=temp_database,
        )

        # Need to create the task in the database
        task_id = temp_database.create_task(simple_task)
        simple_task.id = task_id

        result = await agent.execute_task(simple_task)

        assert result["status"] == "completed"

        # Verify token usage was recorded
        usage_records = temp_database.get_token_usage(project_id=project_id)
        assert len(usage_records) >= 1

        # Find our record
        our_record = None
        for record in usage_records:
            if record["agent_id"] == "db-test-agent":
                our_record = record
                break

        assert our_record is not None
        assert our_record["input_tokens"] > 0
        assert our_record["output_tokens"] > 0
        assert our_record["model_name"] == "claude-sonnet-4-5"
        assert our_record["estimated_cost_usd"] > 0


class TestCodeGenerationTask:
    """Test more complex code generation tasks."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_code_generation_task(self, agent, project_id):
        """Test executing a code generation task."""
        code_task = Task(
            id=2,
            project_id=project_id,
            task_number="INT-2",
            title="Generate Python function",
            description=(
                "Write a Python function called 'is_prime' that takes an integer n "
                "and returns True if n is a prime number, False otherwise. "
                "Include a docstring."
            ),
            status=TaskStatus.IN_PROGRESS,
            assigned_to="integration-test-001",
            priority=1,
        )

        result = await agent.execute_task(code_task)

        assert result["status"] == "completed"
        assert "is_prime" in result["output"]
        assert "def" in result["output"]
        # Token usage should be recorded
        assert result["usage"]["input_tokens"] > 0
        assert result["usage"]["output_tokens"] > 0


class TestConcurrentExecution:
    """Test concurrent task execution."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_agents_concurrent(self, temp_database, project_id):
        """Test that multiple agents can execute concurrently."""
        import asyncio

        agent1 = WorkerAgent(
            agent_id="concurrent-agent-1",
            agent_type="backend",
            provider="anthropic",
            db=temp_database,
        )

        agent2 = WorkerAgent(
            agent_id="concurrent-agent-2",
            agent_type="frontend",
            provider="anthropic",
            db=temp_database,
        )

        task1 = Task(
            id=10,
            project_id=project_id,
            task_number="CONC-1",
            title="Task 1",
            description="Say 'Task 1 complete'",
            status=TaskStatus.IN_PROGRESS,
        )

        task2 = Task(
            id=11,
            project_id=project_id,
            task_number="CONC-2",
            title="Task 2",
            description="Say 'Task 2 complete'",
            status=TaskStatus.IN_PROGRESS,
        )

        # Execute both tasks concurrently
        results = await asyncio.gather(
            agent1.execute_task(task1, model_name="claude-haiku-4"),
            agent2.execute_task(task2, model_name="claude-haiku-4"),
        )

        # Both should complete successfully
        assert results[0]["status"] == "completed"
        assert results[1]["status"] == "completed"

        # Each agent should have its current_task set correctly
        assert agent1.current_task == task1
        assert agent2.current_task == task2
