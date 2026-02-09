"""Event logging for CodeFRAME v2.

Provides an append-only event log for workspace activity. Events are:
- Stored durably in SQLite
- Printed to stdout for CLI visibility
- Available for tailing/streaming

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from rich.console import Console

from codeframe.core.workspace import get_workspace, get_db_connection, Workspace


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

console = Console()


# Event type constants (for consistency)
class EventType:
    """Standard event types emitted by core modules."""

    # Workspace events
    WORKSPACE_INIT = "WORKSPACE_INIT"

    # PRD events
    PRD_ADDED = "PRD_ADDED"
    PRD_UPDATED = "PRD_UPDATED"
    PRD_DELETED = "PRD_DELETED"

    # Task events
    TASKS_GENERATED = "TASKS_GENERATED"
    TASK_STATUS_CHANGED = "TASK_STATUS_CHANGED"
    TASK_CREATED = "TASK_CREATED"
    TASK_UPDATED = "TASK_UPDATED"

    # Run/execution events
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"

    # Agent events
    AGENT_STEP_STARTED = "AGENT_STEP_STARTED"
    AGENT_STEP_COMPLETED = "AGENT_STEP_COMPLETED"

    # ReactAgent lifecycle events
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_FAILED = "AGENT_FAILED"
    AGENT_ITERATION_STARTED = "AGENT_ITERATION_STARTED"
    AGENT_ITERATION_COMPLETED = "AGENT_ITERATION_COMPLETED"
    AGENT_TOOL_DISPATCHED = "AGENT_TOOL_DISPATCHED"
    AGENT_TOOL_RESULT = "AGENT_TOOL_RESULT"

    # Blocker events
    BLOCKER_CREATED = "BLOCKER_CREATED"
    BLOCKER_ANSWERED = "BLOCKER_ANSWERED"
    BLOCKER_RESOLVED = "BLOCKER_RESOLVED"

    # Gate events
    GATES_STARTED = "GATES_STARTED"
    GATES_COMPLETED = "GATES_COMPLETED"

    # Artifact events
    PATCH_EXPORTED = "PATCH_EXPORTED"
    COMMIT_CREATED = "COMMIT_CREATED"
    FILES_MODIFIED = "FILES_MODIFIED"

    # Checkpoint events
    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    CHECKPOINT_RESTORED = "CHECKPOINT_RESTORED"

    # Status events
    STATUS_VIEWED = "STATUS_VIEWED"
    SUMMARY_VIEWED = "SUMMARY_VIEWED"

    # Batch execution events
    BATCH_STARTED = "BATCH_STARTED"
    BATCH_TASK_QUEUED = "BATCH_TASK_QUEUED"
    BATCH_TASK_STARTED = "BATCH_TASK_STARTED"
    BATCH_TASK_COMPLETED = "BATCH_TASK_COMPLETED"
    BATCH_TASK_FAILED = "BATCH_TASK_FAILED"
    BATCH_TASK_BLOCKED = "BATCH_TASK_BLOCKED"
    BATCH_COMPLETED = "BATCH_COMPLETED"
    BATCH_PARTIAL = "BATCH_PARTIAL"
    BATCH_FAILED = "BATCH_FAILED"
    BATCH_CANCELLED = "BATCH_CANCELLED"


@dataclass
class Event:
    """Represents a recorded event.

    Attributes:
        id: Auto-incremented event ID
        workspace_id: Workspace this event belongs to
        event_type: Type of event (see EventType)
        payload: JSON-serializable event data
        created_at: When the event occurred
    """

    id: int
    workspace_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


def emit(
    workspace_id: str,
    event_type: str,
    payload: Optional[dict[str, Any]] = None,
    *,
    repo_path: Optional[Path] = None,
    print_event: bool = True,
) -> Event:
    """Emit an event to the event log.

    Events are stored durably and optionally printed to console.

    Args:
        workspace_id: Workspace ID to emit event for
        event_type: Type of event (use EventType constants)
        payload: Optional event data (must be JSON-serializable)
        repo_path: Optional repo path (used to find workspace if not cached)
        print_event: Whether to print event to console (default True)

    Returns:
        The created Event object
    """
    payload = payload or {}
    now = _utc_now().isoformat()
    payload_json = json.dumps(payload)

    # Find workspace database
    # For now, we need the repo_path to find the DB. In future, we could cache this.
    if repo_path is None:
        # Try current directory
        repo_path = Path.cwd()

    workspace = get_workspace(repo_path)
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO events (workspace_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (workspace_id, event_type, payload_json, now),
        )
        event_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    event = Event(
        id=event_id,
        workspace_id=workspace_id,
        event_type=event_type,
        payload=payload,
        created_at=datetime.fromisoformat(now),
    )

    if print_event:
        _print_event(event)

    return event


def emit_for_workspace(
    workspace: Workspace,
    event_type: str,
    payload: Optional[dict[str, Any]] = None,
    *,
    print_event: bool = True,
) -> Event:
    """Emit an event using a Workspace object directly.

    Preferred when you already have a Workspace reference.

    Args:
        workspace: Workspace object
        event_type: Type of event
        payload: Optional event data
        print_event: Whether to print event to console

    Returns:
        The created Event object
    """
    payload = payload or {}
    now = _utc_now().isoformat()
    payload_json = json.dumps(payload)

    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO events (workspace_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (workspace.id, event_type, payload_json, now),
        )
        event_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    event = Event(
        id=event_id,
        workspace_id=workspace.id,
        event_type=event_type,
        payload=payload,
        created_at=datetime.fromisoformat(now),
    )

    if print_event:
        _print_event(event)

    return event


def list_recent(
    workspace: Workspace,
    limit: int = 20,
    since_id: Optional[int] = None,
) -> list[Event]:
    """List recent events for a workspace.

    Args:
        workspace: Workspace to query
        limit: Maximum number of events to return
        since_id: Only return events after this ID (for pagination)

    Returns:
        List of Event objects, newest first
    """
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()

        if since_id:
            cursor.execute(
                """
                SELECT id, workspace_id, event_type, payload, created_at
                FROM events
                WHERE workspace_id = ? AND id > ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (workspace.id, since_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT id, workspace_id, event_type, payload, created_at
                FROM events
                WHERE workspace_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (workspace.id, limit),
            )

        rows = cursor.fetchall()
    finally:
        conn.close()

    return [
        Event(
            id=row[0],
            workspace_id=row[1],
            event_type=row[2],
            payload=json.loads(row[3]) if row[3] else {},
            created_at=datetime.fromisoformat(row[4]),
        )
        for row in rows
    ]


