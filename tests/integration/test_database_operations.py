"""
Integration tests for database operations.

These tests verify actual database behavior with:
- Real SQLite database operations
- Transaction handling and rollback
- Concurrent access patterns
- Repository pattern functionality

Unlike unit tests, these tests use real database instances to
verify actual persistence behavior.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from codeframe.core.models import AgentMaturity, CallType, TaskStatus, TokenUsage
from codeframe.persistence.database import Database


@pytest.mark.integration
class TestDatabaseProjectOperations:
    """Integration tests for project CRUD operations."""

    def test_project_create_and_retrieve(self, real_db: Database):
        """Test creating and retrieving a project."""
        project_id = real_db.create_project(
            name="test-project",
            description="A test project",
            source_type="git_remote",
            workspace_path="/tmp/test-project",
        )

        project = real_db.get_project(project_id)

        assert project is not None
        assert project["name"] == "test-project"
        assert project["description"] == "A test project"
        assert project["source_type"] == "git_remote"
        assert project["workspace_path"] == "/tmp/test-project"

    def test_project_update(self, real_db: Database):
        """Test updating a project's properties."""
        project_id = real_db.create_project(
            name="original-name",
            description="Original description",
            source_type="empty",
            workspace_path="/tmp/original",
        )

        # Update project
        real_db.update_project(
            project_id,
            {
                "name": "updated-name",
                "description": "Updated description",
            },
        )

        project = real_db.get_project(project_id)

        assert project["name"] == "updated-name"
        assert project["description"] == "Updated description"
        # Unchanged fields preserved
        assert project["workspace_path"] == "/tmp/original"

    def test_project_list_returns_all_projects(self, real_db: Database):
        """Test listing all projects."""
        # Create multiple projects
        ids = []
        for i in range(5):
            project_id = real_db.create_project(
                name=f"project-{i}",
                description=f"Project {i}",
                source_type="empty",
                workspace_path=f"/tmp/project-{i}",
            )
            ids.append(project_id)

        projects = real_db.list_projects()

        assert len(projects) == 5
        project_names = {p["name"] for p in projects}
        expected_names = {f"project-{i}" for i in range(5)}
        assert project_names == expected_names


@pytest.mark.integration
class TestDatabaseTaskOperations:
    """Integration tests for task CRUD operations."""

    def test_task_create_with_issue(self, integration_project):
        """Test creating a task linked to an issue."""
        db = integration_project["db"]
        project_id = integration_project["project_id"]
        issue_id = integration_project["issue_id"]

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="TASK-001",
            parent_issue_number="INT-001",
            title="Implementation Task",
            description="Implement the feature",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=True,
        )

        task = db.get_task(task_id)

        assert task is not None
        assert task.title == "Implementation Task"
        assert task.status == TaskStatus.PENDING
        assert task.project_id == project_id

    def test_task_status_transitions(self, integration_project):
        """Test valid task status transitions."""
        db = integration_project["db"]
        project_id = integration_project["project_id"]
        issue_id = integration_project["issue_id"]

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="STATUS-001",
            parent_issue_number="INT-001",
            title="Status Test",
            description="Test status transitions",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )

        # Transition: PENDING -> ASSIGNED
        db.update_task(task_id, {
            "status": TaskStatus.ASSIGNED.value,
            "assigned_to": "agent-001",
        })
        task = db.get_task(task_id)
        assert task.status == TaskStatus.ASSIGNED

        # Transition: ASSIGNED -> IN_PROGRESS
        db.update_task(task_id, {"status": TaskStatus.IN_PROGRESS.value})
        task = db.get_task(task_id)
        assert task.status == TaskStatus.IN_PROGRESS

        # Transition: IN_PROGRESS -> COMPLETED
        db.update_task(task_id, {"status": TaskStatus.COMPLETED.value})
        task = db.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        # Note: completed_at is set by application logic, not DB trigger

    def test_task_list_by_issue(self, integration_project):
        """Test listing tasks by issue."""
        db = integration_project["db"]
        project_id = integration_project["project_id"]
        issue_id = integration_project["issue_id"]

        # Create multiple tasks
        for i in range(3):
            db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"LIST-{i+1:03d}",
                parent_issue_number="INT-001",
                title=f"Task {i+1}",
                description=f"Task {i+1} description",
                status=TaskStatus.PENDING,
                priority=i,
                workflow_step=i + 1,
                can_parallelize=True,
            )

        # Query tasks via SQL (get_tasks_by_issue is async)
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE issue_id = ?", (issue_id,))
        rows = cursor.fetchall()

        assert len(rows) == 3
        assert all(row["project_id"] == project_id for row in rows)


