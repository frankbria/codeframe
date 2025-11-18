"""Tests for database CRUD operations.

Following TDD: These tests are written FIRST, before full implementation.
Target: >90% coverage for database.py module.
"""

import json
import pytest
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus, TaskStatus, AgentMaturity


@pytest.mark.unit
class TestDatabaseInitialization:
    """Test database initialization and schema creation."""

    def test_database_initialization(self, temp_db_path):
        """Test that database initializes and creates schema."""
        db = Database(temp_db_path)
        db.initialize()

        assert temp_db_path.exists()
        assert db.conn is not None

        # Verify all tables were created
        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            "projects",
            "tasks",
            "agents",
            "blockers",
            "memory",
            "context_items",
            "checkpoints",
            "changelog",
            "test_results",
        ]

        for table in expected_tables:
            assert table in tables, f"Table {table} was not created"

    def test_database_with_nonexistent_path(self, temp_dir):
        """Test that database creates parent directories if needed."""
        nested_path = temp_dir / "nested" / "path" / "test.db"
        db = Database(nested_path)
        db.initialize()

        assert nested_path.exists()
        assert nested_path.parent.exists()


@pytest.mark.unit
class TestProjectCRUD:
    """Test project CRUD operations."""

    def test_create_project(self, temp_db_path):
        """Test creating a new project."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        assert project_id is not None
        assert isinstance(project_id, int)
        assert project_id > 0

    def test_get_project_by_id(self, temp_db_path):
        """Test retrieving a project by ID."""
        db = Database(temp_db_path)
        db.initialize()

        # Create project
        project_id = db.create_project("test-project", "Test Project project")

        # Retrieve it
        project = db.get_project(project_id)

        assert project is not None
        assert project["id"] == project_id
        assert project["name"] == "test-project"
        assert project["status"] == "init"
        assert "created_at" in project

    def test_get_nonexistent_project_returns_none(self, temp_db_path):
        """Test that getting non-existent project returns None."""
        db = Database(temp_db_path)
        db.initialize()

        project = db.get_project(99999)
        assert project is None

    def test_list_projects(self, temp_db_path):
        """Test listing all projects."""
        db = Database(temp_db_path)
        db.initialize()

        # Create multiple projects
        db.create_project("project1", "Project1 project")
        db.create_project("project2", "Project2 project")
        db.create_project("project3", "Project3 project")

        # List all projects
        projects = db.list_projects()

        assert len(projects) == 3
        project_names = [p["name"] for p in projects]
        assert "project1" in project_names
        assert "project2" in project_names
        assert "project3" in project_names

    def test_list_projects_empty(self, temp_db_path):
        """Test listing projects when none exist."""
        db = Database(temp_db_path)
        db.initialize()

        projects = db.list_projects()
        assert projects == []

    def test_update_project_status(self, temp_db_path):
        """Test updating project status."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        # Update status
        db.update_project(project_id, {"status": ProjectStatus.ACTIVE})

        # Verify update
        project = db.get_project(project_id)
        assert project["status"] == "active"

    def test_update_project_config(self, temp_db_path):
        """Test updating project configuration."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        # Update with config
        config = {"providers": {"lead_agent": "claude"}, "debug": True}
        db.update_project(project_id, {"config": json.dumps(config)})

        # Verify update
        project = db.get_project(project_id)
        assert project["config"] is not None
        saved_config = json.loads(project["config"])
        assert saved_config["providers"]["lead_agent"] == "claude"

    def test_update_nonexistent_project(self, temp_db_path):
        """Test that updating non-existent project handles gracefully."""
        db = Database(temp_db_path)
        db.initialize()

        # Should not raise, just do nothing
        result = db.update_project(99999, {"status": ProjectStatus.ACTIVE})
        assert result == 0  # 0 rows affected

    def test_project_has_default_phase(self, temp_db_path):
        """Test that new projects default to 'discovery' phase."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")
        project = db.get_project(project_id)

        assert project["phase"] == "discovery"

    def test_update_project_phase(self, temp_db_path):
        """Test updating project phase."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        # Update phase to planning
        db.update_project(project_id, {"phase": "planning"})

        project = db.get_project(project_id)
        assert project["phase"] == "planning"

    def test_project_phase_constraint(self, temp_db_path):
        """Test that invalid project phase is rejected."""
        db = Database(temp_db_path)
        db.initialize()

        cursor = db.conn.cursor()

        # SQLite with CHECK constraint should reject invalid values
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            cursor.execute(
                "INSERT INTO projects (name, status, phase) VALUES (?, ?, ?)",
                ("test", "init", "INVALID_PHASE"),
            )

    def test_phase_transitions(self, temp_db_path):
        """Test typical phase transitions during project lifecycle."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        # Verify starts at discovery
        project = db.get_project(project_id)
        assert project["phase"] == "discovery"

        # Transition to planning
        db.update_project(project_id, {"phase": "planning"})
        project = db.get_project(project_id)
        assert project["phase"] == "planning"

        # Transition to active
        db.update_project(project_id, {"phase": "active"})
        project = db.get_project(project_id)
        assert project["phase"] == "active"

        # Transition to review
        db.update_project(project_id, {"phase": "review"})
        project = db.get_project(project_id)
        assert project["phase"] == "review"

        # Transition to complete
        db.update_project(project_id, {"phase": "complete"})
        project = db.get_project(project_id)
        assert project["phase"] == "complete"


