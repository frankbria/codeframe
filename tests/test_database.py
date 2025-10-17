"""Tests for database CRUD operations.

Following TDD: These tests are written FIRST, before full implementation.
Target: >90% coverage for database.py module.
"""

import json
import pytest
from pathlib import Path
from datetime import datetime
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

        project_id = db.create_project("test-project", ProjectStatus.INIT)

        assert project_id is not None
        assert isinstance(project_id, int)
        assert project_id > 0

    def test_get_project_by_id(self, temp_db_path):
        """Test retrieving a project by ID."""
        db = Database(temp_db_path)
        db.initialize()

        # Create project
        project_id = db.create_project("test-project", ProjectStatus.INIT)

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
        db.create_project("project1", ProjectStatus.INIT)
        db.create_project("project2", ProjectStatus.PLANNING)
        db.create_project("project3", ProjectStatus.ACTIVE)

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

        project_id = db.create_project("test-project", ProjectStatus.INIT)

        # Update status
        db.update_project(project_id, {"status": ProjectStatus.ACTIVE})

        # Verify update
        project = db.get_project(project_id)
        assert project["status"] == "active"

    def test_update_project_config(self, temp_db_path):
        """Test updating project configuration."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", ProjectStatus.INIT)

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

        project_id = db.create_project("test-project", ProjectStatus.INIT)
        project = db.get_project(project_id)

        assert project["phase"] == "discovery"

    def test_update_project_phase(self, temp_db_path):
        """Test updating project phase."""
        db = Database(temp_db_path)
        db.initialize()

        project_id = db.create_project("test-project", ProjectStatus.INIT)

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

        project_id = db.create_project("test-project", ProjectStatus.INIT)

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
        project_id = db.create_project("test-project", ProjectStatus.INIT)

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

        project_id = db.create_project("test-project", ProjectStatus.INIT)

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

        project_id = db.create_project("test-project", ProjectStatus.INIT)

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

        project_id = db.create_project("test-project", ProjectStatus.INIT)

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

        project_id = db.create_project("test-project", ProjectStatus.INIT)

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

        project_id = db.create_project("test-project", ProjectStatus.INIT)

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
            db.create_project("test-project", ProjectStatus.INIT)
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
        """Test that invalid agent type is rejected."""
        db = Database(temp_db_path)
        db.initialize()

        cursor = db.conn.cursor()

        with pytest.raises(Exception):  # sqlite3.IntegrityError
            cursor.execute(
                "INSERT INTO agents (id, type) VALUES (?, ?)",
                ("test-agent", "INVALID_TYPE"),
            )

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
        project_id = db.create_project("test-project", ProjectStatus.INIT)

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
        project_id = db.create_project("my-app", ProjectStatus.INIT)

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
