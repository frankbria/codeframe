"""Integration tests for agent maturity assessment system.

Tests the complete maturity workflow:
- Maturity calculation based on task history
- Maturity level progression (D1 -> D2 -> D3 -> D4)
- Maturity demotion when performance degrades
- Dashboard API returning maturity information
"""

import pytest
import json
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import AgentMaturity, TaskStatus
from codeframe.persistence.database import Database


@pytest.fixture
def db():
    """Create in-memory database for testing."""
    database = Database(":memory:")
    database.initialize()
    return database


@pytest.fixture
def setup_project(db):
    """Create a project and issue for testing."""
    project_id = db.create_project(
        name="maturity-test-project",
        description="Project for maturity testing",
        source_type="empty",
        workspace_path="/tmp/maturity-test",
    )
    issue_id = db.create_issue({
        "project_id": project_id,
        "issue_number": "1.0",
        "title": "Test issue for maturity",
        "description": "Testing maturity assessment",
    })
    return {"project_id": project_id, "issue_id": issue_id}


class TestMaturityProgression:
    """Test maturity level progression based on performance."""

    def test_maturity_progression_novice_to_expert(self, db, setup_project):
        """Test agent maturity progresses from D1 to D4 as performance improves."""
        project_id = setup_project["project_id"]
        issue_id = setup_project["issue_id"]

        # Create agent at D1 (novice)
        db.create_agent(
            agent_id="progression-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D1,
        )

        agent = WorkerAgent(
            agent_id="progression-agent",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        # Phase 1: Novice (D1) - No tasks yet
        result1 = agent.assess_maturity()
        assert result1["maturity_level"] == AgentMaturity.D1
        assert result1["metrics"]["task_count"] == 0

        # Phase 2: Still Novice (D1) - Poor completion rate
        for i in range(10):
            status = TaskStatus.COMPLETED if i < 3 else TaskStatus.FAILED
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.0",
                title=f"Phase 2 Task {i+1}",
                description="Test",
                status=status,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "progression-agent"})

        result2 = agent.assess_maturity()
        assert result2["maturity_level"] == AgentMaturity.D1
        assert result2["metrics"]["completion_rate"] == 0.3

        # Phase 3: Intermediate (D2) - Better completion with passing tests
        for i in range(20):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.2.{i+1}",
                parent_issue_number="1.0",
                title=f"Phase 3 Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "progression-agent"})
            db.create_test_result(
                task_id=task_id,
                status="passed",
                passed=6,
                failed=4,  # 60% pass rate
            )

        result3 = agent.assess_maturity()
        # Should be D2 (intermediate) with improved scores
        assert result3["maturity_level"] in [AgentMaturity.D2, AgentMaturity.D3]
        assert result3["maturity_score"] >= 0.5

        # Phase 4: Expert (D4) - Excellent completion with 100% passing tests
        for i in range(50):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.3.{i+1}",
                parent_issue_number="1.0",
                title=f"Phase 4 Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "progression-agent"})
            db.create_test_result(
                task_id=task_id,
                status="passed",
                passed=10,
                failed=0,  # 100% pass rate
            )

        result4 = agent.assess_maturity()
        # Should be D4 (expert) with high scores
        assert result4["maturity_level"] == AgentMaturity.D4
        assert result4["maturity_score"] >= 0.9

    def test_maturity_demotion_on_degraded_performance(self, db, setup_project):
        """Test maturity level can decrease when performance degrades."""
        project_id = setup_project["project_id"]
        issue_id = setup_project["issue_id"]

        # Start agent at D3 (advanced)
        db.create_agent(
            agent_id="demotion-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3,
        )

        # First, create history that justifies D3
        for i in range(20):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.0",
                title=f"Good Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "demotion-agent"})
            db.create_test_result(
                task_id=task_id,
                status="passed",
                passed=9,
                failed=1,
            )

        agent = WorkerAgent(
            agent_id="demotion-agent",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        result_before = agent.assess_maturity()
        initial_level = result_before["maturity_level"]
        assert initial_level in [AgentMaturity.D3, AgentMaturity.D4]

        # Now add many failed tasks to degrade performance
        for i in range(40):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.2.{i+1}",
                parent_issue_number="1.0",
                title=f"Failed Task {i+1}",
                description="Test",
                status=TaskStatus.FAILED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "demotion-agent"})

        result_after = agent.assess_maturity()

        # Should be demoted due to poor completion rate
        assert result_after["maturity_level"].value < initial_level.value or \
               result_after["maturity_score"] < result_before["maturity_score"]


