"""Runtime/orchestration for CodeFRAME v2.

Manages task execution runs and the agent loop.

This module is headless - no FastAPI or HTTP dependencies.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from codeframe.core.workspace import Workspace, get_db_connection

from codeframe.core.state_machine import TaskStatus
from codeframe.core import tasks, events

if TYPE_CHECKING:
    from codeframe.core.agent import AgentState


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    """Status of a task execution run."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass
class Run:
    """Represents a task execution run.

    Attributes:
        id: Unique run identifier (UUID)
        workspace_id: Workspace this run belongs to
        task_id: Task being executed
        status: Current run status
        started_at: When the run started
        completed_at: When the run finished (if finished)
    """

    id: str
    workspace_id: str
    task_id: str
    status: RunStatus
    started_at: datetime
    completed_at: Optional[datetime]


def start_task_run(workspace: Workspace, task_id: str) -> Run:
    """Start a new run for a task.

    Transitions the task to IN_PROGRESS and creates a run record.

    Args:
        workspace: Target workspace
        task_id: Task to run

    Returns:
        Created Run

    Raises:
        ValueError: If task not found
        InvalidTransitionError: If task can't transition to IN_PROGRESS
    """
    # Get the task
    task = tasks.get(workspace, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    # Check if there's already an active run
    active = get_active_run(workspace, task_id)
    if active:
        raise ValueError(f"Task already has an active run: {active.id}")

    # Transition task to IN_PROGRESS (validates the transition)
    # If task is in BACKLOG, we need to go through READY first
    if task.status == TaskStatus.BACKLOG:
        tasks.update_status(workspace, task_id, TaskStatus.READY)

    if task.status != TaskStatus.IN_PROGRESS:
        tasks.update_status(workspace, task_id, TaskStatus.IN_PROGRESS)

    # Create run record
    run_id = str(uuid.uuid4())
    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO runs (id, workspace_id, task_id, status, started_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, workspace.id, task_id, RunStatus.RUNNING.value, now),
    )
    conn.commit()
    conn.close()

    run = Run(
        id=run_id,
        workspace_id=workspace.id,
        task_id=task_id,
        status=RunStatus.RUNNING,
        started_at=datetime.fromisoformat(now),
        completed_at=None,
    )

    # Emit run started event
    events.emit_for_workspace(
        workspace,
        events.EventType.RUN_STARTED,
        {"run_id": run_id, "task_id": task_id},
        print_event=True,
    )

    return run


def get_run(workspace: Workspace, run_id: str) -> Optional[Run]:
    """Get a run by ID.

    Args:
        workspace: Workspace to query
        run_id: Run identifier

    Returns:
        Run if found, None otherwise
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, workspace_id, task_id, status, started_at, completed_at
        FROM runs
        WHERE workspace_id = ? AND id = ?
        """,
        (workspace.id, run_id),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return _row_to_run(row)


def get_active_run(workspace: Workspace, task_id: str) -> Optional[Run]:
    """Get the active (RUNNING or BLOCKED) run for a task.

    Args:
        workspace: Workspace to query
        task_id: Task identifier

    Returns:
        Run if found, None otherwise
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, workspace_id, task_id, status, started_at, completed_at
        FROM runs
        WHERE workspace_id = ? AND task_id = ? AND status IN ('RUNNING', 'BLOCKED')
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (workspace.id, task_id),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return _row_to_run(row)


def reset_blocked_run(workspace: Workspace, task_id: str) -> bool:
    """Reset a blocked run so the task can be re-executed.

    Marks the blocked run as FAILED and resets the task status to READY.
    This allows the task to be started fresh with a new run.

    Args:
        workspace: Target workspace
        task_id: Task to reset

    Returns:
        True if a blocked run was reset, False if no blocked run existed
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    # Find and update blocked run
    cursor.execute(
        """
        UPDATE runs
        SET status = ?, completed_at = ?
        WHERE workspace_id = ? AND task_id = ? AND status = ?
        """,
        (
            RunStatus.FAILED.value,
            _utc_now().isoformat(),
            workspace.id,
            task_id,
            RunStatus.BLOCKED.value,
        ),
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()

    if updated:
        # Reset task status to READY
        task = tasks.get(workspace, task_id)
        if task and task.status == TaskStatus.BLOCKED:
            tasks.update_status(workspace, task_id, TaskStatus.READY)

    return updated


def list_runs(
    workspace: Workspace,
    task_id: Optional[str] = None,
    status: Optional[RunStatus] = None,
    limit: int = 20,
) -> list[Run]:
    """List runs in a workspace.

    Args:
        workspace: Workspace to query
        task_id: Optional task filter
        status: Optional status filter
        limit: Maximum runs to return

    Returns:
        List of Runs, newest first
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    query = """
        SELECT id, workspace_id, task_id, status, started_at, completed_at
        FROM runs
        WHERE workspace_id = ?
    """
    params: list = [workspace.id]

    if task_id:
        query += " AND task_id = ?"
        params.append(task_id)

    if status:
        query += " AND status = ?"
        params.append(status.value)

    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [_row_to_run(row) for row in rows]


def complete_run(workspace: Workspace, run_id: str) -> Run:
    """Mark a run as completed.

    Also transitions the task to DONE.

    Args:
        workspace: Target workspace
        run_id: Run to complete

    Returns:
        Updated Run

    Raises:
        ValueError: If run not found or not in RUNNING status
    """
    run = get_run(workspace, run_id)
    if not run:
        raise ValueError(f"Run not found: {run_id}")

    if run.status != RunStatus.RUNNING:
        raise ValueError(f"Run is not running: {run.status}")

    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE runs
        SET status = ?, completed_at = ?
        WHERE id = ?
        """,
        (RunStatus.COMPLETED.value, now, run_id),
    )
    conn.commit()
    conn.close()

    # Transition task to DONE
    tasks.update_status(workspace, run.task_id, TaskStatus.DONE)

    # Emit run completed event
    events.emit_for_workspace(
        workspace,
        events.EventType.RUN_COMPLETED,
        {"run_id": run_id, "task_id": run.task_id},
        print_event=True,
    )

    run.status = RunStatus.COMPLETED
    run.completed_at = datetime.fromisoformat(now)
    return run


