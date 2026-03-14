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
    from codeframe.core.streaming import EventPublisher


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
    event_publisher: Optional["EventPublisher"] = None,
    engine: str = "react",
    stall_timeout_s: int = 300,
    stall_action: str = "blocker",
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
        event_publisher: Optional EventPublisher for SSE streaming (real-time events)
        engine: Agent engine to use ("react", "plan", "claude-code", "opencode", "built-in")
        stall_timeout_s: Seconds without tool activity before stall detection (0 = disabled)
        stall_action: Recovery action on stall ("blocker", "retry", or "fail")

    Returns:
        Final AgentState after execution

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set (for builtin engines) or engine is invalid
    """
    import os
    from codeframe.core.agent import AgentState, AgentStatus
    from codeframe.adapters.llm import get_provider
    from codeframe.core.diagnostics import RunLogger, LogCategory
    from codeframe.core.engine_registry import (
        is_external_engine, resolve_engine, get_external_adapter, get_builtin_adapter,
    )
    from codeframe.core.adapters.agent_adapter import AgentEvent as AdapterEvent

    # Resolve engine (handles "built-in" alias and CODEFRAME_ENGINE env var)
    engine = resolve_engine(engine)

    # External engines manage their own authentication
    if not is_external_engine(engine) and not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is required for agent execution. "
            "Set it with: export ANTHROPIC_API_KEY=your-key"
        )

    # Only create LLM provider for builtin engines (external engines manage their own)
    provider = get_provider("anthropic") if not is_external_engine(engine) else None

    # Create run logger for structured logging
    run_logger = RunLogger(workspace, run.id, run.task_id)
    run_logger.info(LogCategory.AGENT_ACTION, "Starting agent execution", {
        "task_id": run.task_id,
        "dry_run": dry_run,
        "verbose": verbose,
        "engine": engine,
    })

    # Create output logger for streaming (cf work follow)
    from codeframe.core.streaming import RunOutputLogger
    output_logger = RunOutputLogger(workspace, run.id)

    # Load hook config (before main try block so it's available everywhere)
    from codeframe.core.config import load_environment_config
    from codeframe.core.hooks import HookAbortError, HookContext, execute_hook
    env_config = load_environment_config(workspace.repo_path)
    hook_ctx: HookContext | None = None
    if env_config:
        task_record = tasks.get(workspace, run.task_id)
        hook_ctx = HookContext(
            task_id=run.task_id,
            task_title=task_record.title if task_record else "",
            task_status="in_progress",
            workspace_path=str(workspace.repo_path),
        )

    import time as _time_mod
    _perf_start_ms = int(_time_mod.monotonic() * 1000)

    try:
        # Execute before_task hook (aborts on failure)
        if env_config and hook_ctx:
            try:
                hook_result = execute_hook(
                    "before_task", env_config, workspace.repo_path, hook_ctx,
                    abort_on_failure=True,
                )
                if hook_result:
                    events.emit_for_workspace(
                        workspace, events.EventType.HOOK_EXECUTED,
                        {"hook": "before_task", "success": hook_result.success},
                    )
            except HookAbortError as hook_err:
                events.emit_for_workspace(
                    workspace, events.EventType.HOOK_FAILED,
                    {"hook": "before_task", "error": str(hook_err)},
                )
                fail_run(workspace, run.id)
                from codeframe.core.agent import AgentState, AgentStatus
                return AgentState(status=AgentStatus.FAILED)
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

        # Bridge AgentEvent callbacks to workspace event system
        def on_adapter_event(event: AdapterEvent) -> None:
            on_agent_event(event.type, event.data)

        # Get adapter via registry and run
        if is_external_engine(engine):
            from codeframe.core.context_packager import TaskContextPackager
            from codeframe.core.adapters.verification_wrapper import VerificationWrapper

            run_logger.info(
                LogCategory.AGENT_ACTION,
                f"Using external engine: {engine}",
                {"engine": engine},
            )

            packager = TaskContextPackager(workspace)
            packaged = packager.build(run.task_id)

            adapter = get_external_adapter(engine)
            wrapper = VerificationWrapper(
                adapter, workspace, max_correction_rounds=5, verbose=verbose,
            )

            result = wrapper.run(
                run.task_id, packaged.prompt, workspace.repo_path,
                on_event=on_adapter_event,
            )
        else:
            from codeframe.core.stall_detector import StallAction

            resolved_action = StallAction(stall_action)
            builtin_kwargs: dict = {
                "event_publisher": event_publisher,
                "dry_run": dry_run,
                "verbose": verbose,
                "debug": debug,
                "output_logger": output_logger,
                "fix_coordinator": fix_coordinator,
            }
            # Stall detection is only relevant for the react engine
            if engine in ("react", "built-in"):
                builtin_kwargs["stall_timeout_s"] = stall_timeout_s
                builtin_kwargs["stall_action"] = resolved_action

            adapter = get_builtin_adapter(
                engine, workspace, provider, **builtin_kwargs,
            )

            result = adapter.run(
                run.task_id, "", workspace.repo_path,
                on_event=on_adapter_event,
            )

        run_logger.info(
            LogCategory.AGENT_ACTION,
            f"Engine '{engine}' completed: {result.status}",
            {"engine": engine, "output_length": len(result.output)},
        )

        # Map AgentResult to AgentState for rest of runtime
        status_map = {
            "completed": AgentStatus.COMPLETED,
            "failed": AgentStatus.FAILED,
            "blocked": AgentStatus.BLOCKED,
        }
        agent_status = status_map.get(result.status, AgentStatus.FAILED)
        state = AgentState(status=agent_status)

        # Create blocker if adapter reported one and populate state for CLI
        if result.status == "blocked" and result.blocker_question:
            from codeframe.core import blockers as blockers_mod
            blocker_obj = blockers_mod.create(
                workspace, task_id=run.task_id, question=result.blocker_question,
            )
            state.blocker = blocker_obj

        # Log final status
        if state.status == AgentStatus.COMPLETED:
            run_logger.info(LogCategory.STATE_CHANGE, "Agent completed successfully")
        elif state.status == AgentStatus.BLOCKED:
            run_logger.warning(LogCategory.BLOCKER, f"Agent blocked: {result.blocker_question or 'Unknown'}", {
                "blocker_question": result.blocker_question or "Unknown",
            })
        elif state.status == AgentStatus.FAILED:
            run_logger.error(LogCategory.ERROR, "Agent execution failed", {
                "error": (result.error or "")[:500],
            })

        # Update run status based on agent result (before hooks, so hooks see final state)
        if state.status == AgentStatus.COMPLETED:
            complete_run(workspace, run.id)
        elif state.status == AgentStatus.BLOCKED:
            block_run(workspace, run.id, "")
        elif state.status == AgentStatus.FAILED:
            fail_run(workspace, run.id)

        # Record engine performance metrics
        try:
            from codeframe.core import engine_stats
            _perf_duration_ms = int(_time_mod.monotonic() * 1000) - _perf_start_ms
            _perf_tokens = 0
            if hasattr(result, 'token_usage') and result.token_usage:
                _perf_tokens = result.token_usage.total_tokens

            engine_stats.record_run(
                workspace=workspace,
                run_id=run.id,
                engine=engine,
                task_id=run.task_id,
                status=agent_status.value.upper(),
                duration_ms=_perf_duration_ms,
                tokens_used=_perf_tokens,
                gates_passed=None,
                self_corrections=0,
            )
        except Exception:
            logger.debug("Engine stats recording failed", exc_info=True)

        # Execute after_task hooks (non-blocking, after state is persisted)
        if env_config and hook_ctx:
            after_hook = None
            if state.status == AgentStatus.COMPLETED:
                hook_ctx.task_status = "done"
                after_hook = "after_task_success"
            elif state.status == AgentStatus.FAILED:
                hook_ctx.task_status = "failed"
                after_hook = "after_task_failure"

            if after_hook:
                hook_result = execute_hook(
                    after_hook, env_config, workspace.repo_path, hook_ctx,
                    abort_on_failure=False,
                )
                if hook_result:
                    evt = events.EventType.HOOK_EXECUTED if hook_result.success else events.EventType.HOOK_FAILED
                    events.emit_for_workspace(workspace, evt, {"hook": after_hook, "success": hook_result.success})

        return state

    except Exception as exc:
        # Fail the run so it doesn't stay IN_PROGRESS forever
        run_logger.error(LogCategory.ERROR, f"Unhandled error in execute_agent: {exc}", {})
        try:
            fail_run(workspace, run.id)
        except Exception:
            pass  # Best-effort — don't mask the original error
        # Fire after_task_failure hook even on unhandled exceptions
        if env_config and hook_ctx:
            hook_ctx.task_status = "failed"
            execute_hook(
                "after_task_failure", env_config, workspace.repo_path, hook_ctx,
                abort_on_failure=False,
            )
        return AgentState(status=AgentStatus.FAILED)

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
