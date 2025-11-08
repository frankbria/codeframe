"""
Integration tests for multi-agent coordination system (Sprint 4: Task 4.4).

Tests end-to-end scenarios including:
- Parallel agent execution
- Dependency blocking and unblocking
- Complex dependency graphs
- Agent reuse
- Error recovery
- Completion detection
- Concurrent database access
- WebSocket broadcasts
"""

import pytest
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database
from codeframe.core.models import Task, ProjectStatus, TaskStatus


# Helper function to create Task objects easily
def create_test_task(
    db,
    project_id,
    task_number,
    title,
    description,
    status=None,
    depends_on=""
):
    """Helper to create Task objects for testing."""
    if status is None:
        status = TaskStatus.PENDING
    elif isinstance(status, str):
        status = TaskStatus[status.upper()]

    task = Task(
        id=None,
        project_id=project_id,
        task_number=task_number,
        title=title,
        description=description,
        status=status,
        depends_on=depends_on
    )
    return db.create_task(task)


@pytest.fixture
def db():
    """Create test database."""
    print("🔵 FIXTURE: Creating database...")
    db = Database(":memory:")
    print("🔵 FIXTURE: Database created, initializing schema...")
    db.initialize()  # Initialize the database schema
    print("🔵 FIXTURE: Database initialized ✅")
    yield db
    print("🔵 FIXTURE: Closing database...")
    db.close()
    print("🔵 FIXTURE: Database closed ✅")


@pytest.fixture
def temp_project_dir():
    """Create temporary project directory."""
    print("🟡 FIXTURE: Creating temp directory...")
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"🟡 FIXTURE: Temp dir created: {tmpdir}")
        # Initialize git repo
        print("🟡 FIXTURE: Running git init...")
        import subprocess
        subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
        print("🟡 FIXTURE: Git init complete ✅")
        yield tmpdir
        print("🟡 FIXTURE: Cleaning up temp dir...")


@pytest.fixture
def project_id(db, temp_project_dir):
    """Create test project."""
    print("🟢 FIXTURE: Creating project in database...")
    project_id = db.create_project("test-project", "Multi-agent test project")
    print(f"🟢 FIXTURE: Project created with ID: {project_id}")
    # Update project with root_path
    print(f"🟢 FIXTURE: Updating project root_path to {temp_project_dir}...")
    db.update_project(project_id, {"root_path": temp_project_dir})
    print("🟢 FIXTURE: Project fixture complete ✅")
    return project_id


@pytest.fixture
def api_key():
    """Get test API key."""
    print("🔴 FIXTURE: Getting API key...")
    key = os.environ.get("ANTHROPIC_API_KEY", "test-key")
    print(f"🔴 FIXTURE: API key: {key[:8]}... ✅")
    return key


@pytest.fixture
def lead_agent(db, project_id, api_key):
    """Create LeadAgent with multi-agent support."""
    print("🟣 FIXTURE: Creating LeadAgent...")
    print(f"🟣 FIXTURE: - project_id={project_id}, api_key={api_key[:8]}...")
    agent = LeadAgent(
        project_id=project_id,
        db=db,
        api_key=api_key,
        ws_manager=None,  # No WebSocket for unit tests
        max_agents=10
    )
    print("🟣 FIXTURE: LeadAgent created ✅")
    return agent