def fail_run(workspace: Workspace, run_id: str, reason: str = "") -> Run:
    """Mark a run as failed.

    Args:
        workspace: Target workspace
        run_id: Run to fail
        reason: Optional failure reason

    Returns:
        Updated Run

    Raises:
        ValueError: If run not found or not in RUNNING status
    """
    run = get_run(workspace, run_id)
    if not run:
        raise ValueError(f"Run not found: {run_id}")

    if run.status not in (RunStatus.RUNNING, RunStatus.BLOCKED):
        raise ValueError(f"Run is not active: {run.status}")

    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE runs
        SET status = ?, completed_at = ?
        WHERE id = ?
        """,
        (RunStatus.FAILED.value, now, run_id),
    )
    conn.commit()
    conn.close()

    # Emit run failed event
    events.emit_for_workspace(
        workspace,
        events.EventType.RUN_FAILED,
        {"run_id": run_id, "task_id": run.task_id, "reason": reason},
        print_event=True,
    )

    run.status = RunStatus.FAILED
    run.completed_at = datetime.fromisoformat(now)
    return run


def block_run(workspace: Workspace, run_id: str, blocker_id: str) -> Run:
    """Mark a run as blocked.

    Also transitions the task to BLOCKED.

    Args:
        workspace: Target workspace
        run_id: Run to block
        blocker_id: ID of the blocker that caused the block

    Returns:
        Updated Run

    Raises:
        ValueError: If run not found or not in RUNNING status
    """
    run = get_run(workspace, run_id)
    if not run:
        raise ValueError(f"Run not found: {run_id}")

    if run.status != RunStatus.RUNNING:
        raise ValueError(f"Run is not running: {run.status}")

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE runs
        SET status = ?
        WHERE id = ?
        """,
        (RunStatus.BLOCKED.value, run_id),
    )
    conn.commit()
    conn.close()

    # Transition task to BLOCKED
    tasks.update_status(workspace, run.task_id, TaskStatus.BLOCKED)

    run.status = RunStatus.BLOCKED
    return run


