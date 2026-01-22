"""Blocker management for CodeFRAME v2.

Blockers represent human-in-the-loop questions that pause task execution
until answered by a human.

This module is headless - no FastAPI or HTTP dependencies.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from codeframe.core.workspace import Workspace, get_db_connection
from codeframe.core import events, runtime, tasks
from codeframe.core.state_machine import TaskStatus


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class BlockerStatus(str, Enum):
    """Status of a blocker."""

    OPEN = "OPEN"
    ANSWERED = "ANSWERED"
    RESOLVED = "RESOLVED"


@dataclass
class Blocker:
    """Represents a blocker (human-in-the-loop question).

    Attributes:
        id: Unique blocker identifier (UUID)
        workspace_id: Workspace this blocker belongs to
        task_id: Optional task this blocker is associated with
        question: The question being asked
        answer: The answer provided (if answered)
        status: Current blocker status
        created_at: When the blocker was created
        answered_at: When the blocker was answered (if answered)
    """

    id: str
    workspace_id: str
    task_id: Optional[str]
    question: str
    answer: Optional[str]
    status: BlockerStatus
    created_at: datetime
    answered_at: Optional[datetime]


def create(
    workspace: Workspace,
    question: str,
    task_id: Optional[str] = None,
) -> Blocker:
    """Create a new blocker.

    Args:
        workspace: Target workspace
        question: The question to ask
        task_id: Optional associated task ID

    Returns:
        Created Blocker
    """
    blocker_id = str(uuid.uuid4())
    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO blockers (id, workspace_id, task_id, question, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (blocker_id, workspace.id, task_id, question, BlockerStatus.OPEN.value, now),
    )
    conn.commit()
    conn.close()

    blocker = Blocker(
        id=blocker_id,
        workspace_id=workspace.id,
        task_id=task_id,
        question=question,
        answer=None,
        status=BlockerStatus.OPEN,
        created_at=datetime.fromisoformat(now),
        answered_at=None,
    )

    # Emit blocker created event
    events.emit_for_workspace(
        workspace,
        events.EventType.BLOCKER_CREATED,
        {"blocker_id": blocker_id, "task_id": task_id, "question": question[:100]},
        print_event=True,
    )

    return blocker


def get(workspace: Workspace, blocker_id: str) -> Optional[Blocker]:
    """Get a blocker by ID.

    Supports partial ID matching.

    Args:
        workspace: Workspace to query
        blocker_id: Blocker identifier (can be partial)

    Returns:
        Blocker if found, None otherwise
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    # Try exact match first
    cursor.execute(
        """
        SELECT id, workspace_id, task_id, question, answer, status, created_at, answered_at
        FROM blockers
        WHERE workspace_id = ? AND id = ?
        """,
        (workspace.id, blocker_id),
    )
    row = cursor.fetchone()

    # If no exact match, try prefix match
    if not row:
        cursor.execute(
            """
            SELECT id, workspace_id, task_id, question, answer, status, created_at, answered_at
            FROM blockers
            WHERE workspace_id = ? AND id LIKE ?
            """,
            (workspace.id, f"{blocker_id}%"),
        )
        rows = cursor.fetchall()
        if len(rows) == 1:
            row = rows[0]
        elif len(rows) > 1:
            conn.close()
            raise ValueError(f"Multiple blockers match '{blocker_id}'")

    conn.close()

    if not row:
        return None

    return _row_to_blocker(row)


def list_open(workspace: Workspace) -> list[Blocker]:
    """List open blockers.

    Args:
        workspace: Workspace to query

    Returns:
        List of open Blockers, oldest first
    """
    return list_all(workspace, status=BlockerStatus.OPEN)