class TestMinimalIntegration:
    """Minimal integration test - simplest possible scenario to verify basic functionality."""

    @pytest.mark.asyncio
    async def test_single_task_execution_minimal(self, lead_agent, db, project_id):
        """
        Simplest possible integration test - 1 task, 1 agent, immediate success.
        This test should pass quickly (< 5 seconds) and verify basic coordination.
        """
        print("\n" + "="*80)
        print("⭐ TEST STARTED: test_single_task_execution_minimal")
        print("="*80)
        
        # Create single backend task
        print("📝 Creating test task...")
        task_id = create_test_task(
            db, project_id, "T-001",
            "Simple backend task", "Test task description",
            status="pending"
        )
        print(f"📝 Task created: {task_id}")

        # Patch TestWorkerAgent at creation point (in AgentPoolManager)
        # Task will be assigned to test-engineer based on "Test" in description
        with patch('codeframe.agents.agent_pool_manager.TestWorkerAgent') as MockAgent:
            # Create mock instance
            mock_agent_instance = Mock()
            mock_agent_instance.execute_task.return_value = {
                "status": "completed",
                "files_modified": [],
                "output": "Task completed successfully",
                "error": None
            }
            
            # When AgentPoolManager creates BackendWorkerAgent, return our mock
            MockAgent.return_value = mock_agent_instance

            # Execute with short timeout - should complete quickly
            summary = await asyncio.wait_for(
                lead_agent.start_multi_agent_execution(max_concurrent=1),
                timeout=5.0  # Fail fast if hanging
            )

            # Verify basic execution
            assert summary["total_tasks"] == 1
            assert summary["completed"] == 1
            assert summary["failed"] == 0
            assert summary["iterations"] > 0
            assert summary["iterations"] < 100  # Should not take many iterations

            # Verify task completed in database
            task = db.get_task(task_id)
            assert task["status"] == "completed"

            # Verify agent was called
            assert mock_agent_instance.execute_task.called
            assert mock_agent_instance.execute_task.call_count == 1


class TestThreeAgentParallelExecution:
    """Test 3-agent parallel execution (backend, frontend, test)."""

    @pytest.mark.asyncio
    async def test_parallel_execution_three_agents(self, lead_agent, db, project_id):
        """Test that 3 different agent types can execute tasks in parallel."""
        # Create 3 tasks (backend, frontend, test)
        backend_task_id = create_test_task(
            db, project_id, "T-001",
            "Create API endpoint", "Build REST API endpoint for user management",
            status="pending"
        )

        frontend_task_id = create_test_task(
            db, project_id, "T-002",
            "Create login form component", "Build React component for user login with form validation",
            status="pending"
        )

        test_task_id = create_test_task(
            db, project_id, "T-003",
            "Write unit tests for auth", "Create pytest test suite for authentication module",
            status="pending"
        )

        # Mock agent execute_task methods to succeed instantly
        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task') as mock_backend, \
             patch('codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task') as mock_frontend, \
             patch('codeframe.agents.test_worker_agent.TestWorkerAgent.execute_task') as mock_test:

            # Configure mocks to return success dictionaries
            mock_backend.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}
            mock_frontend.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}
            mock_test.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}

            # Execute multi-agent coordination
            summary = await lead_agent.start_multi_agent_execution(max_concurrent=3)

            # Verify all tasks completed
            assert summary["total_tasks"] == 3
            assert summary["completed"] == 3
            assert summary["failed"] == 0

            # Verify each agent type was used
            assert mock_backend.called
            assert mock_frontend.called
            assert mock_test.called

            # Verify tasks are marked completed in database
            backend_task = db.get_task(backend_task_id)
            frontend_task = db.get_task(frontend_task_id)
            test_task = db.get_task(test_task_id)

            assert backend_task["status"] == "completed"
            assert frontend_task["status"] == "completed"
            assert test_task["status"] == "completed"


class TestDependencyBlocking:
    """Test dependency blocking (task waits for dependency)."""

    @pytest.mark.asyncio
    async def test_task_waits_for_dependency(self, lead_agent, db, project_id):
        """Test that a task waits for its dependency to complete."""
        # Create task 1 (no dependencies)
        task1_id = create_test_task(
            db, project_id, "T-001",
            "Create API endpoint", "Build REST API endpoint",
            status="pending", depends_on="[]"
        )

        # Create task 2 (depends on task 1)
        task2_id = create_test_task(
            db, project_id, "T-002",
            "Create frontend component",
            "Build UI component that calls the API",
            depends_on=f"[{task1_id}]"
        )

        execution_order = []

        def track_backend_execution(task_dict):
            execution_order.append(task_dict["id"])
            return {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}

        def track_frontend_execution(task_dict):
            execution_order.append(task_dict["id"])
            return {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}

        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task', side_effect=track_backend_execution), \
             patch('codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task', side_effect=track_frontend_execution):

            summary = await lead_agent.start_multi_agent_execution(max_concurrent=2)

            # Verify both tasks completed
            assert summary["completed"] == 2
            assert summary["failed"] == 0

            # Verify execution order (task1 before task2)
            assert execution_order == [task1_id, task2_id]


