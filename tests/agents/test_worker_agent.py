"""
Tests for Worker Agent token tracking functionality.

Test coverage:
- Token usage recording with valid response
- Zero token handling
- Error handling scenarios (missing project_id, database errors)
- Model name resolution
- Integration with MetricsTracker
- Execute task integration
"""

import pytest
import os
from unittest.mock import Mock, AsyncMock, patch
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import Task, AgentMaturity, CallType, TaskStatus
from codeframe.persistence.database import Database


@pytest.fixture
def db():
    """Create in-memory database for testing with migrations."""
    database = Database(":memory:")
    database.initialize()

    # Apply Sprint 10 migration for token_usage table
    from codeframe.persistence.migrations.migration_007_sprint10_review_polish import (
        migration as migration_007,
    )

    if migration_007.can_apply(database.conn):
        migration_007.apply(database.conn)

    return database


class TestWorkerAgentInitialization:
    """Test WorkerAgent initialization."""

    def test_init_with_default_model_name(self):
        """Test agent initializes with default model name."""
        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
        )

        assert agent.model_name == "claude-sonnet-4-5"

    def test_init_with_custom_model_name(self):
        """Test agent initializes with custom model name."""
        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            model_name="claude-opus-4",
        )

        assert agent.model_name == "claude-opus-4"

    def test_init_stores_all_parameters(self):
        """Test agent stores all initialization parameters."""
        db = Mock(spec=Database)

        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            maturity=AgentMaturity.D2,
            system_prompt="Test prompt",
            db=db,
            model_name="claude-haiku-4",
        )

        assert agent.agent_id == "test-001"
        assert agent.agent_type == "backend"
        assert agent.provider == "anthropic"
        assert agent.maturity == AgentMaturity.D2
        assert agent.system_prompt == "Test prompt"
        assert agent.db == db
        assert agent.model_name == "claude-haiku-4"


class TestWorkerAgentTokenTracking:
    """Test token tracking functionality."""

    @pytest.mark.asyncio
    async def test_record_token_usage_with_valid_response(self, db):
        """Test token usage is recorded with valid LLM response."""
        # Setup
        project_id = db.create_project(
            name="test",
            description="Test project",
            source_type="empty",
            workspace_path="/tmp/test",
        )
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test issue",
                "description": "Test",
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = db.get_task(task_id)

        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            db=db,
            model_name="claude-sonnet-4-5",
        )

        # Execute
        result = await agent._record_token_usage(
            task=task,
            model_name="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=500,
        )
        assert result is False  # False means tracking succeeded

        # Verify token usage was recorded
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM token_usage WHERE task_id = ?", (task_id,))
        usage_row = cursor.fetchone()

        assert usage_row is not None
        # Schema: id, task_id, agent_id, project_id, model_name, input_tokens, output_tokens, estimated_cost_usd, actual_cost_usd, call_type, timestamp
        assert usage_row[1] == task_id  # task_id column
        assert usage_row[2] == "test-001"  # agent_id column
        assert usage_row[4] == "claude-sonnet-4-5"  # model_name column
        assert usage_row[5] == 1000  # input_tokens column
        assert usage_row[6] == 500  # output_tokens column
        assert usage_row[9] == CallType.TASK_EXECUTION.value  # call_type column

    @pytest.mark.asyncio
    async def test_record_token_usage_with_zero_tokens(self, db):
        """Test no-op behavior when both input and output tokens are zero.

        Zero tokens means zero cost, so recording is skipped to avoid
        database bloat. Returns False (success) but creates no record.
        """
        # Setup
        project_id = db.create_project(
            name="test",
            description="Test project",
            source_type="empty",
            workspace_path="/tmp/test",
        )
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test issue",
                "description": "Test",
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = db.get_task(task_id)

        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        # Execute - zero tokens should be skipped (no-op)
        result = await agent._record_token_usage(
            task=task,
            model_name="claude-sonnet-4-5",
            input_tokens=0,
            output_tokens=0,
        )
        # False means operation succeeded (skipped recording)
        assert result is False

        # Verify no token usage was recorded (zero tokens = no-op)
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM token_usage WHERE task_id = ?", (task_id,))
        usage_row = cursor.fetchone()

        # No record created for zero tokens
        assert usage_row is None

    @pytest.mark.asyncio
    async def test_record_token_usage_without_project_id(self, db):
        """Test fail-fast behavior when task has no project_id.

        The method raises a clear ValueError which is caught by the exception
        handler, logged, and returns True to indicate tracking failure.
        """
        # Setup
        # Create task without project_id
        from dataclasses import replace

        task = Task(
            id=1,
            title="Test task",
            description="Test",
            priority=1,
            status=TaskStatus.PENDING,
            task_number="1.0.1",
        )
        # Explicitly set project_id to None
        task = replace(task, project_id=None)

        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        # Execute - raises ValueError internally, caught by exception handler
        result = await agent._record_token_usage(
            task=task,
            model_name="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=500,
        )
        # ValueError is caught, logged, and method returns True (tracking failed)
        assert result is True  # Tracking fails with clear error message

        # Verify no token usage was recorded
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM token_usage WHERE task_id = ?", (task.id,))
        usage_row = cursor.fetchone()

        assert usage_row is None

    @pytest.mark.asyncio
    async def test_record_token_usage_handles_database_error(self, db):
        """Test graceful handling of database errors during token tracking."""
        # Setup
        db = Mock(spec=Database)
        db.save_token_usage = Mock(side_effect=Exception("Database error"))

        task = Task(
            id=1,
            project_id=1,
            title="Test task",
            description="Test",
            priority=1,
            status=TaskStatus.PENDING,
            task_number="1.0.1",
        )

        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        # Simulate database/save_token_usage error; tracking should fail and return True
        result = await agent._record_token_usage(
            task=task,
            model_name="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=500,
        )
        # Tracking fails due to database error
        assert result is True

        # Test passes if no exception is raised (graceful error handling)


