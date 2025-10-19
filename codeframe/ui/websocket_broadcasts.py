"""
WebSocket Broadcast Helpers for Real-Time Dashboard Updates (cf-45).

This module provides helper functions to broadcast various event types
to connected WebSocket clients for live dashboard updates.

Integration Points:
- BackendWorkerAgent (cf-41): Task execution and status changes
- TestRunner (cf-42): Test results
- GitWorkflowManager (cf-44): Commit events
- SelfCorrectionLoop (cf-43): Correction attempts

Message Types:
- task_status_changed: Task status transitions (pending → in_progress → completed)
- agent_status_changed: Agent status updates (idle → working → blocked)
- test_result: Test execution results (passed/failed counts)
- commit_created: Git commits (from cf-44)
- activity_update: Activity feed entries
- progress_update: Progress bar updates
- correction_attempt: Self-correction loop attempts
"""

from datetime import datetime, UTC
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


async def broadcast_task_status(
    manager,
    project_id: int,
    task_id: int,
    status: str,
    agent_id: Optional[str] = None,
    progress: Optional[int] = None
) -> None:
    """
    Broadcast task status change to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID
        status: New task status (pending/in_progress/completed/failed/blocked)
        agent_id: Optional agent ID that's working on the task
        progress: Optional progress percentage (0-100)
    """
    message = {
        "type": "task_status_changed",
        "project_id": project_id,
        "task_id": task_id,
        "status": status,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if agent_id:
        message["agent_id"] = agent_id

    if progress is not None:
        message["progress"] = progress

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast task_status_changed: task {task_id} → {status}")
    except Exception as e:
        logger.error(f"Failed to broadcast task status: {e}")


async def broadcast_agent_status(
    manager,
    project_id: int,
    agent_id: str,
    status: str,
    current_task_id: Optional[int] = None,
    current_task_title: Optional[str] = None,
    progress: Optional[int] = None
) -> None:
    """
    Broadcast agent status change to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        agent_id: Agent identifier (e.g., "backend-1", "lead")
        status: Agent status (idle/working/blocked/offline)
        current_task_id: Optional ID of current task
        current_task_title: Optional title of current task
        progress: Optional progress percentage (0-100)
    """
    message = {
        "type": "agent_status_changed",
        "project_id": project_id,
        "agent_id": agent_id,
        "status": status,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if current_task_id:
        message["current_task"] = {
            "id": current_task_id,
            "title": current_task_title or f"Task #{current_task_id}"
        }

    if progress is not None:
        message["progress"] = progress

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast agent_status_changed: {agent_id} → {status}")
    except Exception as e:
        logger.error(f"Failed to broadcast agent status: {e}")


async def broadcast_test_result(
    manager,
    project_id: int,
    task_id: int,
    status: str,
    passed: int,
    failed: int,
    errors: int,
    total: int,
    duration: float
) -> None:
    """
    Broadcast test execution results to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID that tests were run for
        status: Test status (passed/failed/error/no_tests/timeout)
        passed: Number of tests passed
        failed: Number of tests failed
        errors: Number of tests with errors
        total: Total number of tests
        duration: Test execution duration in seconds
    """
    message = {
        "type": "test_result",
        "project_id": project_id,
        "task_id": task_id,
        "status": status,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "total": total,
        "duration": duration,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    try:
        await manager.broadcast(message)
        logger.debug(
            f"Broadcast test_result: task {task_id}, {status} "
            f"({passed}/{total} passed)"
        )
    except Exception as e:
        logger.error(f"Failed to broadcast test result: {e}")


async def broadcast_commit_created(
    manager,
    project_id: int,
    task_id: int,
    commit_hash: str,
    commit_message: str,
    files_changed: Optional[List[str]] = None
) -> None:
    """
    Broadcast git commit creation to connected clients.

    This integrates with cf-44 (Git Workflow Manager) to show
    commits in the activity feed in real-time.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID the commit is for
        commit_hash: Full or short commit hash
        commit_message: Commit message
        files_changed: Optional list of files changed
    """
    message = {
        "type": "commit_created",
        "project_id": project_id,
        "task_id": task_id,
        "commit_hash": commit_hash,
        "commit_message": commit_message,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if files_changed:
        message["files_changed"] = files_changed

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast commit_created: {commit_hash[:7]} for task {task_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast commit: {e}")


async def broadcast_activity_update(
    manager,
    project_id: int,
    activity_type: str,
    agent_id: str,
    message_text: str,
    task_id: Optional[int] = None
) -> None:
    """
    Broadcast activity feed update to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        activity_type: Type of activity (task_completed, tests_passed, blocker_created, etc.)
        agent_id: Agent that performed the action
        message_text: Human-readable message for activity feed
        task_id: Optional related task ID
    """
    message = {
        "type": "activity_update",
        "project_id": project_id,
        "activity_type": activity_type,
        "agent": agent_id,
        "message": message_text,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if task_id:
        message["task_id"] = task_id

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast activity_update: {activity_type} by {agent_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast activity: {e}")


async def broadcast_progress_update(
    manager,
    project_id: int,
    completed_tasks: int,
    total_tasks: int,
    percentage: float
) -> None:
    """
    Broadcast project progress update to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        completed_tasks: Number of completed tasks
        total_tasks: Total number of tasks
        percentage: Progress percentage (0-100)
    """
    message = {
        "type": "progress_update",
        "project_id": project_id,
        "completed_tasks": completed_tasks,
        "total_tasks": total_tasks,
        "percentage": percentage,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    try:
        await manager.broadcast(message)
        logger.debug(
            f"Broadcast progress_update: {completed_tasks}/{total_tasks} "
            f"({percentage:.1f}%)"
        )
    except Exception as e:
        logger.error(f"Failed to broadcast progress: {e}")


async def broadcast_correction_attempt(
    manager,
    project_id: int,
    task_id: int,
    attempt_number: int,
    max_attempts: int,
    status: str,
    error_summary: Optional[str] = None
) -> None:
    """
    Broadcast self-correction attempt to connected clients.

    This integrates with cf-43 (Self-Correction Loop) to show
    correction attempts in real-time.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID being corrected
        attempt_number: Current attempt number (1-3)
        max_attempts: Maximum attempts (usually 3)
        status: Attempt status (in_progress/success/failed)
        error_summary: Optional error summary for failed attempts
    """
    message = {
        "type": "correction_attempt",
        "project_id": project_id,
        "task_id": task_id,
        "attempt_number": attempt_number,
        "max_attempts": max_attempts,
        "status": status,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if error_summary:
        message["error_summary"] = error_summary

    try:
        await manager.broadcast(message)
        logger.debug(
            f"Broadcast correction_attempt: task {task_id}, "
            f"attempt {attempt_number}/{max_attempts}, {status}"
        )
    except Exception as e:
        logger.error(f"Failed to broadcast correction attempt: {e}")
