"""Comprehensive tests for CodeFRAME server.py API endpoints.

This file adds tests for previously untested endpoints to increase coverage from 51.60% to 85%+.
Focuses on missing coverage lines identified in the coverage report.
"""

import pytest
from unittest.mock import patch, AsyncMock

from codeframe.core.models import (
    TaskStatus,
    Task,
    ProjectStatus,
)


def get_app():
    """Get the current app instance after module reload."""
    from codeframe.ui.server import app
    return app


class TestStartProjectAgent:
    """Test POST /api/projects/{id}/start endpoint."""

    def test_start_project_agent_success(self, api_client):
        """Test starting agent for a project successfully."""
        # Arrange: Create project
        project_id = get_app().state.db.create_project(
            name="Test Start Project",
            description="Test starting agent"
        )

        # Mock the start_agent function and running_agents

        with patch('codeframe.ui.server.start_agent', new_callable=AsyncMock) as mock_start:
            # Act
            response = api_client.post(f"/api/projects/{project_id}/start")

            # Assert
            assert response.status_code == 202
            data = response.json()
            assert "Starting Lead Agent for project" in data["message"]
            assert data["status"] == "starting"

    def test_start_project_agent_not_found(self, api_client):
        """Test starting agent for non-existent project returns 404."""
        # Act
        response = api_client.post("/api/projects/99999/start")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_start_project_agent_already_running(self, api_client):
        """Test starting agent when already running returns 200."""
        # Arrange: Create project and set status to RUNNING
        project_id = get_app().state.db.create_project(
            name="Test Already Running",
            description="Test agent already running"
        )

        # Set project status to RUNNING
        get_app().state.db.update_project(project_id, {"status": ProjectStatus.RUNNING})

        # Act
        response = api_client.post(f"/api/projects/{project_id}/start")

        # Assert - Should return 200 (idempotent behavior)
        assert response.status_code == 200
        data = response.json()
        assert "already running" in data["message"].lower()
        assert data["status"] == "running"

    def test_start_project_agent_missing_api_key(self, api_client):
        """Test starting agent without API key returns 500."""
        # Arrange: Create project
        project_id = get_app().state.db.create_project(
            name="Test Missing API Key",
            description="Test missing API key"
        )

        # Remove API key from environment
        import os
        original_key = os.environ.pop("ANTHROPIC_API_KEY", None)

        try:
            # Act
            response = api_client.post(f"/api/projects/{project_id}/start")

            # Assert - Server returns 500 for configuration errors
            assert response.status_code == 500
            assert "anthropic_api_key" in response.json()["detail"].lower()
        finally:
            # Restore API key
            if original_key:
                os.environ["ANTHROPIC_API_KEY"] = original_key
            else:
                os.environ["ANTHROPIC_API_KEY"] = "test-key"


