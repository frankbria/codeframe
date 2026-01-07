"""
Tests for task approval endpoint (Feature: 016-planning-phase-automation).

These tests verify:
- Task approval transitions project to development phase
- Approved tasks are updated to pending status
- Excluded tasks remain unchanged
- Validation errors for wrong phase
- WebSocket events are broadcast
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from codeframe.core.models import Task, TaskStatus
from codeframe.ui.routers.tasks import approve_tasks, TaskApprovalRequest


@pytest.fixture
def mock_db():
    """Create mock Database with project and tasks."""
    db = MagicMock()
    db.get_project.return_value = {
        "id": 1,
        "name": "Test Project",
        "phase": "planning"
    }
    db.user_has_project_access.return_value = True

    # Mock tasks (using PENDING status which is valid for planning phase)
    mock_tasks = [
        Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING),
        Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING),
        Task(id=3, project_id=1, title="Task 3", status=TaskStatus.PENDING),
    ]
    db.get_project_tasks.return_value = mock_tasks
    db.update_task.return_value = None
    db.update_project.return_value = None

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


class TestTaskApprovalEndpoint:
    """Tests for POST /api/projects/{project_id}/tasks/approve."""

    @pytest.mark.asyncio
    async def test_approve_tasks_returns_success_response(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that approving tasks returns success response with summary."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            response = await approve_tasks(
                project_id=1,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        assert response.success is True
        assert response.phase == "active"
        assert response.approved_count == 3
        assert response.excluded_count == 0

    @pytest.mark.asyncio
    async def test_approve_tasks_with_exclusions(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that excluded tasks are not approved."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[2, 3])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            response = await approve_tasks(
                project_id=1,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        assert response.approved_count == 1
        assert response.excluded_count == 2

    @pytest.mark.asyncio
    async def test_approve_tasks_updates_task_status_to_pending(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that approved tasks are updated to pending status."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            await approve_tasks(
                project_id=1,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        # Verify update_task was called for each task
        assert mock_db.update_task.call_count == 3
        # Verify each call updates status to pending
        for call in mock_db.update_task.call_args_list:
            task_id, updates = call[0]
            assert updates.get("status") == "pending"

    @pytest.mark.asyncio
    async def test_approve_tasks_transitions_phase_to_active(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that project phase is transitioned to active."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager") as mock_phase_manager:
            await approve_tasks(
                project_id=1,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        # Verify PhaseManager.transition was called
        mock_phase_manager.transition.assert_called_once_with(1, "active", mock_db)

    @pytest.mark.asyncio
    async def test_approve_tasks_broadcasts_development_started(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that development_started event is broadcast."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            await approve_tasks(
                project_id=1,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        # Find the development_started broadcast
        calls = mock_manager.broadcast.call_args_list
        development_started_calls = [
            call for call in calls
            if call[0][0].get("type") == "development_started"
        ]

        assert len(development_started_calls) == 1
        message = development_started_calls[0][0][0]
        assert message["type"] == "development_started"
        assert message["project_id"] == 1
        assert message["approved_count"] == 3
        assert message["excluded_count"] == 0

    @pytest.mark.asyncio
    async def test_reject_tasks_returns_rejection_message(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that rejecting tasks returns rejection response."""
        request = TaskApprovalRequest(approved=False, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager):
            response = await approve_tasks(
                project_id=1,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        assert response.success is False
        assert "not approved" in response.message.lower()


class TestTaskApprovalValidation:
    """Tests for task approval validation."""

    @pytest.mark.asyncio
    async def test_approve_tasks_wrong_phase_returns_400(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that approving tasks in wrong phase returns 400."""
        from fastapi import HTTPException

        mock_db.get_project.return_value = {
            "id": 1,
            "name": "Test Project",
            "phase": "discovery"  # Wrong phase
        }

        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             pytest.raises(HTTPException) as exc_info:
            await approve_tasks(
                project_id=1,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 400
        assert "planning" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_approve_tasks_no_tasks_returns_404(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that approving with no tasks returns 404."""
        from fastapi import HTTPException

        mock_db.get_project_tasks.return_value = []  # No tasks

        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             pytest.raises(HTTPException) as exc_info:
            await approve_tasks(
                project_id=1,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 404
        assert "no tasks" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_approve_tasks_project_not_found_returns_404(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that approving for non-existent project returns 404."""
        from fastapi import HTTPException

        mock_db.get_project.return_value = None

        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             pytest.raises(HTTPException) as exc_info:
            await approve_tasks(
                project_id=999,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_tasks_access_denied_returns_403(
        self, mock_db, mock_user, mock_manager
    ):
        """Test that approving without access returns 403."""
        from fastapi import HTTPException

        mock_db.user_has_project_access.return_value = False

        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             pytest.raises(HTTPException) as exc_info:
            await approve_tasks(
                project_id=1,
                request=request,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 403


class TestWebSocketBroadcastForDevelopmentStarted:
    """Tests for broadcast_development_started function."""

    @pytest.mark.asyncio
    async def test_broadcast_development_started_message_format(self):
        """Test that development_started message has correct format."""
        from codeframe.ui.websocket_broadcasts import broadcast_development_started

        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock()

        await broadcast_development_started(
            manager=mock_manager,
            project_id=1,
            approved_count=5,
            excluded_count=2
        )

        mock_manager.broadcast.assert_called_once()
        message = mock_manager.broadcast.call_args[0][0]

        assert message["type"] == "development_started"
        assert message["project_id"] == 1
        assert message["approved_count"] == 5
        assert message["excluded_count"] == 2
        assert "timestamp" in message
        # Verify timestamp format ends with 'Z'
        assert message["timestamp"].endswith("Z")


class TestPlanningBroadcastFunctions:
    """Tests for planning-related WebSocket broadcast functions."""

    @pytest.mark.asyncio
    async def test_broadcast_planning_started(self):
        """Test planning_started broadcast."""
        from codeframe.ui.websocket_broadcasts import broadcast_planning_started

        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock()

        await broadcast_planning_started(manager=mock_manager, project_id=1)

        mock_manager.broadcast.assert_called_once()
        message = mock_manager.broadcast.call_args[0][0]

        assert message["type"] == "planning_started"
        assert message["project_id"] == 1
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_broadcast_issues_generated(self):
        """Test issues_generated broadcast."""
        from codeframe.ui.websocket_broadcasts import broadcast_issues_generated

        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock()

        await broadcast_issues_generated(
            manager=mock_manager, project_id=1, issue_count=5
        )

        mock_manager.broadcast.assert_called_once()
        message = mock_manager.broadcast.call_args[0][0]

        assert message["type"] == "issues_generated"
        assert message["project_id"] == 1
        assert message["issue_count"] == 5
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_broadcast_tasks_decomposed(self):
        """Test tasks_decomposed broadcast."""
        from codeframe.ui.websocket_broadcasts import broadcast_tasks_decomposed

        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock()

        await broadcast_tasks_decomposed(
            manager=mock_manager, project_id=1, task_count=10
        )

        mock_manager.broadcast.assert_called_once()
        message = mock_manager.broadcast.call_args[0][0]

        assert message["type"] == "tasks_decomposed"
        assert message["project_id"] == 1
        assert message["task_count"] == 10
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_broadcast_tasks_ready(self):
        """Test tasks_ready broadcast."""
        from codeframe.ui.websocket_broadcasts import broadcast_tasks_ready

        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock()

        await broadcast_tasks_ready(
            manager=mock_manager, project_id=1, total_tasks=10
        )

        mock_manager.broadcast.assert_called_once()
        message = mock_manager.broadcast.call_args[0][0]

        assert message["type"] == "tasks_ready"
        assert message["project_id"] == 1
        assert message["total_tasks"] == 10
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_broadcast_planning_failed(self):
        """Test planning_failed broadcast."""
        from codeframe.ui.websocket_broadcasts import broadcast_planning_failed

        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock()

        await broadcast_planning_failed(
            manager=mock_manager, project_id=1, error="API Error"
        )

        mock_manager.broadcast.assert_called_once()
        message = mock_manager.broadcast.call_args[0][0]

        assert message["type"] == "planning_failed"
        assert message["project_id"] == 1
        assert message["error"] == "API Error"
        assert message["status"] == "failed"
        assert "timestamp" in message
