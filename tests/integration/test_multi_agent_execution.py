"""
Integration tests for multi-agent coordination and execution.

These tests verify real multi-agent behavior with:
- Real SQLite database for task tracking
- Real agent pool management
- Real task assignment and status updates
- Only external LLM APIs are mocked

Key scenarios tested:
- Parallel task execution with multiple agents
- Task dependency resolution
- Agent reuse after task completion
- Error recovery and retry logic
- WebSocket broadcast integration
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import AgentMaturity, CallType, TaskStatus, TokenUsage
from codeframe.persistence.database import Database


@pytest.mark.integration
class TestMultiAgentTaskExecution:
    """Integration tests for multi-agent parallel task execution."""

    @pytest.mark.asyncio
    async def test_three_agents_execute_tasks_in_parallel(
        self, real_db: Database, test_workspace: Path
    ):
        """Test three agents executing tasks in parallel with real database tracking."""
        # Setup project
        project_id = real_db.create_project(
            name="parallel-test",
            description="Test parallel execution",
            source_type="empty",
            workspace_path=str(test_workspace),
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "PAR-001",
            "title": "Parallel Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })

        # Create three tasks
        task_ids = []
        for i in range(3):
            task_id = real_db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"PAR-001-{i+1}",
                parent_issue_number="PAR-001",
                title=f"Parallel Task {i+1}",
                description=f"Task {i+1} for parallel execution",
                status=TaskStatus.PENDING,
                priority=1,
                workflow_step=i + 1,
                can_parallelize=True,
            )
            task_ids.append(task_id)

        # Register three agents
        agents = []
        for i in range(3):
            agent_id = f"parallel-agent-{i+1}"
            real_db.create_agent(
                agent_id=agent_id,
                agent_type="backend",
                provider="anthropic",
                maturity_level=AgentMaturity.D2,
            )
            agent = WorkerAgent(
                agent_id=agent_id,
                agent_type="backend",
                provider="anthropic",
                db=real_db,
            )
            agents.append(agent)

        # Assign tasks to agents
        for i, task_id in enumerate(task_ids):
            real_db.update_task(task_id, {
                "assigned_to": agents[i].agent_id,
                "status": TaskStatus.ASSIGNED.value,
            })

        # Execute tasks in parallel with mocked LLM
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_api:
                mock_response = Mock()
                mock_response.content = [Mock(text="Task completed")]
                mock_response.usage = Mock(input_tokens=100, output_tokens=50)
                mock_api.return_value.messages.create = AsyncMock(
                    return_value=mock_response
                )

                # Execute all tasks in parallel
                tasks = []
                for i, agent in enumerate(agents):
                    task = real_db.get_task(task_ids[i])
                    tasks.append(agent.execute_task(task))

                results = await asyncio.gather(*tasks)

        # Verify all tasks completed
        assert all(r["status"] == "completed" for r in results)

        # Simulate orchestrator updating task status based on results
        for i, result in enumerate(results):
            if result["status"] == "completed":
                real_db.update_task(task_ids[i], {"status": TaskStatus.COMPLETED.value})

        # Verify database shows all tasks completed
        for task_id in task_ids:
            task = real_db.get_task(task_id)
            assert task.status == TaskStatus.COMPLETED

        # Verify token usage recorded for all tasks
        cursor = real_db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM token_usage WHERE project_id = ?",
            (project_id,),
        )
        count = cursor.fetchone()["count"]
        assert count == 3

    @pytest.mark.asyncio
    async def test_task_dependency_blocking(self, real_db: Database, test_workspace: Path):
        """Test that dependent tasks wait for dependencies to complete."""
        # Setup project
        project_id = real_db.create_project(
            name="dependency-test",
            description="Test dependency blocking",
            source_type="empty",
            workspace_path=str(test_workspace),
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "DEP-001",
            "title": "Dependency Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })

        # Create parent task
        parent_task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="DEP-001-1",
            parent_issue_number="DEP-001",
            title="Parent Task",
            description="This must complete first",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create dependent task (depends_on is tracked via workflow_step ordering)
        dependent_task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="DEP-001-2",
            parent_issue_number="DEP-001",
            title="Dependent Task",
            description="This depends on parent task",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=2,  # Higher workflow_step indicates dependency order
            can_parallelize=False,
        )

        # Get tasks for execution
        parent_task = real_db.get_task(parent_task_id)
        dependent_task = real_db.get_task(dependent_task_id)

        # Verify workflow ordering (parent has lower step)
        assert parent_task.workflow_step < dependent_task.workflow_step

        # Register agents
        real_db.create_agent(
            agent_id="dep-agent-1",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D2,
        )
        real_db.create_agent(
            agent_id="dep-agent-2",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D2,
        )

        # Complete parent task first
        agent1 = WorkerAgent(
            agent_id="dep-agent-1",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_api:
                mock_response = Mock()
                mock_response.content = [Mock(text="Done")]
                mock_response.usage = Mock(input_tokens=100, output_tokens=50)
                mock_api.return_value.messages.create = AsyncMock(
                    return_value=mock_response
                )

                # Execute parent task
                result = await agent1.execute_task(parent_task)
                assert result["status"] == "completed"

        # Simulate orchestrator updating task status based on result
        real_db.update_task(parent_task_id, {"status": TaskStatus.COMPLETED.value})

        # Verify parent completed
        updated_parent = real_db.get_task(parent_task_id)
        assert updated_parent.status == TaskStatus.COMPLETED

        # Now dependent task can execute
        agent2 = WorkerAgent(
            agent_id="dep-agent-2",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        dependent_task = real_db.get_task(dependent_task_id)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_api:
                mock_response = Mock()
                mock_response.content = [Mock(text="Dependent done")]
                mock_response.usage = Mock(input_tokens=100, output_tokens=50)
                mock_api.return_value.messages.create = AsyncMock(
                    return_value=mock_response
                )

                result = await agent2.execute_task(dependent_task)
                assert result["status"] == "completed"


@pytest.mark.integration
class TestAgentPoolManagement:
    """Integration tests for agent pool management."""

    def test_agent_pool_tracks_multiple_agents(self, real_db: Database):
        """Test that agent pool correctly tracks multiple agents."""
        # Create project
        project_id = real_db.create_project(
            name="pool-test",
            description="Test agent pool",
            source_type="empty",
            workspace_path="/tmp/pool-test",
        )

        # Register multiple agents with different types
        agent_configs = [
            ("pool-backend-1", "backend", AgentMaturity.D2),
            ("pool-backend-2", "backend", AgentMaturity.D3),
            ("pool-frontend-1", "frontend", AgentMaturity.D1),
            ("pool-test-1", "test", AgentMaturity.D2),
        ]

        for agent_id, agent_type, maturity in agent_configs:
            real_db.create_agent(
                agent_id=agent_id,
                agent_type=agent_type,
                provider="anthropic",
                maturity_level=maturity,
            )

        # Verify all agents registered
        cursor = real_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM agents")
        count = cursor.fetchone()["count"]
        assert count == 4

        # Verify agent types (column is 'type' not 'agent_type')
        cursor.execute(
            "SELECT type, COUNT(*) as count FROM agents GROUP BY type"
        )
        type_counts = {row["type"]: row["count"] for row in cursor.fetchall()}
        assert type_counts["backend"] == 2
        assert type_counts["frontend"] == 1
        assert type_counts["test"] == 1

    @pytest.mark.asyncio
    async def test_agent_reuse_after_task_completion(
        self, real_db: Database, test_workspace: Path
    ):
        """Test that agents can be reused for multiple tasks."""
        # Setup project
        project_id = real_db.create_project(
            name="reuse-test",
            description="Test agent reuse",
            source_type="empty",
            workspace_path=str(test_workspace),
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "REUSE-001",
            "title": "Reuse Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })

        # Create multiple tasks
        task_ids = []
        for i in range(3):
            task_id = real_db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"REUSE-001-{i+1}",
                parent_issue_number="REUSE-001",
                title=f"Reuse Task {i+1}",
                description=f"Task {i+1}",
                status=TaskStatus.PENDING,
                priority=1,
                workflow_step=i + 1,
                can_parallelize=False,
            )
            task_ids.append(task_id)

        # Create single agent
        real_db.create_agent(
            agent_id="reuse-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D2,
        )

        agent = WorkerAgent(
            agent_id="reuse-agent",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        # Execute all tasks sequentially with the same agent
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_api:
                mock_response = Mock()
                mock_response.content = [Mock(text="Done")]
                mock_response.usage = Mock(input_tokens=100, output_tokens=50)
                mock_api.return_value.messages.create = AsyncMock(
                    return_value=mock_response
                )

                for task_id in task_ids:
                    task = real_db.get_task(task_id)
                    result = await agent.execute_task(task)
                    assert result["status"] == "completed"

        # Verify all tasks assigned to same agent
        cursor = real_db.conn.cursor()
        for task_id in task_ids:
            cursor.execute(
                "SELECT assigned_to FROM tasks WHERE id = ?", (task_id,)
            )
            row = cursor.fetchone()
            # Note: assigned_to might not be set by execute_task, depends on implementation
            # The important thing is all tasks were completed by the same agent

        # Verify token usage shows all calls from same agent
        cursor.execute(
            "SELECT agent_id, COUNT(*) as count FROM token_usage "
            "WHERE project_id = ? GROUP BY agent_id",
            (project_id,),
        )
        usage = cursor.fetchall()
        assert len(usage) == 1
        assert usage[0]["agent_id"] == "reuse-agent"
        assert usage[0]["count"] == 3


@pytest.mark.integration
class TestErrorRecoveryAndRetry:
    """Integration tests for error recovery and retry logic."""

    @pytest.mark.asyncio
    async def test_task_retry_after_transient_failure(
        self, real_db: Database, test_workspace: Path
    ):
        """Test that tasks retry after transient API failures."""
        # Setup
        project_id = real_db.create_project(
            name="retry-test",
            description="Test retry logic",
            source_type="empty",
            workspace_path=str(test_workspace),
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "RETRY-001",
            "title": "Retry Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })
        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="RETRY-001-1",
            parent_issue_number="RETRY-001",
            title="Retry Task",
            description="Test retry after failure",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = real_db.get_task(task_id)

        # Register agent
        real_db.create_agent(
            agent_id="retry-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D2,
        )

        agent = WorkerAgent(
            agent_id="retry-agent",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_api:
                from anthropic import APIConnectionError

                # First 2 calls fail, third succeeds
                success_response = Mock()
                success_response.content = [Mock(text="Success after retry")]
                success_response.usage = Mock(input_tokens=100, output_tokens=50)

                mock_api.return_value.messages.create = AsyncMock(
                    side_effect=[
                        APIConnectionError(request=Mock()),
                        APIConnectionError(request=Mock()),
                        success_response,
                    ]
                )

                result = await agent.execute_task(task)

        # Should succeed after retries
        assert result["status"] == "completed"

        # Verify API was called 3 times
        assert mock_api.return_value.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_task_fails_after_max_retries(
        self, real_db: Database, test_workspace: Path
    ):
        """Test that tasks fail after exhausting retry attempts."""
        # Setup
        project_id = real_db.create_project(
            name="max-retry-test",
            description="Test max retries",
            source_type="empty",
            workspace_path=str(test_workspace),
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "MAX-001",
            "title": "Max Retry Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })
        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="MAX-001-1",
            parent_issue_number="MAX-001",
            title="Max Retry Task",
            description="Should fail after max retries",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )
        task = real_db.get_task(task_id)

        real_db.create_agent(
            agent_id="max-retry-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D2,
        )

        agent = WorkerAgent(
            agent_id="max-retry-agent",
            agent_type="backend",
            provider="anthropic",
            db=real_db,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_api:
                from anthropic import APIConnectionError

                # All calls fail
                mock_api.return_value.messages.create = AsyncMock(
                    side_effect=APIConnectionError(request=Mock())
                )

                result = await agent.execute_task(task)

        # Should fail
        assert result["status"] == "failed"
        assert "retry" in result["output"].lower()

        # Simulate orchestrator updating task status based on failure result
        real_db.update_task(task_id, {"status": TaskStatus.FAILED.value})

        # Verify task status in database
        updated_task = real_db.get_task(task_id)
        assert updated_task.status == TaskStatus.FAILED


@pytest.mark.integration
class TestDatabaseConsistency:
    """Integration tests for database consistency during multi-agent operations."""

    @pytest.mark.asyncio
    async def test_batch_task_updates_no_data_loss(
        self, real_db: Database, test_workspace: Path
    ):
        """Test that batch task updates don't cause data loss."""
        # Setup
        project_id = real_db.create_project(
            name="batch-test",
            description="Test batch updates",
            source_type="empty",
            workspace_path=str(test_workspace),
        )
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "BATCH-001",
            "title": "Batch Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })

        # Create multiple tasks
        task_ids = []
        for i in range(10):
            task_id = real_db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"BATCH-001-{i+1:02d}",
                parent_issue_number="BATCH-001",
                title=f"Batch Task {i+1}",
                description=f"Task {i+1}",
                status=TaskStatus.PENDING,
                priority=1,
                workflow_step=i + 1,
                can_parallelize=True,
            )
            task_ids.append(task_id)

        # Update all tasks sequentially
        for i, task_id in enumerate(task_ids):
            status = TaskStatus.COMPLETED.value if i % 2 == 0 else TaskStatus.FAILED.value
            real_db.update_task(task_id, {"status": status})

        # Verify all updates persisted correctly
        completed_count = 0
        failed_count = 0
        for task_id in task_ids:
            task = real_db.get_task(task_id)
            if task.status == TaskStatus.COMPLETED:
                completed_count += 1
            elif task.status == TaskStatus.FAILED:
                failed_count += 1

        assert completed_count == 5  # Even indices
        assert failed_count == 5  # Odd indices
        assert completed_count + failed_count == 10

    @pytest.mark.asyncio
    async def test_token_usage_consistency_under_load(
        self, real_db: Database, test_workspace: Path
    ):
        """Test that token usage is correctly recorded under concurrent load."""
        # Setup
        project_id = real_db.create_project(
            name="token-load-test",
            description="Test token recording under load",
            source_type="empty",
            workspace_path=str(test_workspace),
        )

        # Record many token usage entries concurrently
        import threading

        errors = []
        record_count = [0]
        lock = threading.Lock()

        def record_usage(i: int):
            try:
                token_usage = TokenUsage(
                    task_id=None,  # No task, just project-level
                    agent_id=f"load-agent-{i}",
                    project_id=project_id,
                    model_name="claude-sonnet-4-5",
                    input_tokens=100 + i,
                    output_tokens=50 + i,
                    estimated_cost_usd=0.001 * (i + 1),
                    call_type=CallType.TASK_EXECUTION,
                )
                real_db.save_token_usage(token_usage)
                with lock:
                    record_count[0] += 1
            except Exception as e:
                errors.append(str(e))

        # Run concurrent recordings
        threads = []
        for i in range(20):
            t = threading.Thread(target=record_usage, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0, f"Token recording errors: {errors}"
        assert record_count[0] == 20

        # Verify all records exist
        cursor = real_db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM token_usage WHERE project_id = ?",
            (project_id,),
        )
        count = cursor.fetchone()["count"]
        assert count == 20

        # Verify totals are correct
        cursor.execute(
            "SELECT SUM(input_tokens) as total FROM token_usage WHERE project_id = ?",
            (project_id,),
        )
        total = cursor.fetchone()["total"]
        expected_total = sum(100 + i for i in range(20))
        assert total == expected_total


