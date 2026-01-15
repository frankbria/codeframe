"""Batch execution conductor for CodeFRAME v2.

Orchestrates execution of multiple tasks, managing parallelization
and coordinating results.

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import os
import signal
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from codeframe.core.workspace import Workspace, get_db_connection
from codeframe.core import events, tasks
from codeframe.core.runtime import RunStatus, get_active_run, get_run


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class BatchStatus(str, Enum):
    """Status of a batch execution."""

    PENDING = "PENDING"       # Created but not started
    RUNNING = "RUNNING"       # Tasks being processed
    COMPLETED = "COMPLETED"   # All tasks finished successfully
    PARTIAL = "PARTIAL"       # Some tasks completed, some failed/blocked
    FAILED = "FAILED"         # Critical failure
    CANCELLED = "CANCELLED"   # User cancelled


class OnFailure(str, Enum):
    """Behavior when a task fails."""

    CONTINUE = "continue"  # Continue with remaining tasks
    STOP = "stop"          # Stop batch on first failure


@dataclass
class BatchRun:
    """Represents a batch execution run.

    Attributes:
        id: Unique batch identifier (UUID)
        workspace_id: Workspace this batch belongs to
        task_ids: Ordered list of task IDs to execute
        status: Current batch status
        strategy: Execution strategy (serial, parallel)
        max_parallel: Max concurrent tasks (for parallel strategy)
        on_failure: Behavior on task failure
        started_at: When the batch started
        completed_at: When the batch finished (if finished)
        results: Dict mapping task_id -> RunStatus value
    """

    id: str
    workspace_id: str
    task_ids: list[str]
    status: BatchStatus
    strategy: str
    max_parallel: int
    on_failure: OnFailure
    started_at: datetime
    completed_at: Optional[datetime]
    results: dict[str, str] = field(default_factory=dict)


def start_batch(
    workspace: Workspace,
    task_ids: list[str],
    strategy: str = "serial",
    max_parallel: int = 4,
    on_failure: str = "continue",
    dry_run: bool = False,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> BatchRun:
    """Start a batch execution of multiple tasks.

    Args:
        workspace: Target workspace
        task_ids: List of task IDs to execute (in order)
        strategy: Execution strategy ("serial" or "parallel")
        max_parallel: Max concurrent tasks for parallel strategy
        on_failure: Behavior on task failure ("continue" or "stop")
        dry_run: If True, don't actually execute tasks
        on_event: Optional callback for batch events

    Returns:
        BatchRun with results populated

    Raises:
        ValueError: If task_ids is empty or contains invalid IDs
    """
    if not task_ids:
        raise ValueError("task_ids cannot be empty")

    # Validate all task IDs exist
    for task_id in task_ids:
        task = tasks.get(workspace, task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

    # Create batch record
    batch_id = str(uuid.uuid4())
    now = _utc_now()
    on_failure_enum = OnFailure(on_failure)

    batch = BatchRun(
        id=batch_id,
        workspace_id=workspace.id,
        task_ids=task_ids,
        status=BatchStatus.PENDING,
        strategy=strategy,
        max_parallel=max_parallel,
        on_failure=on_failure_enum,
        started_at=now,
        completed_at=None,
        results={},
    )

    # Save to database
    _save_batch(workspace, batch)

    # Emit batch started event
    events.emit_for_workspace(
        workspace,
        events.EventType.BATCH_STARTED,
        {
            "batch_id": batch_id,
            "task_ids": task_ids,
            "strategy": strategy,
            "task_count": len(task_ids),
        },
        print_event=True,
    )

    if on_event:
        on_event("batch_started", {"batch_id": batch_id, "task_count": len(task_ids)})

    if dry_run:
        batch.status = BatchStatus.COMPLETED
        batch.completed_at = _utc_now()
        _save_batch(workspace, batch)
        return batch

    # Update status to running
    batch.status = BatchStatus.RUNNING
    _save_batch(workspace, batch)

    # Execute based on strategy
    # Phase 1: Only serial execution is implemented
    # Phase 2 will add parallel execution
    if strategy == "parallel" and max_parallel > 1:
        # For now, fall back to serial with a warning
        print(f"Warning: Parallel execution not yet implemented, using serial")

    _execute_serial(workspace, batch, on_event)

    return batch


def get_batch(workspace: Workspace, batch_id: str) -> Optional[BatchRun]:
    """Get a batch by ID.

    Args:
        workspace: Workspace to query
        batch_id: Batch identifier

    Returns:
        BatchRun if found, None otherwise
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, workspace_id, task_ids, status, strategy, max_parallel,
               on_failure, started_at, completed_at, results
        FROM batch_runs
        WHERE workspace_id = ? AND id = ?
        """,
        (workspace.id, batch_id),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return _row_to_batch(row)


def list_batches(
    workspace: Workspace,
    status: Optional[BatchStatus] = None,
    limit: int = 20,
) -> list[BatchRun]:
    """List batches in a workspace.

    Args:
        workspace: Workspace to query
        status: Optional status filter
        limit: Maximum batches to return

    Returns:
        List of BatchRuns, newest first
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    if status:
        cursor.execute(
            """
            SELECT id, workspace_id, task_ids, status, strategy, max_parallel,
                   on_failure, started_at, completed_at, results
            FROM batch_runs
            WHERE workspace_id = ? AND status = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (workspace.id, status.value, limit),
        )
    else:
        cursor.execute(
            """
            SELECT id, workspace_id, task_ids, status, strategy, max_parallel,
                   on_failure, started_at, completed_at, results
            FROM batch_runs
            WHERE workspace_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (workspace.id, limit),
        )

    rows = cursor.fetchall()
    conn.close()

    return [_row_to_batch(row) for row in rows]