def resume_run(workspace: Workspace, task_id: str) -> Run:
    """Resume a blocked run.

    Args:
        workspace: Target workspace
        task_id: Task whose run to resume

    Returns:
        Resumed Run

    Raises:
        ValueError: If no blocked run found for task
    """
    run = get_active_run(workspace, task_id)
    if not run:
        raise ValueError(f"No active run found for task: {task_id}")

    if run.status != RunStatus.BLOCKED:
        raise ValueError(f"Run is not blocked: {run.status}")

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE runs
        SET status = ?
        WHERE id = ?
        """,
        (RunStatus.RUNNING.value, run.id),
    )
    conn.commit()
    conn.close()

    # Transition task back to IN_PROGRESS
    tasks.update_status(workspace, task_id, TaskStatus.IN_PROGRESS)

    run.status = RunStatus.RUNNING
    return run


def stop_run(workspace: Workspace, task_id: str) -> Run:
    """Stop a running task gracefully.

    Marks the run as failed and transitions task back to READY.

    Args:
        workspace: Target workspace
        task_id: Task whose run to stop

    Returns:
        Stopped Run

    Raises:
        ValueError: If no active run found for task
    """
    run = get_active_run(workspace, task_id)
    if not run:
        raise ValueError(f"No active run found for task: {task_id}")

    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE runs
        SET status = ?, completed_at = ?
        WHERE id = ?
        """,
        (RunStatus.FAILED.value, now, run.id),
    )
    conn.commit()
    conn.close()

    # Transition task back to READY so it can be restarted (if not already)
    task = tasks.get(workspace, task_id)
    if task and task.status != TaskStatus.READY:
        tasks.update_status(workspace, task_id, TaskStatus.READY)

    # Emit event
    events.emit_for_workspace(
        workspace,
        events.EventType.RUN_FAILED,
        {"run_id": run.id, "task_id": task_id, "reason": "Stopped by user"},
        print_event=True,
    )

    run.status = RunStatus.FAILED
    run.completed_at = datetime.fromisoformat(now)
    return run


def execute_stub(workspace: Workspace, run: Run) -> None:
    """Stub agent execution loop (deprecated).

    This is a placeholder kept for backwards compatibility.
    Use execute_agent() for real agent execution.

    Args:
        workspace: Target workspace
        run: Run to execute
    """
    # Emit agent step started
    events.emit_for_workspace(
        workspace,
        events.EventType.AGENT_STEP_STARTED,
        {"run_id": run.id, "step": 1, "description": "Analyzing task"},
        print_event=True,
    )

    # Emit agent step completed (stub does nothing real)
    events.emit_for_workspace(
        workspace,
        events.EventType.AGENT_STEP_COMPLETED,
        {"run_id": run.id, "step": 1, "description": "Analysis complete (stub)"},
        print_event=True,
    )


def execute_agent(
    workspace: Workspace,
    run: Run,
    dry_run: bool = False,
    debug: bool = False,
) -> "AgentState":
    """Execute a task using the agent orchestrator.

    This is the main entry point for real agent execution.
    It coordinates context loading, planning, execution, and verification.

    Args:
        workspace: Target workspace
        run: Run to execute
        dry_run: If True, don't make actual changes
        debug: If True, write detailed debug log to workspace

    Returns:
        Final AgentState after execution

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set
    """
    import os
    from codeframe.core.agent import Agent, AgentStatus
    from codeframe.adapters.llm import get_provider

    # Get LLM provider
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is required for agent execution. "
            "Set it with: export ANTHROPIC_API_KEY=your-key"
        )

    provider = get_provider("anthropic")

    # Create event callback to emit workspace events
    def on_agent_event(event_type: str, data: dict) -> None:
        events.emit_for_workspace(
            workspace,
            events.EventType.AGENT_STEP_STARTED if "started" in event_type else events.EventType.AGENT_STEP_COMPLETED,
            {"run_id": run.id, "agent_event": event_type, **data},
            print_event=True,
        )

    # Create and run agent
    agent = Agent(
        workspace=workspace,
        llm_provider=provider,
        dry_run=dry_run,
        on_event=on_agent_event,
        debug=debug,
    )

    state = agent.run(run.task_id)

    # If agent is BLOCKED, try supervisor resolution
    if state.status == AgentStatus.BLOCKED:
        from codeframe.core.conductor import get_supervisor

        supervisor = get_supervisor(workspace)
        if supervisor.try_resolve_blocked_task(run.task_id):
            # Supervisor resolved the blocker - retry the agent
            print("[Supervisor] Retrying task after auto-resolution...")

            # Create a new agent instance and retry
            agent = Agent(
                workspace=workspace,
                llm_provider=provider,
                dry_run=dry_run,
                on_event=on_agent_event,
                debug=debug,
            )
            state = agent.run(run.task_id)

    # Update run status based on agent result
    if state.status == AgentStatus.COMPLETED:
        complete_run(workspace, run.id)
    elif state.status == AgentStatus.BLOCKED:
        # Get blocker ID from state if available
        blocker_id = ""
        if state.blocker and hasattr(state, "_blocker_id"):
            blocker_id = state._blocker_id
        block_run(workspace, run.id, blocker_id)
    elif state.status == AgentStatus.FAILED:
        fail_run(workspace, run.id)

    return state


def _row_to_run(row: tuple) -> Run:
    """Convert a database row to a Run object."""
    return Run(
        id=row[0],
        workspace_id=row[1],
        task_id=row[2],
        status=RunStatus(row[3]),
        started_at=datetime.fromisoformat(row[4]),
        completed_at=datetime.fromisoformat(row[5]) if row[5] else None,
    )
