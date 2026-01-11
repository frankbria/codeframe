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

from fastapi import BackgroundTasks

from codeframe.core.models import Task, TaskStatus
from codeframe.ui.routers.tasks import approve_tasks, TaskApprovalRequest


@pytest.fixture
def mock_background_tasks():
    """Create mock BackgroundTasks."""
    bg = MagicMock(spec=BackgroundTasks)
    bg.add_task = MagicMock()
    return bg


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
        self, mock_db, mock_user, mock_manager, mock_background_tasks
    ):
        """Test that approving tasks returns success response with summary."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            response = await approve_tasks(
                project_id=1,
                request=request,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert response.success is True
        assert response.phase == "active"
        assert response.approved_count == 3
        assert response.excluded_count == 0

    @pytest.mark.asyncio
    async def test_approve_tasks_with_exclusions(
        self, mock_db, mock_user, mock_manager, mock_background_tasks
    ):
        """Test that excluded tasks are not approved."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[2, 3])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            response = await approve_tasks(
                project_id=1,
                request=request,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert response.approved_count == 1
        assert response.excluded_count == 2

    @pytest.mark.asyncio
    async def test_approve_tasks_updates_task_status_to_pending(
        self, mock_db, mock_user, mock_manager, mock_background_tasks
    ):
        """Test that approved tasks are updated to pending status."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            await approve_tasks(
                project_id=1,
                request=request,
                background_tasks=mock_background_tasks,
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
        self, mock_db, mock_user, mock_manager, mock_background_tasks
    ):
        """Test that project phase is transitioned to active."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager") as mock_phase_manager:
            await approve_tasks(
                project_id=1,
                request=request,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        # Verify PhaseManager.transition was called
        mock_phase_manager.transition.assert_called_once_with(1, "active", mock_db)

    @pytest.mark.asyncio
    async def test_approve_tasks_broadcasts_development_started(
        self, mock_db, mock_user, mock_manager, mock_background_tasks
    ):
        """Test that development_started event is broadcast."""
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            await approve_tasks(
                project_id=1,
                request=request,
                background_tasks=mock_background_tasks,
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
        self, mock_db, mock_user, mock_manager, mock_background_tasks
    ):
        """Test that rejecting tasks returns rejection response."""
        request = TaskApprovalRequest(approved=False, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager):
            response = await approve_tasks(
                project_id=1,
                request=request,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert response.success is False
        assert "not approved" in response.message.lower()


class TestTaskApprovalValidation:
    """Tests for task approval validation."""

    @pytest.mark.asyncio
    async def test_approve_tasks_wrong_phase_returns_400(
        self, mock_db, mock_user, mock_manager, mock_background_tasks
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
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 400
        assert "planning" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_approve_tasks_no_tasks_returns_404(
        self, mock_db, mock_user, mock_manager, mock_background_tasks
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
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 404
        assert "no tasks" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_approve_tasks_project_not_found_returns_404(
        self, mock_db, mock_user, mock_manager, mock_background_tasks
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
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_tasks_access_denied_returns_403(
        self, mock_db, mock_user, mock_manager, mock_background_tasks
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
                background_tasks=mock_background_tasks,
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


# ============================================================================
# Integration and Edge Case Tests
# ============================================================================


class TestPlanningAutomationIntegration:
    """Integration tests for the complete planning automation flow."""

    @pytest.fixture
    def mock_db_with_state(self):
        """Create mock Database that tracks state changes."""
        db = MagicMock()
        # Track project phase changes
        db._project_phase = "planning"
        db._tasks = []

        def get_project(project_id):
            return {
                "id": project_id,
                "name": "Test Project",
                "phase": db._project_phase
            }

        def update_project(project_id, updates):
            if "phase" in updates:
                db._project_phase = updates["phase"]

        def get_project_tasks(project_id):
            return db._tasks

        def update_task(task_id, updates):
            for task in db._tasks:
                if task.id == task_id:
                    if "status" in updates:
                        task.status = TaskStatus(updates["status"])

        db.get_project.side_effect = get_project
        db.update_project.side_effect = update_project
        db.get_project_tasks.side_effect = get_project_tasks
        db.update_task.side_effect = update_task
        db.user_has_project_access.return_value = True

        return db

    @pytest.mark.asyncio
    async def test_end_to_end_planning_to_approval_flow(
        self, mock_db_with_state, mock_user, mock_manager, mock_background_tasks
    ):
        """Test complete flow: planning phase → task approval → development phase."""
        # Setup: Create tasks as if generated by planning automation
        mock_db_with_state._tasks = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING),
        ]

        # Verify starting state
        assert mock_db_with_state._project_phase == "planning"

        # Execute approval
        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager") as mock_pm:
            # Simulate phase manager updating state
            def transition_side_effect(pid, phase, db):
                db._project_phase = phase
            mock_pm.transition.side_effect = transition_side_effect

            response = await approve_tasks(
                project_id=1,
                request=request,
                background_tasks=mock_background_tasks,
                db=mock_db_with_state,
                current_user=mock_user
            )

        # Verify end state
        assert response.success is True
        assert response.phase == "active"
        assert response.approved_count == 2

        # Verify WebSocket notification was sent
        broadcast_calls = [
            call for call in mock_manager.broadcast.call_args_list
            if call[0][0].get("type") == "development_started"
        ]
        assert len(broadcast_calls) == 1

    @pytest.mark.asyncio
    async def test_approval_with_tasks_modified_during_review(
        self, mock_db_with_state, mock_user, mock_manager, mock_background_tasks
    ):
        """Test approval when tasks are modified between generation and approval.

        Scenario: Tasks were generated, user reviews them, but meanwhile
        some tasks are deleted or modified by another process.
        """
        # Setup: Tasks exist initially
        original_tasks = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING),
            Task(id=3, project_id=1, title="Task 3", status=TaskStatus.PENDING),
        ]
        mock_db_with_state._tasks = original_tasks.copy()

        # User tries to exclude task 2 and 3, but task 3 was deleted
        # Simulate: task 3 no longer exists
        mock_db_with_state._tasks = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING),
            # Task 3 was deleted
        ]

        request = TaskApprovalRequest(approved=True, excluded_task_ids=[2, 3])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            response = await approve_tasks(
                project_id=1,
                request=request,
                background_tasks=mock_background_tasks,
                db=mock_db_with_state,
                current_user=mock_user
            )

        # Should still work - task 3 in exclusion list doesn't exist, which is fine
        assert response.success is True
        assert response.approved_count == 1  # Only task 1 approved
        assert response.excluded_count == 1  # Only task 2 excluded (task 3 doesn't exist)


