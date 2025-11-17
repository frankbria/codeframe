"""
Tests for WebSocket broadcast helpers (cf-45).

Tests ensure that broadcast functions correctly format and send
WebSocket messages for real-time dashboard updates.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from codeframe.ui.websocket_broadcasts import (
    broadcast_task_status,
    broadcast_agent_status,
    broadcast_test_result,
    broadcast_commit_created,
    broadcast_activity_update,
    broadcast_progress_update,
    broadcast_correction_attempt,
)


@pytest.fixture
def mock_manager():
    """Create mock ConnectionManager."""
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    return manager


@pytest.mark.asyncio
async def test_broadcast_task_status_basic(mock_manager):
    """Test broadcasting basic task status change."""
    await broadcast_task_status(mock_manager, project_id=1, task_id=42, status="in_progress")

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "task_status_changed"
    assert message["project_id"] == 1
    assert message["task_id"] == 42
    assert message["status"] == "in_progress"
    assert "timestamp" in message
    assert "agent_id" not in message
    assert "progress" not in message


@pytest.mark.asyncio
async def test_broadcast_task_status_with_agent_and_progress(mock_manager):
    """Test broadcasting task status with agent and progress."""
    await broadcast_task_status(
        mock_manager,
        project_id=1,
        task_id=42,
        status="in_progress",
        agent_id="backend-worker",
        progress=75,
    )

    message = mock_manager.broadcast.call_args[0][0]

    assert message["agent_id"] == "backend-worker"
    assert message["progress"] == 75


@pytest.mark.asyncio
async def test_broadcast_agent_status_basic(mock_manager):
    """Test broadcasting basic agent status change."""
    await broadcast_agent_status(mock_manager, project_id=1, agent_id="backend-1", status="working")

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "agent_status_changed"
    assert message["project_id"] == 1
    assert message["agent_id"] == "backend-1"
    assert message["status"] == "working"
    assert "timestamp" in message
    assert "current_task" not in message


@pytest.mark.asyncio
async def test_broadcast_agent_status_with_task(mock_manager):
    """Test broadcasting agent status with current task."""
    await broadcast_agent_status(
        mock_manager,
        project_id=1,
        agent_id="backend-1",
        status="working",
        current_task_id=42,
        current_task_title="Implement login endpoint",
        progress=50,
    )

    message = mock_manager.broadcast.call_args[0][0]

    assert message["current_task"]["id"] == 42
    assert message["current_task"]["title"] == "Implement login endpoint"
    assert message["progress"] == 50


@pytest.mark.asyncio
async def test_broadcast_test_result(mock_manager):
    """Test broadcasting test execution results."""
    await broadcast_test_result(
        mock_manager,
        project_id=1,
        task_id=42,
        status="passed",
        passed=15,
        failed=0,
        errors=0,
        total=15,
        duration=3.5,
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "test_result"
    assert message["project_id"] == 1
    assert message["task_id"] == 42
    assert message["status"] == "passed"
    assert message["passed"] == 15
    assert message["failed"] == 0
    assert message["errors"] == 0
    assert message["total"] == 15
    assert message["duration"] == 3.5


@pytest.mark.asyncio
async def test_broadcast_commit_created_basic(mock_manager):
    """Test broadcasting git commit creation."""
    await broadcast_commit_created(
        mock_manager,
        project_id=1,
        task_id=42,
        commit_hash="abc123def456",
        commit_message="feat: Implement login endpoint",
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "commit_created"
    assert message["project_id"] == 1
    assert message["task_id"] == 42
    assert message["commit_hash"] == "abc123def456"
    assert message["commit_message"] == "feat: Implement login endpoint"
    assert "files_changed" not in message


@pytest.mark.asyncio
async def test_broadcast_commit_created_with_files(mock_manager):
    """Test broadcasting commit with file list."""
    await broadcast_commit_created(
        mock_manager,
        project_id=1,
        task_id=42,
        commit_hash="abc123",
        commit_message="feat: Add auth",
        files_changed=["auth.py", "test_auth.py"],
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["files_changed"] == ["auth.py", "test_auth.py"]


@pytest.mark.asyncio
async def test_broadcast_activity_update(mock_manager):
    """Test broadcasting activity feed update."""
    await broadcast_activity_update(
        mock_manager,
        project_id=1,
        activity_type="task_completed",
        agent_id="backend-worker",
        message_text="Completed task #42: Implement login",
        task_id=42,
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "activity_update"
    assert message["project_id"] == 1
    assert message["activity_type"] == "task_completed"
    assert message["agent"] == "backend-worker"
    assert message["message"] == "Completed task #42: Implement login"
    assert message["task_id"] == 42


@pytest.mark.asyncio
async def test_broadcast_progress_update(mock_manager):
    """Test broadcasting project progress update."""
    await broadcast_progress_update(
        mock_manager, project_id=1, completed_tasks=25, total_tasks=100, percentage=25.0
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "progress_update"
    assert message["project_id"] == 1
    assert message["completed_tasks"] == 25
    assert message["total_tasks"] == 100
    assert message["percentage"] == 25.0


@pytest.mark.asyncio
async def test_broadcast_correction_attempt_in_progress(mock_manager):
    """Test broadcasting self-correction attempt in progress."""
    await broadcast_correction_attempt(
        mock_manager,
        project_id=1,
        task_id=42,
        attempt_number=1,
        max_attempts=3,
        status="in_progress",
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "correction_attempt"
    assert message["project_id"] == 1
    assert message["task_id"] == 42
    assert message["attempt_number"] == 1
    assert message["max_attempts"] == 3
    assert message["status"] == "in_progress"
    assert "error_summary" not in message


@pytest.mark.asyncio
async def test_broadcast_correction_attempt_failed(mock_manager):
    """Test broadcasting failed correction attempt."""
    await broadcast_correction_attempt(
        mock_manager,
        project_id=1,
        task_id=42,
        attempt_number=2,
        max_attempts=3,
        status="failed",
        error_summary="Tests still failing: 3 errors",
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["status"] == "failed"
    assert message["error_summary"] == "Tests still failing: 3 errors"


@pytest.mark.asyncio
async def test_broadcast_handles_exceptions(mock_manager, caplog):
    """Test that broadcast errors are handled gracefully."""
    # Make broadcast raise an exception
    mock_manager.broadcast.side_effect = Exception("Connection lost")

    # Should not raise, just log
    await broadcast_task_status(mock_manager, project_id=1, task_id=42, status="completed")

    # Check error was logged
    assert "Failed to broadcast task status" in caplog.text


@pytest.mark.asyncio
async def test_timestamp_format(mock_manager):
    """Test that timestamps are in correct ISO format with Z suffix."""
    await broadcast_task_status(mock_manager, project_id=1, task_id=42, status="completed")

    message = mock_manager.broadcast.call_args[0][0]
    timestamp = message["timestamp"]

    # Should be ISO format with Z suffix (UTC)
    assert timestamp.endswith("Z")

    # Should be parseable as datetime
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


@pytest.mark.asyncio
async def test_multiple_broadcasts_in_sequence(mock_manager):
    """Test multiple broadcasts work correctly."""
    await broadcast_task_status(mock_manager, 1, 42, "in_progress")
    await broadcast_test_result(mock_manager, 1, 42, "passed", 10, 0, 0, 10, 2.5)
    await broadcast_task_status(mock_manager, 1, 42, "completed")

    assert mock_manager.broadcast.call_count == 3

    # Verify call order
    calls = mock_manager.broadcast.call_args_list
    assert calls[0][0][0]["type"] == "task_status_changed"
    assert calls[0][0][0]["status"] == "in_progress"

    assert calls[1][0][0]["type"] == "test_result"

    assert calls[2][0][0]["type"] == "task_status_changed"
    assert calls[2][0][0]["status"] == "completed"
