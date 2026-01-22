"""Checkpoint management for CodeFRAME v2.

Checkpoints are snapshots of workspace state that can be restored later.
They capture tasks, blockers, and optionally git refs.

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from codeframe.core.workspace import Workspace, get_db_connection
from codeframe.core import events, tasks, blockers, prd


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@dataclass
class Checkpoint:
    """Represents a state checkpoint.

    Attributes:
        id: Unique checkpoint identifier (UUID)
        workspace_id: Workspace this checkpoint belongs to
        name: Human-readable checkpoint name
        snapshot: JSON snapshot of state
        created_at: When the checkpoint was created
    """

    id: str
    workspace_id: str
    name: str
    snapshot: dict
    created_at: datetime


def create(
    workspace: Workspace,
    name: str,
    include_git_ref: bool = True,
) -> Checkpoint:
    """Create a new checkpoint.

    Captures current state of tasks, blockers, PRD, and optionally git ref.

    Args:
        workspace: Target workspace
        name: Checkpoint name
        include_git_ref: Whether to capture current git HEAD

    Returns:
        Created Checkpoint
    """
    checkpoint_id = str(uuid.uuid4())
    now = _utc_now().isoformat()

    # Build snapshot
    snapshot = _build_snapshot(workspace, include_git_ref)
    snapshot_json = json.dumps(snapshot)

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO checkpoints (id, workspace_id, name, snapshot, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (checkpoint_id, workspace.id, name, snapshot_json, now),
    )
    conn.commit()
    conn.close()

    checkpoint = Checkpoint(
        id=checkpoint_id,
        workspace_id=workspace.id,
        name=name,
        snapshot=snapshot,
        created_at=datetime.fromisoformat(now),
    )

    # Emit event
    events.emit_for_workspace(
        workspace,
        events.EventType.CHECKPOINT_CREATED,
        {
            "checkpoint_id": checkpoint_id,
            "name": name,
            "tasks_count": len(snapshot.get("tasks", [])),
        },
        print_event=True,
    )

    return checkpoint


def get(workspace: Workspace, checkpoint_id: str) -> Optional[Checkpoint]:
    """Get a checkpoint by ID or name.

    Args:
        workspace: Workspace to query
        checkpoint_id: Checkpoint ID or name

    Returns:
        Checkpoint if found, None otherwise
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    # Try exact ID match
    cursor.execute(
        """
        SELECT id, workspace_id, name, snapshot, created_at
        FROM checkpoints
        WHERE workspace_id = ? AND (id = ? OR name = ?)
        """,
        (workspace.id, checkpoint_id, checkpoint_id),
    )
    row = cursor.fetchone()

    # Try prefix match if no exact match
    if not row:
        cursor.execute(
            """
            SELECT id, workspace_id, name, snapshot, created_at
            FROM checkpoints
            WHERE workspace_id = ? AND id LIKE ?
            """,
            (workspace.id, f"{checkpoint_id}%"),
        )
        rows = cursor.fetchall()
        if len(rows) == 1:
            row = rows[0]

    conn.close()

    if not row:
        return None

    return _row_to_checkpoint(row)


def list_all(workspace: Workspace, limit: int = 50) -> list[Checkpoint]:
    """List all checkpoints.

    Args:
        workspace: Workspace to query
        limit: Maximum checkpoints to return

    Returns:
        List of Checkpoints, newest first
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, workspace_id, name, snapshot, created_at
        FROM checkpoints
        WHERE workspace_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (workspace.id, limit),
    )
    rows = cursor.fetchall()
    conn.close()

    return [_row_to_checkpoint(row) for row in rows]


def restore(workspace: Workspace, checkpoint_id: str) -> Checkpoint:
    """Restore state from a checkpoint.

    Restores task statuses from the checkpoint. Does not modify files.

    Args:
        workspace: Target workspace
        checkpoint_id: Checkpoint ID or name

    Returns:
        Restored Checkpoint

    Raises:
        ValueError: If checkpoint not found
    """
    checkpoint = get(workspace, checkpoint_id)
    if not checkpoint:
        raise ValueError(f"Checkpoint not found: {checkpoint_id}")

    snapshot = checkpoint.snapshot

    # Restore task statuses
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    for task_data in snapshot.get("tasks", []):
        cursor.execute(
            """
            UPDATE tasks
            SET status = ?, updated_at = ?
            WHERE id = ? AND workspace_id = ?
            """,
            (task_data["status"], _utc_now().isoformat(), task_data["id"], workspace.id),
        )

    conn.commit()
    conn.close()

    # Emit event
    events.emit_for_workspace(
        workspace,
        events.EventType.CHECKPOINT_RESTORED,
        {
            "checkpoint_id": checkpoint.id,
            "name": checkpoint.name,
        },
        print_event=True,
    )

    return checkpoint


def delete(workspace: Workspace, checkpoint_id: str) -> bool:
    """Delete a checkpoint.

    Args:
        workspace: Target workspace
        checkpoint_id: Checkpoint ID or name

    Returns:
        True if deleted, False if not found
    """
    checkpoint = get(workspace, checkpoint_id)
    if not checkpoint:
        return False

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM checkpoints WHERE id = ?",
        (checkpoint.id,),
    )
    conn.commit()
    conn.close()

    return True


def _build_snapshot(workspace: Workspace, include_git_ref: bool = True) -> dict:
    """Build a snapshot of current state."""
    snapshot = {
        "version": 1,
        "created_at": _utc_now().isoformat(),
    }

    # Capture tasks
    all_tasks = tasks.list_tasks(workspace, limit=1000)
    snapshot["tasks"] = [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status.value,
            "priority": t.priority,
            "prd_id": t.prd_id,
        }
        for t in all_tasks
    ]

    # Capture blockers
    all_blockers = blockers.list_all(workspace, limit=1000)
    snapshot["blockers"] = [
        {
            "id": b.id,
            "question": b.question,
            "answer": b.answer,
            "status": b.status.value,
            "task_id": b.task_id,
        }
        for b in all_blockers
    ]

    # Capture latest PRD reference
    latest_prd = prd.get_latest(workspace)
    if latest_prd:
        snapshot["prd"] = {
            "id": latest_prd.id,
            "title": latest_prd.title,
        }

    # Capture git ref
    if include_git_ref:
        git_ref = _get_git_head(workspace.repo_path)
        if git_ref:
            snapshot["git_ref"] = git_ref

    # Task counts summary
    counts = tasks.count_by_status(workspace)
    snapshot["summary"] = {
        "total_tasks": len(all_tasks),
        "tasks_by_status": counts,
        "open_blockers": sum(1 for b in all_blockers if b.status.value == "OPEN"),
    }

    return snapshot


def _get_git_head(repo_path: Path) -> Optional[str]:
    """Get current git HEAD reference."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5,  # Prevent hanging on slow/unresponsive git
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except subprocess.TimeoutExpired:
        # Git command took too long, return None gracefully
        return None
    except Exception:
        pass
    return None


def _row_to_checkpoint(row: tuple) -> Checkpoint:
    """Convert a database row to a Checkpoint object."""
    return Checkpoint(
        id=row[0],
        workspace_id=row[1],
        name=row[2],
        snapshot=json.loads(row[3]) if row[3] else {},
        created_at=datetime.fromisoformat(row[4]),
    )