@pytest.mark.integration
class TestDatabaseAgentOperations:
    """Integration tests for agent CRUD operations."""

    def test_agent_create_and_retrieve(self, real_db: Database):
        """Test creating and retrieving an agent."""
        real_db.create_agent(
            agent_id="test-agent-001",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D1,
        )

        agent = real_db.get_agent("test-agent-001")

        assert agent is not None
        assert agent["id"] == "test-agent-001"
        assert agent["type"] == "backend"
        assert agent["provider"] == "anthropic"
        assert agent["maturity_level"] == AgentMaturity.D1.value

    def test_agent_maturity_update(self, real_db: Database):
        """Test updating agent maturity level."""
        real_db.create_agent(
            agent_id="maturity-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D1,
        )

        # Update maturity
        real_db.update_agent("maturity-agent", {
            "maturity_level": AgentMaturity.D3.value,
        })

        agent = real_db.get_agent("maturity-agent")
        assert agent["maturity_level"] == AgentMaturity.D3.value


@pytest.mark.integration
class TestDatabaseTokenUsage:
    """Integration tests for token usage tracking."""

    def test_token_usage_recording(self, integration_project, sample_task):
        """Test recording token usage for a task."""
        db = integration_project["db"]
        task_id = sample_task["id"]
        project_id = integration_project["project_id"]

        # Record token usage using TokenUsage model
        token_usage = TokenUsage(
            task_id=task_id,
            agent_id="token-agent",
            project_id=project_id,
            model_name="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=500,
            estimated_cost_usd=0.0045,
            call_type=CallType.TASK_EXECUTION,
        )
        db.save_token_usage(token_usage)

        # Verify recording
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT * FROM token_usage WHERE task_id = ?", (task_id,)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["input_tokens"] == 1000
        assert row["output_tokens"] == 500
        assert row["model_name"] == "claude-sonnet-4-5"

    def test_token_usage_aggregation_by_project(self, integration_project):
        """Test aggregating token usage across a project."""
        db = integration_project["db"]
        project_id = integration_project["project_id"]
        issue_id = integration_project["issue_id"]

        # Create multiple tasks with token usage
        for i in range(3):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"AGG-{i+1:03d}",
                parent_issue_number="INT-001",
                title=f"Aggregate Task {i+1}",
                description="Token aggregation test",
                status=TaskStatus.COMPLETED,
                priority=1,
                workflow_step=i + 1,
                can_parallelize=False,
            )

            token_usage = TokenUsage(
                task_id=task_id,
                agent_id="agg-agent",
                project_id=project_id,
                model_name="claude-sonnet-4-5",
                input_tokens=(i + 1) * 100,
                output_tokens=(i + 1) * 50,
                estimated_cost_usd=0.001 * (i + 1),
                call_type=CallType.TASK_EXECUTION,
            )
            db.save_token_usage(token_usage)

        # Aggregate by project
        cursor = db.conn.cursor()
        cursor.execute(
            """
            SELECT
                SUM(input_tokens) as total_input,
                SUM(output_tokens) as total_output,
                SUM(estimated_cost_usd) as total_cost
            FROM token_usage WHERE project_id = ?
            """,
            (project_id,),
        )
        row = cursor.fetchone()

        # 100 + 200 + 300 = 600 input
        # 50 + 100 + 150 = 300 output
        # 0.001 + 0.002 + 0.003 = 0.006 cost
        assert row["total_input"] == 600
        assert row["total_output"] == 300
        assert abs(row["total_cost"] - 0.006) < 0.0001


@pytest.mark.integration
class TestDatabaseConcurrentAccess:
    """Integration tests for concurrent database access."""

    def test_concurrent_task_updates(self, integration_project):
        """Test concurrent task updates don't cause race conditions."""
        db = integration_project["db"]
        project_id = integration_project["project_id"]
        issue_id = integration_project["issue_id"]

        # Create a task
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="CONC-001",
            parent_issue_number="INT-001",
            title="Concurrent Task",
            description="Test concurrent updates",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=1,
            can_parallelize=False,
        )

        update_count = [0]
        errors = []

        def update_task(priority: int):
            try:
                # All threads share the same db instance (SQLite handles locking)
                db.update_task(task_id, {"priority": priority})
                update_count[0] += 1
            except Exception as e:
                errors.append(e)

        # Run 10 concurrent updates (priority must be 0-4 per DB constraint)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_task, i % 5) for i in range(10)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Concurrent update errors: {errors}"
        assert update_count[0] == 10

    def test_concurrent_project_reads(self, real_db: Database):
        """Test concurrent project reads work correctly."""
        # Create a project
        project_id = real_db.create_project(
            name="read-test",
            description="Test concurrent reads",
            source_type="empty",
            workspace_path="/tmp/read-test",
        )

        results = []
        errors = []

        def read_project():
            try:
                project = real_db.get_project(project_id)
                results.append(project)
            except Exception as e:
                errors.append(e)

        # Run 20 concurrent reads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_project) for _ in range(20)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Concurrent read errors: {errors}"
        assert len(results) == 20
        assert all(r["name"] == "read-test" for r in results)


