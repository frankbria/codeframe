"""
Tests for Worker Agent token tracking functionality.

Test coverage:
- Token usage recording with valid response
- Graceful degradation with missing usage info
- Error handling scenarios
- Model name resolution
- Integration with MetricsTracker
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import Task, AgentMaturity, CallType, TaskStatus, Issue
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

        # Mock response with usage info
        response = {
            "status": "completed",
            "output": "Task done",
            "usage": {"input_tokens": 1000, "output_tokens": 500},
        }

        # Execute
        await agent._record_token_usage(task, response)

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
    async def test_record_token_usage_with_no_usage_data(self, db):
        """Test graceful handling when response has no usage data."""
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

        # Mock response without usage info
        response = {"status": "completed", "output": "Task done"}

        # Execute - should not raise exception
        await agent._record_token_usage(task, response)

        # Verify no token usage was recorded
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM token_usage WHERE task_id = ?", (task_id,))
        usage_row = cursor.fetchone()

        assert usage_row is None

    @pytest.mark.asyncio
    async def test_record_token_usage_with_zero_tokens(self, db):
        """Test graceful handling when usage has zero tokens."""
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

        # Mock response with zero tokens
        response = {
            "status": "completed",
            "output": "Task done",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

        # Execute - should not raise exception
        await agent._record_token_usage(task, response)

        # Verify no token usage was recorded
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM token_usage WHERE task_id = ?", (task_id,))
        usage_row = cursor.fetchone()

        assert usage_row is None

    @pytest.mark.asyncio
    async def test_record_token_usage_without_project_id(self, db):
        """Test graceful handling when task has no project_id."""
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

        # Mock response with usage info
        response = {
            "status": "completed",
            "output": "Task done",
            "usage": {"input_tokens": 1000, "output_tokens": 500},
        }

        # Execute - should not raise exception, just log warning
        await agent._record_token_usage(task, response)

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

        # Mock response with usage info
        response = {
            "status": "completed",
            "output": "Task done",
            "usage": {"input_tokens": 1000, "output_tokens": 500},
        }

        # Execute - should not raise exception, just log warning
        await agent._record_token_usage(task, response)

        # No assertion needed - test passes if no exception is raised


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

        # Mock _record_token_usage to verify it's called
        with patch.object(
            agent, "_record_token_usage", new_callable=AsyncMock
        ) as mock_record:
            # Execute
            result = await agent.execute_task(task)

            # Verify _record_token_usage was called
            mock_record.assert_called_once()
            call_args = mock_record.call_args
            assert call_args[0][0] == task  # First argument is task
            assert isinstance(call_args[0][1], dict)  # Second argument is response

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

        # Execute
        await agent.execute_task(task)

        # Verify current_task is set
        assert agent.current_task == task


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

        response = {
            "status": "completed",
            "output": "Task done",
            "usage": {"input_tokens": 1000, "output_tokens": 500},
        }

        # Execute
        await agent._record_token_usage(task, response)

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

        response = {
            "status": "completed",
            "output": "Task done",
            "usage": {"input_tokens": 1000, "output_tokens": 500},
        }

        # Execute
        await agent._record_token_usage(task, response)

        # Verify custom model name was used
        cursor = db.conn.cursor()
        cursor.execute("SELECT model_name FROM token_usage WHERE task_id = ?", (task_id,))
        model_name = cursor.fetchone()[0]

        assert model_name == "claude-opus-4"