class TestMaturityPersistence:
    """Test maturity data persistence and retrieval."""

    def test_maturity_persists_across_agent_instances(self, db, setup_project):
        """Test that maturity level persists across agent recreations."""
        project_id = setup_project["project_id"]
        issue_id = setup_project["issue_id"]

        # Create agent and set up for D2
        db.create_agent(
            agent_id="persistent-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D1,
        )

        # Create tasks to achieve D2
        for i in range(10):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.0",
                title=f"Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "persistent-agent"})

        agent1 = WorkerAgent(
            agent_id="persistent-agent",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        result1 = agent1.assess_maturity()
        maturity_level = result1["maturity_level"]

        # Create new agent instance
        agent2 = WorkerAgent(
            agent_id="persistent-agent",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        # Verify maturity persisted
        agent_data = db.get_agent("persistent-agent")
        assert agent_data["maturity_level"] == maturity_level.value

        # Re-assess should return same level
        result2 = agent2.assess_maturity()
        assert result2["maturity_level"] == maturity_level

    def test_maturity_metrics_accessible_via_api(self, db, setup_project):
        """Test that maturity metrics are included in agent API response."""
        project_id = setup_project["project_id"]
        issue_id = setup_project["issue_id"]

        # Create and assess agent
        db.create_agent(
            agent_id="api-test-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D1,
        )
        db.assign_agent_to_project(project_id, "api-test-agent", role="worker")

        for i in range(5):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.0",
                title=f"Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "api-test-agent"})

        agent = WorkerAgent(
            agent_id="api-test-agent",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )
        agent.assess_maturity()

        # Get agents for project (simulating API call)
        agents = db.get_agents_for_project(project_id, active_only=True)

        assert len(agents) == 1
        agent_data = agents[0]
        assert agent_data["maturity_level"] is not None
        assert agent_data["metrics"] is not None

        # Parse metrics JSON
        metrics = json.loads(agent_data["metrics"]) if isinstance(agent_data["metrics"], str) else agent_data["metrics"]
        assert "maturity_score" in metrics
        assert "completion_rate" in metrics
        assert "last_assessed" in metrics


class TestMaturityAuditTrail:
    """Test maturity assessment audit logging."""

    def test_maturity_changes_logged(self, db, setup_project):
        """Test that maturity assessments are logged to audit trail."""
        # Create agent
        db.create_agent(
            agent_id="audit-test-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D1,
        )

        agent = WorkerAgent(
            agent_id="audit-test-agent",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        # Assess maturity (creates audit log)
        agent.assess_maturity()

        # Query audit log
        cursor = db.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM audit_logs
            WHERE event_type = 'agent.maturity.assessed'
            ORDER BY timestamp DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()

        assert row is not None
        metadata = json.loads(row["metadata"])
        assert "new_maturity" in metadata
        assert metadata["new_maturity"] == "directive"
        assert "maturity_score" in metadata


class TestMaturityTriggers:
    """Test automatic maturity assessment triggers."""

    def test_should_assess_after_enough_new_tasks(self, db, setup_project):
        """Test should_assess_maturity returns True after enough new completed tasks."""
        project_id = setup_project["project_id"]
        issue_id = setup_project["issue_id"]

        db.create_agent(
            agent_id="trigger-test-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D1,
        )

        agent = WorkerAgent(
            agent_id="trigger-test-agent",
            agent_type="backend",
            provider="anthropic",
            db=db,
        )

        # First assessment
        agent.assess_maturity()

        # After assessment, should not immediately need re-assessment
        assert agent.should_assess_maturity(min_tasks_since_last=5) is False

        # Add 5 completed tasks
        for i in range(5):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.0",
                title=f"Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "trigger-test-agent"})

        # Now should need reassessment
        assert agent.should_assess_maturity(min_tasks_since_last=5) is True


class TestTasksByAgentQuery:
    """Test the get_tasks_by_agent database query."""

    def test_get_tasks_by_agent_returns_assigned_tasks(self, db, setup_project):
        """Test that get_tasks_by_agent returns only tasks assigned to the agent."""
        project_id = setup_project["project_id"]
        issue_id = setup_project["issue_id"]

        # Create tasks for different agents
        for i in range(3):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.1.{i+1}",
                parent_issue_number="1.0",
                title=f"Agent1 Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "agent-1"})

        for i in range(2):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"1.2.{i+1}",
                parent_issue_number="1.0",
                title=f"Agent2 Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "agent-2"})

        # Query for agent-1
        agent1_tasks = db.get_tasks_by_agent("agent-1")
        assert len(agent1_tasks) == 3
        for task in agent1_tasks:
            assert task.assigned_to == "agent-1"

        # Query for agent-2
        agent2_tasks = db.get_tasks_by_agent("agent-2")
        assert len(agent2_tasks) == 2
        for task in agent2_tasks:
            assert task.assigned_to == "agent-2"

    def test_get_tasks_by_agent_filters_by_project(self, db):
        """Test that get_tasks_by_agent can filter by project."""
        # Create two projects
        project1_id = db.create_project(
            name="Project 1",
            description="Test",
            source_type="empty",
            workspace_path="/tmp/p1",
        )
        project2_id = db.create_project(
            name="Project 2",
            description="Test",
            source_type="empty",
            workspace_path="/tmp/p2",
        )

        issue1_id = db.create_issue({
            "project_id": project1_id,
            "issue_number": "1.0",
            "title": "Issue 1",
            "description": "Test",
        })
        issue2_id = db.create_issue({
            "project_id": project2_id,
            "issue_number": "1.0",
            "title": "Issue 2",
            "description": "Test",
        })

        # Create tasks for multi-agent in different projects
        for i in range(3):
            task_id = db.create_task_with_issue(
                project_id=project1_id,
                issue_id=issue1_id,
                task_number=f"1.0.{i+1}",
                parent_issue_number="1.0",
                title=f"P1 Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "multi-project-agent"})

        for i in range(2):
            task_id = db.create_task_with_issue(
                project_id=project2_id,
                issue_id=issue2_id,
                task_number=f"1.0.{i+1}",
                parent_issue_number="1.0",
                title=f"P2 Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=1,
                can_parallelize=False,
            )
            db.update_task(task_id, {"assigned_to": "multi-project-agent"})

        # Query without project filter - should get all tasks
        all_tasks = db.get_tasks_by_agent("multi-project-agent")
        assert len(all_tasks) == 5

        # Query with project filter
        p1_tasks = db.get_tasks_by_agent("multi-project-agent", project_id=project1_id)
        assert len(p1_tasks) == 3

        p2_tasks = db.get_tasks_by_agent("multi-project-agent", project_id=project2_id)
        assert len(p2_tasks) == 2
