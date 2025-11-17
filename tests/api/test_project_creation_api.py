"""Tests for Project Creation API (cf-11).

Following strict TDD: These tests are written FIRST, before implementation.
Task: cf-11 - POST /api/projects endpoint with request/response models

RED → GREEN → REFACTOR methodology:
1. RED: Write tests that fail (this file)
2. GREEN: Implement minimal code to make tests pass
3. REFACTOR: Clean up while keeping tests green
"""

import pytest
from fastapi.testclient import TestClient
from codeframe.core.models import ProjectStatus


@pytest.mark.unit
class TestProjectCreationAPI:
    """Test POST /api/projects endpoint for creating new projects."""

    def test_create_project_success(self, temp_db_path):
        """Test successful project creation via API (201 Created)."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            response = client.post(
                "/api/projects", json={"project_name": "test-api-project", "project_type": "python"}
            )

        # ASSERT
        assert response.status_code == 201
        data = response.json()

        # Verify response structure
        assert "id" in data
        assert "name" in data
        assert "status" in data
        assert "created_at" in data

        # Verify values
        assert data["name"] == "test-api-project"
        assert data["status"] == "init"
        assert isinstance(data["id"], int)
        assert data["id"] > 0

    def test_create_project_missing_name(self, temp_db_path):
        """Test that missing project_name returns 400 Bad Request."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            response = client.post("/api/projects", json={"project_type": "python"})

        # ASSERT
        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_create_project_empty_name(self, temp_db_path):
        """Test that empty project_name returns 422 (Pydantic validation error)."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            response = client.post(
                "/api/projects", json={"project_name": "", "project_type": "python"}
            )

        # ASSERT
        assert response.status_code == 422  # Pydantic validation error
        data = response.json()
        assert "detail" in data

    def test_create_project_invalid_type(self, temp_db_path):
        """Test that invalid project_type returns 400 Bad Request."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            response = client.post(
                "/api/projects",
                json={"project_name": "test-project", "project_type": "invalid_type"},
            )

        # ASSERT
        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_create_project_duplicate_name(self, temp_db_path):
        """Test that duplicate project name returns 409 Conflict."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            # Create first project
            response1 = client.post(
                "/api/projects", json={"project_name": "duplicate-test", "project_type": "python"}
            )
            assert response1.status_code == 201

            # Try to create duplicate
            response2 = client.post(
                "/api/projects", json={"project_name": "duplicate-test", "project_type": "python"}
            )

        # ASSERT
        assert response2.status_code == 409
        data = response2.json()
        assert "detail" in data
        assert "exists" in data["detail"].lower() or "duplicate" in data["detail"].lower()

    def test_create_project_returns_all_fields(self, temp_db_path):
        """Test that created project returns all expected fields."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            response = client.post(
                "/api/projects", json={"project_name": "complete-project", "project_type": "python"}
            )

        # ASSERT
        assert response.status_code == 201
        data = response.json()

        # Verify all required fields
        required_fields = ["id", "name", "status", "created_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify field types
        assert isinstance(data["id"], int)
        assert isinstance(data["name"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["created_at"], str)

    def test_create_project_default_type(self, temp_db_path):
        """Test that project_type defaults to 'python' if not specified."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            response = client.post("/api/projects", json={"project_name": "default-type-project"})

        # ASSERT
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "default-type-project"


@pytest.mark.integration
class TestProjectCreationIntegration:
    """Integration tests for project creation API."""

    def test_create_project_persists_to_database(self, temp_db_path):
        """Test that created project is actually stored in database."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            # Create project via API
            response = client.post(
                "/api/projects", json={"project_name": "persist-test", "project_type": "python"}
            )
            assert response.status_code == 201
            created_id = response.json()["id"]

            # Verify it appears in list
            list_response = client.get("/api/projects")
            assert list_response.status_code == 200
            projects = list_response.json()["projects"]

        # ASSERT
        assert len(projects) == 1
        assert projects[0]["id"] == created_id
        assert projects[0]["name"] == "persist-test"
        assert projects[0]["status"] == "init"

    def test_create_multiple_projects(self, temp_db_path):
        """Test creating multiple projects via API."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            # Create multiple projects
            names = ["project-1", "project-2", "project-3"]
            created_ids = []

            for name in names:
                response = client.post(
                    "/api/projects", json={"project_name": name, "project_type": "python"}
                )
                assert response.status_code == 201
                created_ids.append(response.json()["id"])

            # Verify all are listed
            list_response = client.get("/api/projects")
            projects = list_response.json()["projects"]

        # ASSERT
        assert len(projects) == 3
        project_names = [p["name"] for p in projects]
        for name in names:
            assert name in project_names

        # Verify IDs are unique
        project_ids = [p["id"] for p in projects]
        assert len(project_ids) == len(set(project_ids))

    def test_create_project_via_api_then_get_status(self, temp_db_path):
        """Test complete workflow: create via API, then get status."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            # Create project
            create_response = client.post(
                "/api/projects", json={"project_name": "workflow-test", "project_type": "python"}
            )
            assert create_response.status_code == 201
            project_id = create_response.json()["id"]

            # Get project status
            status_response = client.get(f"/api/projects/{project_id}/status")

        # ASSERT
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["project_id"] == project_id
        assert status_data["project_name"] == "workflow-test"
        assert status_data["status"] == "init"


@pytest.mark.unit
class TestProjectCreationErrorHandling:
    """Test error handling for project creation API."""

    def test_create_project_handles_database_errors(self, temp_db_path):
        """Test that database errors are handled gracefully (500 Internal Server Error)."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT & ASSERT
        with TestClient(app) as client:
            # Close the database connection to simulate error
            app.state.db.close()

            response = client.post(
                "/api/projects", json={"project_name": "error-test", "project_type": "python"}
            )

            # Should return 500 Internal Server Error
            assert response.status_code == 500
            data = response.json()
            assert "detail" in data

    def test_create_project_with_extra_fields(self, temp_db_path):
        """Test that extra fields in request are ignored."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT
        with TestClient(app) as client:
            response = client.post(
                "/api/projects",
                json={
                    "project_name": "extra-fields-test",
                    "project_type": "python",
                    "extra_field": "should be ignored",
                    "another_extra": 123,
                },
            )

        # ASSERT
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "extra-fields-test"
        assert "extra_field" not in data
        assert "another_extra" not in data
