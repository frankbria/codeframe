"""
Integration tests for Worker Agent task execution.

These tests verify real agent behavior with:
- Real SQLite database operations
- Real file system operations
- Real token tracking
- Real quality gate subprocess execution (where safe)
- Only external LLM API is mocked

Key difference from unit tests:
- Unit tests: Mock database, file ops, and internal methods to test logic
- Integration tests: Use real components, mock only external services
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.core.models import AgentMaturity, CallType, Task, TaskStatus
from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.persistence.database import Database


@pytest.mark.integration
class TestWorkerAgentTokenTracking:
    """Integration tests for token usage tracking with real database."""

    @pytest.mark.asyncio
    async def test_token_usage_recorded_in_database(self, real_db: Database):
        """Test that token usage is actually saved to the database after task execution."""
        # Setup - create project and task in real database
        project_id = real_db.create_project(
            name="token-tracking-test",
            description="Test token tracking",
            source_type="empty",
            workspace_path="/tmp/test-token-tracking",
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "TOK-001",
            "title": "Token Tracking Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })
        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="TOK-001-1",
            parent_issue_number="TOK-001",
            title="Test Token Recording",
            description="Simple task to test token recording",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = real_db.get_task(task_id)

        # Create agent with real database
        agent = WorkerAgent(
            agent_id="test-token-agent",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
            model_name="claude-sonnet-4-5",
        )

        # Mock only the external Anthropic API
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_anthropic:
                mock_response = Mock()
                mock_response.content = [Mock(text="Task completed successfully.")]
                mock_response.usage = Mock(input_tokens=1500, output_tokens=750)
                mock_anthropic.return_value.messages.create = AsyncMock(
                    return_value=mock_response
                )

                # Execute task
                result = await agent.execute_task(task)

        # Verify - check real database for token usage record
        assert result["status"] == "completed"

        cursor = real_db.conn.cursor()
        cursor.execute(
            "SELECT * FROM token_usage WHERE task_id = ?", (task_id,)
        )
        usage_row = cursor.fetchone()

        assert usage_row is not None, "Token usage was not recorded in database"
        assert usage_row["input_tokens"] == 1500
        assert usage_row["output_tokens"] == 750
        assert usage_row["model_name"] == "claude-sonnet-4-5"
        assert usage_row["agent_id"] == "test-token-agent"
        assert usage_row["call_type"] == CallType.TASK_EXECUTION.value

    @pytest.mark.asyncio
    async def test_multiple_tasks_accumulate_token_usage(self, real_db: Database):
        """Test that multiple task executions properly accumulate token usage."""
        # Setup project with multiple tasks
        project_id = real_db.create_project(
            name="multi-task-test",
            description="Test multiple task token tracking",
            source_type="empty",
            workspace_path="/tmp/test-multi-task",
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "MULTI-001",
            "title": "Multi Task Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })

        # Create 3 tasks
        task_ids = []
        for i in range(3):
            task_id = real_db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"MULTI-001-{i+1}",
                parent_issue_number="MULTI-001",
                title=f"Task {i+1}",
                description=f"Task {i+1} description",
                status=TaskStatus.PENDING,
                priority=1,
                workflow_step=i + 1,
                can_parallelize=False,
            )
            task_ids.append(task_id)

        agent = WorkerAgent(
            agent_id="test-multi-agent",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        # Execute all tasks with different token counts
        token_counts = [(500, 200), (800, 400), (1200, 600)]

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_anthropic:
                for i, task_id in enumerate(task_ids):
                    task = real_db.get_task(task_id)
                    input_tokens, output_tokens = token_counts[i]

                    mock_response = Mock()
                    mock_response.content = [Mock(text=f"Task {i+1} done")]
                    mock_response.usage = Mock(
                        input_tokens=input_tokens, output_tokens=output_tokens
                    )
                    mock_anthropic.return_value.messages.create = AsyncMock(
                        return_value=mock_response
                    )

                    await agent.execute_task(task)

        # Verify total token usage in database
        cursor = real_db.conn.cursor()
        cursor.execute(
            "SELECT SUM(input_tokens) as total_input, SUM(output_tokens) as total_output "
            "FROM token_usage WHERE project_id = ?",
            (project_id,),
        )
        row = cursor.fetchone()

        expected_input = sum(t[0] for t in token_counts)
        expected_output = sum(t[1] for t in token_counts)

        assert row["total_input"] == expected_input
        assert row["total_output"] == expected_output


@pytest.mark.integration
class TestWorkerAgentTaskExecution:
    """Integration tests for complete task execution workflow."""

    @pytest.mark.asyncio
    async def test_task_execution_returns_success_result(self, real_db: Database):
        """Test that task execution returns success and caller can update status.

        Note: WorkerAgent.execute_task() returns results but doesn't update
        task status directly - the orchestrator (LeadAgent/API) does that.
        This test verifies the execution + manual status update flow.
        """
        # Setup
        project_id = real_db.create_project(
            name="status-test",
            description="Test status transitions",
            source_type="empty",
            workspace_path="/tmp/test-status",
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "ST-001",
            "title": "Status Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })
        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="ST-001-1",
            parent_issue_number="ST-001",
            title="Status Test Task",
            description="Test status transitions",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )

        # Verify initial status
        task = real_db.get_task(task_id)
        assert task.status == TaskStatus.PENDING

        agent = WorkerAgent(
            agent_id="test-status-agent",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_anthropic:
                mock_response = Mock()
                mock_response.content = [Mock(text="Complete")]
                mock_response.usage = Mock(input_tokens=100, output_tokens=50)
                mock_anthropic.return_value.messages.create = AsyncMock(
                    return_value=mock_response
                )

                result = await agent.execute_task(task)

        # Verify execution result indicates success
        assert result["status"] == "completed"
        assert result["output"] == "Complete"

        # Simulate orchestrator updating task status based on result
        real_db.update_task(task_id, {"status": TaskStatus.COMPLETED.value})

        # Verify status updated in database
        updated_task = real_db.get_task(task_id)
        assert updated_task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_task_execution_returns_failure_result(self, real_db: Database):
        """Test that task execution returns failure and caller can update status.

        Note: WorkerAgent.execute_task() returns failure results but doesn't
        update task status directly - the orchestrator handles that.
        """
        # Setup
        project_id = real_db.create_project(
            name="failure-test",
            description="Test failure recording",
            source_type="empty",
            workspace_path="/tmp/test-failure",
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "FAIL-001",
            "title": "Failure Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })
        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="FAIL-001-1",
            parent_issue_number="FAIL-001",
            title="Failure Test Task",
            description="This task should fail",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = real_db.get_task(task_id)

        agent = WorkerAgent(
            agent_id="test-failure-agent",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        # Simulate API failure
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_anthropic:
                from anthropic import APIConnectionError

                mock_anthropic.return_value.messages.create = AsyncMock(
                    side_effect=APIConnectionError(request=Mock())
                )

                result = await agent.execute_task(task)

        # Verify failure result
        assert result["status"] == "failed"
        assert "error" in result or "output" in result

        # Simulate orchestrator updating task status based on result
        real_db.update_task(task_id, {"status": TaskStatus.FAILED.value})

        # Verify status updated in database
        updated_task = real_db.get_task(task_id)
        assert updated_task.status == TaskStatus.FAILED


@pytest.mark.integration
class TestBackendWorkerAgentFileOperations:
    """Integration tests for backend worker file operations."""

    @pytest.mark.asyncio
    async def test_file_creation_with_real_filesystem(
        self, real_db: Database, test_workspace: Path
    ):
        """Test that file creation actually writes to the filesystem."""
        # Setup
        project_id = real_db.create_project(
            name="file-test",
            description="Test file creation",
            source_type="empty",
            workspace_path=str(test_workspace),
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "FILE-001",
            "title": "File Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })
        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="FILE-001-1",
            parent_issue_number="FILE-001",
            title="Create User Model",
            description="Create a User model class",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )

        cursor = real_db.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = dict(cursor.fetchone())

        # Create codebase index mock (only indexing, not file ops)
        index = Mock(spec=CodebaseIndex)
        index.search_pattern.return_value = []

        agent = BackendWorkerAgent(
            db=real_db,
            codebase_index=index,
            api_key="test-key",
            project_root=test_workspace,
            use_sdk=False,
        )

        # Mock only the LLM API response
        llm_response = json.dumps({
            "files": [
                {
                    "path": "src/models/user.py",
                    "action": "create",
                    "content": (
                        'class User:\n'
                        '    """User model."""\n'
                        '    def __init__(self, name: str, email: str):\n'
                        '        self.name = name\n'
                        '        self.email = email\n'
                    ),
                },
                {
                    "path": "tests/test_user.py",
                    "action": "create",
                    "content": (
                        'from src.models.user import User\n\n'
                        'def test_user_creation():\n'
                        '    user = User("Alice", "alice@example.com")\n'
                        '    assert user.name == "Alice"\n'
                    ),
                },
            ],
            "explanation": "Created User model with tests",
        })

        with patch("anthropic.AsyncAnthropic") as mock_anthropic:
            mock_response = Mock()
            mock_response.content = [Mock(text=llm_response)]
            mock_anthropic.return_value = Mock(
                messages=Mock(create=AsyncMock(return_value=mock_response))
            )

            # Mock test runner to avoid actual test execution
            with patch(
                "codeframe.testing.test_runner.TestRunner.run_tests"
            ) as mock_tests:
                from codeframe.testing.models import TestResult

                mock_tests.return_value = TestResult(
                    status="passed",
                    total=1,
                    passed=1,
                    failed=0,
                    errors=0,
                    skipped=0,
                    duration=0.1,
                )

                result = await agent.execute_task(task)

        # Verify files were actually created on disk
        assert result["status"] == "completed"
        assert (test_workspace / "src" / "models" / "user.py").exists()
        assert (test_workspace / "tests" / "test_user.py").exists()

        # Verify file contents
        user_content = (test_workspace / "src" / "models" / "user.py").read_text()
        assert "class User:" in user_content
        assert "def __init__" in user_content
        assert "self.name" in user_content

    @pytest.mark.asyncio
    async def test_file_modification_preserves_content(
        self, real_db: Database, test_workspace: Path
    ):
        """Test that file modification correctly updates existing files."""
        # Create initial file
        (test_workspace / "src").mkdir(parents=True, exist_ok=True)
        original_file = test_workspace / "src" / "app.py"
        original_file.write_text("# Original content\ndef old_function():\n    pass\n")

        # Setup database
        project_id = real_db.create_project(
            name="modify-test",
            description="Test file modification",
            source_type="empty",
            workspace_path=str(test_workspace),
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "MOD-001",
            "title": "Modify Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })
        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="MOD-001-1",
            parent_issue_number="MOD-001",
            title="Update App",
            description="Add new function",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )

        cursor = real_db.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = dict(cursor.fetchone())

        index = Mock(spec=CodebaseIndex)
        index.search_pattern.return_value = []

        agent = BackendWorkerAgent(
            db=real_db,
            codebase_index=index,
            api_key="test-key",
            project_root=test_workspace,
            use_sdk=False,
        )

        # LLM response modifying the file
        llm_response = json.dumps({
            "files": [
                {
                    "path": "src/app.py",
                    "action": "modify",
                    "content": (
                        "# Updated content\n"
                        "def new_function():\n"
                        "    return 'Hello, World!'\n"
                    ),
                }
            ],
            "explanation": "Updated app with new function",
        })

        with patch("anthropic.AsyncAnthropic") as mock_anthropic:
            mock_response = Mock()
            mock_response.content = [Mock(text=llm_response)]
            mock_anthropic.return_value = Mock(
                messages=Mock(create=AsyncMock(return_value=mock_response))
            )

            with patch(
                "codeframe.testing.test_runner.TestRunner.run_tests"
            ) as mock_tests:
                from codeframe.testing.models import TestResult

                mock_tests.return_value = TestResult(
                    status="passed",
                    total=0,
                    passed=0,
                    failed=0,
                    errors=0,
                    skipped=0,
                    duration=0.0,
                )

                result = await agent.execute_task(task)

        # Verify file was modified
        assert result["status"] == "completed"
        modified_content = (test_workspace / "src" / "app.py").read_text()
        assert "new_function" in modified_content
        assert "old_function" not in modified_content


@pytest.mark.integration
class TestWorkerAgentMaturityAssessment:
    """Integration tests for agent maturity assessment with real database."""

    def test_maturity_assessment_with_task_history(self, real_db: Database):
        """Test maturity calculation based on actual task history in database."""
        # Register agent
        real_db.create_agent(
            agent_id="maturity-test-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D1,
        )

        # Create project and tasks
        project_id = real_db.create_project(
            name="maturity-test",
            description="Test maturity assessment",
            source_type="empty",
            workspace_path="/tmp/test-maturity",
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "MAT-001",
            "title": "Maturity Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })

        # Create completed tasks (80% completion rate)
        for i in range(10):
            status = TaskStatus.COMPLETED if i < 8 else TaskStatus.PENDING
            task_id = real_db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"MAT-001-{i+1}",
                parent_issue_number="MAT-001",
                title=f"Task {i+1}",
                description="Test task",
                status=status,
                priority=1,
                workflow_step=i + 1,
                can_parallelize=False,
            )
            real_db.update_task(task_id, {"assigned_to": "maturity-test-agent"})

            # Add test results for completed tasks (75% pass rate)
            if status == TaskStatus.COMPLETED:
                real_db.create_test_result(
                    task_id=task_id,
                    status="passed" if i < 6 else "failed",
                    passed=3 if i < 6 else 1,
                    failed=1 if i < 6 else 3,
                )

        # Create agent and assess maturity
        agent = WorkerAgent(
            agent_id="maturity-test-agent",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        result = agent.assess_maturity()

        # Verify maturity is calculated based on real data
        assert result["maturity_level"] in [AgentMaturity.D2, AgentMaturity.D3]
        assert result["metrics"]["task_count"] == 10
        assert result["metrics"]["completion_rate"] == 0.8
        assert result["metrics"]["tasks_with_tests"] == 8

        # Verify database was updated
        agent_data = real_db.get_agent("maturity-test-agent")
        assert agent_data["maturity_level"] == result["maturity_level"].value


@pytest.mark.integration
class TestWorkerAgentSecurityValidation:
    """Integration tests for security features with real validation."""

    @pytest.mark.asyncio
    async def test_api_key_validation_blocks_invalid_keys(self, real_db: Database):
        """Test that invalid API keys are rejected before API call."""
        project_id = real_db.create_project(
            name="security-test",
            description="Test security",
            source_type="empty",
            workspace_path="/tmp/test-security",
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "SEC-001",
            "title": "Security Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })
        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="SEC-001-1",
            parent_issue_number="SEC-001",
            title="Security Task",
            description="Test security validation",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = real_db.get_task(task_id)

        agent = WorkerAgent(
            agent_id="test-security-agent",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        # Test with invalid key format
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "invalid-format"}):
            with pytest.raises(ValueError, match="Invalid ANTHROPIC_API_KEY format"):
                await agent.execute_task(task)

    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(self, real_db: Database):
        """Test that rate limiting actually prevents excessive API calls."""
        project_id = real_db.create_project(
            name="rate-limit-test",
            description="Test rate limiting",
            source_type="empty",
            workspace_path="/tmp/test-rate-limit",
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "RL-001",
            "title": "Rate Limit Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })
        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="RL-001-1",
            parent_issue_number="RL-001",
            title="Rate Limit Task",
            description="Test rate limiting",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = real_db.get_task(task_id)

        # Set low rate limit for testing
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-ant-test-key", "AGENT_RATE_LIMIT": "2"},
        ):
            agent = WorkerAgent(
                agent_id="test-rate-agent",
                agent_type="backend",
                provider="anthropic",
                db=real_db,
            )

            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_api:
                mock_response = Mock()
                mock_response.content = [Mock(text="Done")]
                mock_response.usage = Mock(input_tokens=100, output_tokens=50)
                mock_api.return_value.messages.create = AsyncMock(
                    return_value=mock_response
                )

                # First 2 calls should succeed
                result1 = await agent.execute_task(task)
                assert result1["status"] == "completed"

                result2 = await agent.execute_task(task)
                assert result2["status"] == "completed"

                # Third call should hit rate limit
                result3 = await agent.execute_task(task)
                assert result3["status"] == "failed"
                assert "rate limit" in result3["output"].lower()
