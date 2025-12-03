"""Tests for project_agents junction table and multi-agent methods."""

import pytest
import sqlite3
from codeframe.persistence.database import Database
from codeframe.core.models import AgentMaturity


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    db = Database(":memory:")
    db.initialize()
    return db


@pytest.fixture
def sample_project(db):
    """Create a sample project for testing."""
    project_id = db.create_project(
        name="test-project",
        description="Test project for multi-agent",
        workspace_path="/tmp/test"
    )
    return project_id


@pytest.fixture
def sample_agents(db):
    """Create sample agents for testing."""
    agent_ids = []
    for i in range(3):
        agent_id = f"agent-{i:03d}"
        db.create_agent(
            agent_id=agent_id,
            agent_type="backend" if i < 2 else "frontend",
            provider="claude",
            maturity_level=AgentMaturity.D4
        )
        agent_ids.append(agent_id)
    return agent_ids


# Schema Tests
def test_project_agents_table_exists(db):
    """Verify project_agents table exists with correct schema."""
    cursor = db.conn.cursor()
    cursor.execute("PRAGMA table_info(project_agents)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    # Verify all columns exist
    assert "id" in columns, "Missing id column"
    assert "project_id" in columns, "Missing project_id column"
    assert "agent_id" in columns, "Missing agent_id column"
    assert "role" in columns, "Missing role column"
    assert "assigned_at" in columns, "Missing assigned_at column"
    assert "unassigned_at" in columns, "Missing unassigned_at column"
    assert "is_active" in columns, "Missing is_active column"


def test_project_agents_indexes_exist(db):
    """Verify all performance indexes exist."""
    cursor = db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='project_agents'")
    indexes = {row[0] for row in cursor.fetchall()}

    expected_indexes = {
        "idx_project_agents_project_active",
        "idx_project_agents_agent_active",
        "idx_project_agents_assigned_at",
        "idx_project_agents_unassigned",
        "idx_project_agents_unique_active"
    }

    assert expected_indexes.issubset(indexes), f"Missing indexes: {expected_indexes - indexes}"


def test_agents_table_no_project_id(db):
    """Verify agents table does NOT have project_id column."""
    cursor = db.conn.cursor()
    cursor.execute("PRAGMA table_info(agents)")
    columns = {row[1] for row in cursor.fetchall()}

    assert "project_id" not in columns, "agents table should not have project_id column"
    assert "created_at" in columns, "agents table should have created_at column"


# assign_agent_to_project() Tests
def test_assign_agent_to_project(db, sample_project, sample_agents):
    """Test assigning an agent to a project."""
    assignment_id = db.assign_agent_to_project(
        project_id=sample_project,
        agent_id=sample_agents[0],
        role="primary_backend"
    )

    assert assignment_id is not None
    assert assignment_id > 0


def test_assign_multiple_agents_to_project(db, sample_project, sample_agents):
    """Test assigning multiple agents to same project."""
    for i, agent_id in enumerate(sample_agents):
        assignment_id = db.assign_agent_to_project(
            project_id=sample_project,
            agent_id=agent_id,
            role=f"role-{i}"
        )
        assert assignment_id > 0


def test_assign_agent_to_multiple_projects(db, sample_agents):
    """Test assigning same agent to multiple projects."""
    project1 = db.create_project(name="project1", description="Project 1", workspace_path="/tmp/p1")
    project2 = db.create_project(name="project2", description="Project 2", workspace_path="/tmp/p2")

    agent_id = sample_agents[0]

    assignment1 = db.assign_agent_to_project(project1, agent_id, "backend")
    assignment2 = db.assign_agent_to_project(project2, agent_id, "reviewer")

    assert assignment1 != assignment2


def test_assign_duplicate_active_agent_fails(db, sample_project, sample_agents):
    """Test that assigning same agent to same project twice (while active) fails."""
    agent_id = sample_agents[0]

    db.assign_agent_to_project(sample_project, agent_id, "backend")

    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        db.assign_agent_to_project(sample_project, agent_id, "backend")

    assert "UNIQUE constraint failed" in str(exc_info.value)


def test_assign_agent_after_removal_succeeds(db, sample_project, sample_agents):
    """Test that reassigning after removal works."""
    agent_id = sample_agents[0]

    # First assignment
    db.assign_agent_to_project(sample_project, agent_id, "backend")

    # Remove agent
    db.remove_agent_from_project(sample_project, agent_id)

    # Reassign (should work now)
    assignment_id = db.assign_agent_to_project(sample_project, agent_id, "reviewer")
    assert assignment_id > 0


# get_agents_for_project() Tests
def test_get_agents_for_project_empty(db, sample_project):
    """Test getting agents for project with no assignments."""
    agents = db.get_agents_for_project(sample_project)
    assert agents == []


def test_get_agents_for_project_active_only(db, sample_project, sample_agents):
    """Test getting only active agents for project."""
    # Assign 2 agents
    db.assign_agent_to_project(sample_project, sample_agents[0], "backend")
    db.assign_agent_to_project(sample_project, sample_agents[1], "reviewer")

    # Remove one agent
    db.remove_agent_from_project(sample_project, sample_agents[1])

    # Get active agents
    agents = db.get_agents_for_project(sample_project, active_only=True)

    assert len(agents) == 1
    assert agents[0]["agent_id"] == sample_agents[0]
    assert agents[0]["role"] == "backend"
    assert agents[0]["is_active"] == 1


def test_get_agents_for_project_all(db, sample_project, sample_agents):
    """Test getting all agents (active and inactive) for project."""
    # Assign 2 agents
    db.assign_agent_to_project(sample_project, sample_agents[0], "backend")
    db.assign_agent_to_project(sample_project, sample_agents[1], "reviewer")

    # Remove one agent
    db.remove_agent_from_project(sample_project, sample_agents[1])

    # Get all agents
    agents = db.get_agents_for_project(sample_project, active_only=False)

    assert len(agents) == 2


def test_get_agents_for_project_includes_metadata(db, sample_project, sample_agents):
    """Test that get_agents_for_project returns agent metadata."""
    db.assign_agent_to_project(sample_project, sample_agents[0], "backend")

    agents = db.get_agents_for_project(sample_project)

    assert len(agents) == 1
    agent = agents[0]

    # Check agent fields
    assert agent["agent_id"] == sample_agents[0]
    assert agent["type"] == "backend"
    assert agent["provider"] == "claude"
    assert agent["maturity_level"] == "delegating"

    # Check assignment fields
    assert agent["role"] == "backend"
    assert agent["assigned_at"] is not None
    assert agent["is_active"] == 1


# get_projects_for_agent() Tests
def test_get_projects_for_agent_empty(db, sample_agents):
    """Test getting projects for agent with no assignments."""
    projects = db.get_projects_for_agent(sample_agents[0])
    assert projects == []


def test_get_projects_for_agent_active_only(db, sample_agents):
    """Test getting only active projects for agent."""
    project1 = db.create_project(name="project1", description="Project 1", workspace_path="/tmp/p1")
    project2 = db.create_project(name="project2", description="Project 2", workspace_path="/tmp/p2")

    agent_id = sample_agents[0]

    # Assign to both projects
    db.assign_agent_to_project(project1, agent_id, "backend")
    db.assign_agent_to_project(project2, agent_id, "reviewer")

    # Remove from project2
    db.remove_agent_from_project(project2, agent_id)

    # Get active projects
    projects = db.get_projects_for_agent(agent_id, active_only=True)

    assert len(projects) == 1
    assert projects[0]["project_id"] == project1
    assert projects[0]["role"] == "backend"


def test_get_projects_for_agent_all(db, sample_agents):
    """Test getting all projects (active and inactive) for agent."""
    project1 = db.create_project(name="project1", description="Project 1", workspace_path="/tmp/p1")
    project2 = db.create_project(name="project2", description="Project 2", workspace_path="/tmp/p2")

    agent_id = sample_agents[0]

    # Assign to both projects
    db.assign_agent_to_project(project1, agent_id, "backend")
    db.assign_agent_to_project(project2, agent_id, "reviewer")

    # Remove from project2
    db.remove_agent_from_project(project2, agent_id)

    # Get all projects
    projects = db.get_projects_for_agent(agent_id, active_only=False)

    assert len(projects) == 2


# remove_agent_from_project() Tests
def test_remove_agent_from_project(db, sample_project, sample_agents):
    """Test removing agent from project (soft delete)."""
    agent_id = sample_agents[0]

    db.assign_agent_to_project(sample_project, agent_id, "backend")

    rows_affected = db.remove_agent_from_project(sample_project, agent_id)

    assert rows_affected == 1

    # Verify agent is no longer active
    agents = db.get_agents_for_project(sample_project, active_only=True)
    assert len(agents) == 0

    # Verify agent still exists in history
    agents = db.get_agents_for_project(sample_project, active_only=False)
    assert len(agents) == 1
    assert agents[0]["is_active"] == 0
    assert agents[0]["unassigned_at"] is not None


def test_remove_nonexistent_assignment(db, sample_project, sample_agents):
    """Test removing agent that's not assigned returns 0."""
    rows_affected = db.remove_agent_from_project(sample_project, sample_agents[0])
    assert rows_affected == 0


def test_remove_already_removed_agent(db, sample_project, sample_agents):
    """Test removing already-removed agent returns 0."""
    agent_id = sample_agents[0]

    db.assign_agent_to_project(sample_project, agent_id, "backend")
    db.remove_agent_from_project(sample_project, agent_id)

    # Try to remove again
    rows_affected = db.remove_agent_from_project(sample_project, agent_id)
    assert rows_affected == 0


# get_agent_assignment() Tests
def test_get_agent_assignment(db, sample_project, sample_agents):
    """Test getting assignment details for agent-project pair."""
    agent_id = sample_agents[0]

    db.assign_agent_to_project(sample_project, agent_id, "backend")

    assignment = db.get_agent_assignment(sample_project, agent_id)

    assert assignment is not None
    assert assignment["project_id"] == sample_project
    assert assignment["agent_id"] == agent_id
    assert assignment["role"] == "backend"
    assert assignment["is_active"] == 1
    assert assignment["unassigned_at"] is None


def test_get_agent_assignment_nonexistent(db, sample_project, sample_agents):
    """Test getting nonexistent assignment returns None."""
    assignment = db.get_agent_assignment(sample_project, sample_agents[0])
    assert assignment is None


def test_get_agent_assignment_returns_latest(db, sample_project, sample_agents):
    """Test that get_agent_assignment returns most recent assignment."""
    agent_id = sample_agents[0]

    # First assignment
    db.assign_agent_to_project(sample_project, agent_id, "backend")
    db.remove_agent_from_project(sample_project, agent_id)

    # Second assignment
    db.assign_agent_to_project(sample_project, agent_id, "reviewer")

    assignment = db.get_agent_assignment(sample_project, agent_id)

    assert assignment["role"] == "reviewer"
    assert assignment["is_active"] == 1


# reassign_agent_role() Tests
def test_reassign_agent_role(db, sample_project, sample_agents):
    """Test updating agent's role on project."""
    agent_id = sample_agents[0]

    db.assign_agent_to_project(sample_project, agent_id, "backend")

    rows_affected = db.reassign_agent_role(sample_project, agent_id, "lead_backend")

    assert rows_affected == 1

    assignment = db.get_agent_assignment(sample_project, agent_id)
    assert assignment["role"] == "lead_backend"


def test_reassign_role_nonexistent_assignment(db, sample_project, sample_agents):
    """Test reassigning role for nonexistent assignment returns 0."""
    rows_affected = db.reassign_agent_role(sample_project, sample_agents[0], "backend")
    assert rows_affected == 0


def test_reassign_role_inactive_assignment(db, sample_project, sample_agents):
    """Test reassigning role for inactive assignment returns 0."""
    agent_id = sample_agents[0]

    db.assign_agent_to_project(sample_project, agent_id, "backend")
    db.remove_agent_from_project(sample_project, agent_id)

    rows_affected = db.reassign_agent_role(sample_project, agent_id, "reviewer")
    assert rows_affected == 0


# get_available_agents() Tests
def test_get_available_agents_all(db, sample_agents):
    """Test getting all available agents."""
    agents = db.get_available_agents()

    assert len(agents) == 3
    assert agents[0]["active_assignments"] == 0


def test_get_available_agents_filter_by_type(db, sample_agents):
    """Test filtering available agents by type."""
    backend_agents = db.get_available_agents(agent_type="backend")
    frontend_agents = db.get_available_agents(agent_type="frontend")

    assert len(backend_agents) == 2
    assert len(frontend_agents) == 1


def test_get_available_agents_exclude_project(db, sample_project, sample_agents):
    """Test excluding agents already on project."""
    # Assign one agent to project
    db.assign_agent_to_project(sample_project, sample_agents[0], "backend")

    # Get available agents excluding this project
    agents = db.get_available_agents(exclude_project_id=sample_project)

    # Should return only agents not on project
    agent_ids = [a["id"] for a in agents]
    assert sample_agents[0] not in agent_ids
    assert len(agents) == 2


def test_get_available_agents_respects_capacity(db):
    """Test that agents at capacity (3+ projects) are not returned."""
    # Create agent
    agent_id = "busy-agent"
    db.create_agent(agent_id, "backend", "claude", AgentMaturity.D4)

    # Assign to 3 projects
    for i in range(3):
        project_id = db.create_project(
            name=f"project-{i}",
            description=f"Project {i}",
            workspace_path=f"/tmp/p{i}"
        )
        db.assign_agent_to_project(project_id, agent_id, "backend")

    # Agent should not appear in available agents
    agents = db.get_available_agents()
    agent_ids = [a["id"] for a in agents]
    assert agent_id not in agent_ids


def test_get_available_agents_ordering(db, sample_agents):
    """Test that available agents are ordered by assignment count and heartbeat."""
    project1 = db.create_project(
        name="project1",
        description="Project 1",
        workspace_path="/tmp/p1"
    )

    # Assign one agent to a project
    db.assign_agent_to_project(project1, sample_agents[0], "backend")

    agents = db.get_available_agents()

    # First agent should have 0 assignments (sample_agents[1] or [2])
    assert agents[0]["active_assignments"] == 0

    # Last agent should have 1 assignment (sample_agents[0])
    assert agents[-1]["active_assignments"] == 1
    assert agents[-1]["id"] == sample_agents[0]


# Foreign Key Constraint Tests
def test_cascade_delete_project(db, sample_project, sample_agents):
    """Test that deleting project cascades to project_agents."""
    db.assign_agent_to_project(sample_project, sample_agents[0], "backend")

    # Delete project
    cursor = db.conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (sample_project,))
    db.conn.commit()

    # Verify assignment is deleted
    cursor.execute("SELECT COUNT(*) FROM project_agents WHERE project_id = ?", (sample_project,))
    count = cursor.fetchone()[0]
    assert count == 0


def test_cascade_delete_agent(db, sample_project, sample_agents):
    """Test that deleting agent cascades to project_agents."""
    agent_id = sample_agents[0]
    db.assign_agent_to_project(sample_project, agent_id, "backend")

    # Delete agent
    cursor = db.conn.cursor()
    cursor.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    db.conn.commit()

    # Verify assignment is deleted
    cursor.execute("SELECT COUNT(*) FROM project_agents WHERE agent_id = ?", (agent_id,))
    count = cursor.fetchone()[0]
    assert count == 0


# Check Constraint Tests
def test_unassigned_at_check_constraint(db, sample_project, sample_agents):
    """Test that unassigned_at must be >= assigned_at."""
    agent_id = sample_agents[0]
    db.assign_agent_to_project(sample_project, agent_id, "backend")

    # Try to set unassigned_at to before assigned_at
    cursor = db.conn.cursor()
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        cursor.execute(
            """
            UPDATE project_agents
            SET unassigned_at = '2020-01-01 00:00:00'
            WHERE project_id = ? AND agent_id = ?
            """,
            (sample_project, agent_id)
        )

    assert "CHECK constraint failed" in str(exc_info.value)
