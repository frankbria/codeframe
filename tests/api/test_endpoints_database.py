"""Tests for Status Server endpoints with database integration.

Following TDD: These tests are written FIRST, before implementation.
Task: cf-8.3 - Wire endpoints to database
"""

import pytest
from codeframe.core.models import AgentMaturity


def get_app():
    """Get the current app instance after module reload."""
    from codeframe.ui.server import app

    return app


@pytest.mark.unit
class TestProjectsEndpoint:
    """Test GET /api/projects endpoint with database."""

    def test_list_projects_empty_database(self, api_client):
        """Test listing projects when database is empty."""
        # ACT
        response = api_client.get("/api/projects")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert data["projects"] == []

    def test_list_projects_with_data(self, api_client):
        """Test listing projects with actual database data."""
        # Create test projects in database
        db = get_app().state.db
        db.create_project("test-project-1", "Test Project 1 project")
        db.create_project("test-project-2", "Test Project 2 project")

        # ACT
        response = api_client.get("/api/projects")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert len(data["projects"]) == 2

        # Verify project data
        projects = {p["name"]: p for p in data["projects"]}
        assert "test-project-1" in projects
        assert projects["test-project-1"]["status"] == "init"
        assert "test-project-2" in projects
        assert projects["test-project-2"]["status"] == "init"

    def test_list_projects_returns_all_fields(self, api_client):
        """Test that list_projects returns all expected fields."""
        db = get_app().state.db
        db.create_project("full-project", "Full Project project")

        # ACT
        response = api_client.get("/api/projects")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        project = data["projects"][0]

        # Verify required fields exist
        assert "id" in project
        assert "name" in project
        assert "status" in project
        assert "created_at" in project


@pytest.mark.unit
class TestProjectStatusEndpoint:
    """Test GET /api/projects/{id}/status endpoint with database."""

    def test_get_project_status_success(self, api_client):
        """Test getting project status for existing project."""
        db = get_app().state.db
        project_id = db.create_project("status-project", "Status Project project")

        # ACT
        response = api_client.get(f"/api/projects/{project_id}/status")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == project_id
        assert data["name"] == "status-project"
        assert data["status"] == "init"

    def test_get_project_status_not_found(self, api_client):
        """Test getting status for non-existent project returns 404."""
        # ACT
        response = api_client.get("/api/projects/99999/status")

        # ASSERT
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_get_project_status_returns_complete_data(self, api_client):
        """Test that project status returns all expected fields."""
        db = get_app().state.db
        project_id = db.create_project("complete-project", "Complete Project project")

        # ACT
        response = api_client.get(f"/api/projects/{project_id}/status")

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        # Verify all expected fields
        assert "project_id" in data
        assert "name" in data
        assert "status" in data
        assert isinstance(data["project_id"], int)
        assert isinstance(data["name"], str)
        assert isinstance(data["status"], str)


@pytest.mark.unit
class TestAgentsEndpoint:
    """Test GET /api/projects/{id}/agents endpoint with database."""

    def test_get_agents_empty_list(self, api_client):
        """Test getting agents when no agents exist for project."""
        db = get_app().state.db
        project_id = db.create_project("no-agents-project", "No Agents Project project")

        # ACT
        response = api_client.get(f"/api/projects/{project_id}/agents")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_get_agents_with_data(self, api_client):
        """Test getting agents with actual database data."""
        db = get_app().state.db
        project_id = db.create_project("agents-project", "Agents Project project")

        # Create test agents and assign them to project
        db.create_agent("lead-agent", "lead", "claude", AgentMaturity.D3)
        db.create_agent("backend-agent", "backend", "claude", AgentMaturity.D2)

        # Assign agents to project
        db.assign_agent_to_project(project_id, "lead-agent", "leader")
        db.assign_agent_to_project(project_id, "backend-agent", "worker")

        # ACT
        response = api_client.get(f"/api/projects/{project_id}/agents")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

        # Verify agent data
        agents = {a["agent_id"]: a for a in data}
        assert "lead-agent" in agents
        assert "backend-agent" in agents

    def test_get_agents_returns_all_fields(self, api_client):
        """Test that agents endpoint returns all expected fields."""
        db = get_app().state.db
        project_id = db.create_project("full-agents-project", "Full Agents Project project")
        db.create_agent("test-agent", "test", "claude", AgentMaturity.D4)

        # Assign agent to project
        db.assign_agent_to_project(project_id, "test-agent", "worker")

        # ACT
        response = api_client.get(f"/api/projects/{project_id}/agents")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        agent = data[0]

        # Verify required fields (agent assignment response)
        assert "agent_id" in agent
        assert "assignment_id" in agent
        assert "role" in agent


@pytest.mark.integration
class TestEndpointDatabaseIntegration:
    """Integration tests for endpoints with database."""

    def test_complete_project_workflow_via_api(self, api_client):
        """Test complete workflow: create project, get status, verify agents."""
        db = get_app().state.db

        # ACT: Create project and agent
        project_id = db.create_project("workflow-project", "Workflow Project project")
        db.create_agent("workflow-lead", "lead", "claude", AgentMaturity.D3)

        # Test 1: List projects - verify our project exists (don't assume total count)
        response = api_client.get("/api/projects")
        assert response.status_code == 200
        projects = response.json()["projects"]
        assert any(p["id"] == project_id or p["name"] == "workflow-project" for p in projects)

        # Test 2: Get project status
        response = api_client.get(f"/api/projects/{project_id}/status")
        assert response.status_code == 200
        status = response.json()
        assert status["name"] == "workflow-project"
        assert status["status"] == "init"

        # Test 3: Get agents
        response = api_client.get(f"/api/projects/{project_id}/agents")
        assert response.status_code == 200
        agents = response.json()  # Returns list directly, not wrapped in dict
        assert len(agents) == 0  # No agents assigned yet

    def test_endpoints_survive_multiple_requests(self, api_client):
        """Test that endpoints work consistently across multiple requests."""
        db = get_app().state.db
        project_id = db.create_project("stable-project", "Stable Project project")

        # ACT & ASSERT: Make multiple requests
        for _ in range(5):
            # List projects - verify our project exists (don't assume total count)
            response = api_client.get("/api/projects")
            assert response.status_code == 200
            projects = response.json()["projects"]
            assert any(p["id"] == project_id or p["name"] == "stable-project" for p in projects)

            # Get project status
            response = api_client.get(f"/api/projects/{project_id}/status")
            assert response.status_code == 200
            assert response.json()["name"] == "stable-project"

            # Get agents
            response = api_client.get(f"/api/projects/{project_id}/agents")
            assert response.status_code == 200