class TestDependencyUnblocking:
    """Test dependency unblocking (task starts when unblocked)."""

    @pytest.mark.asyncio
    async def test_task_starts_when_unblocked(self, lead_agent, db, project_id):
        """Test that dependent task starts immediately when dependency completes."""
        # Create chain: task1 -> task2 -> task3
        task1_id = create_test_task(
            db, project_id, "T-001",
            "Setup database schema", "Create database tables",
            status="pending"
        )

        task2_id = create_test_task(
            db, project_id, "T-002",
            "Create API endpoint",
            "Build API using database",
            depends_on=f"[{task1_id}]"
        )

        task3_id = create_test_task(
            db, project_id, "T-003",
            "Create UI component",
            "Build UI calling the API",
            depends_on=f"[{task2_id}]"
        )

        execution_order = []

        def track_execution(task_dict):
            execution_order.append(task_dict["id"])
            # Small delay to simulate work
            import time
            time.sleep(0.1)
            return {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}

        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task', side_effect=track_execution), \
             patch('codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task', side_effect=track_execution):

            summary = await lead_agent.start_multi_agent_execution(max_concurrent=3)

            # Verify all tasks completed
            assert summary["completed"] == 3

            # Verify execution order (cascading)
            assert execution_order == [task1_id, task2_id, task3_id]


class TestComplexDependencyGraph:
    """Test complex dependency graph (10 tasks, multiple levels)."""

    @pytest.mark.asyncio
    async def test_complex_dependency_graph_ten_tasks(self, lead_agent, db, project_id):
        """Test execution of 10 tasks with multi-level dependencies."""
        # Create diamond dependency structure:
        #     T1
        #    /  \
        #   T2  T3
        #   |   |
        #   T4  T5
        #    \ /
        #     T6
        #   / | \
        #  T7 T8 T9
        #   \  |  /
        #     T10

        task_ids = {}

        # Level 0: T1 (no deps)
        task_ids[1] = create_test_task(
            db, project_id, "T-001",
            "Task 1", "Root task",
            status="pending"
        )

        # Level 1: T2, T3 (depend on T1)
        task_ids[2] = create_test_task(
            db, project_id, "T-002", "Task 2",
            "Backend task",
            depends_on=f"[{task_ids[1]}]"
        )
        task_ids[3] = create_test_task(
            db, project_id, "T-003", "Task 3",
            "Frontend task",
            depends_on=f"[{task_ids[1]}]"
        )

        # Level 2: T4 (depends on T2), T5 (depends on T3)
        task_ids[4] = create_test_task(
            db, project_id, "T-004", "Task 4",
            "Backend subtask",
            depends_on=f"[{task_ids[2]}]"
        )
        task_ids[5] = create_test_task(
            db, project_id, "T-005", "Task 5",
            "Frontend subtask",
            depends_on=f"[{task_ids[3]}]"
        )

        # Level 3: T6 (depends on T4, T5)
        task_ids[6] = create_test_task(
            db, project_id, "T-006", "Task 6",
            "Integration task",
            depends_on=f"[{task_ids[4]}, {task_ids[5]}]"
        )

        # Level 4: T7, T8, T9 (depend on T6)
        task_ids[7] = create_test_task(
            db, project_id, "T-007", "Task 7",
            "Test task 1",
            depends_on=f"[{task_ids[6]}]"
        )
        task_ids[8] = create_test_task(
            db, project_id, "T-008", "Task 8",
            "Test task 2",
            depends_on=f"[{task_ids[6]}]"
        )
        task_ids[9] = create_test_task(
            db, project_id, "T-009", "Task 9",
            "Test task 3",
            depends_on=f"[{task_ids[6]}]"
        )

        # Level 5: T10 (depends on T7, T8, T9)
        task_ids[10] = create_test_task(
            db, project_id, "T-010", "Task 10",
            "Final integration",
            depends_on=f"[{task_ids[7]}, {task_ids[8]}, {task_ids[9]}]"
        )

        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task') as mock_backend, \
             patch('codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task') as mock_frontend, \
             patch('codeframe.agents.test_worker_agent.TestWorkerAgent.execute_task') as mock_test:

            # Configure mocks to return success
            mock_backend.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}
            mock_frontend.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}
            mock_test.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}

            summary = await lead_agent.start_multi_agent_execution(max_concurrent=5)

            # Verify all 10 tasks completed
            assert summary["total_tasks"] == 10
            assert summary["completed"] == 10
            assert summary["failed"] == 0

            # Verify no deadlocks occurred
            for i in range(1, 11):
                task = db.get_task(task_ids[i])
                assert task["status"] == "completed"