def tail(
    workspace: Workspace,
    since_id: int = 0,
) -> Iterator[Event]:
    """Tail the event log, yielding new events.

    This is a generator that yields events as they appear.
    Note: This is a simple polling implementation. For real-time,
    consider using a file watcher or database triggers.

    Args:
        workspace: Workspace to tail
        since_id: Start after this event ID

    Yields:
        Event objects as they are recorded
    """
    import time

    last_id = since_id

    while True:
        events = list_recent(workspace, limit=50, since_id=last_id)

        # Events are returned newest-first, so reverse for chronological order
        for event in reversed(events):
            if event.id > last_id:
                last_id = event.id
                yield event

        time.sleep(0.5)  # Poll interval


def _print_event(event: Event) -> None:
    """Print an event to the console in a readable format."""
    timestamp = event.created_at.strftime("%H:%M:%S")
    type_color = _get_event_color(event.event_type)

    console.print(
        f"[dim]{timestamp}[/dim] [{type_color}]{event.event_type}[/{type_color}]",
        end="",
    )

    # Print key payload items if present
    if event.payload:
        items = []
        for key in ["path", "task_id", "status", "name", "title"]:
            if key in event.payload:
                items.append(f"{key}={event.payload[key]}")
        if items:
            console.print(f" [dim]{' '.join(items)}[/dim]")
        else:
            console.print()
    else:
        console.print()


def _get_event_color(event_type: str) -> str:
    """Get the Rich color for an event type."""
    if "ERROR" in event_type or "FAILED" in event_type:
        return "red"
    if "COMPLETED" in event_type or "CREATED" in event_type:
        return "green"
    if "STARTED" in event_type or "INIT" in event_type:
        return "blue"
    if "BLOCKED" in event_type or "BLOCKER" in event_type:
        return "yellow"
    return "cyan"