class TestWorkerAgentExecuteTask:
    """Test execute_task integration with token tracking."""

    @pytest.mark.asyncio
    async def test_execute_task_calls_token_tracking(self, db):
        """Test execute_task calls _record_token_usage."""
        # Setup
        project_id = db.create_project(
            name="test",
            description="Test project",
            source_type="empty",
            workspace_path="/tmp/test",
        )
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test issue",
                "description": "Test",
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = db.get_task(task_id)

        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        # Mock environment and API
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                # Mock API response
                mock_response = Mock()
                mock_response.content = [Mock(text="Task completed")]
                mock_response.usage.input_tokens = 1000
                mock_response.usage.output_tokens = 500
                mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
                
                # Mock _record_token_usage to verify it's called
                with patch.object(
                    agent, "_record_token_usage", new_callable=AsyncMock, return_value=False
                ) as mock_record:
                    # Execute
                    result = await agent.execute_task(task)

                    # Verify _record_token_usage was called
                    mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_task_sets_current_task(self, db):
        """Test execute_task sets current_task for project context."""
        # Setup
        project_id = db.create_project(
            name="test",
            description="Test project",
            source_type="empty",
            workspace_path="/tmp/test",
        )
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test issue",
                "description": "Test",
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = db.get_task(task_id)

        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        # Mock environment and API
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                # Mock API response
                mock_response = Mock()
                mock_response.content = [Mock(text="Task completed")]
                mock_response.usage.input_tokens = 100
                mock_response.usage.output_tokens = 50
                mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
                
                # Execute
                await agent.execute_task(task)

                # Verify current_task is set
                # Note: current_task will be dict since db.get_task returns dict
                assert agent.current_task is not None


class TestWorkerAgentModelNameResolution:
    """Test model name resolution for different scenarios."""

    @pytest.mark.asyncio
    async def test_uses_default_model_name(self, db):
        """Test token tracking uses default model name."""
        # Setup
        project_id = db.create_project(
            name="test",
            description="Test project",
            source_type="empty",
            workspace_path="/tmp/test",
        )
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test issue",
                "description": "Test",
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = db.get_task(task_id)

        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            db=db,
            # No model_name specified - should use default
        )

        # Execute
        result = await agent._record_token_usage(
            task=task,
            model_name="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=500,
        )
        assert result is False

        # Verify default model name was used
        cursor = db.conn.cursor()
        cursor.execute("SELECT model_name FROM token_usage WHERE task_id = ?", (task_id,))
        model_name = cursor.fetchone()[0]

        assert model_name == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_uses_custom_model_name(self, db):
        """Test token tracking uses custom model name."""
        # Setup
        project_id = db.create_project(
            name="test",
            description="Test project",
            source_type="empty",
            workspace_path="/tmp/test",
        )
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test issue",
                "description": "Test",
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test task",
            description="Test",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = db.get_task(task_id)

        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="anthropic",
            db=db,
            model_name="claude-opus-4",
        )

        # Execute
        result = await agent._record_token_usage(
            task=task,
            model_name="claude-opus-4",
            input_tokens=1000,
            output_tokens=500,
        )
        assert result is False

        # Verify custom model name was used
        cursor = db.conn.cursor()
        cursor.execute("SELECT model_name FROM token_usage WHERE task_id = ?", (task_id,))
        model_name = cursor.fetchone()[0]

        assert model_name == "claude-opus-4"