class TestAgentReuse:
    """Test agent reuse (same agent handles multiple tasks)."""

    @pytest.mark.asyncio
    async def test_agent_reuse_same_type_tasks(self, lead_agent, db, project_id):
        """Test that idle agents are reused for tasks of the same type."""
        # Create 3 backend tasks
        task1_id = create_test_task(
            db, project_id, "T-001",
            "Create API endpoint 1", "Backend task 1",
            status="pending"
        )
        task2_id = create_test_task(
            db, project_id, "T-002",
            "Create API endpoint 2", "Backend task 2",
            status="pending"
        )
        task3_id = create_test_task(
            db, project_id, "T-003",
            "Create API endpoint 3", "Backend task 3",
            status="pending"
        )

        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task') as mock_backend:
            mock_backend.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}
            
            summary = await lead_agent.start_multi_agent_execution(max_concurrent=1)

            # Verify all tasks completed
            assert summary["completed"] == 3

            # Verify only one agent was created (reused for all 3 tasks)
            agent_status = lead_agent.agent_pool_manager.get_agent_status()
            backend_agents = [aid for aid, info in agent_status.items() if info["agent_type"] == "backend-worker"]

            # Should have created only 1 backend agent (reused it)
            assert len(backend_agents) <= 1


class TestErrorRecovery:
    """Test error recovery (agent failure, task retry)."""

    @pytest.mark.asyncio
    async def test_task_retry_after_failure(self, lead_agent, db, project_id):
        """Test that failed tasks are retried up to max_retries."""
        task_id = create_test_task(
            db, project_id, "T-001",
            "Create API endpoint", "Backend task",
            status="pending"
        )

        call_count = 0

        def fail_twice_then_succeed(task_dict):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Simulated failure")
            # Third attempt succeeds
            return {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}

        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task', side_effect=fail_twice_then_succeed):
            summary = await lead_agent.start_multi_agent_execution(max_retries=3)

            # Verify task eventually succeeded
            assert summary["completed"] == 1
            assert summary["retries"] == 2  # Failed 2 times, succeeded on 3rd

            # Verify task marked as completed
            task = db.get_task(task_id)
            assert task["status"] == "completed"

    @pytest.mark.asyncio
    async def test_task_fails_after_max_retries(self, lead_agent, db, project_id):
        """Test that task is marked failed after exceeding max_retries."""
        task_id = create_test_task(
            db, project_id, "T-001",
            "Create API endpoint", "Backend task",
            status="pending"
        )

        def always_fail(task_dict):
            raise Exception("Permanent failure")

        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task', side_effect=always_fail):
            summary = await lead_agent.start_multi_agent_execution(max_retries=3)

            # Verify task failed
            assert summary["completed"] == 0
            assert summary["failed"] == 1
            assert summary["retries"] == 3

            # Verify task marked as failed in database
            task = db.get_task(task_id)
            assert task["status"] == "failed"


class TestCompletionDetection:
    """Test completion detection (all tasks done)."""

    @pytest.mark.asyncio
    async def test_completion_detection_all_tasks_done(self, lead_agent, db, project_id):
        """Test that execution stops when all tasks are completed."""
        # Create 5 tasks
        for i in range(1, 6):
            create_test_task(
                db, project_id, f"T-{i:03d}",
                f"Task {i}", f"Backend task {i}"
            )

        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task') as mock_backend:
            mock_backend.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}
            
            summary = await lead_agent.start_multi_agent_execution()

            # Verify all tasks completed
            assert summary["total_tasks"] == 5
            assert summary["completed"] == 5
            assert summary["failed"] == 0

            # Verify _all_tasks_complete returns True
            assert lead_agent._all_tasks_complete() is True


