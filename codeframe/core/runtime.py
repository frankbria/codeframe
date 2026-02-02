"""Runtime/orchestration for CodeFRAME v2.

Manages task execution runs and the agent loop.

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from codeframe.core import events, tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import Workspace, get_db_connection

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from codeframe.core.agent import AgentState
    from codeframe.core.conductor import GlobalFixCoordinator


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
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO runs (id, workspace_id, task_id, status, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, workspace.id, task_id, RunStatus.RUNNING.value, now),
        )
        conn.commit()
    finally:
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


def get_latest_run(workspace: Workspace, task_id: str) -> Optional[Run]:
    """Get the most recent run for a task (any status).

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
        WHERE workspace_id = ? AND task_id = ?
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

    Also transitions the task to FAILED status.

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

    # Update task status to FAILED
    tasks.update_status(workspace, run.task_id, TaskStatus.FAILED)

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
    verbose: bool = False,
    fix_coordinator: Optional["GlobalFixCoordinator"] = None,
) -> "AgentState":
    """Execute a task using the agent orchestrator.

    This is the main entry point for real agent execution.
    It coordinates context loading, planning, execution, and verification.

    Args:
        workspace: Target workspace
        run: Run to execute
        dry_run: If True, don't make actual changes
        debug: If True, write detailed debug log to workspace
        verbose: If True, print detailed progress to stdout
        fix_coordinator: Optional coordinator for global fixes (for parallel execution)

    Returns:
        Final AgentState after execution

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set
    """
    import os
    from codeframe.core.agent import Agent, AgentStatus
    from codeframe.adapters.llm import get_provider
    from codeframe.core.diagnostics import RunLogger, LogCategory

    # Get LLM provider
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is required for agent execution. "
            "Set it with: export ANTHROPIC_API_KEY=your-key"
        )

    provider = get_provider("anthropic")

    # Create run logger for structured logging
    run_logger = RunLogger(workspace, run.id, run.task_id)
    run_logger.info(LogCategory.AGENT_ACTION, "Starting agent execution", {
        "task_id": run.task_id,
        "dry_run": dry_run,
        "verbose": verbose,
    })

    # Create output logger for streaming (cf work follow)
    from codeframe.core.streaming import RunOutputLogger
    output_logger = RunOutputLogger(workspace, run.id)

    try:
        # Create event callback to emit workspace events and log
        def on_agent_event(event_type: str, data: dict) -> None:
            events.emit_for_workspace(
                workspace,
                events.EventType.AGENT_STEP_STARTED if "started" in event_type else events.EventType.AGENT_STEP_COMPLETED,
                {"run_id": run.id, "agent_event": event_type, **data},
                print_event=True,
            )

            # Also log to run logger for diagnosis
            category = _event_type_to_category(event_type)
            run_logger.info(category, f"Agent event: {event_type}", data)

        # Create and run agent
        agent = Agent(
            workspace=workspace,
            llm_provider=provider,
            dry_run=dry_run,
            on_event=on_agent_event,
            debug=debug,
            verbose=verbose,
            fix_coordinator=fix_coordinator,
            output_logger=output_logger,
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
                    verbose=verbose,
                    fix_coordinator=fix_coordinator,
                    output_logger=output_logger,
                )
                state = agent.run(run.task_id)

        # If agent FAILED, check if supervisor can help with common technical issues
        if state.status == AgentStatus.FAILED:
            from codeframe.core.conductor import get_supervisor, SUPERVISOR_TACTICAL_PATTERNS

            if debug:
                logger.debug("Agent FAILED - analyzing for supervisor intervention")
                logger.debug("state.blocker: %s", state.blocker)
                logger.debug(
                    "state.step_results count: %d",
                    len(state.step_results) if state.step_results else 0
                )
                logger.debug(
                    "state.gate_results count: %d",
                    len(state.gate_results) if state.gate_results else 0
                )

            # Extract error message from available sources
            error_msg = ""
            error_source = "none"
            if state.blocker:
                error_msg = state.blocker.reason or state.blocker.question or ""
                error_source = "blocker"
            elif state.step_results:
                # Check last step result for error info
                last_result = state.step_results[-1]
                if debug:
                    error_preview = last_result.error[:200] if last_result.error else "None"
                    logger.debug(
                        "Last step result: status=%s, error=%s",
                        last_result.status, error_preview
                    )
                if hasattr(last_result, 'error') and last_result.error:
                    error_msg = last_result.error
                    error_source = "step_result.error"
                elif hasattr(last_result, 'output') and last_result.output:
                    error_msg = last_result.output
                    error_source = "step_result.output"
            elif state.gate_results:
                # Check gate results for failure info
                for gate in state.gate_results:
                    if debug:
                        logger.debug("Gate result: passed=%s", gate.passed)
                    if not gate.passed:
                        for check in gate.checks:
                            if debug:
                                output_preview = check.output[:100] if check.output else "None"
                                logger.debug(
                                    "  Check: %s status=%s output=%s",
                                    check.name, check.status, output_preview
                                )
                            if check.output:
                                error_msg = check.output
                                error_source = f"gate.{check.name}"
                                break

            if debug:
                logger.debug("Extracted error from: %s", error_source)
                error_preview = error_msg[:300] if error_msg else "EMPTY"
                logger.debug("Error message (first 300 chars): %s", error_preview)

            error_msg_lower = error_msg.lower()
            matched_patterns = [p for p in SUPERVISOR_TACTICAL_PATTERNS if p in error_msg_lower]
            if debug:
                logger.debug("Matched tactical patterns: %s", matched_patterns)

            if error_msg and matched_patterns:
                supervisor = get_supervisor(workspace)
                resolution = supervisor._generate_tactical_resolution(error_msg)
                logger.info(
                    "Supervisor detected recoverable error, providing guidance: %s...",
                    resolution[:100]
                )

                # Create a blocker with the resolution for the agent's next run
                from codeframe.core import blockers
                blocker = blockers.create(
                    workspace,
                    task_id=run.task_id,
                    question=f"Technical error: {error_msg[:500]}",
                )
                blockers.answer(workspace, blocker.id, resolution)
                if debug:
                    logger.debug("Created blocker %s and answered with resolution", blocker.id[:8])

                # Retry the agent with the new context
                logger.info("Supervisor retrying task with guidance...")
                agent = Agent(
                    workspace=workspace,
                    llm_provider=provider,
                    dry_run=dry_run,
                    on_event=on_agent_event,
                    debug=debug,
                    verbose=verbose,
                    fix_coordinator=fix_coordinator,
                    output_logger=output_logger,
                )
                state = agent.run(run.task_id)
                if debug:
                    logger.debug("Retry completed with status: %s", state.status)
            elif debug:
                logger.debug(
                    "No supervisor intervention - error_msg empty=%s, no pattern match=%s",
                    not error_msg, not matched_patterns
                )

        # Log final status
        if state.status == AgentStatus.COMPLETED:
            run_logger.info(LogCategory.STATE_CHANGE, "Agent completed successfully")
        elif state.status == AgentStatus.BLOCKED:
            blocker_reason = state.blocker.question if state.blocker else "Unknown"
            run_logger.warning(LogCategory.BLOCKER, f"Agent blocked: {blocker_reason[:200]}", {
                "blocker_question": blocker_reason,
            })
        elif state.status == AgentStatus.FAILED:
            # Log detailed error information for diagnosis
            error_info = {}
            if state.step_results:
                last_step = state.step_results[-1]
                error_info["last_step_status"] = last_step.status.value if hasattr(last_step.status, 'value') else str(last_step.status)
                error_info["last_step_error"] = last_step.error[:500] if last_step.error else None
            if state.gate_results:
                error_info["gate_failures"] = sum(1 for g in state.gate_results if not g.passed)
            run_logger.error(LogCategory.ERROR, "Agent execution failed", error_info)

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

    finally:
        # Always close the output logger to ensure file is properly flushed
        output_logger.close()