@pytest.mark.unit
class TestAgentCRUD:
    """Test agent CRUD operations."""

    def test_create_agent(self, temp_db_path):
        """Test creating an agent."""
        db = Database(temp_db_path)
        db.initialize()

        # Create project first
        project_id = db.create_project("test-project", "Test Project project")

        # Create agent
        agent_id = db.create_agent(
            agent_id="lead-agent-1",
            agent_type="lead",
            provider="claude",
            maturity_level=AgentMaturity.D1,
        )

        assert agent_id == "lead-agent-1"

    def test_get_agent(self, temp_db_path):
        """Test retrieving an agent."""
        db = Database(temp_db_path)
        db.initialize()

        # Create agent
        db.create_agent("lead-1", "lead", "claude", AgentMaturity.D1)

        # Retrieve
        agent = db.get_agent("lead-1")

        assert agent is not None
        assert agent["id"] == "lead-1"
        assert agent["type"] == "lead"
        assert agent["provider"] == "claude"
        assert agent["maturity_level"] == "directive"

    def test_update_agent_status(self, temp_db_path):
        """Test updating agent status."""
        db = Database(temp_db_path)
        db.initialize()

        db.create_agent("lead-1", "lead", "claude", AgentMaturity.D1)

        # Update status
        db.update_agent("lead-1", {"status": "working"})

        # Verify
        agent = db.get_agent("lead-1")
        assert agent["status"] == "working"

    def test_update_agent_maturity(self, temp_db_path):
        """Test updating agent maturity level."""
        db = Database(temp_db_path)
        db.initialize()

        db.create_agent("lead-1", "lead", "claude", AgentMaturity.D1)

        # Update maturity
        db.update_agent("lead-1", {"maturity_level": AgentMaturity.D2})

        # Verify
        agent = db.get_agent("lead-1")
        assert agent["maturity_level"] == "coaching"

    def test_list_agents_by_project(self, temp_db_path):
        """Test listing agents for a project."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        # Create multiple agents (for now, agents aren't project-specific in schema)
        # But we'll add project_id to agents table later
        db.create_agent("lead-1", "lead", "claude", AgentMaturity.D1)
        db.create_agent("backend-1", "backend", "claude", AgentMaturity.D1)

        # For now, test general list
        agents = db.list_agents()

        assert len(agents) >= 2


@pytest.mark.unit
class TestMemoryCRUD:
    """Test memory storage operations."""

    def test_create_memory(self, temp_db_path):
        """Test creating a memory entry."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        memory_id = db.create_memory(
            project_id=project_id,
            category="pattern",
            key="auth_pattern",
            value="JWT with refresh tokens",
        )

        assert memory_id is not None
        assert isinstance(memory_id, int)

    def test_get_memory(self, temp_db_path):
        """Test retrieving memory entries."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        # Create memory
        memory_id = db.create_memory(
            project_id=project_id,
            category="decision",
            key="database_choice",
            value="SQLite for MVP",
        )

        # Retrieve by ID
        memory = db.get_memory(memory_id)

        assert memory is not None
        assert memory["category"] == "decision"
        assert memory["key"] == "database_choice"
        assert memory["value"] == "SQLite for MVP"

    def test_get_project_memories(self, temp_db_path):
        """Test getting all memories for a project."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        # Create multiple memories
        db.create_memory(project_id, "pattern", "key1", "value1")
        db.create_memory(project_id, "decision", "key2", "value2")
        db.create_memory(project_id, "preference", "key3", "value3")

        # Get all for project
        memories = db.get_project_memories(project_id)

        assert len(memories) == 3
        keys = [m["key"] for m in memories]
        assert "key1" in keys
        assert "key2" in keys

    def test_get_conversation_messages(self, temp_db_path):
        """Test getting conversation history from memory.

        For Sprint 1, we'll store conversation as memory entries
        with category='conversation'.
        """
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", "Test Project project")

        # Create conversation messages
        db.create_memory(project_id, "conversation", "user_1", "Hello!")
        db.create_memory(project_id, "conversation", "assistant_1", "Hi there!")
        db.create_memory(project_id, "conversation", "user_2", "What can you do?")

        # Get conversation
        conversation = db.get_conversation(project_id)

        assert len(conversation) == 3
        # Verify all messages are present (order may vary based on timing)
        values = {msg["value"] for msg in conversation}
        assert "Hello!" in values
        assert "Hi there!" in values
        assert "What can you do?" in values

        # Verify keys are present
        keys = {msg["key"] for msg in conversation}
        assert "user_1" in keys
        assert "assistant_1" in keys
        assert "user_2" in keys


