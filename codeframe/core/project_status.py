"""Project status and session management for CodeFRAME v2.

This module provides v2-compatible functions for retrieving workspace status,
progress metrics, and session state. It works with the v2 Workspace model.

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from codeframe.core.workspace import Workspace
from codeframe.core import tasks, blockers
from codeframe.core.session_manager import SessionManager
from codeframe.core.state_machine import TaskStatus

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class TaskCounts:
    """Task count statistics."""

    total: int
    backlog: int
    ready: int
    in_progress: int
    done: int
    blocked: int
    failed: int


@dataclass
class ProgressMetrics:
    """Project progress metrics."""

    completed_count: int
    total_count: int
    progress_percentage: float
    open_blockers: int


@dataclass
class WorkspaceStatus:
    """Comprehensive workspace status."""

    workspace_id: str
    workspace_name: str
    repo_path: str
    tech_stack: Optional[str]
    task_counts: TaskCounts
    progress: ProgressMetrics
    created_at: datetime


@dataclass
class SessionState:
    """Session state for a workspace."""

    has_session: bool
    last_session_summary: str
    last_session_timestamp: str
    next_actions: list[str]
    progress_pct: float
    active_blockers: list[dict]


# ============================================================================
# Status Functions
# ============================================================================


def get_task_counts(workspace: Workspace) -> TaskCounts:
    """Get task count statistics for a workspace.

    Args:
        workspace: Target workspace

    Returns:
        TaskCounts with counts for each status
    """
    counts = tasks.count_by_status(workspace)

    return TaskCounts(
        total=sum(counts.values()),
        backlog=counts.get(TaskStatus.BACKLOG.value, 0),
        ready=counts.get(TaskStatus.READY.value, 0),
        in_progress=counts.get(TaskStatus.IN_PROGRESS.value, 0),
        done=counts.get(TaskStatus.DONE.value, 0),
        blocked=counts.get(TaskStatus.BLOCKED.value, 0),
        failed=counts.get(TaskStatus.FAILED.value, 0),
    )


def get_progress_metrics(workspace: Workspace) -> ProgressMetrics:
    """Calculate progress metrics for a workspace.

    Progress percentage is calculated as completed tasks / total tasks.

    Args:
        workspace: Target workspace

    Returns:
        ProgressMetrics with completion progress and blocker count
    """
    counts = tasks.count_by_status(workspace)

    total = sum(counts.values())
    completed = counts.get(TaskStatus.DONE.value, 0)

    if total > 0:
        progress_pct = round((completed / total) * 100, 1)
    else:
        progress_pct = 0.0

    # Count open blockers
    open_blockers_list = blockers.list_open(workspace, limit=1000)
    open_blocker_count = len(open_blockers_list)

    return ProgressMetrics(
        completed_count=completed,
        total_count=total,
        progress_percentage=progress_pct,
        open_blockers=open_blocker_count,
    )


def get_workspace_status(workspace: Workspace) -> WorkspaceStatus:
    """Get comprehensive status for a workspace.

    Combines task counts, progress metrics, and workspace metadata.

    Args:
        workspace: Target workspace

    Returns:
        WorkspaceStatus with all status information
    """
    task_counts = get_task_counts(workspace)
    progress = get_progress_metrics(workspace)

    return WorkspaceStatus(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        repo_path=str(workspace.repo_path),
        tech_stack=workspace.tech_stack,
        task_counts=task_counts,
        progress=progress,
        created_at=workspace.created_at,
    )


# ============================================================================
# Session Functions
# ============================================================================


def get_session_state(workspace: Workspace) -> SessionState:
    """Get current session state for a workspace.

    Loads session state from .codeframe/session_state.json.

    Args:
        workspace: Target workspace

    Returns:
        SessionState with session information
    """
    session_mgr = SessionManager(str(workspace.repo_path))
    session = session_mgr.load_session()

    if not session:
        return SessionState(
            has_session=False,
            last_session_summary="No previous session",
            last_session_timestamp=_utc_now().isoformat(),
            next_actions=[],
            progress_pct=0.0,
            active_blockers=[],
        )

    last_session = session.get("last_session", {})

    return SessionState(
        has_session=True,
        last_session_summary=last_session.get("summary", "No summary"),
        last_session_timestamp=last_session.get("timestamp", _utc_now().isoformat()),
        next_actions=session.get("next_actions", []),
        progress_pct=session.get("progress_pct", 0.0),
        active_blockers=session.get("active_blockers", []),
    )


def save_session_state(
    workspace: Workspace,
    summary: str,
    completed_tasks: Optional[list[str]] = None,
    next_actions: Optional[list[str]] = None,
    current_plan: Optional[str] = None,
    active_blockers: Optional[list[dict]] = None,
    progress_pct: float = 0.0,
) -> None:
    """Save session state for a workspace.

    Saves session state to .codeframe/session_state.json.

    Args:
        workspace: Target workspace
        summary: Summary of the session
        completed_tasks: List of completed task IDs
        next_actions: List of next action items
        current_plan: Current task/plan
        active_blockers: List of active blocker dicts
        progress_pct: Progress percentage
    """
    session_mgr = SessionManager(str(workspace.repo_path))

    state = {
        "summary": summary,
        "completed_tasks": completed_tasks or [],
        "next_actions": next_actions or [],
        "current_plan": current_plan,
        "active_blockers": active_blockers or [],
        "progress_pct": progress_pct,
    }

    session_mgr.save_session(state)


def clear_session_state(workspace: Workspace) -> None:
    """Clear session state for a workspace.

    Removes .codeframe/session_state.json.

    Args:
        workspace: Target workspace
    """
    session_mgr = SessionManager(str(workspace.repo_path))
    session_mgr.clear_session()
