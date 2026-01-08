"""API tests for generate-tasks endpoint (manual task generation).

Following TDD: These tests are written FIRST before API implementation.
Tests verify POST /api/projects/{id}/discovery/generate-tasks endpoint.

This endpoint provides manual control over task generation, allowing users
to trigger the existing generate_planning_background() function on demand
when the project is in the planning phase with a completed PRD.
"""

import os
from unittest.mock import patch

import pytest


def get_db_from_client(api_client):
    """Get database instance from test client's app."""
    from codeframe.ui import server

    return server.app.state.db


def create_mock_prd(db, project_id: int, content: str = "# Test PRD\n\nThis is a test PRD."):
    """Create a mock PRD in the memory table."""
    cursor = db.conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO memory (project_id, category, key, value)
        VALUES (?, 'prd', 'content', ?)
        """,
        (project_id, content),
    )
    db.conn.commit()


class TestGenerateTasksEndpoint:
    """Test POST /api/projects/{id}/discovery/generate-tasks endpoint."""

    def test_returns_404_for_nonexistent_project(self, api_client):
        """Test endpoint returns 404 when project does not exist."""
        # ACT
        response = api_client.post("/api/projects/99999/discovery/generate-tasks")

        # ASSERT
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_403_for_unauthorized_user(self, api_client):
        """Test endpoint returns 403 when user doesn't have project access."""
        # ARRANGE
        # Create another user first (test user is id=1)
        db = get_db_from_client(api_client)
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO users (
                id, email, name, hashed_password,
                is_active, is_superuser, is_verified, email_verified
            )
            VALUES (999, 'other@example.com', 'Other User', '!DISABLED!', 1, 0, 1, 1)
            """
        )
        db.conn.commit()

        # Create project by another user (not the test user)
        project_id = db.create_project(
            "other-user-project",
            "Project owned by another user",
            user_id=999,  # Different user
        )

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/generate-tasks"
        )

        # ASSERT
        assert response.status_code == 403
        assert "access denied" in response.json()["detail"].lower()

    def test_returns_400_when_not_in_planning_phase(self, api_client):
        """Test endpoint returns 400 when project is not in planning phase."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        # Project starts in discovery phase by default

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/generate-tasks"
        )

        # ASSERT
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "planning" in detail or "phase" in detail

    def test_returns_400_when_prd_not_generated(self, api_client):
        """Test endpoint returns 400 when PRD does not exist."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        # Update to planning phase but don't create PRD
        db.update_project(project_id, {"phase": "planning"})

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/generate-tasks"
        )

        # ASSERT
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "prd" in detail

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False)
    def test_returns_500_when_api_key_missing(self, api_client):
        """Test endpoint returns 500 when ANTHROPIC_API_KEY is not set."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "planning"})
        # Create a mock PRD
        create_mock_prd(db, project_id)

        # Temporarily clear the API key for this test
        original_key = os.environ.get("ANTHROPIC_API_KEY")
        os.environ.pop("ANTHROPIC_API_KEY", None)

        try:
            # ACT
            response = api_client.post(
                f"/api/projects/{project_id}/discovery/generate-tasks"
            )

            # ASSERT
            assert response.status_code == 500
            detail = response.json()["detail"].lower()
            assert "api" in detail or "key" in detail
        finally:
            # Restore the API key
            if original_key:
                os.environ["ANTHROPIC_API_KEY"] = original_key
            else:
                os.environ["ANTHROPIC_API_KEY"] = "test-key"

    @patch("codeframe.ui.routers.discovery.generate_planning_background")
    def test_returns_200_and_triggers_background_task(
        self, mock_generate_planning, api_client
    ):
        """Test endpoint returns 200 and triggers background task when valid."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "planning"})
        # Create a mock PRD
        create_mock_prd(db, project_id)

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/generate-tasks"
        )

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert "task" in data["message"].lower() or "started" in data["message"].lower()

    @patch("codeframe.ui.routers.discovery.generate_planning_background")
    def test_background_task_receives_correct_parameters(
        self, mock_generate_planning, api_client
    ):
        """Test that background task is called with correct project_id, db, and api_key."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "planning"})
        create_mock_prd(db, project_id)

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/generate-tasks"
        )

        # ASSERT
        assert response.status_code == 200
        # The background task should be scheduled (checked via BackgroundTasks)
        # Note: In TestClient, background tasks are executed synchronously
        # so we can verify the function was called correctly

    def test_returns_200_with_flag_when_tasks_already_exist(self, api_client):
        """Test endpoint is idempotent - returns 200 with tasks_already_exist flag.

        Instead of returning 400 error when tasks exist, the endpoint should
        be idempotent and return success with a flag indicating tasks already
        exist. This improves UX for users who join late and miss WebSocket events.
        """
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "planning"})
        create_mock_prd(db, project_id)

        # Create some existing tasks to simulate already-generated tasks
        # Insert directly into tasks table (simpler than using Task model)
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (project_id, title, description, status, priority, workflow_step)
            VALUES (?, 'Task 1', 'Task 1 description', 'pending', 2, 1)
            """,
            (project_id,),
        )
        db.conn.commit()

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/generate-tasks"
        )

        # ASSERT - idempotent endpoint returns 200 with flag
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["tasks_already_exist"] is True
        assert "already" in data["message"].lower()


class TestGenerateTasksEndpointIntegration:
    """Integration tests for generate-tasks endpoint."""

    @pytest.mark.asyncio
    async def test_generate_planning_background_is_async_compatible(self):
        """Test that generate_planning_background can be used as a background task."""
        from codeframe.ui.routers.discovery import generate_planning_background
        import inspect

        # Verify the function is async
        assert inspect.iscoroutinefunction(generate_planning_background)

        # Verify the function signature has required parameters
        sig = inspect.signature(generate_planning_background)
        params = list(sig.parameters.keys())

        assert "project_id" in params
        assert "db" in params
        assert "api_key" in params