def _event_type_to_category(event_type: str):
    """Map agent event types to log categories.

    Args:
        event_type: The agent event type string

    Returns:
        LogCategory appropriate for the event
    """
    from codeframe.core.diagnostics import LogCategory

    if "planning" in event_type.lower():
        return LogCategory.AGENT_ACTION
    elif "verification" in event_type.lower() or "gate" in event_type.lower():
        return LogCategory.VERIFICATION
    elif "error" in event_type.lower() or "failed" in event_type.lower():
        return LogCategory.ERROR
    elif "blocker" in event_type.lower():
        return LogCategory.BLOCKER
    elif "llm" in event_type.lower() or "context" in event_type.lower():
        return LogCategory.LLM_CALL
    elif "file" in event_type.lower():
        return LogCategory.FILE_OPERATION
    elif "shell" in event_type.lower() or "command" in event_type.lower():
        return LogCategory.SHELL_COMMAND
    else:
        return LogCategory.AGENT_ACTION


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


# ============================================================================
# Task Approval and Assignment (Route Delegation Helpers)
# ============================================================================


@dataclass
class ApprovalResult:
    """Result of task approval operation.

    Attributes:
        approved_count: Number of tasks approved (transitioned to READY)
        excluded_count: Number of tasks excluded from approval
        approved_task_ids: List of approved task IDs
        excluded_task_ids: List of excluded task IDs
    """

    approved_count: int
    excluded_count: int
    approved_task_ids: list[str]
    excluded_task_ids: list[str]


