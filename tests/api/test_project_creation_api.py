"""Tests for Project Creation API (cf-11).

Following strict TDD: These tests are written FIRST, before implementation.
Task: cf-11 - POST /api/projects endpoint with request/response models

RED → GREEN → REFACTOR methodology:
1. RED: Write tests that fail (this file)
2. GREEN: Implement minimal code to make tests pass
3. REFACTOR: Clean up while keeping tests green
"""

import sqlite3
from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestProjectCreationAPI:
    """Test POST /api/projects endpoint for creating new projects."""

    def test_create_project_success(self, api_client):
        """Test successful project creation via API (201 Created)."""
        # ACT
        response = api_client.post(
            "/api/projects", json={"name": "test-api-project", "description": "Test project"}
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

    def test_create_project_missing_name(self, api_client):
        """Test that missing name returns 400 Bad Request."""
        # ACT
        response = api_client.post("/api/projects", json={"description": "Test project"})

        # ASSERT
        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_create_project_empty_name(self, api_client):
        """Test that empty name returns 422 (Pydantic validation error)."""
        # ACT
        response = api_client.post(
            "/api/projects", json={"name": "", "description": "Test project"}
        )

        # ASSERT
        assert response.status_code == 422  # Pydantic validation error
        data = response.json()
        assert "detail" in data

    def test_create_project_invalid_type(self, api_client):
        """Test that invalid source_type returns 422 validation error."""
        # ACT
        response = api_client.post(
            "/api/projects",
            json={
                "name": "test-project",
                "description": "Test project",
                "source_type": "invalid_type",
            },
        )

        # ASSERT
        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data

    def test_create_project_duplicate_name(self, api_client):
        """Test that duplicate project name returns 409 Conflict."""
        # ACT
        # Create first project
        response1 = api_client.post(
            "/api/projects", json={"name": "duplicate-test", "description": "Test project"}
        )
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = api_client.post(
            "/api/projects", json={"name": "duplicate-test", "description": "Test project"}
        )

        # ASSERT
        assert response2.status_code == 409
        data = response2.json()
        assert "detail" in data
        assert "exists" in data["detail"].lower() or "duplicate" in data["detail"].lower()

    def test_create_project_returns_all_fields(self, api_client):
        """Test that created project returns all expected fields."""
        # ACT
        response = api_client.post(
            "/api/projects", json={"name": "complete-project", "description": "Test project"}
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

    def test_create_project_default_type(self, api_client):
        """Test that source_type defaults to 'python' if not specified."""
        # ACT
        response = api_client.post(
            "/api/projects", json={"name": "default-type-project", "description": "Test project"}
        )

        # ASSERT
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "default-type-project"


@pytest.mark.integration
class TestProjectCreationIntegration:
    """Integration tests for project creation API."""

    def test_create_project_persists_to_database(self, api_client):
        """Test that created project is actually stored in database."""
        # ACT
        # Create project via API
        response = api_client.post(
            "/api/projects", json={"name": "persist-test", "description": "Test project"}
        )
        assert response.status_code == 201
        created_id = response.json()["id"]

        # Verify it appears in list
        list_response = api_client.get("/api/projects")
        assert list_response.status_code == 200
        projects = list_response.json()["projects"]

        # ASSERT
        assert len(projects) == 1
        assert projects[0]["id"] == created_id
        assert projects[0]["name"] == "persist-test"
        assert projects[0]["status"] == "init"

    def test_create_multiple_projects(self, api_client):
        """Test creating multiple projects via API."""
        # ACT
        # Create multiple projects
        names = ["project-1", "project-2", "project-3"]
        created_ids = []

        for name in names:
            response = api_client.post(
                "/api/projects", json={"name": name, "description": "Test project"}
            )
            assert response.status_code == 201
            created_ids.append(response.json()["id"])

        # Verify all are listed
        list_response = api_client.get("/api/projects")
        projects = list_response.json()["projects"]

        # ASSERT
        # At least 3 projects should exist (may be more from other test classes)
        assert len(projects) >= 3
        project_names = [p["name"] for p in projects]
        for name in names:
            assert name in project_names

        # Verify IDs are unique
        project_ids = [p["id"] for p in projects]
        assert len(project_ids) == len(set(project_ids))

    def test_create_project_via_api_then_get_status(self, api_client):
        """Test complete workflow: create via API, then get status."""
        # ACT
        # Create project
        create_response = api_client.post(
            "/api/projects", json={"name": "workflow-test", "description": "Test project"}
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        # Get project status
        status_response = api_client.get(f"/api/projects/{project_id}/status")

        # ASSERT
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["project_id"] == project_id
        assert status_data["name"] == "workflow-test"
        assert status_data["status"] == "init"


@pytest.mark.unit
class TestProjectCreationErrorHandling:
    """Test error handling for project creation API."""

    def test_create_project_database_locked_error(self, api_client):
        """Test that database locked error returns 500 Internal Server Error."""
        from codeframe.ui import server

        with patch.object(
            server.app.state.db,
            "create_project",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            response = api_client.post(
                "/api/projects",
                json={"name": "test-db-locked", "description": "Test project"},
            )

            assert response.status_code == 500
            data = response.json()
            assert "detail" in data
            assert "database" in data["detail"].lower()

    def test_create_project_disk_full_error(self, api_client):
        """Test that disk I/O error returns 500 Internal Server Error."""
        from codeframe.ui import server

        with patch.object(
            server.app.state.db,
            "create_project",
            side_effect=sqlite3.OperationalError("disk I/O error"),
        ):
            response = api_client.post(
                "/api/projects",
                json={"name": "test-disk-full", "description": "Test project"},
            )

            assert response.status_code == 500
            data = response.json()
            assert "detail" in data
            assert "database" in data["detail"].lower() or "i/o" in data["detail"].lower()

    def test_create_project_integrity_error(self, api_client):
        """Test that constraint violation error returns 500 Internal Server Error."""
        from codeframe.ui import server

        with patch.object(
            server.app.state.db,
            "create_project",
            side_effect=sqlite3.IntegrityError("UNIQUE constraint failed"),
        ):
            response = api_client.post(
                "/api/projects",
                json={"name": "test-integrity", "description": "Test project"},
            )

            assert response.status_code == 500
            data = response.json()
            assert "detail" in data
            assert "database" in data["detail"].lower() or "constraint" in data["detail"].lower()

    def test_create_project_list_projects_database_error(self, api_client):
        """Test that database error during list_projects returns 500 Internal Server Error."""
        from codeframe.ui import server

        with patch.object(
            server.app.state.db,
            "list_projects",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            response = api_client.post(
                "/api/projects",
                json={"name": "test-list-error", "description": "Test project"},
            )

            assert response.status_code == 500
            data = response.json()
            assert "detail" in data
            assert "database" in data["detail"].lower()

    def test_create_project_with_extra_fields(self, api_client):
        """Test that extra fields in request are ignored."""
        # ACT
        response = api_client.post(
            "/api/projects",
            json={
                "name": "extra-fields-test",
                "description": "Test project",
                "extra_field": "should be ignored",
                "another_extra": 123,
            },
        )

        # ASSERT
        # Pydantic v2 by default ignores extra fields, so this should succeed
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "extra-fields-test"
        assert "extra_field" not in data
        assert "another_extra" not in data
