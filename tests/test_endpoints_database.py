"""Tests for Status Server endpoints with database integration.

Following TDD: These tests are written FIRST, before implementation.
Task: cf-8.3 - Wire endpoints to database
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from codeframe.core.models import ProjectStatus, AgentMaturity


@pytest.mark.unit
class TestProjectsEndpoint:
    """Test GET /api/projects endpoint with database."""

    def test_list_projects_empty_database(self, temp_db_path):
        """Test listing projects when database is empty."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            response = client.get("/api/projects")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert data["projects"] == []

    def test_list_projects_with_data(self, temp_db_path):
        """Test listing projects with actual database data."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            # Create test projects in database
            db = app.state.db
            project1_id = db.create_project("test-project-1", ProjectStatus.ACTIVE)
            project2_id = db.create_project("test-project-2", ProjectStatus.PLANNING)

            # ACT
            response = client.get("/api/projects")

            # ASSERT
            assert response.status_code == 200
            data = response.json()
            assert "projects" in data
            assert len(data["projects"]) == 2

            # Verify project data
            projects = {p["name"]: p for p in data["projects"]}
            assert "test-project-1" in projects
            assert projects["test-project-1"]["status"] == "active"
            assert "test-project-2" in projects
            assert projects["test-project-2"]["status"] == "planning"

    def test_list_projects_returns_all_fields(self, temp_db_path):
        """Test that list_projects returns all expected fields."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            db = app.state.db
            db.create_project("full-project", ProjectStatus.ACTIVE)

            # ACT
            response = client.get("/api/projects")

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

    def test_get_project_status_success(self, temp_db_path):
        """Test getting project status for existing project."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            db = app.state.db
            project_id = db.create_project("status-project", ProjectStatus.ACTIVE)

            # ACT
            response = client.get(f"/api/projects/{project_id}/status")

            # ASSERT
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == project_id
            assert data["project_name"] == "status-project"
            assert data["status"] == "active"

    def test_get_project_status_not_found(self, temp_db_path):
        """Test getting status for non-existent project returns 404."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            # ACT
            response = client.get("/api/projects/99999/status")

            # ASSERT
            assert response.status_code == 404
            data = response.json()
            assert "detail" in data
            assert "not found" in data["detail"].lower()

    def test_get_project_status_returns_complete_data(self, temp_db_path):
        """Test that project status returns all expected fields."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            db = app.state.db
            project_id = db.create_project("complete-project", ProjectStatus.ACTIVE)

            # ACT
            response = client.get(f"/api/projects/{project_id}/status")

            # ASSERT
            assert response.status_code == 200
            data = response.json()

            # Verify all expected fields
            assert "project_id" in data
            assert "project_name" in data
            assert "status" in data
            assert isinstance(data["project_id"], int)
            assert isinstance(data["project_name"], str)
            assert isinstance(data["status"], str)


@pytest.mark.unit
class TestAgentsEndpoint:
    """Test GET /api/projects/{id}/agents endpoint with database."""

    def test_get_agents_empty_list(self, temp_db_path):
        """Test getting agents when no agents exist for project."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            db = app.state.db
            project_id = db.create_project("no-agents-project", ProjectStatus.INIT)

            # ACT
            response = client.get(f"/api/projects/{project_id}/agents")

            # ASSERT
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data
            assert data["agents"] == []

    def test_get_agents_with_data(self, temp_db_path):
        """Test getting agents with actual database data."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            db = app.state.db
            project_id = db.create_project("agents-project", ProjectStatus.ACTIVE)

            # Create test agents
            db.create_agent("lead-agent", "lead", "claude", AgentMaturity.D3)
            db.create_agent("backend-agent", "backend", "claude", AgentMaturity.D2)

            # ACT
            response = client.get(f"/api/projects/{project_id}/agents")

            # ASSERT
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data
            assert len(data["agents"]) == 2

            # Verify agent data
            agents = {a["id"]: a for a in data["agents"]}
            assert "lead-agent" in agents
            assert agents["lead-agent"]["type"] == "lead"
            assert agents["lead-agent"]["provider"] == "claude"
            assert agents["lead-agent"]["maturity_level"] == "supporting"

    def test_get_agents_returns_all_fields(self, temp_db_path):
        """Test that agents endpoint returns all expected fields."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            db = app.state.db
            project_id = db.create_project("full-agents-project", ProjectStatus.ACTIVE)
            db.create_agent("test-agent", "test", "claude", AgentMaturity.D4)

            # ACT
            response = client.get(f"/api/projects/{project_id}/agents")

            # ASSERT
            assert response.status_code == 200
            data = response.json()
            agent = data["agents"][0]

            # Verify required fields
            assert "id" in agent
            assert "type" in agent
            assert "provider" in agent
            assert "maturity_level" in agent
            assert "status" in agent


@pytest.mark.integration
class TestEndpointDatabaseIntegration:
    """Integration tests for endpoints with database."""

    def test_complete_project_workflow_via_api(self, temp_db_path):
        """Test complete workflow: create project, get status, verify agents."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            db = app.state.db

            # ACT: Create project and agent
            project_id = db.create_project("workflow-project", ProjectStatus.ACTIVE)
            db.create_agent("workflow-lead", "lead", "claude", AgentMaturity.D3)

            # Test 1: List projects
            response = client.get("/api/projects")
            assert response.status_code == 200
            projects = response.json()["projects"]
            assert len(projects) == 1
            assert projects[0]["name"] == "workflow-project"

            # Test 2: Get project status
            response = client.get(f"/api/projects/{project_id}/status")
            assert response.status_code == 200
            status = response.json()
            assert status["project_name"] == "workflow-project"
            assert status["status"] == "active"

            # Test 3: Get agents
            response = client.get(f"/api/projects/{project_id}/agents")
            assert response.status_code == 200
            agents = response.json()["agents"]
            assert len(agents) == 1
            assert agents[0]["id"] == "workflow-lead"

    def test_endpoints_survive_multiple_requests(self, temp_db_path):
        """Test that endpoints work consistently across multiple requests."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        with TestClient(app) as client:
            db = app.state.db
            project_id = db.create_project("stable-project", ProjectStatus.ACTIVE)

            # ACT & ASSERT: Make multiple requests
            for _ in range(5):
                # List projects
                response = client.get("/api/projects")
                assert response.status_code == 200
                assert len(response.json()["projects"]) == 1

                # Get project status
                response = client.get(f"/api/projects/{project_id}/status")
                assert response.status_code == 200
                assert response.json()["project_name"] == "stable-project"

                # Get agents
                response = client.get(f"/api/projects/{project_id}/agents")
                assert response.status_code == 200