class TestGetTasks:
    """Test GET /api/projects/{id}/tasks endpoint with filters."""

    def test_get_tasks_with_status_filter(self, api_client):
        """Test getting tasks filtered by status."""
        # Arrange: Create project and tasks
        project_id = get_app().state.db.create_project(
            name="Test Tasks Filter",
            description="Test task filtering"
        )

        task1 = Task(
            project_id=project_id,
            title="Task 1",
            description="In progress task",
            status=TaskStatus.IN_PROGRESS,
            priority=1,
            workflow_step=5,
        )
        task1_id = get_app().state.db.create_task(task1)

        task2 = Task(
            project_id=project_id,
            title="Task 2",
            description="Completed task",
            status=TaskStatus.COMPLETED,
            priority=2,
            workflow_step=5,
        )
        task2_id = get_app().state.db.create_task(task2)

        # Act: Get only in-progress tasks
        response = api_client.get(
            f"/api/projects/{project_id}/tasks",
            params={"status": "in_progress"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["status"] == "in_progress"

    def test_get_tasks_with_limit(self, api_client):
        """Test getting tasks with limit parameter."""
        # Arrange: Create project with multiple tasks
        project_id = get_app().state.db.create_project(
            name="Test Tasks Limit",
            description="Test task limit"
        )

        # Create 10 tasks
        for i in range(10):
            task = Task(
                project_id=project_id,
                title=f"Task {i}",
                description=f"Task {i}",
                status=TaskStatus.TODO,
                priority=i,
                workflow_step=5,
            )
            get_app().state.db.create_task(task)

        # Act: Get only 5 tasks
        response = api_client.get(
            f"/api/projects/{project_id}/tasks",
            params={"limit": 5}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 5

    def test_get_tasks_project_not_found(self, api_client):
        """Test getting tasks for non-existent project."""
        # Act
        response = api_client.get("/api/projects/99999/tasks")

        # Assert
        assert response.status_code == 404


class TestGetActivity:
    """Test GET /api/projects/{id}/activity endpoint."""

    def test_get_activity_success(self, api_client):
        """Test getting project activity."""
        # Arrange: Create project
        project_id = get_app().state.db.create_project(
            name="Test Activity",
            description="Test activity feed"
        )

        # Create some activity (memory entries)
        get_app().state.db.create_memory(
            project_id=project_id,
            category="activity",
            key="event",
            value="Project started"
        )

        # Act
        response = api_client.get(f"/api/projects/{project_id}/activity")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "activity" in data
        assert isinstance(data["activity"], list)

    def test_get_activity_with_limit(self, api_client):
        """Test getting activity with limit parameter."""
        # Arrange: Create project with multiple activity entries
        project_id = get_app().state.db.create_project(
            name="Test Activity Limit",
            description="Test activity limit"
        )

        # Create 20 activity entries
        for i in range(20):
            get_app().state.db.create_memory(
                project_id=project_id,
                category="activity",
                key="event",
                value=f"Event {i}"
            )

        # Act: Get only 10 entries
        response = api_client.get(
            f"/api/projects/{project_id}/activity",
            params={"limit": 10}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["activity"]) <= 10

    def test_get_activity_project_not_found(self, api_client):
        """Test getting activity for non-existent project."""
        # Act
        response = api_client.get("/api/projects/99999/activity")

        # Assert
        assert response.status_code == 404


class TestGetBlocker:
    """Test GET /api/blockers/{id} endpoint."""

    def test_get_blocker_success(self, api_client):
        """Test getting a specific blocker."""
        # Arrange: Create project and task with blocker
        project_id = get_app().state.db.create_project(
            name="Test Get Blocker",
            description="Test getting blocker"
        )

        task = Task(
            project_id=project_id,
            title="Blocked Task",
            description="Task with blocker",
            status=TaskStatus.BLOCKED,
            priority=1,
            workflow_step=5,
        )
        task_id = get_app().state.db.create_task(task)

        # Create blocker
        blocker_id = get_app().state.db.create_blocker(
            agent_id="test-agent",
            project_id=project_id,
            task_id=task_id,
            blocker_type="requirement",
            question="How should we implement authentication?",
            priority="high"
        )

        # Act
        response = api_client.get(f"/api/blockers/{blocker_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == blocker_id
        assert data["task_id"] == task_id
        assert data["status"] == "active"

    def test_get_blocker_not_found(self, api_client):
        """Test getting non-existent blocker."""
        # Act
        response = api_client.get("/api/blockers/99999")

        # Assert
        assert response.status_code == 404


class TestBlockerMetrics:
    """Test GET /api/projects/{id}/blockers/metrics endpoint."""

    def test_get_blocker_metrics_success(self, api_client):
        """Test getting blocker metrics for a project."""
        # Arrange: Create project with blockers
        project_id = get_app().state.db.create_project(
            name="Test Blocker Metrics",
            description="Test blocker metrics"
        )

        task = Task(
            project_id=project_id,
            title="Blocked Task",
            description="Task with blocker",
            status=TaskStatus.BLOCKED,
            priority=1,
            workflow_step=5,
        )
        task_id = get_app().state.db.create_task(task)

        # Create active blocker
        get_app().state.db.create_blocker(
            agent_id="test-agent",
            project_id=project_id,
            task_id=task_id,
            blocker_type="requirement",
            question="Blocker 1",
            priority="high"
        )

        # Act
        response = api_client.get(f"/api/projects/{project_id}/blockers/metrics")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "total_count" in data
        assert "active_count" in data
        assert "resolved_count" in data
        assert data["total_count"] >= 1

    def test_get_blocker_metrics_project_not_found(self, api_client):
        """Test getting metrics for non-existent project."""
        # Act
        response = api_client.get("/api/projects/99999/blockers/metrics")

        # Assert
        assert response.status_code == 404


class TestPauseResumeProject:
    """Test POST /api/projects/{id}/pause and /resume endpoints."""

    def test_pause_project_success(self, api_client):
        """Test pausing a running project."""
        # Arrange: Create project
        project_id = get_app().state.db.create_project(
            name="Test Pause",
            description="Test pausing project"
        )

        # Set project to running
        get_app().state.db.update_project(project_id, {"status": ProjectStatus.RUNNING})

        # Act
        response = api_client.post(f"/api/projects/{project_id}/pause")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"

    def test_pause_project_not_found(self, api_client):
        """Test pausing non-existent project."""
        # Act
        response = api_client.post("/api/projects/99999/pause")

        # Assert
        assert response.status_code == 404

    def test_resume_project_success(self, api_client):
        """Test resuming a paused project."""
        # Arrange: Create paused project
        project_id = get_app().state.db.create_project(
            name="Test Resume",
            description="Test resuming project"
        )

        # Set project to paused
        get_app().state.db.update_project(project_id, {"status": ProjectStatus.PAUSED})

        # Act
        response = api_client.post(f"/api/projects/{project_id}/resume")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"

    def test_resume_project_not_found(self, api_client):
        """Test resuming non-existent project."""
        # Act
        response = api_client.post("/api/projects/99999/resume")

        # Assert
        assert response.status_code == 404


class TestDeploymentMode:
    """Test deployment mode functions."""

    def test_get_deployment_mode_default(self):
        """Test default deployment mode is self-hosted."""
        from codeframe.ui.server import get_deployment_mode, DeploymentMode
        import os

        # Remove env var if set
        original = os.environ.pop("CODEFRAME_DEPLOYMENT_MODE", None)

        try:
            mode = get_deployment_mode()
            assert mode == DeploymentMode.SELF_HOSTED
        finally:
            if original:
                os.environ["CODEFRAME_DEPLOYMENT_MODE"] = original

    def test_get_deployment_mode_hosted(self):
        """Test hosted deployment mode."""
        from codeframe.ui.server import get_deployment_mode, DeploymentMode
        import os

        original = os.environ.get("CODEFRAME_DEPLOYMENT_MODE")
        os.environ["CODEFRAME_DEPLOYMENT_MODE"] = "hosted"

        try:
            mode = get_deployment_mode()
            assert mode == DeploymentMode.HOSTED
        finally:
            if original:
                os.environ["CODEFRAME_DEPLOYMENT_MODE"] = original
            else:
                os.environ.pop("CODEFRAME_DEPLOYMENT_MODE", None)

    def test_is_hosted_mode(self):
        """Test is_hosted_mode function."""
        from codeframe.ui.server import is_hosted_mode
        import os

        # Test self-hosted
        original = os.environ.get("CODEFRAME_DEPLOYMENT_MODE")
        os.environ["CODEFRAME_DEPLOYMENT_MODE"] = "self_hosted"

        try:
            assert not is_hosted_mode()

            # Test hosted
            os.environ["CODEFRAME_DEPLOYMENT_MODE"] = "hosted"
            assert is_hosted_mode()
        finally:
            if original:
                os.environ["CODEFRAME_DEPLOYMENT_MODE"] = original
            else:
                os.environ.pop("CODEFRAME_DEPLOYMENT_MODE", None)


class TestConnectionManager:
    """Test WebSocket ConnectionManager class."""

    @pytest.mark.asyncio
    async def test_connection_manager_connect(self):
        """Test connecting a WebSocket."""
        from codeframe.ui.server import ConnectionManager

        manager = ConnectionManager()
        mock_websocket = AsyncMock()

        await manager.connect(mock_websocket)

        assert mock_websocket in manager.active_connections
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_manager_disconnect(self):
        """Test disconnecting a WebSocket."""
        from codeframe.ui.server import ConnectionManager

        manager = ConnectionManager()
        mock_websocket = AsyncMock()

        await manager.connect(mock_websocket)
        manager.disconnect(mock_websocket)

        assert mock_websocket not in manager.active_connections

    @pytest.mark.asyncio
    async def test_connection_manager_broadcast(self):
        """Test broadcasting to all connections."""
        from codeframe.ui.server import ConnectionManager

        manager = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect(mock_ws1)
        await manager.connect(mock_ws2)

        message = {"type": "test", "data": "hello"}
        await manager.broadcast(message)

        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_connection_manager_broadcast_handles_exception(self):
        """Test broadcast continues when a connection fails."""
        from codeframe.ui.server import ConnectionManager

        manager = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        # Make first websocket fail
        mock_ws1.send_json.side_effect = Exception("Connection lost")

        await manager.connect(mock_ws1)
        await manager.connect(mock_ws2)

        message = {"type": "test", "data": "hello"}
        await manager.broadcast(message)

        # Both should be called, but ws1 fails silently
        mock_ws1.send_json.assert_called_once()
        mock_ws2.send_json.assert_called_once_with(message)