def cancel_batch(workspace: Workspace, batch_id: str) -> BatchRun:
    """Cancel a running batch.

    Sends SIGTERM to any running subprocesses and marks the batch as cancelled.

    Args:
        workspace: Target workspace
        batch_id: Batch to cancel

    Returns:
        Updated BatchRun

    Raises:
        ValueError: If batch not found or not in a cancellable state
    """
    batch = get_batch(workspace, batch_id)
    if not batch:
        raise ValueError(f"Batch not found: {batch_id}")

    if batch.status not in (BatchStatus.PENDING, BatchStatus.RUNNING):
        raise ValueError(f"Batch cannot be cancelled: {batch.status}")

    # Update status
    batch.status = BatchStatus.CANCELLED
    batch.completed_at = _utc_now()
    _save_batch(workspace, batch)

    # Emit event
    events.emit_for_workspace(
        workspace,
        events.EventType.BATCH_CANCELLED,
        {"batch_id": batch_id},
        print_event=True,
    )

    return batch


def _execute_serial(
    workspace: Workspace,
    batch: BatchRun,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> None:
    """Execute tasks serially (one at a time).

    Updates batch.results and batch.status as tasks complete.
    """
    completed_count = 0
    failed_count = 0
    blocked_count = 0

    for i, task_id in enumerate(batch.task_ids):
        # Check if batch was cancelled
        current_batch = get_batch(workspace, batch.id)
        if current_batch and current_batch.status == BatchStatus.CANCELLED:
            break

        # Emit task queued event
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_TASK_QUEUED,
            {"batch_id": batch.id, "task_id": task_id, "position": i + 1},
            print_event=True,
        )

        # Get task info for display
        task = tasks.get(workspace, task_id)
        task_title = task.title if task else task_id

        print(f"\n[{i + 1}/{len(batch.task_ids)}] Starting task {task_id}: {task_title}")

        # Emit task started event
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_TASK_STARTED,
            {"batch_id": batch.id, "task_id": task_id},
            print_event=True,
        )

        if on_event:
            on_event("batch_task_started", {"task_id": task_id, "position": i + 1})

        # Execute task via subprocess
        result_status = _execute_task_subprocess(workspace, task_id)

        # Record result
        batch.results[task_id] = result_status
        _save_batch(workspace, batch)

        # Emit appropriate event based on result
        if result_status == RunStatus.COMPLETED.value:
            completed_count += 1
            events.emit_for_workspace(
                workspace,
                events.EventType.BATCH_TASK_COMPLETED,
                {"batch_id": batch.id, "task_id": task_id},
                print_event=True,
            )
            print(f"      ✓ Completed")
        elif result_status == RunStatus.BLOCKED.value:
            blocked_count += 1
            events.emit_for_workspace(
                workspace,
                events.EventType.BATCH_TASK_BLOCKED,
                {"batch_id": batch.id, "task_id": task_id},
                print_event=True,
            )
            print(f"      ⊘ Blocked")
        else:
            failed_count += 1
            events.emit_for_workspace(
                workspace,
                events.EventType.BATCH_TASK_FAILED,
                {"batch_id": batch.id, "task_id": task_id, "status": result_status},
                print_event=True,
            )
            print(f"      ✗ Failed: {result_status}")

            # Check on_failure behavior
            if batch.on_failure == OnFailure.STOP:
                print(f"\nStopping batch due to --on-failure=stop")
                break

        if on_event:
            on_event("batch_task_completed", {"task_id": task_id, "status": result_status})

    # Determine final batch status
    total = len(batch.task_ids)
    executed = completed_count + failed_count + blocked_count

    if completed_count == total:
        batch.status = BatchStatus.COMPLETED
        event_type = events.EventType.BATCH_COMPLETED
    elif completed_count == 0 and (failed_count > 0 or blocked_count > 0):
        batch.status = BatchStatus.FAILED
        event_type = events.EventType.BATCH_FAILED
    elif completed_count > 0:
        batch.status = BatchStatus.PARTIAL
        event_type = events.EventType.BATCH_PARTIAL
    else:
        # Nothing executed (e.g., cancelled before start)
        batch.status = BatchStatus.CANCELLED
        event_type = events.EventType.BATCH_CANCELLED

    batch.completed_at = _utc_now()
    _save_batch(workspace, batch)

    # Emit batch completion event
    events.emit_for_workspace(
        workspace,
        event_type,
        {
            "batch_id": batch.id,
            "completed": completed_count,
            "failed": failed_count,
            "blocked": blocked_count,
            "total": total,
        },
        print_event=True,
    )

    # Print summary
    print(f"\nBatch {batch.status.value.lower()}: {completed_count}/{total} tasks completed")
    if failed_count > 0:
        print(f"  Failed: {failed_count}")
    if blocked_count > 0:
        print(f"  Blocked: {blocked_count}")