@pytest.mark.integration
class TestDatabaseTransactions:
    """Integration tests for transaction handling."""

    def test_transaction_rollback_on_error(self, real_db: Database):
        """Test that transactions rollback on error."""
        # Create initial project
        project_id = real_db.create_project(
            name="rollback-test",
            description="Test rollback",
            source_type="empty",
            workspace_path="/tmp/rollback-test",
        )

        # Get initial state
        original_project = real_db.get_project(project_id)

        # Attempt invalid update that should fail
        try:
            # Try to update with invalid data type
            cursor = real_db.conn.cursor()
            cursor.execute("BEGIN TRANSACTION")
            cursor.execute(
                "UPDATE projects SET name = ? WHERE id = ?",
                ("updated-name", project_id),
            )
            # Force an error
            raise ValueError("Simulated error")
        except ValueError:
            real_db.conn.rollback()

        # Verify rollback
        project = real_db.get_project(project_id)
        assert project["name"] == original_project["name"]


@pytest.mark.integration
class TestDatabaseBlockerOperations:
    """Integration tests for blocker operations."""

    def test_blocker_create_and_resolve(self, integration_project, sample_task):
        """Test creating and resolving a blocker."""
        db = integration_project["db"]
        task_id = sample_task["id"]
        project_id = integration_project["project_id"]

        # Create agent for blocker
        db.create_agent(
            agent_id="blocker-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D2,
        )

        # Create blocker (requires agent_id and project_id)
        blocker_id = db.create_blocker(
            agent_id="blocker-agent",
            project_id=project_id,
            task_id=task_id,
            blocker_type="SYNC",
            question="How should we handle authentication?",
        )

        # Verify blocker exists (query directly since no get_blockers_by_task method)
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM blockers WHERE task_id = ?", (task_id,))
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["question"] == "How should we handle authentication?"
        assert rows[0]["status"] == "PENDING"  # Status is uppercase

        # Resolve blocker
        db.resolve_blocker(
            blocker_id,
            answer="Use JWT tokens with refresh mechanism",
        )

        # Verify resolution
        cursor.execute("SELECT * FROM blockers WHERE task_id = ?", (task_id,))
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["status"] == "RESOLVED"
        assert rows[0]["answer"] == "Use JWT tokens with refresh mechanism"

    def test_active_blockers_query(self, integration_project):
        """Test querying active (unresolved) blockers."""
        db = integration_project["db"]
        project_id = integration_project["project_id"]
        issue_id = integration_project["issue_id"]

        # Create agent for blockers
        db.create_agent(
            agent_id="active-blocker-agent",
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D2,
        )

        # Create multiple tasks with blockers
        for i in range(3):
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"BLOCK-{i+1:03d}",
                parent_issue_number="INT-001",
                title=f"Blocked Task {i+1}",
                description="Has blocker",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
                workflow_step=i + 1,
                can_parallelize=False,
            )

            db.create_blocker(
                agent_id="active-blocker-agent",
                project_id=project_id,
                task_id=task_id,
                blocker_type="SYNC",
                question=f"Question {i+1}",
            )

        # Get all active blockers (status is uppercase)
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM blockers WHERE status = 'PENDING'"
        )
        count = cursor.fetchone()["count"]

        assert count == 3


@pytest.mark.integration
class TestDatabaseFilePersistence:
    """Integration tests for file-based database persistence."""

    def test_data_persists_across_connections(self, tmp_path: Path):
        """Test that data persists when reopening database file."""
        db_path = tmp_path / "persist_test.db"

        # First connection - create data
        db1 = Database(str(db_path))
        db1.initialize()
        project_id = db1.create_project(
            name="persistent-project",
            description="Should persist",
            source_type="empty",
            workspace_path="/tmp/persist",
        )
        db1.conn.close()

        # Second connection - verify data
        db2 = Database(str(db_path))
        db2.initialize()
        project = db2.get_project(project_id)
        db2.conn.close()

        assert project is not None
        assert project["name"] == "persistent-project"

    def test_schema_migration_on_reopen(self, tmp_path: Path):
        """Test that schema is properly initialized on reopen."""
        db_path = tmp_path / "schema_test.db"

        # Create initial database
        db1 = Database(str(db_path))
        db1.initialize()
        db1.conn.close()

        # Reopen and verify tables exist
        db2 = Database(str(db_path))
        db2.initialize()

        cursor = db2.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row["name"] for row in cursor.fetchall()}
        db2.conn.close()

        # Verify essential tables exist
        assert "projects" in tables
        assert "tasks" in tables
        assert "issues" in tables
        assert "blockers" in tables
        assert "agents" in tables
        assert "token_usage" in tables
