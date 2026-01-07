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
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


async def broadcast_task_status(
    manager,
    project_id: int,
    task_id: int,
    status: str,
    agent_id: Optional[str] = None,
    progress: Optional[int] = None,
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if agent_id:
        message["agent_id"] = agent_id

    if progress is not None:
        message["progress"] = progress

    try:
        await manager.broadcast(message, project_id=project_id)
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
    progress: Optional[int] = None,
    tasks_completed: Optional[int] = None,
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
        tasks_completed: Optional count of tasks completed by this agent
    """
    message = {
        "type": "agent_status_changed",
        "project_id": project_id,
        "agent_id": agent_id,
        "status": status,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if current_task_id:
        message["current_task"] = {
            "id": current_task_id,
            "title": current_task_title if current_task_title else f"Task #{current_task_id}",
        }

    if progress is not None:
        message["progress"] = progress

    if tasks_completed is not None:
        message["tasks_completed"] = tasks_completed

    try:
        await manager.broadcast(message, project_id=project_id)
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
    duration: float = 0.0,
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
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
    files_changed: Optional[int] = None,
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if files_changed is not None:
        message["files_changed"] = files_changed

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast commit_created: {commit_hash[:7]} for task {task_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast commit: {e}")


async def broadcast_activity_update(
    manager,
    project_id: int,
    activity_type: str,
    message_text: str,
    task_id: Optional[int] = None,
    agent_id: Optional[str] = None,
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if task_id:
        message["task_id"] = task_id

    if agent_id:
        message["agent_id"] = agent_id

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast activity_update: {activity_type} - {message_text[:50]}")
    except Exception as e:
        logger.error(f"Failed to broadcast activity: {e}")


async def broadcast_progress_update(
    manager, project_id: int, completed: int, total: int, percentage: Optional[int] = None
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
    # Calculate progress percentage with safety checks
    if percentage is None:
        if total <= 0:
            percentage = 0.0
        else:
            percentage = round((float(completed) / float(total)) * 100, 1)
            # Clamp to [0.0, 100.0] range
            percentage = max(0.0, min(100.0, percentage))

    message = {
        "type": "progress_update",
        "project_id": project_id,
        "completed": completed,
        "total": total,
        "percentage": percentage,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
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
    error_summary: Optional[str] = None,
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if error_summary:
        message["error_summary"] = error_summary

    try:
        await manager.broadcast(message, project_id=project_id)
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
    manager, project_id: int, agent_id: str, agent_type: str, tasks_completed: int = 0
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast agent_created: {agent_id} ({agent_type})")
    except Exception as e:
        logger.error(f"Failed to broadcast agent creation: {e}")


async def broadcast_agent_retired(
    manager, project_id: int, agent_id: str, tasks_completed: int = 0
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast agent_retired: {agent_id} ({tasks_completed} tasks)")
    except Exception as e:
        logger.error(f"Failed to broadcast agent retirement: {e}")


async def broadcast_task_assigned(
    manager, project_id: int, task_id: int, agent_id: str, task_title: Optional[str] = None
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if task_title:
        message["task_title"] = task_title

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast task_assigned: task {task_id} → {agent_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast task assignment: {e}")


async def broadcast_task_blocked(
    manager, project_id: int, task_id: int, blocked_by: List[int], task_title: Optional[str] = None
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if task_title:
        message["task_title"] = task_title

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(
            f"Broadcast task_blocked: task {task_id} blocked by " f"{len(blocked_by)} tasks"
        )
    except Exception as e:
        logger.error(f"Failed to broadcast task blocked: {e}")


async def broadcast_task_unblocked(
    manager,
    project_id: int,
    task_id: int,
    unblocked_by: Optional[int] = None,
    task_title: Optional[str] = None,
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if unblocked_by:
        message["unblocked_by"] = unblocked_by

    if task_title:
        message["task_title"] = task_title

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast task_unblocked: task {task_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast task unblocked: {e}")


# Blocker broadcast functions (049-human-in-loop)


async def broadcast_blocker_created(
    manager,
    project_id: int,
    blocker_id: int,
    agent_id: str,
    task_id: Optional[int],
    blocker_type: str,
    question: str,
    agent_name: Optional[str] = None,
    task_title: Optional[str] = None,
) -> None:
    """
    Broadcast blocker creation to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        blocker_id: Blocker ID
        agent_id: Agent ID that created the blocker
        task_id: Optional task ID associated with blocker
        blocker_type: Type of blocker ('SYNC' or 'ASYNC')
        question: Question for user
        agent_name: Optional agent display name
        task_title: Optional task title
    """
    message = {
        "type": "blocker_created",
        "project_id": project_id,
        "blocker": {
            "id": blocker_id,
            "agent_id": agent_id,
            "task_id": task_id,
            "blocker_type": blocker_type,
            "question": question,
            "status": "PENDING",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
    }

    if agent_name:
        message["blocker"]["agent_name"] = agent_name

    if task_title:
        message["blocker"]["task_title"] = task_title

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast blocker_created: blocker {blocker_id} by {agent_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast blocker created: {e}")


async def broadcast_blocker_resolved(
    manager, project_id: int, blocker_id: int, answer: str
) -> None:
    """
    Broadcast blocker resolution to connected clients.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        blocker_id: Blocker ID that was resolved
        answer: User's answer to the blocker
    """
    message = {
        "type": "blocker_resolved",
        "project_id": project_id,
        "blocker_id": blocker_id,
        "answer": answer,
        "resolved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast blocker_resolved: blocker {blocker_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast blocker resolved: {e}")


async def broadcast_agent_resumed(
    manager, project_id: int, agent_id: str, task_id: int, blocker_id: int
) -> None:
    """
    Broadcast agent resume after blocker resolution.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        agent_id: Agent ID that resumed
        task_id: Task ID being resumed
        blocker_id: Blocker ID that was resolved
    """
    message = {
        "type": "agent_resumed",
        "project_id": project_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "blocker_id": blocker_id,
        "resumed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast agent_resumed: agent {agent_id} on task {task_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast agent resumed: {e}")


async def broadcast_blocker_expired(
    manager, project_id: int, blocker_id: int, agent_id: str, task_id: Optional[int], question: str
) -> None:
    """
    Broadcast blocker expiration (>24h pending) to connected clients (T047).

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        blocker_id: Blocker ID that expired
        agent_id: Agent ID that created the blocker
        task_id: Optional task ID associated with blocker
        question: Original blocker question
    """
    message = {
        "type": "blocker_expired",
        "project_id": project_id,
        "blocker_id": blocker_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "question": question,
        "expired_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast blocker_expired: blocker {blocker_id} by {agent_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast blocker expired: {e}")


# ============================================================================
# Discovery Answer UI Broadcasts (Feature: 012-discovery-answer-ui)
# ============================================================================


async def broadcast_discovery_answer_submitted(
    manager,
    project_id: int,
    question_id: str,
    answer_preview: str,
    current_index: int,
    total_questions: int,
) -> None:
    """
    Broadcast when user submits discovery answer.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        question_id: Unique identifier of the answered question
        answer_preview: First 100 chars of the answer
        current_index: Current question index (0-based)
        total_questions: Total number of questions
    """
    # Calculate progress percentage with safety checks
    if total_questions <= 0:
        percentage = 0.0
    else:
        # Ensure values are treated as numbers and compute percentage
        percentage = round((float(current_index) / float(total_questions)) * 100, 1)
        # Clamp to [0.0, 100.0] range
        percentage = max(0.0, min(100.0, percentage))

    message = {
        "type": "discovery_answer_submitted",
        "project_id": project_id,
        "question_id": question_id,
        "answer_preview": answer_preview[:100],  # Limit to 100 chars
        "progress": {
            "current": current_index,
            "total": total_questions,
            "percentage": percentage,
        },
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast discovery_answer_submitted: question {question_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast discovery answer submission: {e}")


async def broadcast_discovery_question_presented(
    manager,
    project_id: int,
    question_id: str,
    question_text: str,
    current_index: int,
    total_questions: int,
) -> None:
    """
    Broadcast when next discovery question is presented.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        question_id: Unique identifier of the question
        question_text: Full text of the question
        current_index: Current question number (1-based for display)
        total_questions: Total number of questions
    """
    message = {
        "type": "discovery_question_presented",
        "project_id": project_id,
        "question_id": question_id,
        "question_text": question_text,
        "current_index": current_index,
        "total_questions": total_questions,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast discovery_question_presented: {question_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast discovery question presented: {e}")


async def broadcast_discovery_progress_updated(
    manager,
    project_id: int,
    current_index: int,
    total_questions: int,
    percentage: float,
) -> None:
    """
    Broadcast discovery progress updates.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        current_index: Current question index (0-based)
        total_questions: Total number of questions
        percentage: Completion percentage (0.0 - 100.0)
    """
    message = {
        "type": "discovery_progress_updated",
        "project_id": project_id,
        "progress": {
            "current": current_index,
            "total": total_questions,
            "percentage": percentage,
        },
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast discovery_progress_updated: {percentage}%")
    except Exception as e:
        logger.error(f"Failed to broadcast discovery progress update: {e}")


async def broadcast_discovery_completed(
    manager,
    project_id: int,
    total_answers: int,
    next_phase: str = "prd_generation",
) -> None:
    """
    Broadcast when discovery phase is completed.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        total_answers: Total number of answers collected
        next_phase: Next project phase (default: prd_generation)
    """
    message = {
        "type": "discovery_completed",
        "project_id": project_id,
        "total_answers": total_answers,
        "next_phase": next_phase,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast discovery_completed: {total_answers} answers")
    except Exception as e:
        logger.error(f"Failed to broadcast discovery completion: {e}")


# ============================================================================
# Planning Phase Automation Broadcasts (Feature: 016-planning-phase-automation)
# ============================================================================


async def broadcast_planning_started(manager, project_id: int) -> None:
    """
    Broadcast when planning automation begins after PRD completion.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
    """
    message = {
        "type": "planning_started",
        "project_id": project_id,
        "status": "in_progress",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast planning_started for project {project_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast planning started: {e}")


async def broadcast_issues_generated(
    manager, project_id: int, issue_count: int
) -> None:
    """
    Broadcast when issues have been generated from PRD.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        issue_count: Number of issues generated
    """
    message = {
        "type": "issues_generated",
        "project_id": project_id,
        "issue_count": issue_count,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast issues_generated: {issue_count} issues for project {project_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast issues generated: {e}")


async def broadcast_tasks_decomposed(
    manager, project_id: int, task_count: int
) -> None:
    """
    Broadcast when tasks have been decomposed from issues.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        task_count: Number of tasks created
    """
    message = {
        "type": "tasks_decomposed",
        "project_id": project_id,
        "task_count": task_count,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast tasks_decomposed: {task_count} tasks for project {project_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast tasks decomposed: {e}")


async def broadcast_tasks_ready(
    manager, project_id: int, total_tasks: int
) -> None:
    """
    Broadcast when all tasks are ready for user review.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        total_tasks: Total number of tasks ready for review
    """
    message = {
        "type": "tasks_ready",
        "project_id": project_id,
        "total_tasks": total_tasks,
        "status": "ready_for_review",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast tasks_ready: {total_tasks} tasks for project {project_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast tasks ready: {e}")


async def broadcast_planning_failed(
    manager, project_id: int, error: str
) -> None:
    """
    Broadcast when planning automation fails.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        error: Error message describing the failure
    """
    message = {
        "type": "planning_failed",
        "project_id": project_id,
        "status": "failed",
        "error": error,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(f"Broadcast planning_failed for project {project_id}: {error}")
    except Exception as e:
        logger.error(f"Failed to broadcast planning failed: {e}")


async def broadcast_development_started(
    manager, project_id: int, approved_count: int, excluded_count: int
) -> None:
    """
    Broadcast when development phase starts after task approval.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        approved_count: Number of tasks approved
        excluded_count: Number of tasks excluded from approval
    """
    message = {
        "type": "development_started",
        "project_id": project_id,
        "approved_count": approved_count,
        "excluded_count": excluded_count,
        "phase": "active",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message, project_id=project_id)
        logger.debug(
            f"Broadcast development_started for project {project_id}: "
            f"{approved_count} approved, {excluded_count} excluded"
        )
    except Exception as e:
        logger.error(f"Failed to broadcast development started: {e}")
