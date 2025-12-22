"""
Comprehensive tests for Project.get_status() method.

Tests cover:
- Task statistics aggregation
- Agent counting (active/idle)
- Progress percentage calculation
- Blocker counting
- Quality metrics integration
- Last activity timestamp formatting
- Error handling (missing project, no database, empty data)
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from codeframe.core.project import Project
from codeframe.core.models import TaskStatus, Task, ProjectStatus
from codeframe.persistence.database import Database


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    db = Database(db_path)
    db.initialize()

    yield db

    # Cleanup
    db.conn.close()
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def test_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        codeframe_dir = project_dir / ".codeframe"
        codeframe_dir.mkdir(parents=True, exist_ok=True)

        yield project_dir


@pytest.fixture
def project_with_db(test_db, test_project_dir):
    """Create a Project instance with a test database."""
    # Create project in database first
    project_id = test_db.create_project(
        name="test_project", status="active", description="Test project"
    )

    # Create project instance
    project = Project(project_dir=test_project_dir)
    project.db = test_db
    project._status = ProjectStatus.ACTIVE

    # Save config
    from codeframe.core.config import ProjectConfig

    config = ProjectConfig(project_name="test_project", project_type="python")
    project.config.save(config)

    yield project, project_id, test_db


class TestGetStatusBasic:
    """Test basic get_status() functionality."""

    def test_no_database_returns_minimal_status(self, test_project_dir):
        """Test that get_status() returns minimal status when database is not initialized."""
        project = Project(project_dir=test_project_dir)
        from codeframe.core.config import ProjectConfig

        config = ProjectConfig(project_name="test_project", project_type="python")
        project.config.save(config)

        status = project.get_status()

        assert status["id"] is None
        assert status["name"] == "test_project"
        assert status["status"] == "init"
        assert status["tasks"]["total"] == 0
        assert status["agents"]["total"] == 0
        assert status["progress_pct"] == 0.0
        assert status["blockers"] == 0
        assert status["quality"] is None
        assert status["last_activity"] == "No activity yet"

    def test_project_not_in_database_returns_minimal_status(self, project_with_db):
        """Test that get_status() returns minimal status when project not found in database."""
        project, project_id, test_db = project_with_db

        # Change config to non-existent project
        from codeframe.core.config import ProjectConfig

        config = ProjectConfig(project_name="nonexistent_project", project_type="python")
        project.config.save(config)

        status = project.get_status()

        assert status["id"] is None
        assert status["name"] == "nonexistent_project"
        assert status["tasks"]["total"] == 0
        assert status["last_activity"] == "No activity yet"

    def test_empty_project_returns_zero_counts(self, project_with_db):
        """Test that an empty project (no tasks, no agents) returns zero counts."""
        project, project_id, test_db = project_with_db

        status = project.get_status()

        assert status["id"] == project_id
        assert status["name"] == "test_project"
        assert status["tasks"] == {
            "total": 0,
            "completed": 0,
            "in_progress": 0,
            "blocked": 0,
            "pending": 0,
        }
        assert status["agents"] == {"active": 0, "idle": 0, "total": 0}
        assert status["progress_pct"] == 0.0
        assert status["blockers"] == 0
        assert status["last_activity"] == "No activity yet"


class TestTaskAggregation:
    """Test task statistics aggregation."""

    def test_mixed_task_statuses_aggregate_correctly(self, project_with_db):
        """Test that tasks with mixed statuses are aggregated correctly."""
        project, project_id, test_db = project_with_db

        # Create tasks with different statuses
        tasks_data = [
            {"status": TaskStatus.COMPLETED, "count": 5},
            {"status": TaskStatus.IN_PROGRESS, "count": 3},
            {"status": TaskStatus.BLOCKED, "count": 2},
            {"status": TaskStatus.PENDING, "count": 4},
            {"status": TaskStatus.ASSIGNED, "count": 1},  # Should count as pending
        ]

        task_num = 1
        for task_data in tasks_data:
            for _ in range(task_data["count"]):
                test_db.create_task(
                    Task(
                        project_id=project_id,
                        task_number=f"1.{task_num}",
                        title=f"Task {task_num}",
                        description="Test task",
                        status=task_data["status"],
                    )
                )
                task_num += 1

        status = project.get_status()

        assert status["tasks"]["total"] == 15
        assert status["tasks"]["completed"] == 5
        assert status["tasks"]["in_progress"] == 3
        assert status["tasks"]["blocked"] == 2
        assert status["tasks"]["pending"] == 5  # 4 PENDING + 1 ASSIGNED

    def test_failed_tasks_included_in_total(self, project_with_db):
        """Test that FAILED tasks are included in total count."""
        project, project_id, test_db = project_with_db

        # Create a mix of tasks including FAILED
        for i, status in enumerate([TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.PENDING], 1):
            test_db.create_task(
                Task(
                    project_id=project_id,
                    task_number=f"1.{i}",
                    title=f"Task {i}",
                    status=status,
                )
            )

        status = project.get_status()

        assert status["tasks"]["total"] == 3
        assert status["tasks"]["completed"] == 1
        assert status["tasks"]["pending"] == 1
        # FAILED tasks don't have a specific counter but are in total


class TestProgressCalculation:
    """Test progress percentage calculation."""

    def test_progress_0_percent_no_tasks(self, project_with_db):
        """Test that progress is 0% when there are no tasks."""
        project, project_id, test_db = project_with_db

        status = project.get_status()

        assert status["progress_pct"] == 0.0

    def test_progress_0_percent_no_completed_tasks(self, project_with_db):
        """Test that progress is 0% when there are tasks but none completed."""
        project, project_id, test_db = project_with_db

        for i in range(1, 6):
            test_db.create_task(
                Task(
                    project_id=project_id,
                    task_number=f"1.{i}",
                    title=f"Task {i}",
                    status=TaskStatus.PENDING,
                )
            )

        status = project.get_status()

        assert status["progress_pct"] == 0.0

    def test_progress_50_percent(self, project_with_db):
        """Test that progress is 50% when half the tasks are completed."""
        project, project_id, test_db = project_with_db

        for i in range(1, 11):
            status_val = TaskStatus.COMPLETED if i <= 5 else TaskStatus.PENDING
            test_db.create_task(
                Task(
                    project_id=project_id,
                    task_number=f"1.{i}",
                    title=f"Task {i}",
                    status=status_val,
                )
            )

        status = project.get_status()

        assert status["progress_pct"] == 50.0

    def test_progress_100_percent(self, project_with_db):
        """Test that progress is 100% when all tasks are completed."""
        project, project_id, test_db = project_with_db

        for i in range(1, 6):
            test_db.create_task(
                Task(
                    project_id=project_id,
                    task_number=f"1.{i}",
                    title=f"Task {i}",
                    status=TaskStatus.COMPLETED,
                )
            )

        status = project.get_status()

        assert status["progress_pct"] == 100.0

    def test_progress_rounded_to_one_decimal(self, project_with_db):
        """Test that progress percentage is rounded to 1 decimal place."""
        project, project_id, test_db = project_with_db

        # Create 7 tasks, 2 completed -> 28.571...% -> 28.6%
        for i in range(1, 8):
            status_val = TaskStatus.COMPLETED if i <= 2 else TaskStatus.PENDING
            test_db.create_task(
                Task(
                    project_id=project_id,
                    task_number=f"1.{i}",
                    title=f"Task {i}",
                    status=status_val,
                )
            )

        status = project.get_status()

        assert status["progress_pct"] == 28.6


class TestAgentCounting:
    """Test agent counting (active/idle)."""

    def test_no_agents_returns_zero_counts(self, project_with_db):
        """Test that projects with no agents return zero counts."""
        project, project_id, test_db = project_with_db

        status = project.get_status()

        assert status["agents"] == {"active": 0, "idle": 0, "total": 0}

    def test_agents_with_status_working_counted_as_active(self, project_with_db):
        """Test that agents with status='working' are counted as active."""
        project, project_id, test_db = project_with_db

        # Create agent and assign to project
        agent_id = "agent-001"
        from codeframe.core.models import AgentMaturity

        test_db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D4,
        )
        test_db.update_agent(agent_id, {"status": "working"})
        test_db.assign_agent_to_project(project_id, agent_id, role="backend")

        status = project.get_status()

        assert status["agents"]["total"] == 1
        assert status["agents"]["active"] == 1
        assert status["agents"]["idle"] == 0

    def test_agents_with_current_task_counted_as_active(self, project_with_db):
        """Test that agents with current_task_id are counted as active."""
        project, project_id, test_db = project_with_db
        from codeframe.core.models import AgentMaturity

        # Create task
        task = Task(
            project_id=project_id, task_number="1.1", title="Task 1", status=TaskStatus.IN_PROGRESS
        )
        task_id = test_db.create_task(task)

        # Create agent with current_task_id
        agent_id = "agent-002"
        test_db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D4,
        )
        test_db.update_agent(agent_id, {"status": "idle", "current_task_id": task_id})
        test_db.assign_agent_to_project(project_id, agent_id, role="backend")

        status = project.get_status()

        assert status["agents"]["total"] == 1
        assert status["agents"]["active"] == 1
        assert status["agents"]["idle"] == 0

    def test_idle_agents_counted_correctly(self, project_with_db):
        """Test that idle agents (no task, status=idle) are counted correctly."""
        project, project_id, test_db = project_with_db
        from codeframe.core.models import AgentMaturity

        # Create idle agent
        agent_id = "agent-003"
        test_db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D4,
        )
        test_db.update_agent(agent_id, {"status": "idle", "current_task_id": None})
        test_db.assign_agent_to_project(project_id, agent_id, role="backend")

        status = project.get_status()

        assert status["agents"]["total"] == 1
        assert status["agents"]["active"] == 0
        assert status["agents"]["idle"] == 1

    def test_mixed_active_idle_agents(self, project_with_db):
        """Test counting with a mix of active and idle agents."""
        project, project_id, test_db = project_with_db
        from codeframe.core.models import AgentMaturity

        # Create a task for agent-002
        task = Task(
            project_id=project_id, task_number="1.1", title="Task 1", status=TaskStatus.IN_PROGRESS
        )
        task_id = test_db.create_task(task)

        # Create 2 active agents and 1 idle agent
        agents_data = [
            {"id": "agent-001", "status": "working", "task_id": None},  # Active (status=working)
            {"id": "agent-002", "status": "idle", "task_id": task_id},  # Active (has task)
            {"id": "agent-003", "status": "idle", "task_id": None},  # Idle
        ]

        for agent_data in agents_data:
            test_db.create_agent(
                agent_id=agent_data["id"],
                agent_type="backend",
                provider="anthropic",
                maturity_level=AgentMaturity.D4,
            )
            test_db.update_agent(
                agent_data["id"],
                {"status": agent_data["status"], "current_task_id": agent_data["task_id"]},
            )
            test_db.assign_agent_to_project(project_id, agent_data["id"], role="backend")

        status = project.get_status()

        assert status["agents"]["total"] == 3
        assert status["agents"]["active"] == 2
        assert status["agents"]["idle"] == 1


class TestBlockerCounting:
    """Test blocker counting."""

    def test_no_blockers_returns_zero(self, project_with_db):
        """Test that projects with no blockers return zero."""
        project, project_id, test_db = project_with_db

        status = project.get_status()

        assert status["blockers"] == 0

    def test_pending_blockers_counted(self, project_with_db):
        """Test that pending blockers are counted correctly."""
        project, project_id, test_db = project_with_db

        # Create pending blockers
        for i in range(1, 4):
            test_db.create_blocker(
                agent_id=f"agent-{i}",
                project_id=project_id,
                task_id=None,  # No associated task
                question=f"Question {i}?",
                blocker_type="SYNC",
            )

        status = project.get_status()

        assert status["blockers"] == 3

    def test_resolved_blockers_not_counted(self, project_with_db):
        """Test that RESOLVED blockers are not counted."""
        project, project_id, test_db = project_with_db

        # Create pending and resolved blockers
        blocker_id = test_db.create_blocker(
            agent_id="agent-001",
            project_id=project_id,
            task_id=None,  # No associated task
            question="Question?",
            blocker_type="SYNC",
        )

        # Resolve the blocker
        test_db.resolve_blocker(blocker_id, answer="Answer")

        status = project.get_status()

        assert status["blockers"] == 0


class TestQualityMetrics:
    """Test quality metrics integration."""

    def test_no_quality_data_returns_none(self, project_with_db):
        """Test that projects with no quality data return None for quality metrics."""
        project, project_id, test_db = project_with_db

        status = project.get_status()

        assert status["quality"] is None

    def test_quality_metrics_retrieved_from_tracker(self, project_with_db):
        """Test that quality metrics are retrieved from QualityTracker when available."""
        project, project_id, test_db = project_with_db

        # Create quality history file
        from codeframe.enforcement.quality_tracker import QualityTracker, QualityMetrics

        tracker = QualityTracker(project_path=project.project_dir)
        metrics = QualityMetrics(
            timestamp=datetime.now(timezone.utc).isoformat(),
            response_count=5,
            test_pass_rate=95.5,
            coverage_percentage=87.5,
            total_tests=100,
            passed_tests=95,
            failed_tests=5,
        )
        tracker.record(metrics)

        status = project.get_status()

        assert status["quality"] is not None
        assert status["quality"]["test_pass_rate"] == 95.5
        assert status["quality"]["coverage_pct"] == 87.5


class TestLastActivityFormatting:
    """Test last activity timestamp formatting."""

    def test_no_activity_returns_no_activity_yet(self, project_with_db):
        """Test that projects with no activity return 'No activity yet'."""
        project, project_id, test_db = project_with_db

        status = project.get_status()

        assert status["last_activity"] == "No activity yet"

    def test_recent_activity_formatted_as_just_now(self, project_with_db):
        """Test that activity within the last minute is formatted as 'just now'."""
        project, project_id, test_db = project_with_db

        # Create recent activity (within last 30 seconds)
        cursor = test_db.conn.cursor()
        timestamp = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        cursor.execute(
            """
            INSERT INTO changelog (project_id, agent_id, action, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (project_id, "agent-001", "test_action", timestamp),
        )
        test_db.conn.commit()

        status = project.get_status()

        assert status["last_activity"] == "just now"

    def test_activity_formatted_as_minutes_ago(self, project_with_db):
        """Test that activity within the last hour is formatted as 'X minutes ago'."""
        project, project_id, test_db = project_with_db

        # Manually insert activity with timestamp 5 minutes ago
        cursor = test_db.conn.cursor()
        timestamp = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        cursor.execute(
            """
            INSERT INTO changelog (project_id, agent_id, action, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (project_id, "agent-001", "test_action", timestamp),
        )
        test_db.conn.commit()

        status = project.get_status()

        assert "minute" in status["last_activity"]
        assert "ago" in status["last_activity"]

    def test_activity_formatted_as_hours_ago(self, project_with_db):
        """Test that activity within the last day is formatted as 'X hours ago'."""
        project, project_id, test_db = project_with_db

        # Manually insert activity with timestamp 3 hours ago
        cursor = test_db.conn.cursor()
        timestamp = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        cursor.execute(
            """
            INSERT INTO changelog (project_id, agent_id, action, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (project_id, "agent-001", "test_action", timestamp),
        )
        test_db.conn.commit()

        status = project.get_status()

        assert "hour" in status["last_activity"]
        assert "ago" in status["last_activity"]

    def test_activity_formatted_as_days_ago(self, project_with_db):
        """Test that activity older than a day is formatted as 'X days ago'."""
        project, project_id, test_db = project_with_db

        # Manually insert activity with timestamp 2 days ago
        cursor = test_db.conn.cursor()
        timestamp = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        cursor.execute(
            """
            INSERT INTO changelog (project_id, agent_id, action, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (project_id, "agent-001", "test_action", timestamp),
        )
        test_db.conn.commit()

        status = project.get_status()

        assert "day" in status["last_activity"]
        assert "ago" in status["last_activity"]

    def test_singular_plural_formatting(self, project_with_db):
        """Test that singular/plural formatting is correct (1 minute vs 2 minutes)."""
        project, project_id, test_db = project_with_db

        # Manually insert activity with timestamp 1 minute ago
        cursor = test_db.conn.cursor()
        timestamp = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        cursor.execute(
            """
            INSERT INTO changelog (project_id, agent_id, action, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (project_id, "agent-001", "test_action", timestamp),
        )
        test_db.conn.commit()

        status = project.get_status()

        assert "1 minute ago" in status["last_activity"]


class TestErrorHandling:
    """Test error handling."""

    def test_database_error_returns_error_status(self, project_with_db):
        """Test that database errors return a valid error status."""
        project, project_id, test_db = project_with_db

        # Close the database connection to simulate error
        test_db.conn.close()

        status = project.get_status()

        # Should still return a valid dictionary with error field
        assert isinstance(status, dict)
        assert "error" in status
        assert status["tasks"]["total"] == 0
        assert status["last_activity"] == "Error retrieving activity"