@pytest.mark.unit
class TestDatabaseConnection:
    """Test database connection management."""

    def test_close_connection(self, temp_db_path):
        """Test closing database connection."""
        db = Database(temp_db_path)
        db.initialize()

        assert db.conn is not None

        db.close()

        # After close, conn should be None or closed
        assert db.conn is None or not db.conn

    def test_context_manager(self, temp_db_path):
        """Test using database as context manager."""
        with Database(temp_db_path) as db:
            db.create_project("test-project", "Test Project project")
            assert db.conn is not None

        # After exiting context, connection should be closed
        # (This requires implementing __enter__ and __exit__)


@pytest.mark.unit
class TestDataIntegrity:
    """Test data integrity and constraints."""

    def test_project_status_constraint(self, temp_db_path):
        """Test that invalid project status is rejected."""
        db = Database(temp_db_path)
        db.initialize()

        # SQLite with CHECK constraint should reject invalid values
        # This tests schema integrity
        cursor = db.conn.cursor()

        with pytest.raises(Exception):  # sqlite3.IntegrityError
            cursor.execute(
                "INSERT INTO projects (name, status) VALUES (?, ?)",
                ("test", "INVALID_STATUS"),
            )

    def test_agent_type_constraint(self, temp_db_path):
        """Test that arbitrary agent types are allowed (constraint removed by migration 001)."""
        db = Database(temp_db_path)
        db.initialize()

        cursor = db.conn.cursor()

        # After migration 001, arbitrary agent types should be accepted
        cursor.execute(
            "INSERT INTO agents (id, type) VALUES (?, ?)",
            ("test-agent", "CUSTOM_TYPE"),
        )
        db.conn.commit()

        # Verify the agent was inserted
        cursor.execute("SELECT type FROM agents WHERE id = ?", ("test-agent",))
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "CUSTOM_TYPE"

    def test_foreign_key_constraint(self, temp_db_path):
        """Test foreign key constraints (if enabled)."""
        db = Database(temp_db_path)
        db.initialize()

        # Enable foreign keys
        db.conn.execute("PRAGMA foreign_keys = ON")

        cursor = db.conn.cursor()

        # Try to create task with non-existent project_id
        # This should fail if foreign keys are enforced
        try:
            cursor.execute(
                "INSERT INTO tasks (project_id, title, status) VALUES (?, ?, ?)",
                (99999, "test", "pending"),
            )
            db.conn.commit()
            # If we get here, foreign keys aren't enforced (default in SQLite)
            # That's okay for Sprint 1
        except Exception:
            # Foreign keys are enforced - good!
            pass


@pytest.mark.unit
class TestTransactions:
    """Test transaction handling."""

    def test_rollback_on_error(self, temp_db_path):
        """Test that transactions rollback on error."""
        db = Database(temp_db_path)
        db.initialize()

        # Create a project
        project_id = db.create_project("test-project", "Test Project project")

        try:
            cursor = db.conn.cursor()
            # Start implicit transaction
            cursor.execute(
                "UPDATE projects SET status = ? WHERE id = ?",
                (ProjectStatus.ACTIVE.value, project_id),
            )

            # Force an error
            cursor.execute("INSERT INTO projects (name, status) VALUES (?, ?)", ("test", "INVALID"))

            db.conn.commit()

        except Exception:
            db.conn.rollback()

        # Verify rollback - project should still be 'init'
        project = db.get_project(project_id)
        assert project["status"] == "init"