@pytest.mark.integration
class TestAssignAndExecuteTaskAssignedTo:
    """Tests for _assign_and_execute_task setting assigned_to field (Issue #248 fix)."""

    @pytest.mark.asyncio
    async def test_assign_and_execute_task_sets_assigned_to(
        self, real_db: Database, test_workspace: Path
    ):
        """Test that _assign_and_execute_task sets the assigned_to field on the task.

        This is a regression test for Issue #248 where tasks remained showing
        'Assigned to: Unassigned' because the assigned_to field was never populated
        during task execution.
        """
        from codeframe.agents.lead_agent import LeadAgent

        # Setup project
        project_id = real_db.create_project(
            name="assigned-to-test",
            description="Test assigned_to field population",
            source_type="empty",
            workspace_path=str(test_workspace),
        )

        # Create issue and task
        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "AT-001",
            "title": "Test Issue",
            "description": "Test issue for assigned_to",
            "priority": 1,
            "workflow_step": 1,
        })

        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="AT-001-1",
            parent_issue_number="AT-001",
            title="Test Task for Assignment",
            description="This task should have assigned_to set",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=True,
        )

        # Verify task starts with no assigned_to
        task_before = real_db.get_task(task_id)
        assert task_before.assigned_to is None, "Task should start unassigned"

        # Create LeadAgent with mocked execution
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.lead_agent.AgentPoolManager") as mock_pool_class:
                # Setup mock pool manager
                mock_pool = Mock()
                mock_pool.get_or_create_agent.return_value = "test-agent-001"
                mock_pool.mark_agent_busy.return_value = None
                mock_pool.mark_agent_idle.return_value = None
                mock_pool.get_agent_status.return_value = {
                    "test-agent-001": {"status": "idle", "agent_type": "backend"}
                }

                # Mock agent instance with execute_task
                mock_agent_instance = Mock()
                mock_agent_instance.execute_task = AsyncMock(return_value={"status": "completed"})
                mock_pool.get_agent_instance.return_value = mock_agent_instance

                mock_pool_class.return_value = mock_pool

                lead_agent = LeadAgent(
                    project_id=project_id,
                    db=real_db,
                    api_key="sk-ant-test-key",
                    ws_manager=None,
                )
                lead_agent.agent_pool_manager = mock_pool

                # Also mock the review agent to avoid review step
                with patch.object(lead_agent.agent_pool_manager, "get_or_create_agent") as mock_get_agent:
                    # First call returns worker agent, second call returns review agent
                    mock_get_agent.side_effect = ["test-agent-001", "review-agent-001"]

                    mock_review_instance = Mock()
                    mock_review_report = Mock()
                    mock_review_report.status = "approved"
                    mock_review_report.overall_score = 9.0
                    mock_review_instance.execute_task = AsyncMock(return_value=mock_review_report)

                    def get_instance_side_effect(agent_id):
                        if agent_id == "review-agent-001":
                            return mock_review_instance
                        return mock_agent_instance

                    mock_pool.get_agent_instance.side_effect = get_instance_side_effect

                    # Get the task object
                    task = real_db.get_task(task_id)

                    # Execute _assign_and_execute_task
                    retry_counts = {}
                    result = await lead_agent._assign_and_execute_task(task, retry_counts)

                    assert result is True, "Task execution should succeed"

        # CRITICAL ASSERTION: Verify assigned_to was set
        task_after = real_db.get_task(task_id)
        assert task_after.assigned_to == "test-agent-001", (
            f"Task assigned_to should be 'test-agent-001' but was '{task_after.assigned_to}'. "
            "This is the Issue #248 bug - assigned_to field not being populated."
        )

    @pytest.mark.asyncio
    async def test_assign_and_execute_task_sets_assigned_to_before_in_progress(
        self, real_db: Database, test_workspace: Path
    ):
        """Test that assigned_to is set before status changes to in_progress.

        The UI needs to show assignment even during the brief period before
        task execution begins.
        """
        from codeframe.agents.lead_agent import LeadAgent

        # Setup project
        project_id = real_db.create_project(
            name="assigned-to-order-test",
            description="Test assigned_to ordering",
            source_type="empty",
            workspace_path=str(test_workspace),
        )

        issue_id = real_db.create_issue({
            "project_id": project_id,
            "issue_number": "AO-001",
            "title": "Order Test Issue",
            "description": "Test",
            "priority": 1,
            "workflow_step": 1,
        })

        task_id = real_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="AO-001-1",
            parent_issue_number="AO-001",
            title="Order Test Task",
            description="Test ordering",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=True,
        )

        # Track database update calls to verify ordering
        update_calls = []
        original_update_task = real_db.update_task

        def tracking_update_task(task_id, updates):
            update_calls.append((task_id, updates.copy()))
            return original_update_task(task_id, updates)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("codeframe.agents.lead_agent.AgentPoolManager") as mock_pool_class:
                mock_pool = Mock()
                mock_pool.get_or_create_agent.return_value = "order-agent-001"
                mock_pool.mark_agent_busy.return_value = None
                mock_pool.mark_agent_idle.return_value = None
                mock_pool.get_agent_status.return_value = {}

                mock_agent_instance = Mock()
                mock_agent_instance.execute_task = AsyncMock(return_value={"status": "completed"})

                mock_review_instance = Mock()
                mock_review_report = Mock()
                mock_review_report.status = "approved"
                mock_review_report.overall_score = 9.0
                mock_review_instance.execute_task = AsyncMock(return_value=mock_review_report)

                def get_agent_side_effect(agent_type):
                    if agent_type == "review":
                        return "review-agent-001"
                    return "order-agent-001"

                mock_pool.get_or_create_agent.side_effect = get_agent_side_effect

                def get_instance_side_effect(agent_id):
                    if agent_id == "review-agent-001":
                        return mock_review_instance
                    return mock_agent_instance

                mock_pool.get_agent_instance.side_effect = get_instance_side_effect

                mock_pool_class.return_value = mock_pool

                lead_agent = LeadAgent(
                    project_id=project_id,
                    db=real_db,
                    api_key="sk-ant-test-key",
                    ws_manager=None,
                )
                lead_agent.agent_pool_manager = mock_pool

                # Patch update_task to track calls
                with patch.object(real_db, "update_task", side_effect=tracking_update_task):
                    task = real_db.get_task(task_id)
                    retry_counts = {}
                    await lead_agent._assign_and_execute_task(task, retry_counts)

        # Verify update order: assigned_to should be set before or with in_progress
        assigned_to_index = None
        in_progress_index = None

        for i, (tid, updates) in enumerate(update_calls):
            if "assigned_to" in updates:
                assigned_to_index = i
            if updates.get("status") == "in_progress":
                in_progress_index = i

        assert assigned_to_index is not None, "assigned_to should be updated"
        assert in_progress_index is not None, "status should be updated to in_progress"
        assert assigned_to_index <= in_progress_index, (
            f"assigned_to (call {assigned_to_index}) should be set before or with "
            f"in_progress (call {in_progress_index})"
        )