def _execute_task_subprocess(workspace: Workspace, task_id: str) -> str:
    """Execute a single task via subprocess.

    Runs `cf work start <task_id> --execute` as a subprocess.

    Args:
        workspace: Target workspace
        task_id: Task to execute

    Returns:
        RunStatus value string (COMPLETED, FAILED, BLOCKED)
    """
    # Build command
    cmd = [
        sys.executable, "-m", "codeframe.cli.app",
        "work", "start", task_id, "--execute"
    ]

    try:
        # Run subprocess
        result = subprocess.run(
            cmd,
            cwd=workspace.repo_path,
            capture_output=False,  # Let output flow to terminal
            text=True,
        )

        # Check the run status from database
        # The subprocess should have updated the run record
        run = get_active_run(workspace, task_id)
        if run:
            return run.status.value

        # If no active run, check if there's a recent completed/failed run
        # by listing runs for this task
        from codeframe.core.runtime import list_runs
        runs = list_runs(workspace, task_id=task_id, limit=1)
        if runs:
            return runs[0].status.value

        # Fallback based on subprocess exit code
        if result.returncode == 0:
            return RunStatus.COMPLETED.value
        else:
            return RunStatus.FAILED.value

    except Exception as e:
        print(f"      Error executing task: {e}")
        return RunStatus.FAILED.value


def _save_batch(workspace: Workspace, batch: BatchRun) -> None:
    """Save or update a batch record in the database."""
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    task_ids_json = json.dumps(batch.task_ids)
    results_json = json.dumps(batch.results) if batch.results else None
    completed_at = batch.completed_at.isoformat() if batch.completed_at else None

    cursor.execute(
        """
        INSERT OR REPLACE INTO batch_runs
        (id, workspace_id, task_ids, status, strategy, max_parallel, on_failure,
         started_at, completed_at, results)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch.id,
            batch.workspace_id,
            task_ids_json,
            batch.status.value,
            batch.strategy,
            batch.max_parallel,
            batch.on_failure.value,
            batch.started_at.isoformat(),
            completed_at,
            results_json,
        ),
    )
    conn.commit()
    conn.close()


def _row_to_batch(row: tuple) -> BatchRun:
    """Convert a database row to a BatchRun object."""
    return BatchRun(
        id=row[0],
        workspace_id=row[1],
        task_ids=json.loads(row[2]),
        status=BatchStatus(row[3]),
        strategy=row[4],
        max_parallel=row[5],
        on_failure=OnFailure(row[6]),
        started_at=datetime.fromisoformat(row[7]),
        completed_at=datetime.fromisoformat(row[8]) if row[8] else None,
        results=json.loads(row[9]) if row[9] else {},
    )
