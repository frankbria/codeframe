"""Tests for Multi-Agent Per Project API endpoints.

Multi-Agent Per Project - Phase 3: API Endpoints
Tests for:
- GET /api/projects/{project_id}/agents
- POST /api/projects/{project_id}/agents
- DELETE /api/projects/{project_id}/agents/{agent_id}
- PATCH /api/projects/{project_id}/agents/{agent_id}
- GET /api/agents/{agent_id}/projects
"""

import pytest
from fastapi.testclient import TestClient
from codeframe.core.models import AgentMaturity


@pytest.mark.usefixtures("api_client")
class TestMultiAgentAPI:
    """Test class for multi-agent per project API endpoints."""

    def test_get_project_agents_empty(self, api_client: TestClient):
        """Test getting agents for a project with no agents assigned."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Get agents for project (should be empty)
        response = api_client.get(f"/api/projects/{project_id}/agents")
        assert response.status_code == 200
        agents = response.json()
        assert isinstance(agents, list)
        assert len(agents) == 0

    def test_get_project_agents_nonexistent_project(self, api_client: TestClient):
        """Test getting agents for a non-existent project."""
        response = api_client.get("/api/projects/99999/agents")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_assign_agent_to_project_success(self, api_client: TestClient):
        """Test successfully assigning an agent to a project."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Create an agent
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )

        # Assign agent to project
        response = api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "assignment_id" in data
        assert data["assignment_id"] > 0
        assert "message" in data
        assert "backend-001" in data["message"]
        assert "primary_backend" in data["message"]

    def test_assign_agent_nonexistent_project(self, api_client: TestClient):
        """Test assigning an agent to a non-existent project."""
        response = api_client.post(
            "/api/projects/99999/agents",
            json={"agent_id": "backend-001", "role": "worker"},
        )
        assert response.status_code == 404
        assert "project" in response.json()["detail"].lower()

    def test_assign_nonexistent_agent(self, api_client: TestClient):
        """Test assigning a non-existent agent to a project."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Try to assign non-existent agent
        response = api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "nonexistent-agent", "role": "worker"},
        )
        assert response.status_code == 404
        assert "agent" in response.json()["detail"].lower()

    def test_assign_agent_already_assigned(self, api_client: TestClient):
        """Test assigning an agent that is already assigned to the project."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Create an agent
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )

        # Assign agent to project (first time)
        response = api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )
        assert response.status_code == 201

        # Try to assign same agent again
        response = api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "secondary_backend"},
        )
        assert response.status_code == 400
        assert "already assigned" in response.json()["detail"].lower()

    def test_get_project_agents_with_assignments(self, api_client: TestClient):
        """Test getting agents for a project with multiple agents assigned."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Create multiple agents
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )
        db.create_agent(
            agent_id="frontend-001",
            agent_type="frontend",
            provider="claude",
            maturity_level=AgentMaturity.D3,
        )
        db.create_agent(
            agent_id="test-001",
            agent_type="test",
            provider="claude",
            maturity_level=AgentMaturity.D4,
        )

        # Assign all agents to project
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "frontend-001", "role": "primary_frontend"},
        )
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "test-001", "role": "qa_engineer"},
        )

        # Get agents for project
        response = api_client.get(f"/api/projects/{project_id}/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 3

        # Verify all agents are present with correct roles
        agent_ids = {agent["agent_id"] for agent in agents}
        assert agent_ids == {"backend-001", "frontend-001", "test-001"}

        roles = {agent["agent_id"]: agent["role"] for agent in agents}
        assert roles["backend-001"] == "primary_backend"
        assert roles["frontend-001"] == "primary_frontend"
        assert roles["test-001"] == "qa_engineer"

        # Verify all agents are active
        for agent in agents:
            assert agent["is_active"] is True
            assert agent["unassigned_at"] is None

    def test_get_project_agents_active_only(self, api_client: TestClient):
        """Test filtering agents by active status."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Create agents
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )
        db.create_agent(
            agent_id="backend-002",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )

        # Assign both agents
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-002", "role": "secondary_backend"},
        )

        # Remove one agent
        response = api_client.delete(f"/api/projects/{project_id}/agents/backend-002")
        assert response.status_code == 204

        # Get active agents only (default)
        response = api_client.get(f"/api/projects/{project_id}/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 1
        assert agents[0]["agent_id"] == "backend-001"

        # Get all agents (including inactive)
        response = api_client.get(f"/api/projects/{project_id}/agents?is_active=false")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 2

    def test_remove_agent_from_project_success(self, api_client: TestClient):
        """Test successfully removing an agent from a project."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Create and assign an agent
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )

        # Remove agent from project
        response = api_client.delete(f"/api/projects/{project_id}/agents/backend-001")
        assert response.status_code == 204

        # Verify agent is no longer active
        response = api_client.get(f"/api/projects/{project_id}/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 0

    def test_remove_agent_not_assigned(self, api_client: TestClient):
        """Test removing an agent that is not assigned to the project."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Try to remove non-assigned agent
        response = api_client.delete(f"/api/projects/{project_id}/agents/backend-001")
        assert response.status_code == 404
        assert "no active assignment" in response.json()["detail"].lower()

    def test_update_agent_role_success(self, api_client: TestClient):
        """Test successfully updating an agent's role on a project."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Create and assign an agent
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )

        # Update agent role
        response = api_client.patch(
            f"/api/projects/{project_id}/agents/backend-001",
            json={"role": "secondary_backend"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "secondary_backend" in data["message"]

        # Verify role was updated
        response = api_client.get(f"/api/projects/{project_id}/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 1
        assert agents[0]["role"] == "secondary_backend"

    def test_update_agent_role_not_assigned(self, api_client: TestClient):
        """Test updating role for an agent that is not assigned to the project."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Try to update role for non-assigned agent
        response = api_client.patch(
            f"/api/projects/{project_id}/agents/backend-001",
            json={"role": "secondary_backend"},
        )
        assert response.status_code == 404
        assert "no active assignment" in response.json()["detail"].lower()

    def test_get_agent_projects_empty(self, api_client: TestClient):
        """Test getting projects for an agent with no assignments."""
        # Create an agent
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )

        # Get projects for agent (should be empty)
        response = api_client.get("/api/agents/backend-001/projects")
        assert response.status_code == 200
        projects = response.json()
        assert isinstance(projects, list)
        assert len(projects) == 0

    def test_get_agent_projects_nonexistent_agent(self, api_client: TestClient):
        """Test getting projects for a non-existent agent."""
        response = api_client.get("/api/agents/nonexistent-agent/projects")
        assert response.status_code == 404
        assert "agent" in response.json()["detail"].lower()

    def test_get_agent_projects_with_assignments(self, api_client: TestClient):
        """Test getting projects for an agent with multiple assignments."""
        # Create multiple projects
        project_ids = []
        for i in range(3):
            response = api_client.post(
                "/api/projects",
                json={"name": f"Project {i}", "description": f"Description {i}"},
            )
            assert response.status_code == 201
            project_ids.append(response.json()["id"])

        # Create an agent
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )

        # Assign agent to all projects with different roles
        roles = ["primary_backend", "secondary_backend", "code_reviewer"]
        for project_id, role in zip(project_ids, roles):
            api_client.post(
                f"/api/projects/{project_id}/agents",
                json={"agent_id": "backend-001", "role": role},
            )

        # Get projects for agent
        response = api_client.get("/api/agents/backend-001/projects")
        assert response.status_code == 200
        projects = response.json()
        assert len(projects) == 3

        # Verify all projects are present with correct roles
        project_id_set = {project["project_id"] for project in projects}
        assert project_id_set == set(project_ids)

        # Verify roles
        project_roles = {project["project_id"]: project["role"] for project in projects}
        for project_id, expected_role in zip(project_ids, roles):
            assert project_roles[project_id] == expected_role

        # Verify all assignments are active
        for project in projects:
            assert project["is_active"] is True
            assert project["unassigned_at"] is None

    def test_get_agent_projects_active_only(self, api_client: TestClient):
        """Test filtering projects by active status."""
        # Create two projects
        response = api_client.post(
            "/api/projects",
            json={"name": "Project 1", "description": "Description 1"},
        )
        assert response.status_code == 201
        project_id_1 = response.json()["id"]

        response = api_client.post(
            "/api/projects",
            json={"name": "Project 2", "description": "Description 2"},
        )
        assert response.status_code == 201
        project_id_2 = response.json()["id"]

        # Create an agent
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )

        # Assign agent to both projects
        api_client.post(
            f"/api/projects/{project_id_1}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )
        api_client.post(
            f"/api/projects/{project_id_2}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )

        # Remove agent from project 2
        response = api_client.delete(f"/api/projects/{project_id_2}/agents/backend-001")
        assert response.status_code == 204

        # Get active projects only (default)
        response = api_client.get("/api/agents/backend-001/projects")
        assert response.status_code == 200
        projects = response.json()
        assert len(projects) == 1
        assert projects[0]["project_id"] == project_id_1

        # Get all projects (including inactive)
        response = api_client.get("/api/agents/backend-001/projects?active_only=false")
        assert response.status_code == 200
        projects = response.json()
        assert len(projects) == 2

    def test_agent_reassignment_after_removal(self, api_client: TestClient):
        """Test that an agent can be reassigned after being removed."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Create an agent
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )

        # Assign agent
        response = api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )
        assert response.status_code == 201

        # Remove agent
        response = api_client.delete(f"/api/projects/{project_id}/agents/backend-001")
        assert response.status_code == 204

        # Reassign agent with different role
        response = api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "code_reviewer"},
        )
        assert response.status_code == 201

        # Verify new assignment
        response = api_client.get(f"/api/projects/{project_id}/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 1
        assert agents[0]["agent_id"] == "backend-001"
        assert agents[0]["role"] == "code_reviewer"

    def test_multiple_agents_different_roles(self, api_client: TestClient):
        """Test assigning multiple agents with different roles to same project."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Create multiple agents of same type
        from codeframe.ui import server

        db = server.app.state.db
        db.create_agent(
            agent_id="backend-001",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D2,
        )
        db.create_agent(
            agent_id="backend-002",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D3,
        )
        db.create_agent(
            agent_id="backend-003",
            agent_type="backend",
            provider="claude",
            maturity_level=AgentMaturity.D4,
        )

        # Assign agents with different roles
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": "primary_backend"},
        )
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-002", "role": "secondary_backend"},
        )
        api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-003", "role": "code_reviewer"},
        )

        # Verify all assignments
        response = api_client.get(f"/api/projects/{project_id}/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 3

        # Verify correct role assignment
        roles = {agent["agent_id"]: agent["role"] for agent in agents}
        assert roles["backend-001"] == "primary_backend"
        assert roles["backend-002"] == "secondary_backend"
        assert roles["backend-003"] == "code_reviewer"

    def test_agent_assignment_request_validation(self, api_client: TestClient):
        """Test Pydantic validation for agent assignment request."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Test missing agent_id
        response = api_client.post(f"/api/projects/{project_id}/agents", json={"role": "worker"})
        assert response.status_code == 422  # Validation error

        # Test empty agent_id
        response = api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "", "role": "worker"},
        )
        assert response.status_code == 422  # Validation error

        # Test empty role
        response = api_client.post(
            f"/api/projects/{project_id}/agents",
            json={"agent_id": "backend-001", "role": ""},
        )
        assert response.status_code == 422  # Validation error

    def test_agent_role_update_request_validation(self, api_client: TestClient):
        """Test Pydantic validation for role update request."""
        # Create a project
        response = api_client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "Test description"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Test missing role
        response = api_client.patch(f"/api/projects/{project_id}/agents/backend-001", json={})
        assert response.status_code == 422  # Validation error

        # Test empty role
        response = api_client.patch(
            f"/api/projects/{project_id}/agents/backend-001", json={"role": ""}
        )
        assert response.status_code == 422  # Validation error
