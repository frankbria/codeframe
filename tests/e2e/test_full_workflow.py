"""
E2E tests for full CodeFRAME workflow (Discovery → Completion).

Tests the complete autonomous coding workflow including:
- Discovery phase (Socratic Q&A)
- Task generation
- Multi-agent execution
- Quality gates enforcement
- Review agent analysis
- Checkpoint creation and restore
- Human-in-the-loop blocker resolution
- Context management (flash save)
- Session lifecycle (pause/resume)
- Cost tracking accuracy

Test fixture: Hello World REST API (3 endpoints)
Expected duration: ~5-10 minutes per test
"""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest
from codeframe.agents.lead_agent import LeadAgent
from codeframe.agents.review_agent import ReviewAgent
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import AgentStatus, AgentType, TaskStatus
from codeframe.core.project import Project
from codeframe.lib.checkpoint_manager import CheckpointManager
from codeframe.lib.context_manager import ContextManager
from codeframe.lib.metrics_tracker import MetricsTracker
from codeframe.lib.quality_gates import QualityGates
from codeframe.persistence.database import Database


# Test fixtures
HELLO_WORLD_PRD_PATH = Path(__file__).parent / "fixtures" / "hello_world_api" / "prd.md"


@pytest.fixture
async def temp_project_dir():
    """Create a temporary directory for test project."""
    temp_dir = tempfile.mkdtemp(prefix="codeframe_e2e_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def test_database(temp_project_dir):
    """Create a test database instance."""
    db_path = temp_project_dir / "test_state.db"
    db = Database(str(db_path))
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def test_project(test_database, temp_project_dir):
    """Create a test project."""
    project = await Project.create(
        name="HelloWorldAPI",
        description="E2E test fixture: Simple REST API with 3 endpoints",
        database=test_database,
        project_path=str(temp_project_dir)
    )
    yield project


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_discovery_phase(test_project, test_database):
    """
    T146: Test discovery phase (Socratic Q&A).

    Validates:
    - Lead agent can engage in discovery Q&A
    - PRD is generated from user responses
    - Discovery state is saved to database
    """
    # Arrange
    lead_agent = LeadAgent(
        agent_id="lead-001",
        project_id=test_project.id,
        db=test_database
    )

    # Simulate discovery Q&A responses
    discovery_responses = [
        "Build a REST API",
        "Python with FastAPI",
        "Health check, simple greeting, personalized greeting",
        "85% test coverage, all tests passing",
        "No, this is for testing"
    ]

    # Act
    await lead_agent.start_discovery(initial_prompt="Build a Hello World API")

    # Simulate answering discovery questions
    for response in discovery_responses:
        await lead_agent.process_discovery_response(response)

    # Assert
    assert lead_agent.discovery_complete is True
    assert lead_agent.prd is not None
    assert "REST API" in lead_agent.prd
    assert "FastAPI" in lead_agent.prd

    # Verify discovery state saved to database
    project_state = await test_database.get_project_state(test_project.id)
    assert project_state["discovery_complete"] is True
    assert project_state["prd"] is not None


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_task_generation(test_project, test_database):
    """
    T147: Test task generation phase.

    Validates:
    - Tasks are generated from PRD
    - Tasks have dependencies properly set
    - Tasks are stored in database
    """
    # Arrange
    lead_agent = LeadAgent(
        agent_id="lead-001",
        project_id=test_project.id,
        db=test_database
    )

    # Load Hello World API PRD
    with open(HELLO_WORLD_PRD_PATH, "r") as f:
        prd_content = f.read()

    # Act
    tasks = await lead_agent.generate_tasks_from_prd(prd_content)

    # Assert
    assert len(tasks) > 0, "Should generate tasks from PRD"
    assert any("health" in task.description.lower() for task in tasks), "Should have health endpoint task"
    assert any("hello" in task.description.lower() for task in tasks), "Should have greeting endpoint task"

    # Verify task dependencies
    setup_tasks = [t for t in tasks if "setup" in t.description.lower()]
    implementation_tasks = [t for t in tasks if "implement" in t.description.lower()]
    assert len(setup_tasks) > 0, "Should have setup tasks"
    assert len(implementation_tasks) > 0, "Should have implementation tasks"

    # Verify tasks stored in database
    stored_tasks = await test_database.get_tasks_by_project(test_project.id)
    assert len(stored_tasks) == len(tasks)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_multi_agent_execution(test_project, test_database, temp_project_dir):
    """
    T148: Test multi-agent execution phase.

    Validates:
    - Multiple worker agents can execute tasks concurrently
    - Agent coordination works correctly
    - Task status updates propagate to all agents
    """
    # Arrange
    backend_agent = WorkerAgent(
        agent_id="backend-001",
        agent_type=AgentType.BACKEND_DEVELOPER,
        project_id=test_project.id,
        db=test_database
    )

    test_agent = WorkerAgent(
        agent_id="test-001",
        agent_type=AgentType.TEST_ENGINEER,
        project_id=test_project.id,
        db=test_database
    )

    # Create simple tasks
    task1 = await test_database.create_task(
        project_id=test_project.id,
        agent_id=backend_agent.agent_id,
        description="Implement /health endpoint",
        status=TaskStatus.PENDING,
        dependencies=[]
    )

    task2 = await test_database.create_task(
        project_id=test_project.id,
        agent_id=test_agent.agent_id,
        description="Write tests for /health endpoint",
        status=TaskStatus.PENDING,
        dependencies=[task1.id]
    )

    # Act
    # Execute backend task
    await backend_agent.execute_task(task1.id)

    # Execute test task (depends on backend task)
    await test_agent.execute_task(task2.id)

    # Assert
    task1_final = await test_database.get_task(task1.id)
    task2_final = await test_database.get_task(task2.id)

    assert task1_final.status == TaskStatus.COMPLETED
    assert task2_final.status == TaskStatus.COMPLETED

    # Verify agent coordination (task2 should not start until task1 completes)
    assert task1_final.completed_at < task2_final.started_at


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_quality_gates_block(test_project, test_database, temp_project_dir):
    """
    T149: Test quality gates block bad code.

    Validates:
    - Quality gates run before task completion
    - Failing tests block task completion
    - Blocker is created with remediation guidance
    """
    # Arrange
    agent = WorkerAgent(
        agent_id="backend-001",
        agent_type=AgentType.BACKEND_DEVELOPER,
        project_id=test_project.id,
        db=test_database
    )

    quality_gates = QualityGates(db=test_database, project_path=str(temp_project_dir))

    # Create a task with intentionally failing test
    task = await test_database.create_task(
        project_id=test_project.id,
        agent_id=agent.agent_id,
        description="Implement endpoint with failing test",
        status=TaskStatus.IN_PROGRESS,
        dependencies=[]
    )

    # Create a test file that will fail
    test_file = temp_project_dir / "test_failing.py"
    test_file.write_text("""
def test_failing():
    assert 1 == 2, "Intentional test failure"
""")

    # Act
    gate_result = await quality_gates.run_all_gates(task.id)

    # Assert
    assert gate_result.passed is False, "Quality gates should fail"
    assert any("test" in failure.gate_name.lower() for failure in gate_result.failures)

    # Verify blocker was created
    blockers = await test_database.get_blockers_by_task(task.id)
    assert len(blockers) > 0, "Blocker should be created"
    assert "test" in blockers[0].question.lower()

    # Verify task status is still IN_PROGRESS (not completed)
    task_final = await test_database.get_task(task.id)
    assert task_final.status == TaskStatus.IN_PROGRESS


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_review_agent_analysis(test_project, test_database, temp_project_dir):
    """
    T150: Test review agent finds issues.

    Validates:
    - Review agent analyzes code quality
    - Security vulnerabilities are detected
    - Review findings are stored in database
    """
    # Arrange
    review_agent = ReviewAgent(
        agent_id="review-001",
        project_id=test_project.id,
        db=test_database
    )

    # Create a code file with SQL injection vulnerability
    code_file = temp_project_dir / "vulnerable.py"
    code_file.write_text("""
def get_user(user_id: str):
    query = f"SELECT * FROM users WHERE id = {user_id}"  # SQL injection!
    return execute_query(query)
""")

    # Create a task for review
    task = await test_database.create_task(
        project_id=test_project.id,
        agent_id=review_agent.agent_id,
        description="Review code for security issues",
        status=TaskStatus.IN_PROGRESS,
        dependencies=[]
    )

    # Act
    await review_agent.execute_task(task.id)

    # Assert
    reviews = await test_database.get_code_reviews(task.id)
    assert len(reviews) > 0, "Should have review findings"

    # Check for SQL injection finding
    sql_injection_found = any(
        "sql" in review.finding.lower() or "injection" in review.finding.lower()
        for review in reviews
    )
    assert sql_injection_found, "Should detect SQL injection vulnerability"

    # Check severity
    critical_findings = [r for r in reviews if r.severity == "critical"]
    assert len(critical_findings) > 0, "SQL injection should be critical severity"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_checkpoint_restore(test_project, test_database, temp_project_dir):
    """
    T151: Test checkpoint creation and restore.

    Validates:
    - Checkpoint can be created with git commit + DB snapshot
    - Checkpoint can be restored successfully
    - Restored state matches checkpoint state
    """
    # Arrange
    checkpoint_mgr = CheckpointManager(
        db=test_database,
        project_path=str(temp_project_dir)
    )

    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=temp_project_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_project_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_project_dir, check=True)

    # Create initial file and commit
    initial_file = temp_project_dir / "initial.txt"
    initial_file.write_text("Initial content")
    subprocess.run(["git", "add", "."], cwd=temp_project_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_project_dir, check=True)

    # Act: Create checkpoint
    checkpoint_id = await checkpoint_mgr.create_checkpoint(
        project_id=test_project.id,
        name="Before changes",
        description="Checkpoint before making changes"
    )

    # Make changes after checkpoint
    changed_file = temp_project_dir / "changed.txt"
    changed_file.write_text("Changed content")
    subprocess.run(["git", "add", "."], cwd=temp_project_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Changes after checkpoint"], cwd=temp_project_dir, check=True)

    # Restore checkpoint
    await checkpoint_mgr.restore_checkpoint(checkpoint_id)

    # Assert
    assert initial_file.exists(), "Initial file should exist after restore"
    assert not changed_file.exists(), "Changed file should not exist after restore"

    # Verify checkpoint metadata
    checkpoint = await test_database.get_checkpoint_by_id(checkpoint_id)
    assert checkpoint is not None
    assert checkpoint.name == "Before changes"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_blocker_resolution(test_project, test_database):
    """
    T152: Test human-in-the-loop blocker resolution.

    Validates:
    - Blocker can be created when agent needs human input
    - Human can resolve blocker with answer
    - Agent can continue execution after resolution
    """
    # Arrange
    agent = WorkerAgent(
        agent_id="backend-001",
        agent_type=AgentType.BACKEND_DEVELOPER,
        project_id=test_project.id,
        db=test_database
    )

    task = await test_database.create_task(
        project_id=test_project.id,
        agent_id=agent.agent_id,
        description="Implement feature requiring human decision",
        status=TaskStatus.IN_PROGRESS,
        dependencies=[]
    )

    # Act: Create blocker
    blocker = await test_database.create_blocker(
        task_id=task.id,
        agent_id=agent.agent_id,
        question="Should we use OAuth 2.0 or JWT for authentication?",
        priority="high",
        context={"task": task.description}
    )

    # Simulate human resolution
    await test_database.resolve_blocker(
        blocker_id=blocker.id,
        resolution="Use JWT with refresh tokens",
        resolved_by="human_user"
    )

    # Assert
    resolved_blocker = await test_database.get_blocker(blocker.id)
    assert resolved_blocker.status == "resolved"
    assert resolved_blocker.resolution == "Use JWT with refresh tokens"

    # Verify agent can access resolution
    agent_blockers = await test_database.get_blockers_by_agent(agent.agent_id)
    resolved_blockers = [b for b in agent_blockers if b.status == "resolved"]
    assert len(resolved_blockers) > 0


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_context_flash_save(test_project, test_database):
    """
    T153: Test context management (flash save).

    Validates:
    - Context items can be saved to database
    - Flash save archives COLD tier items
    - Token usage is reduced after flash save
    """
    # Arrange
    agent = WorkerAgent(
        agent_id="backend-001",
        agent_type=AgentType.BACKEND_DEVELOPER,
        project_id=test_project.id,
        db=test_database
    )

    context_mgr = ContextManager(db=test_database)

    # Add many context items to trigger flash save
    from codeframe.core.models import ContextItemType
    for i in range(100):
        await agent.save_context_item(
            item_type=ContextItemType.CODE,
            content=f"Context item {i}" * 100  # Make it large
        )

    # Act: Trigger flash save
    if await agent.should_flash_save():
        result = await agent.flash_save()

        # Assert
        assert result["success"] is True
        assert result["items_archived"] > 0
        assert result["reduction_percentage"] > 20  # Should reduce by at least 20%

        # Verify COLD items are archived
        hot_items = await agent.load_context(tier="hot")
        warm_items = await agent.load_context(tier="warm")
        cold_items = await context_mgr.get_context_items(
            project_id=test_project.id,
            agent_id=agent.agent_id,
            tier="cold"
        )

        assert len(hot_items) > 0, "Should have HOT tier items"
        assert len(cold_items) > 0, "Should have COLD tier items"
        assert result["items_archived"] == len(cold_items)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_session_lifecycle(test_project, test_database, temp_project_dir):
    """
    T154: Test session lifecycle (pause/resume).

    Validates:
    - Session state can be saved
    - Session state can be restored after CLI restart
    - Progress and next actions are preserved
    """
    # Arrange
    from codeframe.core.session_manager import SessionManager

    session_mgr = SessionManager(project_path=str(temp_project_dir))

    # Create initial session state
    initial_state = {
        "summary": "Completed Task #1, Task #2",
        "completed_tasks": [1, 2],
        "next_actions": [
            "Implement Task #3",
            "Write tests for Task #3"
        ],
        "current_plan": "Build Hello World API",
        "active_blockers": [],
        "progress_pct": 40.0
    }

    # Act: Save session
    session_mgr.save_session(initial_state)

    # Simulate CLI restart by creating new SessionManager
    new_session_mgr = SessionManager(project_path=str(temp_project_dir))
    restored_state = new_session_mgr.load_session()

    # Assert
    assert restored_state is not None
    assert restored_state["last_session"]["summary"] == initial_state["summary"]
    assert restored_state["next_actions"] == initial_state["next_actions"]
    assert restored_state["progress_pct"] == initial_state["progress_pct"]


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_cost_tracking_accuracy(test_project, test_database):
    """
    T155: Test cost tracking accuracy.

    Validates:
    - Token usage is recorded after task execution
    - Costs are calculated correctly based on model pricing
    - Cost accuracy is within ±5%
    """
    # Arrange
    agent = WorkerAgent(
        agent_id="backend-001",
        agent_type=AgentType.BACKEND_DEVELOPER,
        project_id=test_project.id,
        db=test_database
    )

    metrics_tracker = MetricsTracker(db=test_database)

    task = await test_database.create_task(
        project_id=test_project.id,
        agent_id=agent.agent_id,
        description="Simple task for cost tracking",
        status=TaskStatus.IN_PROGRESS,
        dependencies=[]
    )

    # Simulate task execution with known token usage
    expected_input_tokens = 1000
    expected_output_tokens = 500
    model = "claude-sonnet-4-5"

    # Act: Record token usage
    await metrics_tracker.record_token_usage(
        project_id=test_project.id,
        agent_id=agent.agent_id,
        task_id=task.id,
        model=model,
        input_tokens=expected_input_tokens,
        output_tokens=expected_output_tokens,
        call_type="task_execution"
    )

    # Calculate expected cost
    # Sonnet 4.5: $3/MTok input, $15/MTok output
    expected_cost = (expected_input_tokens / 1_000_000 * 3) + (expected_output_tokens / 1_000_000 * 15)

    # Get actual cost from tracker
    costs = await metrics_tracker.get_project_costs(test_project.id)
    actual_cost = costs["total_cost"]

    # Assert: Within ±5% tolerance
    tolerance = expected_cost * 0.05
    assert abs(actual_cost - expected_cost) <= tolerance, \
        f"Cost accuracy failed: expected {expected_cost}, got {actual_cost}"

    # Verify cost breakdown
    assert costs["by_agent"][agent.agent_id] == actual_cost
    assert costs["by_model"][model] == actual_cost
