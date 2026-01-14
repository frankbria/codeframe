"""Task state machine for CodeFRAME v2.

Defines the authoritative task statuses and allowed transitions.
Per GOLDEN_PATH.md, the CLI is the authority for transitions.

Statuses:
- BACKLOG: Task identified but not ready to work on
- READY: Task is ready to be started
- IN_PROGRESS: Task is actively being worked on
- BLOCKED: Task is blocked by a blocker (human-in-the-loop)
- DONE: Task completed successfully
- MERGED: Task changes merged (optional, for later)

This module is headless - no FastAPI or HTTP dependencies.
"""

from enum import Enum
from typing import Set


class TaskStatus(str, Enum):
    """Task execution status.

    Uses str mixin for easy JSON serialization and SQLite storage.
    """

    BACKLOG = "BACKLOG"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    MERGED = "MERGED"


# Allowed status transitions (from -> set of allowed targets)
ALLOWED_TRANSITIONS: dict[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.READY},
    TaskStatus.READY: {TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG},
    TaskStatus.IN_PROGRESS: {TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.READY},
    TaskStatus.BLOCKED: {TaskStatus.IN_PROGRESS, TaskStatus.READY},
    TaskStatus.DONE: {TaskStatus.READY, TaskStatus.MERGED},
    TaskStatus.MERGED: set(),  # Terminal state
}


class InvalidTransitionError(Exception):
    """Raised when an invalid status transition is attempted."""

    def __init__(self, current: TaskStatus, target: TaskStatus):
        self.current = current
        self.target = target
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        allowed_str = ", ".join(s.value for s in allowed) if allowed else "none"
        super().__init__(
            f"Invalid transition: {current.value} -> {target.value}. "
            f"Allowed transitions from {current.value}: {allowed_str}"
        )


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    """Check if a status transition is allowed.

    Args:
        current: Current task status
        target: Desired target status

    Returns:
        True if transition is allowed, False otherwise
    """
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    return target in allowed


def validate_transition(current: TaskStatus, target: TaskStatus) -> None:
    """Validate a status transition, raising if invalid.

    Args:
        current: Current task status
        target: Desired target status

    Raises:
        InvalidTransitionError: If the transition is not allowed
    """
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)


def get_allowed_transitions(current: TaskStatus) -> Set[TaskStatus]:
    """Get the set of statuses that can be transitioned to from current.

    Args:
        current: Current task status

    Returns:
        Set of allowed target statuses
    """
    return ALLOWED_TRANSITIONS.get(current, set()).copy()


def parse_status(value: str) -> TaskStatus:
    """Parse a string into a TaskStatus.

    Accepts both uppercase and lowercase input.

    Args:
        value: Status string (e.g., "READY", "ready", "in_progress")

    Returns:
        TaskStatus enum value

    Raises:
        ValueError: If the string doesn't match any status
    """
    normalized = value.upper().replace("-", "_")
    try:
        return TaskStatus(normalized)
    except ValueError:
        valid = ", ".join(s.value for s in TaskStatus)
        raise ValueError(f"Invalid status '{value}'. Valid statuses: {valid}")