class TestConcurrentApprovalAttempts:
    """Tests for race condition handling in task approval."""

    @pytest.mark.asyncio
    async def test_double_approval_second_fails(self, mock_db, mock_user, mock_manager, mock_background_tasks):
        """Test that approving already-approved project fails gracefully.

        Scenario: Two users try to approve at the same time. First succeeds,
        second should fail because project is no longer in planning phase.
        """
        from fastapi import HTTPException

        # First approval changes phase to active
        def get_project_after_first_approval(project_id):
            # Simulate state after first approval
            return {
                "id": project_id,
                "name": "Test Project",
                "phase": "active"  # Already transitioned
            }

        mock_db.get_project.side_effect = get_project_after_first_approval

        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             pytest.raises(HTTPException) as exc_info:
            await approve_tasks(
                project_id=1,
                request=request,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        # Should fail with 400 - wrong phase
        assert exc_info.value.status_code == 400
        assert "planning" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_phase_transition_failure_leaves_tasks_unchanged(
        self, mock_user, mock_manager, mock_background_tasks
    ):
        """Test that if phase transition fails, tasks are not modified.

        This verifies the transaction ordering fix - phase transition
        happens before task updates.
        """
        from fastapi import HTTPException

        mock_db = MagicMock()
        mock_db.get_project.return_value = {
            "id": 1, "name": "Test", "phase": "planning"
        }
        mock_db.user_has_project_access.return_value = True
        mock_db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING),
        ]

        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager") as mock_pm:
            # Simulate phase transition failure
            mock_pm.transition.side_effect = HTTPException(
                status_code=400, detail="Invalid transition"
            )

            with pytest.raises(HTTPException):
                await approve_tasks(
                    project_id=1,
                    request=request,
                    background_tasks=mock_background_tasks,
                    db=mock_db,
                    current_user=mock_user
                )

        # Critical: update_task should NOT have been called since phase transition failed first
        mock_db.update_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_tasks_deleted_between_fetch_and_update(
        self, mock_user, mock_manager, mock_background_tasks
    ):
        """Test handling when tasks are deleted during approval process.

        Scenario: Tasks are fetched, but before update_task is called,
        the task is deleted by another process.
        """
        mock_db = MagicMock()
        mock_db.get_project.return_value = {
            "id": 1, "name": "Test", "phase": "planning"
        }
        mock_db.user_has_project_access.return_value = True
        mock_db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING),
        ]

        # Simulate update_task failing for task 2 (deleted)
        def update_task_with_deletion(task_id, updates):
            if task_id == 2:
                raise Exception("Task not found")  # Simulates deletion
            return None

        mock_db.update_task.side_effect = update_task_with_deletion

        request = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"):
            # Currently the implementation doesn't handle this - it would raise
            # This test documents the current behavior
            with pytest.raises(Exception, match="Task not found"):
                await approve_tasks(
                    project_id=1,
                    request=request,
                    background_tasks=mock_background_tasks,
                    db=mock_db,
                    current_user=mock_user
                )