def approve_tasks(
    workspace: Workspace,
    excluded_task_ids: Optional[list[str]] = None,
) -> ApprovalResult:
    """Approve tasks for execution by transitioning them to READY status.

    This function handles the "task approval" workflow:
    1. Gets all BACKLOG tasks in the workspace
    2. Excludes specified tasks (if any)
    3. Transitions remaining tasks to READY status

    This is the v2 equivalent of the v1 approval endpoint. It does NOT
    trigger execution - use start_approved_batch() for that.

    Args:
        workspace: Target workspace
        excluded_task_ids: Optional list of task IDs to exclude from approval

    Returns:
        ApprovalResult with counts and IDs

    Example:
        result = approve_tasks(workspace, excluded_task_ids=["task-1", "task-2"])
        print(f"Approved {result.approved_count} tasks")
        if result.approved_count > 0:
            batch = start_approved_batch(workspace, result.approved_task_ids)
    """
    excluded = set(excluded_task_ids or [])

    # Get all BACKLOG tasks
    backlog_tasks = tasks.list_tasks(workspace, status=TaskStatus.BACKLOG)

    approved_ids = []
    excluded_ids = []

    for task in backlog_tasks:
        if task.id in excluded:
            excluded_ids.append(task.id)
        else:
            # Transition to READY
            tasks.update_status(workspace, task.id, TaskStatus.READY)
            approved_ids.append(task.id)

    logger.info(
        f"Approved {len(approved_ids)} tasks, excluded {len(excluded_ids)} "
        f"for workspace {workspace.id}"
    )

    return ApprovalResult(
        approved_count=len(approved_ids),
        excluded_count=len(excluded_ids),
        approved_task_ids=approved_ids,
        excluded_task_ids=excluded_ids,
    )


@dataclass
class AssignmentResult:
    """Result of task assignment check.

    Attributes:
        pending_count: Number of pending (READY) tasks
        executing_count: Number of tasks currently executing (IN_PROGRESS)
        can_assign: Whether new tasks can be assigned
        reason: Explanation if can_assign is False
    """

    pending_count: int
    executing_count: int
    can_assign: bool
    reason: str


def check_assignment_status(workspace: Workspace) -> AssignmentResult:
    """Check if tasks can be assigned for execution.

    This function helps determine whether to start new task execution:
    1. Counts pending (READY) tasks
    2. Counts currently executing (IN_PROGRESS) tasks
    3. Determines if new assignments are possible

    Used by routes to provide feedback before triggering execution.

    Args:
        workspace: Target workspace

    Returns:
        AssignmentResult with status and explanation

    Example:
        status = check_assignment_status(workspace)
        if status.can_assign:
            batch = start_approved_batch(workspace)
        else:
            print(status.reason)
    """
    # Count tasks by status
    status_counts = tasks.count_by_status(workspace)
    ready_count = status_counts.get(TaskStatus.READY.value, 0)
    in_progress_count = status_counts.get(TaskStatus.IN_PROGRESS.value, 0)

    if ready_count == 0:
        return AssignmentResult(
            pending_count=0,
            executing_count=in_progress_count,
            can_assign=False,
            reason="No pending tasks to assign.",
        )

    if in_progress_count > 0:
        return AssignmentResult(
            pending_count=ready_count,
            executing_count=in_progress_count,
            can_assign=False,
            reason=f"Execution already in progress ({in_progress_count} task(s) running).",
        )

    return AssignmentResult(
        pending_count=ready_count,
        executing_count=0,
        can_assign=True,
        reason=f"{ready_count} task(s) ready for assignment.",
    )


def get_ready_task_ids(workspace: Workspace) -> list[str]:
    """Get IDs of all READY tasks in the workspace.

    Convenience function for starting batch execution.

    Args:
        workspace: Target workspace

    Returns:
        List of task IDs in READY status
    """
    ready_tasks = tasks.list_tasks(workspace, status=TaskStatus.READY)
    return [t.id for t in ready_tasks]
