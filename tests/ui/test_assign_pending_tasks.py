"""
Tests for assign pending tasks endpoint (Issue #248 fix).

This module tests the POST /api/projects/{project_id}/tasks/assign endpoint
that allows users to manually trigger task assignment for stuck pending tasks.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import BackgroundTasks, HTTPException, Request

from codeframe.core.models import Task, TaskStatus


@pytest.fixture
def mock_request():
    """Create mock starlette Request for rate limiter."""
    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    request.state = MagicMock()
    request.state.user = None
    return request


@pytest.fixture
def mock_background_tasks(monkeypatch):
    """Create mock BackgroundTasks.

    Also clears ANTHROPIC_API_KEY to make tests deterministic.
    Tests that need API key behavior should explicitly set it.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    bg = MagicMock(spec=BackgroundTasks)
    bg.add_task = MagicMock()
    return bg


@pytest.fixture
def mock_db():
    """Create mock Database with project in active phase."""
    db = MagicMock()
    db.get_project.return_value = {
        "id": 1,
        "name": "Test Project",
        "phase": "active"  # Must be in active phase to assign tasks
    }
    db.user_has_project_access.return_value = True
    return db


@pytest.fixture
def mock_user():
    """Create mock authenticated user."""
    user = MagicMock()
    user.id = 1
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_manager():
    """Create mock ConnectionManager."""
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    return manager