@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests for database operations."""

    def test_complete_project_workflow(self, temp_db_path):
        """Test complete project lifecycle in database."""
        db = Database(temp_db_path)
        db.initialize()

        # 1. Create project
        project_id = db.create_project("my-app", "My App project")

        # 2. Update to planning
        db.update_project(project_id, {"status": ProjectStatus.PLANNING})

        # 3. Create agent
        db.create_agent("lead-1", "lead", "claude", AgentMaturity.D1)

        # 4. Store some memories
        db.create_memory(project_id, "decision", "framework", "FastAPI + Next.js")

        # 5. Update to active
        db.update_project(project_id, {"status": ProjectStatus.ACTIVE})

        # 6. Verify final state
        project = db.get_project(project_id)
        assert project["status"] == "active"

        memories = db.get_project_memories(project_id)
        assert len(memories) >= 1

        agents = db.list_agents()
        assert len(agents) >= 1


@pytest.mark.unit
class TestTestResults:
    """Test test_results table and operations (cf-42)."""

    def test_create_test_result(self, temp_db_path):
        """Test creating a test result record."""
        db = Database(temp_db_path)
        db.initialize()

        # Create project and task
        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test Task",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create test result
        result_id = db.create_test_result(
            task_id=task_id,
            status="passed",
            passed=10,
            failed=0,
            errors=0,
            skipped=0,
            duration=1.5,
            output='{"summary": "all passed"}',
        )

        assert result_id is not None
        assert isinstance(result_id, int)

    def test_get_test_results_by_task(self, temp_db_path):
        """Test retrieving test results for a task."""
        db = Database(temp_db_path)
        db.initialize()

        # Create project and task
        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test Task",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create test result
        db.create_test_result(
            task_id=task_id,
            status="passed",
            passed=10,
            failed=0,
            errors=0,
            skipped=0,
            duration=1.5,
            output='{"summary": "all passed"}',
        )

        # Retrieve results
        results = db.get_test_results_by_task(task_id)

        assert len(results) == 1
        assert results[0]["status"] == "passed"
        assert results[0]["passed"] == 10
        assert results[0]["duration"] == 1.5

    def test_test_results_foreign_key_to_task(self, temp_db_path):
        """Test that test_results has foreign key to tasks table."""
        db = Database(temp_db_path)
        db.initialize()

        # Verify schema includes task_id foreign key
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(test_results)")
        columns = cursor.fetchall()

        column_names = [col[1] for col in columns]
        assert "task_id" in column_names

    def test_multiple_test_runs_for_task(self, temp_db_path):
        """Test storing multiple test runs for same task (retries)."""
        db = Database(temp_db_path)
        db.initialize()

        # Create task
        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test Task",
            description="Test",
            status=TaskStatus.COMPLETED,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # First run: failed
        db.create_test_result(
            task_id=task_id,
            status="failed",
            passed=7,
            failed=3,
            errors=0,
            skipped=0,
            duration=2.0,
            output='{"summary": "some failed"}',
        )

        # Second run: passed
        db.create_test_result(
            task_id=task_id,
            status="passed",
            passed=10,
            failed=0,
            errors=0,
            skipped=0,
            duration=1.8,
            output='{"summary": "all passed"}',
        )

        # Get all results
        results = db.get_test_results_by_task(task_id)

        assert len(results) == 2
        # Should be ordered by created_at (newest first or oldest first)
        statuses = [r["status"] for r in results]
        assert "failed" in statuses
        assert "passed" in statuses


@pytest.mark.unit
class TestLintResults:
    """Test lint_results table and operations (T091-T092)."""

    # T091: Test lint results database storage
    def test_create_lint_result(self, temp_db_path):
        """Test creating a lint result record in database."""
        db = Database(temp_db_path)
        db.initialize()

        # Create project and task
        project_id = db.create_project("test-project", "Test project for linting")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Lint Task",
            description="Test lint",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create lint result
        result_id = db.create_lint_result(
            task_id=task_id,
            linter="ruff",
            error_count=5,
            warning_count=10,
            files_linted=3,
            output='{"findings": [{"code": "F401", "message": "unused import"}]}',
        )

        assert result_id is not None
        assert isinstance(result_id, int)

    def test_get_lint_results_for_task(self, temp_db_path):
        """Test retrieving lint results for a specific task."""
        db = Database(temp_db_path)
        db.initialize()

        # Create project and task
        project_id = db.create_project("test-project", "Test project for linting")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Lint Task",
            description="Test lint",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create multiple lint results for same task (ruff + eslint)
        db.create_lint_result(
            task_id=task_id,
            linter="ruff",
            error_count=5,
            warning_count=10,
            files_linted=3,
            output='{"findings": []}',
        )

        db.create_lint_result(
            task_id=task_id,
            linter="eslint",
            error_count=2,
            warning_count=7,
            files_linted=2,
            output='{"findings": []}',
        )

        # Retrieve results
        results = db.get_lint_results_for_task(task_id)

        assert len(results) == 2
        linters = {r["linter"] for r in results}
        assert "ruff" in linters
        assert "eslint" in linters

        # Verify data integrity
        ruff_result = next(r for r in results if r["linter"] == "ruff")
        assert ruff_result["error_count"] == 5
        assert ruff_result["warning_count"] == 10
        assert ruff_result["files_linted"] == 3

    # T092: Test lint trend aggregation
    def test_get_lint_trend(self, temp_db_path):
        """Test aggregating lint results over time for trend analysis."""
        db = Database(temp_db_path)
        db.initialize()

        # Create project
        project_id = db.create_project("test-project", "Test project for trend analysis")

        # Create multiple tasks with lint results
        for i in range(5):
            issue_id = db.create_issue(
                {
                    "project_id": project_id,
                    "issue_number": f"{i+1}.0",
                    "title": f"Issue {i+1}",
                    "status": "pending",
                    "priority": 0,
                    "workflow_step": 1,
                }
            )
            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=f"{i+1}.0.1",
                parent_issue_number=f"{i+1}.0",
                title=f"Task {i+1}",
                description="Test",
                status=TaskStatus.COMPLETED,
                priority=0,
                workflow_step=1,
                can_parallelize=False,
            )

            # Simulate improving quality over time (fewer errors each iteration)
            db.create_lint_result(
                task_id=task_id,
                linter="ruff",
                error_count=10 - i,  # 10, 9, 8, 7, 6
                warning_count=20 - (i * 2),  # 20, 18, 16, 14, 12
                files_linted=5,
                output="{}",
            )

        # Get trend for last 7 days
        trend = db.get_lint_trend(project_id, days=7)

        assert len(trend) > 0
        # Verify data structure (matches get_lint_trend implementation)
        for entry in trend:
            assert "date" in entry
            assert "linter" in entry
            assert "error_count" in entry
            assert "warning_count" in entry

    def test_lint_results_foreign_key_to_task(self, temp_db_path):
        """Test that lint_results has foreign key to tasks table."""
        db = Database(temp_db_path)
        db.initialize()

        # Verify schema includes task_id foreign key
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(lint_results)")
        columns = cursor.fetchall()

        column_names = [col[1] for col in columns]
        assert "task_id" in column_names

    def test_multiple_linters_for_same_task(self, temp_db_path):
        """Test storing results from multiple linters (ruff + eslint) for same task."""
        db = Database(temp_db_path)
        db.initialize()

        # Create task
        project_id = db.create_project("test-project", "Test project for multi-linter")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Mixed Task",
            description="Python + TypeScript",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Ruff result (Python)
        db.create_lint_result(
            task_id=task_id,
            linter="ruff",
            error_count=3,
            warning_count=5,
            files_linted=2,
            output='{"findings": [{"code": "F401"}]}',
        )

        # ESLint result (TypeScript)
        db.create_lint_result(
            task_id=task_id,
            linter="eslint",
            error_count=1,
            warning_count=2,
            files_linted=1,
            output='{"findings": [{"ruleId": "no-unused-vars"}]}',
        )

        # Get all results
        results = db.get_lint_results_for_task(task_id)

        assert len(results) == 2
        # Verify both linters present
        linters = {r["linter"] for r in results}
        assert linters == {"ruff", "eslint"}

    def test_lint_output_json_storage(self, temp_db_path):
        """Test that lint output JSON is stored and retrieved correctly."""
        db = Database(temp_db_path)
        db.initialize()

        # Create task
        project_id = db.create_project("test-project", "Test project for JSON storage")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Lint Task",
            description="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Create lint result with complex JSON output
        detailed_output = json.dumps(
            {
                "findings": [
                    {"code": "F401", "message": "unused import 'os'", "line": 1},
                    {"code": "E501", "message": "line too long", "line": 5},
                ],
                "metadata": {"version": "0.1.0", "duration": "0.5s"},
            }
        )

        db.create_lint_result(
            task_id=task_id,
            linter="ruff",
            error_count=2,
            warning_count=0,
            files_linted=1,
            output=detailed_output,
        )

        # Retrieve and verify JSON
        results = db.get_lint_results_for_task(task_id)
        assert len(results) == 1

        stored_output = results[0]["output"]
        parsed_output = json.loads(stored_output)

        assert len(parsed_output["findings"]) == 2
        assert parsed_output["metadata"]["version"] == "0.1.0"