def list_all(
    workspace: Workspace,
    status: Optional[BlockerStatus] = None,
    task_id: Optional[str] = None,
    limit: int = 100,
) -> list[Blocker]:
    """List blockers with optional filters.

    Args:
        workspace: Workspace to query
        status: Optional status filter
        task_id: Optional task filter
        limit: Maximum blockers to return

    Returns:
        List of Blockers, oldest first
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    query = """
        SELECT id, workspace_id, task_id, question, answer, status, created_at, answered_at
        FROM blockers
        WHERE workspace_id = ?
    """
    params: list = [workspace.id]

    if status:
        query += " AND status = ?"
        params.append(status.value)

    if task_id:
        query += " AND task_id = ?"
        params.append(task_id)

    query += " ORDER BY created_at ASC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [_row_to_blocker(row) for row in rows]


def list_for_task(workspace: Workspace, task_id: str) -> list[Blocker]:
    """List all blockers for a specific task.

    Args:
        workspace: Workspace to query
        task_id: Task to filter by

    Returns:
        List of Blockers for the task
    """
    return list_all(workspace, task_id=task_id)


def answer(workspace: Workspace, blocker_id: str, text: str) -> Blocker:
    """Answer a blocker.

    Args:
        workspace: Target workspace
        blocker_id: Blocker to answer (can be partial ID)
        text: Answer text

    Returns:
        Updated Blocker

    Raises:
        ValueError: If blocker not found or already resolved
    """
    blocker = get(workspace, blocker_id)
    if not blocker:
        raise ValueError(f"Blocker not found: {blocker_id}")

    if blocker.status == BlockerStatus.RESOLVED:
        raise ValueError(f"Blocker already resolved: {blocker_id}")

    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE blockers
        SET answer = ?, status = ?, answered_at = ?
        WHERE id = ?
        """,
        (text, BlockerStatus.ANSWERED.value, now, blocker.id),
    )
    conn.commit()
    conn.close()

    # Emit blocker answered event
    events.emit_for_workspace(
        workspace,
        events.EventType.BLOCKER_ANSWERED,
        {"blocker_id": blocker.id, "task_id": blocker.task_id},
        print_event=True,
    )

    blocker.answer = text
    blocker.status = BlockerStatus.ANSWERED
    blocker.answered_at = datetime.fromisoformat(now)

    # Automatically reset the associated task to READY so it can be restarted
    # This eliminates the need for separate "work stop" and "work resume" commands
    if blocker.task_id:
        try:
            # Stop the blocked run (marks it as FAILED)
            active_run = runtime.get_active_run(workspace, blocker.task_id)
            if active_run and active_run.status == runtime.RunStatus.BLOCKED:
                runtime.stop_run(workspace, blocker.task_id)
            # Task is now READY and can be restarted with `cf work start <id> --execute`
        except ValueError:
            # No active run found, just ensure task is READY
            task = tasks.get(workspace, blocker.task_id)
            if task and task.status == TaskStatus.BLOCKED:
                tasks.update_status(workspace, blocker.task_id, TaskStatus.READY)

    return blocker


def resolve(workspace: Workspace, blocker_id: str) -> Blocker:
    """Mark a blocker as resolved.

    Args:
        workspace: Target workspace
        blocker_id: Blocker to resolve (can be partial ID)

    Returns:
        Updated Blocker

    Raises:
        ValueError: If blocker not found or not answered
    """
    blocker = get(workspace, blocker_id)
    if not blocker:
        raise ValueError(f"Blocker not found: {blocker_id}")

    if blocker.status == BlockerStatus.OPEN:
        raise ValueError(f"Blocker must be answered before resolving: {blocker_id}")

    if blocker.status == BlockerStatus.RESOLVED:
        raise ValueError(f"Blocker already resolved: {blocker_id}")

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE blockers
        SET status = ?
        WHERE id = ?
        """,
        (BlockerStatus.RESOLVED.value, blocker.id),
    )
    conn.commit()
    conn.close()

    # Emit blocker resolved event
    events.emit_for_workspace(
        workspace,
        events.EventType.BLOCKER_RESOLVED,
        {"blocker_id": blocker.id, "task_id": blocker.task_id},
        print_event=True,
    )

    blocker.status = BlockerStatus.RESOLVED
    return blocker


def count_by_status(workspace: Workspace) -> dict[str, int]:
    """Count blockers by status.

    Args:
        workspace: Workspace to query

    Returns:
        Dict mapping status string to count
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT status, COUNT(*) as count
        FROM blockers
        WHERE workspace_id = ?
        GROUP BY status
        """,
        (workspace.id,),
    )
    rows = cursor.fetchall()
    conn.close()

    return {row[0]: row[1] for row in rows}


def _row_to_blocker(row: tuple) -> Blocker:
    """Convert a database row to a Blocker object."""
    return Blocker(
        id=row[0],
        workspace_id=row[1],
        task_id=row[2],
        question=row[3],
        answer=row[4],
        status=BlockerStatus(row[5]),
        created_at=datetime.fromisoformat(row[6]),
        answered_at=datetime.fromisoformat(row[7]) if row[7] else None,
    )