class TestAssignPendingTasksEndpoint:
    """Tests for POST /api/projects/{project_id}/tasks/assign."""

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_with_pending_tasks(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request
    ):
        """Test that endpoint triggers execution when pending tasks exist."""
        from codeframe.ui.routers.tasks import assign_pending_tasks

        # Setup: 2 pending unassigned tasks
        mock_db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING, assigned_to=None),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING, assigned_to=None),
            Task(id=3, project_id=1, title="Task 3", status=TaskStatus.COMPLETED, assigned_to="agent-1"),
        ]

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            response = await assign_pending_tasks(
                request=mock_request,
                project_id=1,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert response.success is True
        assert response.pending_count == 2
        assert "2" in response.message
        mock_background_tasks.add_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_no_pending_tasks(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request
    ):
        """Test that endpoint returns success but doesn't trigger execution when no pending tasks."""
        from codeframe.ui.routers.tasks import assign_pending_tasks

        # Setup: No pending tasks
        mock_db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.COMPLETED, assigned_to="agent-1"),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.IN_PROGRESS, assigned_to="agent-2"),
        ]

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            response = await assign_pending_tasks(
                request=mock_request,
                project_id=1,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert response.success is True
        assert response.pending_count == 0
        assert "no pending" in response.message.lower()
        mock_background_tasks.add_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_wrong_phase(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request
    ):
        """Test that endpoint returns 400 when project is not in active phase."""
        from codeframe.ui.routers.tasks import assign_pending_tasks

        # Setup: Project in planning phase
        mock_db.get_project.return_value = {
            "id": 1,
            "name": "Test Project",
            "phase": "planning"
        }

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             pytest.raises(HTTPException) as exc_info:
            await assign_pending_tasks(
                request=mock_request,
                project_id=1,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 400
        assert "active" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_project_not_found(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request
    ):
        """Test that endpoint returns 404 when project doesn't exist."""
        from codeframe.ui.routers.tasks import assign_pending_tasks

        mock_db.get_project.return_value = None

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             pytest.raises(HTTPException) as exc_info:
            await assign_pending_tasks(
                request=mock_request,
                project_id=999,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_access_denied(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request
    ):
        """Test that endpoint returns 403 when user doesn't have access."""
        from codeframe.ui.routers.tasks import assign_pending_tasks

        mock_db.user_has_project_access.return_value = False

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             pytest.raises(HTTPException) as exc_info:
            await assign_pending_tasks(
                request=mock_request,
                project_id=1,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_without_api_key(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request, caplog
    ):
        """Test that endpoint warns when API key is missing."""
        from codeframe.ui.routers.tasks import assign_pending_tasks
        import logging

        mock_db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING, assigned_to=None),
        ]

        # Ensure no API key
        env_without_key = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

        with caplog.at_level(logging.WARNING):
            with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
                 patch.dict(os.environ, env_without_key, clear=True):
                response = await assign_pending_tasks(
                    request=mock_request,
                    project_id=1,
                    background_tasks=mock_background_tasks,
                    db=mock_db,
                    current_user=mock_user
                )

        # Should return failure when API key missing
        assert response.success is False
        assert response.pending_count == 1
        assert "api key" in response.message.lower() or "not configured" in response.message.lower()

        # Background task should NOT be scheduled
        mock_background_tasks.add_task.assert_not_called()

        # Should log warning
        assert any("ANTHROPIC_API_KEY" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_only_counts_unassigned(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request
    ):
        """Test that only pending AND unassigned tasks are counted."""
        from codeframe.ui.routers.tasks import assign_pending_tasks

        # Setup: Mix of tasks - only 1 is pending AND unassigned
        mock_db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING, assigned_to=None),      # Count this
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING, assigned_to="agent-1"), # Already assigned
            Task(id=3, project_id=1, title="Task 3", status=TaskStatus.IN_PROGRESS, assigned_to=None),  # Not pending
        ]

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            response = await assign_pending_tasks(
                request=mock_request,
                project_id=1,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        # Should not trigger because there's an in_progress task
        assert response.pending_count == 1
        assert "in progress" in response.message.lower()
        mock_background_tasks.add_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_blocked_when_execution_in_progress(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request
    ):
        """Test that assignment is blocked when tasks are already in progress."""
        from codeframe.ui.routers.tasks import assign_pending_tasks

        # Setup: 2 pending tasks + 1 in progress
        mock_db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING, assigned_to=None),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING, assigned_to=None),
            Task(id=3, project_id=1, title="Task 3", status=TaskStatus.IN_PROGRESS, assigned_to="agent-1"),
        ]

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            response = await assign_pending_tasks(
                request=mock_request,
                project_id=1,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        # Should return success but NOT schedule execution
        assert response.success is True
        assert response.pending_count == 2
        assert "in progress" in response.message.lower()
        assert "1 task" in response.message.lower()  # Reports 1 task running
        mock_background_tasks.add_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_allowed_when_no_execution_in_progress(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request
    ):
        """Test that assignment proceeds when no tasks are in progress."""
        from codeframe.ui.routers.tasks import assign_pending_tasks

        # Setup: Only pending and completed tasks, no in_progress or assigned
        mock_db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING, assigned_to=None),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING, assigned_to=None),
            Task(id=3, project_id=1, title="Task 3", status=TaskStatus.COMPLETED, assigned_to="agent-1"),
        ]

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            response = await assign_pending_tasks(
                request=mock_request,
                project_id=1,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        # Should schedule execution
        assert response.success is True
        assert response.pending_count == 2
        assert "started" in response.message.lower()
        mock_background_tasks.add_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_assign_pending_tasks_blocked_when_tasks_assigned(
        self, mock_db, mock_user, mock_manager, mock_background_tasks, mock_request
    ):
        """Test that assignment is blocked when tasks are in ASSIGNED status."""
        from codeframe.ui.routers.tasks import assign_pending_tasks

        # Setup: 2 pending tasks + 1 assigned (not yet in_progress)
        mock_db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING, assigned_to=None),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING, assigned_to=None),
            Task(id=3, project_id=1, title="Task 3", status=TaskStatus.ASSIGNED, assigned_to="agent-1"),
        ]

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            response = await assign_pending_tasks(
                request=mock_request,
                project_id=1,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        # Should return success but NOT schedule execution
        assert response.success is True
        assert response.pending_count == 2
        assert "in progress" in response.message.lower() or "assigned" in response.message.lower()
        mock_background_tasks.add_task.assert_not_called()


class TestAssignPendingTasksResponseModel:
    """Tests for TaskAssignmentResponse model."""

    def test_response_model_structure(self):
        """Test that response model has correct fields."""
        from codeframe.ui.routers.tasks import TaskAssignmentResponse

        response = TaskAssignmentResponse(
            success=True,
            pending_count=5,
            message="Test message"
        )

        assert response.success is True
        assert response.pending_count == 5
        assert response.message == "Test message"


class TestAssignPendingTasksFunctionSignature:
    """Tests to ensure endpoint signature is correct."""

    def test_endpoint_accepts_required_parameters(self):
        """Test that endpoint function accepts required parameters."""
        from codeframe.ui.routers.tasks import assign_pending_tasks
        import inspect

        sig = inspect.signature(assign_pending_tasks)
        params = list(sig.parameters.keys())

        assert "request" in params  # Required for rate limiting
        assert "project_id" in params
        assert "background_tasks" in params
        assert "db" in params
        assert "current_user" in params
