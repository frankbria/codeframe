"""
WebSocket Broadcast Helpers for Real-Time Dashboard Updates (cf-45).

This module provides helper functions to broadcast various event types
to connected WebSocket clients for live dashboard updates.

Integration Points:
- BackendWorkerAgent (cf-41): Task execution and status changes
- TestRunner (cf-42): Test results
- GitWorkflowManager (cf-44): Commit events
- SelfCorrectionLoop (cf-43): Correction attempts
- Multi-Agent Coordination (Sprint 4): Agent lifecycle and task assignments

Message Types:
- task_status_changed: Task status transitions (pending → in_progress → completed)
- agent_status_changed: Agent status updates (idle → working → blocked)
- test_result: Test execution results (passed/failed counts)
- commit_created: Git commits (from cf-44)
- activity_update: Activity feed entries
- progress_update: Progress bar updates
- correction_attempt: Self-correction loop attempts
- agent_created: New agent instantiated (Sprint 4)
- agent_retired: Agent removed from pool (Sprint 4)
- task_assigned: Task assigned to agent (Sprint 4)
- task_blocked: Task blocked by dependencies (Sprint 4)
- task_unblocked: Task unblocked (Sprint 4)
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
            "title": current_task_title if current_task_title else f"Task #{current_task_id}"
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
    passed: int = 0,
    failed: int = 0,
    errors: int = 0,
    skipped: int = 0,
    duration: float = 0.0
) -> None:
    """
    Broadcast test execution results to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID that tests were run for
        status: Test result status (passed/failed/error/timeout/no_tests)
        passed: Number of passed tests
        failed: Number of failed tests
        errors: Number of test errors
        skipped: Number of skipped tests
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
        "skipped": skipped,
        "duration": duration,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    try:
        await manager.broadcast(message)
        logger.debug(
            f"Broadcast test_result: task {task_id}, "
            f"{passed} passed, {failed} failed, {errors} errors"
        )
    except Exception as e:
        logger.error(f"Failed to broadcast test result: {e}")


async def broadcast_commit_created(
    manager,
    project_id: int,
    task_id: int,
    commit_hash: str,
    commit_message: str,
    files_changed: Optional[int] = None
) -> None:
    """
    Broadcast git commit creation to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID that triggered the commit
        commit_hash: Git commit hash (short form)
        commit_message: Commit message
        files_changed: Optional number of files changed
    """
    message = {
        "type": "commit_created",
        "project_id": project_id,
        "task_id": task_id,
        "commit_hash": commit_hash,
        "commit_message": commit_message,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if files_changed is not None:
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
    message_text: str,
    task_id: Optional[int] = None,
    agent_id: Optional[str] = None
) -> None:
    """
    Broadcast activity feed update to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        activity_type: Type of activity (task/agent/test/commit/etc.)
        message_text: Human-readable activity message
        task_id: Optional related task ID
        agent_id: Optional related agent ID
    """
    message = {
        "type": "activity_update",
        "project_id": project_id,
        "activity_type": activity_type,
        "message": message_text,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if task_id:
        message["task_id"] = task_id

    if agent_id:
        message["agent_id"] = agent_id

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast activity_update: {activity_type} - {message_text[:50]}")
    except Exception as e:
        logger.error(f"Failed to broadcast activity: {e}")


async def broadcast_progress_update(
    manager,
    project_id: int,
    completed: int,
    total: int,
    percentage: Optional[int] = None
) -> None:
    """
    Broadcast project progress update to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        completed: Number of completed tasks
        total: Total number of tasks
        percentage: Optional progress percentage (auto-calculated if not provided)
    """
    if percentage is None and total > 0:
        percentage = int((completed / total) * 100)

    message = {
        "type": "progress_update",
        "project_id": project_id,
        "completed": completed,
        "total": total,
        "percentage": percentage if percentage is not None else 0,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast progress_update: {completed}/{total} ({percentage}%)")
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

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID being corrected
        attempt_number: Current attempt number (1-3)
        max_attempts: Maximum attempts allowed
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


# ============================================================================
# Sprint 4: Multi-Agent Coordination Broadcasts
# ============================================================================

async def broadcast_agent_created(
    manager,
    project_id: int,
    agent_id: str,
    agent_type: str,
    tasks_completed: int = 0
) -> None:
    """
    Broadcast agent creation to connected clients (Sprint 4).

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        agent_id: Unique agent identifier (e.g., "backend-worker-001")
        agent_type: Agent type (e.g., "backend-worker", "frontend-specialist")
        tasks_completed: Initial task completion count (default: 0)
    """
    message = {
        "type": "agent_created",
        "project_id": project_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "status": "idle",
        "tasks_completed": tasks_completed,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast agent_created: {agent_id} ({agent_type})")
    except Exception as e:
        logger.error(f"Failed to broadcast agent creation: {e}")


async def broadcast_agent_retired(
    manager,
    project_id: int,
    agent_id: str,
    tasks_completed: int = 0
) -> None:
    """
    Broadcast agent retirement to connected clients (Sprint 4).

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        agent_id: Agent identifier being retired
        tasks_completed: Total tasks completed by this agent
    """
    message = {
        "type": "agent_retired",
        "project_id": project_id,
        "agent_id": agent_id,
        "tasks_completed": tasks_completed,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast agent_retired: {agent_id} ({tasks_completed} tasks)")
    except Exception as e:
        logger.error(f"Failed to broadcast agent retirement: {e}")


async def broadcast_task_assigned(
    manager,
    project_id: int,
    task_id: int,
    agent_id: str,
    task_title: Optional[str] = None
) -> None:
    """
    Broadcast task assignment to agent (Sprint 4).

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID being assigned
        agent_id: Agent ID receiving the task
        task_title: Optional task title for display
    """
    message = {
        "type": "task_assigned",
        "project_id": project_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if task_title:
        message["task_title"] = task_title

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast task_assigned: task {task_id} → {agent_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast task assignment: {e}")


async def broadcast_task_blocked(
    manager,
    project_id: int,
    task_id: int,
    blocked_by: List[int],
    task_title: Optional[str] = None
) -> None:
    """
    Broadcast task blocked by dependencies (Sprint 4).

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID that is blocked
        blocked_by: List of task IDs blocking this task
        task_title: Optional task title for display
    """
    message = {
        "type": "task_blocked",
        "project_id": project_id,
        "task_id": task_id,
        "blocked_by": blocked_by,
        "blocked_count": len(blocked_by),
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if task_title:
        message["task_title"] = task_title

    try:
        await manager.broadcast(message)
        logger.debug(
            f"Broadcast task_blocked: task {task_id} blocked by "
            f"{len(blocked_by)} tasks"
        )
    except Exception as e:
        logger.error(f"Failed to broadcast task blocked: {e}")


async def broadcast_task_unblocked(
    manager,
    project_id: int,
    task_id: int,
    unblocked_by: Optional[int] = None,
    task_title: Optional[str] = None
) -> None:
    """
    Broadcast task unblocked (Sprint 4).

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_id: Task ID that was unblocked
        unblocked_by: Optional ID of task whose completion unblocked this one
        task_title: Optional task title for display
    """
    message = {
        "type": "task_unblocked",
        "project_id": project_id,
        "task_id": task_id,
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    }

    if unblocked_by:
        message["unblocked_by"] = unblocked_by

    if task_title:
        message["task_title"] = task_title

    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast task_unblocked: task {task_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast task unblocked: {e}")