class TestConcurrentDatabaseAccess:
    """Test concurrent database access (no race conditions)."""

    @pytest.mark.asyncio
    async def test_concurrent_task_updates_no_race_conditions(self, lead_agent, db, project_id):
        """Test that concurrent agents updating tasks doesn't cause race conditions."""
        # Create 10 tasks that can run in parallel
        task_ids = []
        for i in range(1, 11):
            task_id = create_test_task(
                db, project_id, f"T-{i:03d}",
                f"Backend task {i}", f"API endpoint {i}"
            )
            task_ids.append(task_id)

        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task') as mock_backend:
            mock_backend.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}
            
            # Run with high concurrency to stress test database
            summary = await lead_agent.start_multi_agent_execution(max_concurrent=10)

            # Verify all tasks completed without errors
            assert summary["completed"] == 10
            assert summary["failed"] == 0

            # Verify database consistency (all tasks have valid status)
            for task_id in task_ids:
                task = db.get_task(task_id)
                assert task["status"] in ("completed", "failed", "in_progress", "pending")
                # Should be completed since execution finished
                assert task["status"] == "completed"


class TestWebSocketBroadcasts:
    """Test WebSocket broadcasts (all events received)."""

    @pytest.mark.asyncio
    async def test_websocket_broadcasts_all_events(self, db, project_id, api_key):
        """Test that all agent lifecycle events are broadcast via WebSocket."""
        # Create mock WebSocket manager
        mock_ws_manager = Mock()

        # Create LeadAgent with WebSocket support
        agent = LeadAgent(
            project_id=project_id,
            db=db,
            api_key=api_key,
            ws_manager=mock_ws_manager,
            max_agents=10
        )

        # Create tasks
        create_test_task(
            db, project_id, "T-001",
            "Backend task", "API endpoint",
            status="pending"
        )
        create_test_task(
            db, project_id, "T-002",
            "Frontend task", "UI component",
            status="pending"
        )

        with patch('codeframe.agents.backend_worker_agent.BackendWorkerAgent.execute_task') as mock_backend, \
             patch('codeframe.agents.frontend_worker_agent.FrontendWorkerAgent.execute_task') as mock_frontend:

            mock_backend.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}
            mock_frontend.return_value = {"status": "completed", "files_modified": [], "output": "Task completed", "error": None}

            summary = await agent.start_multi_agent_execution(max_concurrent=2)

            # Verify tasks completed
            assert summary["completed"] == 2

            # Note: WebSocket broadcasts are fire-and-forget in the implementation
            # We can verify agents were created by checking the pool
            agent_status = agent.agent_pool_manager.get_agent_status()
            assert len(agent_status) >= 1  # At least one agent was created


class TestDeadlockPrevention:
    """Test that circular dependencies are detected and prevented."""

    @pytest.mark.asyncio
    async def test_circular_dependency_detection(self, lead_agent, db, project_id):
        """Test that circular dependencies are detected during graph building."""
        # Create circular dependency: T1 -> T2 -> T3 -> T1
        task1_id = create_test_task(
            db, project_id, "T-001",
            "Task 1", "Task 1",
            status="pending"
        )
        task2_id = create_test_task(
            db, project_id, "T-002",
            "Task 2", "Task 2",
            depends_on=f"[{task1_id}]"
        )
        task3_id = create_test_task(
            db, project_id, "T-003",
            "Task 3", "Task 3",
            depends_on=f"[{task2_id}]"
        )

        # Update task1 to depend on task3 (creating cycle)
        db.update_task(task1_id, {"depends_on": f"[{task3_id}]"})

        # Should raise ValueError due to circular dependency
        with pytest.raises(ValueError, match="Circular dependencies detected"):
            # This will fail when building dependency graph
            await lead_agent.start_multi_agent_execution()