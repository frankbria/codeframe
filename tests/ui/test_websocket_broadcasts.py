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
    broadcast_agent_created,
    broadcast_agent_retired,
    broadcast_task_assigned,
    broadcast_task_blocked,
    broadcast_task_unblocked,
    broadcast_blocker_created,
    broadcast_blocker_resolved,
    broadcast_agent_resumed,
    broadcast_blocker_expired,
    broadcast_discovery_answer_submitted,
    broadcast_discovery_question_presented,
    broadcast_discovery_progress_updated,
    broadcast_discovery_completed,
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
        skipped=0,
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
    assert message["skipped"] == 0
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
    assert message["agent_id"] == "backend-worker"
    assert message["message"] == "Completed task #42: Implement login"
    assert message["task_id"] == 42


@pytest.mark.asyncio
async def test_broadcast_progress_update(mock_manager):
    """Test broadcasting project progress update."""
    await broadcast_progress_update(
        mock_manager, project_id=1, completed=25, total=100, percentage=25.0
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "progress_update"
    assert message["project_id"] == 1
    assert message["completed"] == 25
    assert message["total"] == 100
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


# ============================================================================
# Tests for error handling in existing broadcast functions
# ============================================================================


@pytest.mark.asyncio
async def test_broadcast_agent_status_error_handling(mock_manager, caplog):
    """Test agent status broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("WebSocket error")

    await broadcast_agent_status(mock_manager, project_id=1, agent_id="agent-1", status="idle")

    assert "Failed to broadcast agent status" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_test_result_error_handling(mock_manager, caplog):
    """Test test result broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Network error")

    await broadcast_test_result(
        mock_manager, project_id=1, task_id=42, status="passed", passed=10
    )

    assert "Failed to broadcast test result" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_commit_created_error_handling(mock_manager, caplog):
    """Test commit broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Connection lost")

    await broadcast_commit_created(
        mock_manager, project_id=1, task_id=42, commit_hash="abc123", commit_message="fix: bug"
    )

    assert "Failed to broadcast commit" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_activity_update_error_handling(mock_manager, caplog):
    """Test activity update broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Broadcast failed")

    await broadcast_activity_update(
        mock_manager, project_id=1, activity_type="task", message_text="Task completed"
    )

    assert "Failed to broadcast activity" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_progress_update_error_handling(mock_manager, caplog):
    """Test progress update broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_progress_update(mock_manager, project_id=1, completed=10, total=100)

    assert "Failed to broadcast progress" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_correction_attempt_error_handling(mock_manager, caplog):
    """Test correction attempt broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_correction_attempt(
        mock_manager, project_id=1, task_id=42, attempt_number=1, max_attempts=3, status="in_progress"
    )

    assert "Failed to broadcast correction attempt" in caplog.text


# ============================================================================
# Tests for Sprint 4: Multi-Agent Coordination Broadcasts
# ============================================================================


@pytest.mark.asyncio
async def test_broadcast_agent_created_basic(mock_manager):
    """Test broadcasting agent creation."""
    await broadcast_agent_created(
        mock_manager, project_id=1, agent_id="backend-worker-001", agent_type="backend-worker"
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "agent_created"
    assert message["project_id"] == 1
    assert message["agent_id"] == "backend-worker-001"
    assert message["agent_type"] == "backend-worker"
    assert message["status"] == "idle"
    assert message["tasks_completed"] == 0
    assert "timestamp" in message


@pytest.mark.asyncio
async def test_broadcast_agent_created_with_completed_tasks(mock_manager):
    """Test broadcasting agent creation with tasks completed."""
    await broadcast_agent_created(
        mock_manager,
        project_id=1,
        agent_id="backend-worker-002",
        agent_type="backend-worker",
        tasks_completed=5,
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["tasks_completed"] == 5


@pytest.mark.asyncio
async def test_broadcast_agent_created_error_handling(mock_manager, caplog):
    """Test agent created broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_agent_created(
        mock_manager, project_id=1, agent_id="agent-1", agent_type="worker"
    )

    assert "Failed to broadcast agent creation" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_agent_retired_basic(mock_manager):
    """Test broadcasting agent retirement."""
    await broadcast_agent_retired(
        mock_manager, project_id=1, agent_id="backend-worker-001", tasks_completed=10
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "agent_retired"
    assert message["project_id"] == 1
    assert message["agent_id"] == "backend-worker-001"
    assert message["tasks_completed"] == 10
    assert "timestamp" in message


@pytest.mark.asyncio
async def test_broadcast_agent_retired_default_tasks(mock_manager):
    """Test broadcasting agent retirement with default tasks completed."""
    await broadcast_agent_retired(mock_manager, project_id=1, agent_id="agent-1")

    message = mock_manager.broadcast.call_args[0][0]
    assert message["tasks_completed"] == 0


@pytest.mark.asyncio
async def test_broadcast_agent_retired_error_handling(mock_manager, caplog):
    """Test agent retired broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_agent_retired(mock_manager, project_id=1, agent_id="agent-1")

    assert "Failed to broadcast agent retirement" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_task_assigned_basic(mock_manager):
    """Test broadcasting task assignment."""
    await broadcast_task_assigned(
        mock_manager, project_id=1, task_id=42, agent_id="backend-worker-001"
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "task_assigned"
    assert message["project_id"] == 1
    assert message["task_id"] == 42
    assert message["agent_id"] == "backend-worker-001"
    assert "timestamp" in message
    assert "task_title" not in message


@pytest.mark.asyncio
async def test_broadcast_task_assigned_with_title(mock_manager):
    """Test broadcasting task assignment with title."""
    await broadcast_task_assigned(
        mock_manager,
        project_id=1,
        task_id=42,
        agent_id="backend-worker-001",
        task_title="Implement login endpoint",
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["task_title"] == "Implement login endpoint"


@pytest.mark.asyncio
async def test_broadcast_task_assigned_error_handling(mock_manager, caplog):
    """Test task assigned broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_task_assigned(mock_manager, project_id=1, task_id=42, agent_id="agent-1")

    assert "Failed to broadcast task assignment" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_task_blocked_basic(mock_manager):
    """Test broadcasting task blocked by dependencies."""
    await broadcast_task_blocked(
        mock_manager, project_id=1, task_id=42, blocked_by=[10, 20, 30]
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "task_blocked"
    assert message["project_id"] == 1
    assert message["task_id"] == 42
    assert message["blocked_by"] == [10, 20, 30]
    assert message["blocked_count"] == 3
    assert "timestamp" in message
    assert "task_title" not in message


@pytest.mark.asyncio
async def test_broadcast_task_blocked_with_title(mock_manager):
    """Test broadcasting task blocked with title."""
    await broadcast_task_blocked(
        mock_manager,
        project_id=1,
        task_id=42,
        blocked_by=[10],
        task_title="Complete user auth",
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["task_title"] == "Complete user auth"


@pytest.mark.asyncio
async def test_broadcast_task_blocked_error_handling(mock_manager, caplog):
    """Test task blocked broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_task_blocked(mock_manager, project_id=1, task_id=42, blocked_by=[10])

    assert "Failed to broadcast task blocked" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_task_unblocked_basic(mock_manager):
    """Test broadcasting task unblocked."""
    await broadcast_task_unblocked(mock_manager, project_id=1, task_id=42)

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "task_unblocked"
    assert message["project_id"] == 1
    assert message["task_id"] == 42
    assert "timestamp" in message
    assert "unblocked_by" not in message
    assert "task_title" not in message


@pytest.mark.asyncio
async def test_broadcast_task_unblocked_with_unblocked_by(mock_manager):
    """Test broadcasting task unblocked with unblocked_by."""
    await broadcast_task_unblocked(
        mock_manager, project_id=1, task_id=42, unblocked_by=10
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["unblocked_by"] == 10


@pytest.mark.asyncio
async def test_broadcast_task_unblocked_with_title(mock_manager):
    """Test broadcasting task unblocked with title."""
    await broadcast_task_unblocked(
        mock_manager, project_id=1, task_id=42, task_title="Implement auth"
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["task_title"] == "Implement auth"


@pytest.mark.asyncio
async def test_broadcast_task_unblocked_error_handling(mock_manager, caplog):
    """Test task unblocked broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_task_unblocked(mock_manager, project_id=1, task_id=42)

    assert "Failed to broadcast task unblocked" in caplog.text


# ============================================================================
# Tests for Blocker Broadcasts (049-human-in-loop)
# ============================================================================


@pytest.mark.asyncio
async def test_broadcast_blocker_created_basic(mock_manager):
    """Test broadcasting blocker creation."""
    await broadcast_blocker_created(
        mock_manager,
        project_id=1,
        blocker_id=5,
        agent_id="backend-worker-001",
        task_id=42,
        blocker_type="SYNC",
        question="Which authentication library should we use?",
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "blocker_created"
    assert message["project_id"] == 1
    assert message["blocker"]["id"] == 5
    assert message["blocker"]["agent_id"] == "backend-worker-001"
    assert message["blocker"]["task_id"] == 42
    assert message["blocker"]["blocker_type"] == "SYNC"
    assert message["blocker"]["question"] == "Which authentication library should we use?"
    assert message["blocker"]["status"] == "PENDING"
    assert "created_at" in message["blocker"]
    assert "agent_name" not in message["blocker"]
    assert "task_title" not in message["blocker"]


@pytest.mark.asyncio
async def test_broadcast_blocker_created_with_optional_fields(mock_manager):
    """Test broadcasting blocker creation with optional fields."""
    await broadcast_blocker_created(
        mock_manager,
        project_id=1,
        blocker_id=5,
        agent_id="backend-worker-001",
        task_id=42,
        blocker_type="ASYNC",
        question="Should we use Redis or Memcached?",
        agent_name="Backend Worker #1",
        task_title="Implement caching layer",
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["blocker"]["agent_name"] == "Backend Worker #1"
    assert message["blocker"]["task_title"] == "Implement caching layer"


@pytest.mark.asyncio
async def test_broadcast_blocker_created_no_task(mock_manager):
    """Test broadcasting blocker creation without task_id."""
    await broadcast_blocker_created(
        mock_manager,
        project_id=1,
        blocker_id=5,
        agent_id="backend-worker-001",
        task_id=None,
        blocker_type="SYNC",
        question="Global question?",
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["blocker"]["task_id"] is None


@pytest.mark.asyncio
async def test_broadcast_blocker_created_error_handling(mock_manager, caplog):
    """Test blocker created broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_blocker_created(
        mock_manager,
        project_id=1,
        blocker_id=5,
        agent_id="agent-1",
        task_id=42,
        blocker_type="SYNC",
        question="Question?",
    )

    assert "Failed to broadcast blocker created" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_blocker_resolved_basic(mock_manager):
    """Test broadcasting blocker resolution."""
    await broadcast_blocker_resolved(
        mock_manager, project_id=1, blocker_id=5, answer="Use JWT tokens"
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "blocker_resolved"
    assert message["project_id"] == 1
    assert message["blocker_id"] == 5
    assert message["answer"] == "Use JWT tokens"
    assert "resolved_at" in message


@pytest.mark.asyncio
async def test_broadcast_blocker_resolved_error_handling(mock_manager, caplog):
    """Test blocker resolved broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_blocker_resolved(mock_manager, project_id=1, blocker_id=5, answer="Answer")

    assert "Failed to broadcast blocker resolved" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_agent_resumed_basic(mock_manager):
    """Test broadcasting agent resume after blocker resolution."""
    await broadcast_agent_resumed(
        mock_manager, project_id=1, agent_id="backend-worker-001", task_id=42, blocker_id=5
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "agent_resumed"
    assert message["project_id"] == 1
    assert message["agent_id"] == "backend-worker-001"
    assert message["task_id"] == 42
    assert message["blocker_id"] == 5
    assert "resumed_at" in message


@pytest.mark.asyncio
async def test_broadcast_agent_resumed_error_handling(mock_manager, caplog):
    """Test agent resumed broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_agent_resumed(
        mock_manager, project_id=1, agent_id="agent-1", task_id=42, blocker_id=5
    )

    assert "Failed to broadcast agent resumed" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_blocker_expired_basic(mock_manager):
    """Test broadcasting blocker expiration."""
    await broadcast_blocker_expired(
        mock_manager,
        project_id=1,
        blocker_id=5,
        agent_id="backend-worker-001",
        task_id=42,
        question="Which library?",
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "blocker_expired"
    assert message["project_id"] == 1
    assert message["blocker_id"] == 5
    assert message["agent_id"] == "backend-worker-001"
    assert message["task_id"] == 42
    assert message["question"] == "Which library?"
    assert "expired_at" in message


@pytest.mark.asyncio
async def test_broadcast_blocker_expired_no_task(mock_manager):
    """Test broadcasting blocker expiration without task_id."""
    await broadcast_blocker_expired(
        mock_manager,
        project_id=1,
        blocker_id=5,
        agent_id="agent-1",
        task_id=None,
        question="Question?",
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["task_id"] is None


@pytest.mark.asyncio
async def test_broadcast_blocker_expired_error_handling(mock_manager, caplog):
    """Test blocker expired broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_blocker_expired(
        mock_manager,
        project_id=1,
        blocker_id=5,
        agent_id="agent-1",
        task_id=42,
        question="Question?",
    )

    assert "Failed to broadcast blocker expired" in caplog.text


# ============================================================================
# Tests for Discovery Answer UI Broadcasts (012-discovery-answer-ui)
# ============================================================================


@pytest.mark.asyncio
async def test_broadcast_discovery_answer_submitted_basic(mock_manager):
    """Test broadcasting discovery answer submission."""
    await broadcast_discovery_answer_submitted(
        mock_manager,
        project_id=1,
        question_id="q1",
        answer_preview="This is a long answer that will be truncated if it exceeds 100 characters in length to fit the preview.",
        current_index=1,
        total_questions=5,
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "discovery_answer_submitted"
    assert message["project_id"] == 1
    assert message["question_id"] == "q1"
    # Should be truncated to 100 chars
    assert len(message["answer_preview"]) <= 100
    assert message["progress"]["current"] == 1
    assert message["progress"]["total"] == 5
    assert message["progress"]["percentage"] == 20.0
    assert "timestamp" in message


@pytest.mark.asyncio
async def test_broadcast_discovery_answer_submitted_percentage_calculation(mock_manager):
    """Test percentage calculation in discovery answer submission."""
    await broadcast_discovery_answer_submitted(
        mock_manager,
        project_id=1,
        question_id="q2",
        answer_preview="Answer",
        current_index=3,
        total_questions=10,
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["progress"]["percentage"] == 30.0


@pytest.mark.asyncio
async def test_broadcast_discovery_answer_submitted_zero_total(mock_manager):
    """Test discovery answer submission with zero total questions."""
    await broadcast_discovery_answer_submitted(
        mock_manager,
        project_id=1,
        question_id="q1",
        answer_preview="Answer",
        current_index=0,
        total_questions=0,
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["progress"]["percentage"] == 0.0


@pytest.mark.asyncio
async def test_broadcast_discovery_answer_submitted_clamping(mock_manager):
    """Test percentage clamping in discovery answer submission."""
    # Test upper bound clamping
    await broadcast_discovery_answer_submitted(
        mock_manager,
        project_id=1,
        question_id="q1",
        answer_preview="Answer",
        current_index=10,
        total_questions=5,  # More current than total
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["progress"]["percentage"] <= 100.0


@pytest.mark.asyncio
async def test_broadcast_discovery_answer_submitted_error_handling(mock_manager, caplog):
    """Test discovery answer submission broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_discovery_answer_submitted(
        mock_manager,
        project_id=1,
        question_id="q1",
        answer_preview="Answer",
        current_index=1,
        total_questions=5,
    )

    assert "Failed to broadcast discovery answer submission" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_discovery_question_presented_basic(mock_manager):
    """Test broadcasting discovery question presented."""
    await broadcast_discovery_question_presented(
        mock_manager,
        project_id=1,
        question_id="q2",
        question_text="What is the target user base?",
        current_index=2,
        total_questions=5,
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "discovery_question_presented"
    assert message["project_id"] == 1
    assert message["question_id"] == "q2"
    assert message["question_text"] == "What is the target user base?"
    assert message["current_index"] == 2
    assert message["total_questions"] == 5
    assert "timestamp" in message


@pytest.mark.asyncio
async def test_broadcast_discovery_question_presented_error_handling(mock_manager, caplog):
    """Test discovery question presented broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_discovery_question_presented(
        mock_manager,
        project_id=1,
        question_id="q1",
        question_text="Question?",
        current_index=1,
        total_questions=5,
    )

    assert "Failed to broadcast discovery question presented" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_discovery_progress_updated_basic(mock_manager):
    """Test broadcasting discovery progress update."""
    await broadcast_discovery_progress_updated(
        mock_manager, project_id=1, current_index=3, total_questions=10, percentage=30.0
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "discovery_progress_updated"
    assert message["project_id"] == 1
    assert message["progress"]["current"] == 3
    assert message["progress"]["total"] == 10
    assert message["progress"]["percentage"] == 30.0
    assert "timestamp" in message


@pytest.mark.asyncio
async def test_broadcast_discovery_progress_updated_error_handling(mock_manager, caplog):
    """Test discovery progress updated broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_discovery_progress_updated(
        mock_manager, project_id=1, current_index=1, total_questions=5, percentage=20.0
    )

    assert "Failed to broadcast discovery progress update" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_discovery_completed_basic(mock_manager):
    """Test broadcasting discovery completion."""
    await broadcast_discovery_completed(
        mock_manager, project_id=1, total_answers=5, next_phase="prd_generation"
    )

    mock_manager.broadcast.assert_called_once()
    message = mock_manager.broadcast.call_args[0][0]

    assert message["type"] == "discovery_completed"
    assert message["project_id"] == 1
    assert message["total_answers"] == 5
    assert message["next_phase"] == "prd_generation"
    assert "timestamp" in message


@pytest.mark.asyncio
async def test_broadcast_discovery_completed_default_next_phase(mock_manager):
    """Test broadcasting discovery completion with default next phase."""
    await broadcast_discovery_completed(mock_manager, project_id=1, total_answers=10)

    message = mock_manager.broadcast.call_args[0][0]
    assert message["next_phase"] == "prd_generation"


@pytest.mark.asyncio
async def test_broadcast_discovery_completed_error_handling(mock_manager, caplog):
    """Test discovery completed broadcast handles exceptions gracefully."""
    mock_manager.broadcast.side_effect = Exception("Error")

    await broadcast_discovery_completed(mock_manager, project_id=1, total_answers=5)

    assert "Failed to broadcast discovery completion" in caplog.text


# ============================================================================
# Tests for Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_broadcast_progress_update_auto_calculation(mock_manager):
    """Test progress update with automatic percentage calculation."""
    await broadcast_progress_update(mock_manager, project_id=1, completed=25, total=100)

    message = mock_manager.broadcast.call_args[0][0]
    assert message["percentage"] == 25.0


@pytest.mark.asyncio
async def test_broadcast_progress_update_zero_total(mock_manager):
    """Test progress update with zero total."""
    await broadcast_progress_update(mock_manager, project_id=1, completed=0, total=0)

    message = mock_manager.broadcast.call_args[0][0]
    assert message["percentage"] == 0.0


@pytest.mark.asyncio
async def test_broadcast_progress_update_negative_total(mock_manager):
    """Test progress update with negative total."""
    await broadcast_progress_update(mock_manager, project_id=1, completed=5, total=-10)

    message = mock_manager.broadcast.call_args[0][0]
    assert message["percentage"] == 0.0


@pytest.mark.asyncio
async def test_broadcast_progress_update_clamping_upper(mock_manager):
    """Test progress update percentage clamping to 100%."""
    await broadcast_progress_update(mock_manager, project_id=1, completed=150, total=100)

    message = mock_manager.broadcast.call_args[0][0]
    assert message["percentage"] == 100.0


@pytest.mark.asyncio
async def test_broadcast_progress_update_clamping_lower(mock_manager):
    """Test progress update percentage clamping to 0%."""
    await broadcast_progress_update(mock_manager, project_id=1, completed=-10, total=100)

    message = mock_manager.broadcast.call_args[0][0]
    assert message["percentage"] >= 0.0


@pytest.mark.asyncio
async def test_broadcast_agent_status_with_task_no_title(mock_manager):
    """Test agent status with task ID but no title."""
    await broadcast_agent_status(
        mock_manager, project_id=1, agent_id="agent-1", status="working", current_task_id=42
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["current_task"]["id"] == 42
    assert message["current_task"]["title"] == "Task #42"


@pytest.mark.asyncio
async def test_broadcast_commit_created_with_files_count(mock_manager):
    """Test commit broadcast with file count."""
    await broadcast_commit_created(
        mock_manager,
        project_id=1,
        task_id=42,
        commit_hash="abc123",
        commit_message="feat: Add feature",
        files_changed=5,
    )

    message = mock_manager.broadcast.call_args[0][0]
    assert message["files_changed"] == 5
