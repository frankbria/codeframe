"""Batch execution conductor for CodeFRAME v2.

Orchestrates execution of multiple tasks, managing parallelization
and coordinating results.

This module is headless - no FastAPI or HTTP dependencies.
"""

import hashlib
import json
import re
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from codeframe.core.workspace import Workspace, get_db_connection
from codeframe.core import events, tasks, blockers
from codeframe.core.dependency_graph import create_execution_plan, CycleDetectedError
from codeframe.core.dependency_analyzer import analyze_dependencies, apply_inferred_dependencies
from codeframe.core.runtime import RunStatus, get_active_run, reset_blocked_run


# Tactical patterns that the supervisor should auto-resolve
SUPERVISOR_TACTICAL_PATTERNS = [
    # Virtual environment / package management
    "virtual environment", "venv", "virtualenv",
    "pip install", "npm install", "uv sync",
    "break-system-packages", "pipx",
    "package manager", "dependency installation",
    "externally-managed",  # PEP 668 error - use venv or uv
    "externally managed",
    # Module/import issues
    "no module named", "__main__", "cannot be directly executed",
    "modulenotfounderror", "importerror",
    # Configuration
    "pytest.ini", "pyproject.toml", "asyncio_default_fixture_loop_scope",
    "fixture scope", "loop scope", "configuration file",
    # Common tactical questions
    "would you like me to", "would you prefer",
    "should i create", "should i use",
    "which approach", "which version",
    "overwrite", "existing file",
]

# Cache of resolved decisions to avoid duplicate LLM calls
_decision_cache: dict[str, str] = {}

# Track running subprocesses for force stop capability
# Structure: {batch_id: {task_id: Popen}}
_active_processes: dict[str, dict[str, subprocess.Popen]] = {}
# Lock for thread-safe access to _active_processes
_active_processes_lock = threading.Lock()
# Lock for thread-safe batch database writes
_batch_db_lock = threading.Lock()


class SupervisorResolver:
    """Resolves tactical blockers at the conductor level.

    Instead of each worker agent independently creating blockers,
    the conductor uses this resolver to:
    1. Evaluate blockers with the supervision model (stronger)
    2. Auto-resolve tactical decisions
    3. Deduplicate similar questions across workers
    4. Only surface true human-required decisions
    """

    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self._llm = None  # Lazy initialization

    @property
    def llm(self):
        """Lazy-load LLM provider."""
        if self._llm is None:
            from codeframe.adapters.llm import get_provider
            self._llm = get_provider()
        return self._llm

    def try_resolve_blocked_task(self, task_id: str) -> bool:
        """Try to resolve a blocked task's blocker autonomously.

        Args:
            task_id: The blocked task ID

        Returns:
            True if blocker was resolved (task should retry),
            False if blocker requires human input
        """
        # Get the task's open blockers
        task_blockers = blockers.list_all(
            self.workspace,
            task_id=task_id,
            status=blockers.BlockerStatus.OPEN,
        )

        if not task_blockers:
            return False

        blocker = task_blockers[0]  # Most recent open blocker
        question = blocker.question.lower()

        # Check cache first
        cache_key = self._get_cache_key(question)
        if cache_key in _decision_cache:
            print("      [Supervisor] Using cached decision for similar question")
            self._auto_answer_blocker(blocker, _decision_cache[cache_key])
            return True

        # Check if question matches tactical patterns
        if self._is_tactical_question(question):
            print("      [Supervisor] Detected tactical question, auto-resolving")
            resolution = self._generate_tactical_resolution(blocker.question)
            _decision_cache[cache_key] = resolution
            self._auto_answer_blocker(blocker, resolution)
            return True

        # Use supervision model to classify if uncertain
        classification = self._classify_with_supervision(blocker.question)

        if classification == "tactical":
            print("      [Supervisor] Model classified as tactical, auto-resolving")
            resolution = self._generate_tactical_resolution(blocker.question)
            _decision_cache[cache_key] = resolution
            self._auto_answer_blocker(blocker, resolution)
            return True

        # This is a genuine human-required decision
        print("      [Supervisor] Question requires human input")
        return False

    def _is_tactical_question(self, question: str) -> bool:
        """Check if question matches known tactical patterns."""
        return any(pattern in question for pattern in SUPERVISOR_TACTICAL_PATTERNS)

    def _get_cache_key(self, question: str) -> str:
        """Generate a cache key for deduplication.

        Normalizes similar questions to the same key.
        """
        # Simple normalization - could be improved with embeddings
        q = question.lower()
        if "virtual environment" in q or "venv" in q or "virtualenv" in q:
            return "venv_creation"
        if "fixture scope" in q or "asyncio" in q:
            return "asyncio_fixture_scope"
        if "package manager" in q or "pip" in q or "npm" in q:
            return "package_manager"
        if "pytest" in q and ("fail" in q or "verification" in q):
            return "pytest_failure"
        # Fallback to hash of first 50 chars
        return f"blocker_{hash(q[:50])}"

    def _classify_with_supervision(self, question: str) -> str:
        """Use supervision model to classify the blocker question."""
        from codeframe.adapters.llm import Purpose

        prompt = f"""Classify this blocker question from a coding agent:

Question: {question}

Is this:
1. TACTICAL - A decision the agent should make autonomously (venv, package manager, config options, test framework, file handling)
2. HUMAN - Genuinely requires human input (conflicting requirements, missing credentials, business logic, security policy)

Respond with exactly one word: TACTICAL or HUMAN"""

        try:
            response = self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                purpose=Purpose.SUPERVISION,
                max_tokens=10,
                temperature=0.0,
            )
            result = response.content.strip().upper()
            return "tactical" if "TACTICAL" in result else "human"
        except Exception as e:
            print(f"      [Supervisor] Classification failed: {e}")
            # Default to tactical for common patterns
            return "tactical" if self._is_tactical_question(question.lower()) else "human"

    def _generate_tactical_resolution(self, question: str) -> str:
        """Generate an autonomous resolution for tactical questions."""
        q = question.lower()

        # Common resolutions
        if "virtual environment" in q or "venv" in q:
            return "Create a Python virtual environment using 'python -m venv .venv' or 'uv venv', then activate it and install dependencies."
        if "externally-managed" in q or "externally managed" in q:
            return "This system uses an externally-managed Python. Use 'uv pip install' instead of 'pip install', or create a virtual environment first with 'uv venv' then 'source .venv/bin/activate'."
        if "__main__" in q or "cannot be directly executed" in q:
            return "Create a __main__.py file in the package directory with the entry point code (e.g., 'from .cli import main; main()' or similar)."
        if "no module named" in q or "modulenotfounderror" in q:
            return "Install the missing module using 'uv pip install <module>' or add it to requirements.txt and run 'uv pip install -r requirements.txt'."
        if "importerror" in q:
            return "Check that the module is installed and the import path is correct. For local modules, ensure __init__.py exists in the package directory."
        if "fixture scope" in q or "asyncio" in q or "asyncio_default_fixture_loop_scope" in q:
            return "Add '[tool.pytest.ini_options]\nasyncio_default_fixture_loop_scope = \"function\"' to pyproject.toml or 'asyncio_default_fixture_loop_scope = function' to pytest.ini."
        if "package manager" in q:
            return "Use the project's default package manager (uv for Python, npm for JS). For Python, prefer 'uv pip install' or 'uv sync'."
        if "pytest" in q and "fail" in q:
            return "Fix the failing tests and retry."
        if "overwrite" in q or "existing file" in q:
            return "Overwrite the existing file with the new content."
        if "which version" in q:
            return "Use the latest stable version."

        # Generic resolution
        return "Proceed with the most appropriate approach based on best practices."

    def _auto_answer_blocker(self, blocker: blockers.Blocker, answer: str) -> None:
        """Auto-answer a blocker and reset the task for retry."""
        # Answer the blocker
        blockers.answer(self.workspace, blocker.id, f"[Auto-resolved by supervisor] {answer}")

        # Reset the blocked run so task can retry
        if blocker.task_id:
            reset_blocked_run(self.workspace, blocker.task_id)


# Global supervisor instance per workspace (created lazily)
_supervisors: dict[str, SupervisorResolver] = {}


def get_supervisor(workspace: Workspace) -> SupervisorResolver:
    """Get or create a supervisor resolver for a workspace."""
    if workspace.id not in _supervisors:
        _supervisors[workspace.id] = SupervisorResolver(workspace)
    return _supervisors[workspace.id]


@dataclass
class GlobalFix:
    """A global fix that affects project-wide state.

    Attributes:
        error_signature: Hash of the normalized error
        fix_description: What the fix does
        fix_type: Type of fix (shell, edit, create)
        command: Shell command (for shell type)
        file_path: File to modify (for edit/create)
        status: pending, executing, completed, failed
    """
    error_signature: str
    fix_description: str
    fix_type: str
    command: Optional[str] = None
    file_path: Optional[str] = None
    status: str = "pending"
    result: Optional[str] = None


class GlobalFixCoordinator:
    """Coordinates global fixes across parallel agents.

    When multiple agents hit the same global issue (e.g., missing local package),
    this coordinator ensures:
    1. Only ONE fix is executed (not N times for N agents)
    2. Other agents wait for the fix to complete
    3. Completed fixes are cached to skip redundant work

    Thread-safe for parallel batch execution.
    """

    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self._lock = threading.Lock()
        self._pending: dict[str, GlobalFix] = {}   # error_sig -> GlobalFix
        self._completed: dict[str, GlobalFix] = {} # error_sig -> GlobalFix (succeeded)
        self._condition = threading.Condition(self._lock)

    def _hash_error(self, error: str) -> str:
        """Create a stable hash for an error message.

        Normalizes variable parts (line numbers, paths) before hashing.
        """
        # Remove line numbers
        normalized = re.sub(r"line \d+", "line N", error)
        # Remove specific file paths but keep filename
        normalized = re.sub(r"/[^\s:]+/([^/\s:]+)", r"\1", normalized)
        # Remove memory addresses
        normalized = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", normalized)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def request_fix(
        self,
        error: str,
        fix_type: str,
        fix_description: str,
        command: Optional[str] = None,
        file_path: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> tuple[str, bool]:
        """Request a global fix from the coordinator.

        Returns:
            Tuple of (status, should_execute):
            - ("already_completed", False): Fix was already done, just retry verification
            - ("pending", False): Another agent is handling it, wait and retry
            - ("execute", True): You are responsible for executing this fix
        """
        error_sig = self._hash_error(error)

        with self._lock:
            # Already completed successfully?
            if error_sig in self._completed:
                print("  [GlobalFix] Fix already completed for this error")
                return ("already_completed", False)

            # Already being worked on?
            if error_sig in self._pending:
                print("  [GlobalFix] Another agent is fixing this, waiting...")
                # Wait for completion (with timeout)
                return ("pending", False)

            # This agent will handle it
            fix = GlobalFix(
                error_signature=error_sig,
                fix_description=fix_description,
                fix_type=fix_type,
                command=command,
                file_path=file_path,
                status="executing",
            )
            self._pending[error_sig] = fix
            print(f"  [GlobalFix] Agent taking ownership: {fix_description[:60]}...")
            return ("execute", True)

    def report_fix_result(
        self,
        error: str,
        success: bool,
        result_message: Optional[str] = None,
    ) -> None:
        """Report the result of executing a global fix.

        Args:
            error: Original error message
            success: Whether the fix succeeded
            result_message: Optional details about the result
        """
        error_sig = self._hash_error(error)

        with self._lock:
            if error_sig not in self._pending:
                return  # Not our fix

            fix = self._pending.pop(error_sig)
            fix.status = "completed" if success else "failed"
            fix.result = result_message

            if success:
                self._completed[error_sig] = fix
                print("  [GlobalFix] Fix completed successfully")
            else:
                print(f"  [GlobalFix] Fix failed: {result_message}")

            # Notify any waiting agents
            self._condition.notify_all()

    def wait_for_fix(self, error: str, timeout: float = 60.0) -> bool:
        """Wait for another agent to complete a fix.

        Args:
            error: Error message we're waiting on
            timeout: Max seconds to wait

        Returns:
            True if fix was completed successfully, False otherwise
        """
        error_sig = self._hash_error(error)

        with self._condition:
            start = datetime.now(timezone.utc)
            while error_sig in self._pending:
                remaining = timeout - (datetime.now(timezone.utc) - start).total_seconds()
                if remaining <= 0:
                    print("  [GlobalFix] Timeout waiting for fix")
                    return False
                self._condition.wait(timeout=remaining)

            # Check if it completed successfully
            return error_sig in self._completed

    def is_fixed(self, error: str) -> bool:
        """Check if an error has already been fixed."""
        error_sig = self._hash_error(error)
        with self._lock:
            return error_sig in self._completed


# Global coordinator instances per workspace
_coordinators: dict[str, GlobalFixCoordinator] = {}


def get_fix_coordinator(workspace: Workspace) -> GlobalFixCoordinator:
    """Get or create a global fix coordinator for a workspace."""
    if workspace.id not in _coordinators:
        _coordinators[workspace.id] = GlobalFixCoordinator(workspace)
    return _coordinators[workspace.id]


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
    engine: str = "plan"


def start_batch(
    workspace: Workspace,
    task_ids: list[str],
    strategy: str = "serial",
    max_parallel: int = 4,
    on_failure: str = "continue",
    dry_run: bool = False,
    max_retries: int = 0,
    on_event: Optional[Callable[[str, dict], None]] = None,
    engine: str = "plan",
) -> BatchRun:
    """Start a batch execution of multiple tasks.

    Args:
        workspace: Target workspace
        task_ids: List of task IDs to execute (in order)
        strategy: Execution strategy ("serial" or "parallel")
        max_parallel: Max concurrent tasks for parallel strategy
        on_failure: Behavior on task failure ("continue" or "stop")
        dry_run: If True, don't actually execute tasks
        max_retries: Max retry attempts for failed tasks (0 = no retries)
        on_event: Optional callback for batch events
        engine: Agent engine to use ("plan" or "react")

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
        engine=engine,
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
    if strategy == "auto":
        # Use LLM to infer dependencies, then execute in parallel
        try:
            print("\nAnalyzing task dependencies with LLM...")
            dependencies = analyze_dependencies(workspace, task_ids)

            # Show inferred dependencies
            deps_with_values = {k: v for k, v in dependencies.items() if v}
            if deps_with_values:
                print("Inferred dependencies:")
                for tid, deps in deps_with_values.items():
                    task = tasks.get(workspace, tid)
                    task_title = task.title[:40] if task else tid[:8]
                    dep_titles = []
                    for d in deps:
                        dep_task = tasks.get(workspace, d)
                        dep_titles.append(dep_task.title[:30] if dep_task else d[:8])
                    print(f"  {task_title} <- {', '.join(dep_titles)}")
            else:
                print("No dependencies inferred - tasks appear independent")

            # Apply inferred dependencies to task records
            # Note: This persists the dependencies to the database so they're
            # available for future executions and batch resumes
            apply_inferred_dependencies(workspace, dependencies)

            # Execute with parallel strategy
            _execute_parallel(workspace, batch, on_event)
        except CycleDetectedError as e:
            print(f"Error: {e}")
            print("Falling back to serial execution")
            _execute_serial(workspace, batch, on_event)
        except Exception as e:
            print(f"Dependency analysis failed: {e}")
            print("Falling back to serial execution")
            _execute_serial(workspace, batch, on_event)
    elif strategy == "parallel" and max_parallel > 1:
        try:
            _execute_parallel(workspace, batch, on_event)
        except CycleDetectedError as e:
            print(f"Error: {e}")
            print("Falling back to serial execution")
            _execute_serial(workspace, batch, on_event)
    else:
        _execute_serial(workspace, batch, on_event)

    # Retry failed tasks if max_retries > 0
    if max_retries > 0:
        _execute_retries(workspace, batch, max_retries, on_event)

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
               on_failure, started_at, completed_at, results, engine
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
                   on_failure, started_at, completed_at, results, engine
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
                   on_failure, started_at, completed_at, results, engine
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


def stop_batch(workspace: Workspace, batch_id: str, force: bool = False) -> BatchRun:
    """Stop a running batch.

    Graceful stop (force=False):
        - Marks batch as CANCELLED
        - Execution loops will exit after current task completes
        - Running tasks are allowed to finish naturally

    Force stop (force=True):
        - Marks batch as CANCELLED immediately
        - Sends SIGTERM to all running subprocesses
        - Processes have a brief window to cleanup before termination

    Args:
        workspace: Target workspace
        batch_id: Batch to stop
        force: If True, terminate running processes immediately

    Returns:
        Updated BatchRun

    Raises:
        ValueError: If batch not found or not stoppable
    """
    batch = get_batch(workspace, batch_id)
    if not batch:
        raise ValueError(f"Batch not found: {batch_id}")

    if batch.status not in (BatchStatus.PENDING, BatchStatus.RUNNING):
        raise ValueError(f"Batch cannot be stopped (status={batch.status})")

    # Update status first - execution loops check this
    batch.status = BatchStatus.CANCELLED
    batch.completed_at = _utc_now()
    _save_batch(workspace, batch)

    terminated_count = 0
    with _active_processes_lock:
        if force and batch_id in _active_processes:
            # Terminate all running processes for this batch
            processes = _active_processes.get(batch_id, {})
            for task_id, process in list(processes.items()):
                try:
                    if process.poll() is None:  # Still running
                        process.terminate()  # SIGTERM
                        terminated_count += 1
                except (ProcessLookupError, OSError):
                    pass  # Process already exited

            # Cleanup tracking
            _active_processes.pop(batch_id, None)

    # Emit event
    event_data = {"batch_id": batch_id, "force": force}
    if terminated_count > 0:
        event_data["terminated_processes"] = terminated_count

    events.emit_for_workspace(
        workspace,
        events.EventType.BATCH_CANCELLED,
        event_data,
        print_event=True,
    )

    return batch


def resume_batch(
    workspace: Workspace,
    batch_id: str,
    force: bool = False,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> BatchRun:
    """Resume a batch by re-running failed/blocked tasks.

    Args:
        workspace: Target workspace
        batch_id: Batch to resume
        force: If True, re-run all tasks including completed ones
        on_event: Optional callback for batch events

    Returns:
        Updated BatchRun with new results

    Raises:
        ValueError: If batch not found or not in a resumable state
    """
    batch = get_batch(workspace, batch_id)
    if not batch:
        raise ValueError(f"Batch not found: {batch_id}")

    # Check if batch is in a resumable state
    resumable_statuses = (
        BatchStatus.PARTIAL,
        BatchStatus.FAILED,
        BatchStatus.CANCELLED,
    )
    if batch.status not in resumable_statuses:
        raise ValueError(
            f"Batch cannot be resumed (status={batch.status}). "
            f"Only {', '.join(s.value for s in resumable_statuses)} batches can be resumed."
        )

    # Determine which tasks to re-run
    if force:
        # Re-run all tasks
        tasks_to_run = batch.task_ids
        print(f"Resuming batch {batch_id[:8]}... (force mode: re-running all {len(tasks_to_run)} tasks)")
    else:
        # Only re-run failed/blocked tasks
        failed_statuses = {"FAILED", "BLOCKED"}
        tasks_to_run = [
            tid for tid in batch.task_ids
            if batch.results.get(tid) in failed_statuses or tid not in batch.results
        ]
        if not tasks_to_run:
            print(f"No failed or blocked tasks to resume in batch {batch_id[:8]}")
            return batch
        print(f"Resuming batch {batch_id[:8]}... (re-running {len(tasks_to_run)} failed/blocked tasks)")

    # Emit batch resumed event
    events.emit_for_workspace(
        workspace,
        events.EventType.BATCH_STARTED,  # Reuse BATCH_STARTED for resume
        {
            "batch_id": batch_id,
            "task_ids": tasks_to_run,
            "strategy": batch.strategy,
            "task_count": len(tasks_to_run),
            "is_resume": True,
        },
        print_event=True,
    )

    if on_event:
        on_event("batch_resumed", {"batch_id": batch_id, "task_count": len(tasks_to_run)})

    # Update status to running
    batch.status = BatchStatus.RUNNING
    batch.completed_at = None  # Clear completed_at since we're running again
    _save_batch(workspace, batch)

    # Execute the tasks
    _execute_serial_resume(workspace, batch, tasks_to_run, on_event)

    return batch


def _execute_serial_resume(
    workspace: Workspace,
    batch: BatchRun,
    tasks_to_run: list[str],
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> None:
    """Execute a subset of tasks serially for resume.

    Similar to _execute_serial but only runs specified tasks and
    merges results with existing batch results.
    """
    completed_count = 0
    failed_count = 0
    blocked_count = 0

    # Count existing successful results (tasks not being re-run)
    for task_id in batch.task_ids:
        if task_id not in tasks_to_run:
            if batch.results.get(task_id) == RunStatus.COMPLETED.value:
                completed_count += 1

    for i, task_id in enumerate(tasks_to_run):
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
        previous_status = batch.results.get(task_id, "N/A")

        print(f"\n[{i + 1}/{len(tasks_to_run)}] Retrying task {task_id}: {task_title}")
        print(f"      Previous status: {previous_status}")

        # Emit task started event
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_TASK_STARTED,
            {"batch_id": batch.id, "task_id": task_id, "is_retry": True},
            print_event=True,
        )

        if on_event:
            on_event("batch_task_started", {"task_id": task_id, "position": i + 1, "is_retry": True})

        # Execute task via subprocess
        result_status = _execute_task_subprocess(workspace, task_id, batch.id, engine=batch.engine)

        # Record result (overwrites previous result)
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
            print(f"      ✓ Completed (was: {previous_status})")
        elif result_status == RunStatus.BLOCKED.value:
            blocked_count += 1
            events.emit_for_workspace(
                workspace,
                events.EventType.BATCH_TASK_BLOCKED,
                {"batch_id": batch.id, "task_id": task_id},
                print_event=True,
            )
            print("      ⊘ Still blocked")
        else:
            failed_count += 1
            events.emit_for_workspace(
                workspace,
                events.EventType.BATCH_TASK_FAILED,
                {"batch_id": batch.id, "task_id": task_id, "status": result_status},
                print_event=True,
            )
            print(f"      ✗ Still failed: {result_status}")

            # Note: resume doesn't stop on failure, always continues
            # to give all failed tasks a chance

        if on_event:
            on_event("batch_task_completed", {"task_id": task_id, "status": result_status})

    # Determine final batch status based on ALL results
    total = len(batch.task_ids)

    # Recount from results
    final_completed = sum(1 for s in batch.results.values() if s == RunStatus.COMPLETED.value)
    final_failed = sum(1 for s in batch.results.values() if s == RunStatus.FAILED.value)
    final_blocked = sum(1 for s in batch.results.values() if s == RunStatus.BLOCKED.value)

    if final_completed == total:
        batch.status = BatchStatus.COMPLETED
        event_type = events.EventType.BATCH_COMPLETED

        # Run batch-level validation (full gate sweep)
        validation_passed, validation_error = _run_batch_level_validation(workspace, batch)

        if not validation_passed:
            # Gates failed - change status to PARTIAL (tasks done, integration broken)
            batch.status = BatchStatus.PARTIAL
            event_type = events.EventType.BATCH_PARTIAL
            print("\n⚠️  Batch marked PARTIAL due to failed batch-level gates")
            print(f"Validation error: {validation_error}")

    elif final_completed == 0 and (final_failed > 0 or final_blocked > 0):
        batch.status = BatchStatus.FAILED
        event_type = events.EventType.BATCH_FAILED
    elif final_completed > 0:
        batch.status = BatchStatus.PARTIAL
        event_type = events.EventType.BATCH_PARTIAL
    else:
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
            "completed": final_completed,
            "failed": final_failed,
            "blocked": final_blocked,
            "total": total,
            "is_resume": True,
        },
        print_event=True,
    )

    # Print summary
    print(f"\nBatch resume {batch.status.value.lower()}: {final_completed}/{total} tasks completed")
    if final_failed > 0:
        print(f"  Failed: {final_failed}")
    if final_blocked > 0:
        print(f"  Blocked: {final_blocked}")


def _execute_retries(
    workspace: Workspace,
    batch: BatchRun,
    max_retries: int,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> None:
    """Retry failed tasks up to max_retries times.

    After the initial execution pass, this function re-runs any failed
    tasks, continuing until all tasks succeed or max_retries is exhausted.

    Args:
        workspace: Target workspace
        batch: BatchRun with initial results
        max_retries: Maximum retry attempts per task
        on_event: Optional callback for events
    """
    failed_statuses = {RunStatus.FAILED.value}  # Only retry FAILED, not BLOCKED

    for retry_num in range(1, max_retries + 1):
        # Find tasks that failed
        failed_tasks = [
            tid for tid in batch.task_ids
            if batch.results.get(tid) in failed_statuses
        ]

        if not failed_tasks:
            # All tasks succeeded, no retries needed
            break

        print(f"\n{'='*60}")
        print(f"Retry attempt {retry_num}/{max_retries}: {len(failed_tasks)} failed task(s)")
        print(f"{'='*60}")

        # Emit retry event
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_STARTED,  # Reuse for retry
            {
                "batch_id": batch.id,
                "task_ids": failed_tasks,
                "retry_attempt": retry_num,
                "max_retries": max_retries,
            },
            print_event=True,
        )

        if on_event:
            on_event("batch_retry_started", {
                "batch_id": batch.id,
                "retry_attempt": retry_num,
                "task_count": len(failed_tasks),
            })

        # Re-run each failed task
        for i, task_id in enumerate(failed_tasks):
            # Check if batch was cancelled
            current_batch = get_batch(workspace, batch.id)
            if current_batch and current_batch.status == BatchStatus.CANCELLED:
                return

            task = tasks.get(workspace, task_id)
            task_title = task.title if task else task_id
            previous_status = batch.results.get(task_id, "N/A")

            print(f"\n[Retry {retry_num}, {i + 1}/{len(failed_tasks)}] {task_id}: {task_title}")
            print(f"      Previous: {previous_status}")

            # Execute task
            result_status = _execute_task_subprocess(workspace, task_id, batch.id, engine=batch.engine)

            # Update result
            batch.results[task_id] = result_status
            _save_batch(workspace, batch)

            if result_status == RunStatus.COMPLETED.value:
                print(f"      ✓ Succeeded on retry {retry_num}")
            else:
                remaining = max_retries - retry_num
                if remaining > 0:
                    print(f"      ✗ Still failed ({remaining} retries left)")
                else:
                    print(f"      ✗ Failed after {max_retries} retries")

            if on_event:
                on_event("batch_task_retried", {
                    "task_id": task_id,
                    "retry_attempt": retry_num,
                    "status": result_status,
                })

    # Recalculate final batch status after all retries
    total = len(batch.task_ids)
    final_completed = sum(1 for s in batch.results.values() if s == RunStatus.COMPLETED.value)
    final_failed = sum(1 for s in batch.results.values() if s == RunStatus.FAILED.value)
    final_blocked = sum(1 for s in batch.results.values() if s == RunStatus.BLOCKED.value)

    if final_completed == total:
        batch.status = BatchStatus.COMPLETED
        event_type = events.EventType.BATCH_COMPLETED

        # Run batch-level validation (full gate sweep)
        validation_passed, validation_error = _run_batch_level_validation(workspace, batch)

        if not validation_passed:
            # Gates failed - change status to PARTIAL (tasks done, integration broken)
            batch.status = BatchStatus.PARTIAL
            event_type = events.EventType.BATCH_PARTIAL
            print("\n⚠️  Batch marked PARTIAL due to failed batch-level gates")
            print(f"Validation error: {validation_error}")

    elif final_completed == 0 and (final_failed > 0 or final_blocked > 0):
        batch.status = BatchStatus.FAILED
        event_type = events.EventType.BATCH_FAILED
    elif final_completed > 0:
        batch.status = BatchStatus.PARTIAL
        event_type = events.EventType.BATCH_PARTIAL
    else:
        batch.status = BatchStatus.CANCELLED
        event_type = events.EventType.BATCH_CANCELLED

    batch.completed_at = _utc_now()
    _save_batch(workspace, batch)

    # Emit final status event
    events.emit_for_workspace(
        workspace,
        event_type,
        {
            "batch_id": batch.id,
            "completed": final_completed,
            "failed": final_failed,
            "blocked": final_blocked,
            "total": total,
            "retries_used": max_retries,
        },
        print_event=True,
    )

    # Print retry summary
    if final_failed == 0:
        print("\n✓ All tasks succeeded after retries")
    else:
        print(f"\n⚠ {final_failed} task(s) still failing after {max_retries} retries")


def _run_batch_level_validation(workspace: Workspace, batch: BatchRun) -> tuple[bool, Optional[str]]:
    """Run full gate sweep after all tasks complete to catch cross-task inconsistencies.

    Args:
        workspace: The workspace
        batch: The batch run that just completed

    Returns:
        Tuple of (passed: bool, failure_summary: Optional[str])
        - passed=True means all gates passed
        - passed=False means gates failed, with summary of failures
    """
    from codeframe.core import gates

    print("\n[Conductor] Running batch-level validation (full gate sweep)...")

    # Run all auto-detected gates against the full workspace
    result = gates.run(workspace, gates=None, verbose=False, auto_install_deps=True)

    if result.passed:
        print("[Conductor] ✓ Batch-level validation passed")
        return True, None
    else:
        # Extract failure summary
        failure_summary = result.get_error_summary()
        if not failure_summary:
            failure_summary = "Gates failed (see individual gate outputs)"

        print(f"[Conductor] ✗ Batch-level validation failed:\n{failure_summary}")

        # Emit batch validation failed event
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_VALIDATION_FAILED,
            {
                "batch_id": batch.id,
                "failed_gates": [check.name for check in result.checks if check.status == gates.GateStatus.FAILED],
                "summary": failure_summary[:500],  # Truncate for event payload
            },
            print_event=True,
        )

        return False, failure_summary


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
        result_status = _execute_task_subprocess(workspace, task_id, batch.id, engine=batch.engine)

        # If task is BLOCKED, try supervisor resolution
        if result_status == RunStatus.BLOCKED.value:
            supervisor = get_supervisor(workspace)
            if supervisor.try_resolve_blocked_task(task_id):
                # Supervisor resolved the blocker - retry the task
                print("      [Supervisor] Retrying task after auto-resolution...")
                result_status = _execute_task_subprocess(workspace, task_id, batch.id, engine=batch.engine)

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
            print("      ✓ Completed")
        elif result_status == RunStatus.BLOCKED.value:
            blocked_count += 1
            events.emit_for_workspace(
                workspace,
                events.EventType.BATCH_TASK_BLOCKED,
                {"batch_id": batch.id, "task_id": task_id},
                print_event=True,
            )
            print("      ⊘ Blocked (requires human input)")
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
                print("\nStopping batch due to --on-failure=stop")
                break

        if on_event:
            on_event("batch_task_completed", {"task_id": task_id, "status": result_status})

    # Determine final batch status
    total = len(batch.task_ids)
    completed_count + failed_count + blocked_count

    if completed_count == total:
        batch.status = BatchStatus.COMPLETED
        event_type = events.EventType.BATCH_COMPLETED

        # Run batch-level validation (full gate sweep)
        validation_passed, validation_error = _run_batch_level_validation(workspace, batch)

        if not validation_passed:
            # Gates failed - change status to PARTIAL (tasks done, integration broken)
            batch.status = BatchStatus.PARTIAL
            event_type = events.EventType.BATCH_PARTIAL
            print("\n⚠️  Batch marked PARTIAL due to failed batch-level gates")
            print(f"Validation error: {validation_error}")

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


def _execute_parallel(
    workspace: Workspace,
    batch: BatchRun,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> None:
    """Execute tasks in parallel using dependency-aware groups.

    Creates an execution plan from task dependencies and executes each group
    in sequence. Tasks within a group run in parallel, up to max_parallel.

    Args:
        workspace: Target workspace
        batch: BatchRun to execute
        on_event: Optional callback for batch events

    Raises:
        CycleDetectedError: If circular dependencies are detected
    """
    # Create execution plan based on dependencies
    plan = create_execution_plan(workspace, batch.task_ids)

    print(f"\nExecution plan: {plan.num_groups} groups, {plan.total_tasks} tasks")
    if plan.can_run_parallel():
        print(f"Parallelizable groups found - using max {batch.max_parallel} workers")
    else:
        print("All tasks are sequential (chain dependencies)")

    completed_count = 0
    failed_count = 0
    blocked_count = 0
    task_index = 0  # Global task counter for progress display

    for group_idx, group in enumerate(plan.groups):
        # Check if batch was cancelled
        current_batch = get_batch(workspace, batch.id)
        if current_batch and current_batch.status == BatchStatus.CANCELLED:
            break

        # Check if any previous failure should stop execution
        if batch.on_failure == OnFailure.STOP and failed_count > 0:
            print("\nStopping batch due to --on-failure=stop")
            break

        group_size = len(group)
        print(f"\n{'─'*60}")
        print(f"Group {group_idx + 1}/{plan.num_groups}: {group_size} task(s)")

        if group_size == 1:
            # Single task - run directly
            task_id = group[0]
            task_index += 1
            result = _execute_single_task(
                workspace, batch, task_id, task_index, len(batch.task_ids), on_event
            )
            if result == RunStatus.COMPLETED.value:
                completed_count += 1
            elif result == RunStatus.BLOCKED.value:
                blocked_count += 1
            else:
                failed_count += 1
        else:
            # Multiple tasks - run in parallel
            effective_workers = min(group_size, batch.max_parallel)
            print(f"Running {group_size} tasks with {effective_workers} workers")

            # Execute group in parallel
            results = _execute_group_parallel(
                workspace, batch, group, task_index, len(batch.task_ids),
                effective_workers, on_event
            )

            # Process results
            for task_id, result_status in results.items():
                task_index += 1
                if result_status == RunStatus.COMPLETED.value:
                    completed_count += 1
                elif result_status == RunStatus.BLOCKED.value:
                    blocked_count += 1
                else:
                    failed_count += 1

                # Check stop on failure within parallel group
                if batch.on_failure == OnFailure.STOP and failed_count > 0:
                    # Can't stop mid-group, but will stop after group completes
                    pass

    # Determine final batch status
    total = len(batch.task_ids)
    completed_count + failed_count + blocked_count

    if completed_count == total:
        batch.status = BatchStatus.COMPLETED
        event_type = events.EventType.BATCH_COMPLETED

        # Run batch-level validation (full gate sweep)
        validation_passed, validation_error = _run_batch_level_validation(workspace, batch)

        if not validation_passed:
            # Gates failed - change status to PARTIAL (tasks done, integration broken)
            batch.status = BatchStatus.PARTIAL
            event_type = events.EventType.BATCH_PARTIAL
            print("\n⚠️  Batch marked PARTIAL due to failed batch-level gates")
            print(f"Validation error: {validation_error}")

    elif completed_count == 0 and (failed_count > 0 or blocked_count > 0):
        batch.status = BatchStatus.FAILED
        event_type = events.EventType.BATCH_FAILED
    elif completed_count > 0:
        batch.status = BatchStatus.PARTIAL
        event_type = events.EventType.BATCH_PARTIAL
    else:
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
            "strategy": "parallel",
            "groups": plan.num_groups,
        },
        print_event=True,
    )

    # Print summary
    print(f"\nBatch {batch.status.value.lower()}: {completed_count}/{total} tasks completed")
    print(f"  Execution: {plan.num_groups} groups (parallel strategy)")
    if failed_count > 0:
        print(f"  Failed: {failed_count}")
    if blocked_count > 0:
        print(f"  Blocked: {blocked_count}")


def _execute_single_task(
    workspace: Workspace,
    batch: BatchRun,
    task_id: str,
    position: int,
    total: int,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> str:
    """Execute a single task and update batch results.

    Helper for parallel execution that handles one task.

    Returns:
        RunStatus value string
    """
    # Emit task queued event
    events.emit_for_workspace(
        workspace,
        events.EventType.BATCH_TASK_QUEUED,
        {"batch_id": batch.id, "task_id": task_id, "position": position},
        print_event=True,
    )

    # Get task info for display
    task = tasks.get(workspace, task_id)
    task_title = task.title if task else task_id

    print(f"\n[{position}/{total}] Starting task {task_id}: {task_title}")

    # Emit task started event
    events.emit_for_workspace(
        workspace,
        events.EventType.BATCH_TASK_STARTED,
        {"batch_id": batch.id, "task_id": task_id},
        print_event=True,
    )

    if on_event:
        on_event("batch_task_started", {"task_id": task_id, "position": position})

    # Execute task via subprocess
    result_status = _execute_task_subprocess(workspace, task_id, batch.id, engine=batch.engine)

    # If task is BLOCKED, try supervisor resolution
    if result_status == RunStatus.BLOCKED.value:
        supervisor = get_supervisor(workspace)
        if supervisor.try_resolve_blocked_task(task_id):
            # Supervisor resolved the blocker - retry the task
            print("      [Supervisor] Retrying task after auto-resolution...")
            result_status = _execute_task_subprocess(workspace, task_id, batch.id, engine=batch.engine)

    # Record result
    batch.results[task_id] = result_status
    _save_batch(workspace, batch)

    # Emit appropriate event based on result
    if result_status == RunStatus.COMPLETED.value:
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_TASK_COMPLETED,
            {"batch_id": batch.id, "task_id": task_id},
            print_event=True,
        )
        print("      ✓ Completed")
    elif result_status == RunStatus.BLOCKED.value:
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_TASK_BLOCKED,
            {"batch_id": batch.id, "task_id": task_id},
            print_event=True,
        )
        print("      ⊘ Blocked (requires human input)")
    else:
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_TASK_FAILED,
            {"batch_id": batch.id, "task_id": task_id, "status": result_status},
            print_event=True,
        )
        print(f"      ✗ Failed: {result_status}")

    if on_event:
        on_event("batch_task_completed", {"task_id": task_id, "status": result_status})

    return result_status


def _execute_group_parallel(
    workspace: Workspace,
    batch: BatchRun,
    group: list[str],
    start_index: int,
    total: int,
    max_workers: int,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> dict[str, str]:
    """Execute a group of tasks in parallel.

    Args:
        workspace: Target workspace
        batch: BatchRun being executed
        group: List of task IDs to execute concurrently
        start_index: Starting task index for progress display
        total: Total tasks in batch
        max_workers: Maximum concurrent workers
        on_event: Optional callback for events

    Returns:
        Dict mapping task_id -> RunStatus value
    """
    results: dict[str, str] = {}

    # Show which tasks are starting
    for i, task_id in enumerate(group):
        task = tasks.get(workspace, task_id)
        task_title = task.title if task else task_id
        print(f"  [{start_index + i + 1}/{total}] Queued: {task_id}: {task_title}")

        # Emit task queued event
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_TASK_QUEUED,
            {"batch_id": batch.id, "task_id": task_id, "position": start_index + i + 1, "parallel": True},
            print_event=True,
        )

    def execute_task(task_id: str) -> tuple[str, str]:
        """Execute a single task and return (task_id, status)."""
        # Emit task started event
        events.emit_for_workspace(
            workspace,
            events.EventType.BATCH_TASK_STARTED,
            {"batch_id": batch.id, "task_id": task_id, "parallel": True},
            print_event=True,
        )

        if on_event:
            on_event("batch_task_started", {"task_id": task_id, "parallel": True})

        # Execute via subprocess
        result_status = _execute_task_subprocess(workspace, task_id, batch.id, engine=batch.engine)

        # Record result (thread-safe due to GIL for simple dict operations)
        batch.results[task_id] = result_status
        _save_batch(workspace, batch)

        return task_id, result_status

    # Execute tasks in parallel using thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(execute_task, tid): tid for tid in group}

        for future in as_completed(futures):
            task_id, result_status = future.result()
            results[task_id] = result_status

            # Get task info for display
            task = tasks.get(workspace, task_id)
            task_title = task.title if task else task_id

            # Emit appropriate event and print result
            if result_status == RunStatus.COMPLETED.value:
                events.emit_for_workspace(
                    workspace,
                    events.EventType.BATCH_TASK_COMPLETED,
                    {"batch_id": batch.id, "task_id": task_id, "parallel": True},
                    print_event=True,
                )
                print(f"  ✓ {task_id}: Completed")
            elif result_status == RunStatus.BLOCKED.value:
                events.emit_for_workspace(
                    workspace,
                    events.EventType.BATCH_TASK_BLOCKED,
                    {"batch_id": batch.id, "task_id": task_id, "parallel": True},
                    print_event=True,
                )
                print(f"  ⊘ {task_id}: Blocked")
            else:
                events.emit_for_workspace(
                    workspace,
                    events.EventType.BATCH_TASK_FAILED,
                    {"batch_id": batch.id, "task_id": task_id, "status": result_status, "parallel": True},
                    print_event=True,
                )
                print(f"  ✗ {task_id}: Failed ({result_status})")

            if on_event:
                on_event("batch_task_completed", {"task_id": task_id, "status": result_status, "parallel": True})

    return results


def _execute_task_subprocess(
    workspace: Workspace,
    task_id: str,
    batch_id: Optional[str] = None,
    engine: str = "plan",
) -> str:
    """Execute a single task via subprocess.

    Runs `cf work start <task_id> --execute --engine <engine>` as a subprocess.

    Args:
        workspace: Target workspace
        task_id: Task to execute
        batch_id: Optional batch ID for process tracking (enables force stop)
        engine: Agent engine to use ("plan" or "react")

    Returns:
        RunStatus value string (COMPLETED, FAILED, BLOCKED)
    """
    # Build command
    cmd = [
        sys.executable, "-m", "codeframe.cli.app",
        "work", "start", task_id, "--execute",
        "--engine", engine,
    ]

    process = None
    try:
        # Use Popen instead of run for process tracking
        process = subprocess.Popen(
            cmd,
            cwd=workspace.repo_path,
            stdout=None,  # Let output flow to terminal
            stderr=None,
            text=True,
        )

        # Track process if batch_id provided (thread-safe)
        if batch_id:
            with _active_processes_lock:
                if batch_id not in _active_processes:
                    _active_processes[batch_id] = {}
                _active_processes[batch_id][task_id] = process

        # Wait for completion (outside lock to avoid blocking)
        returncode = process.wait()

        # Untrack process (thread-safe)
        if batch_id:
            with _active_processes_lock:
                if batch_id in _active_processes:
                    _active_processes[batch_id].pop(task_id, None)
                    if not _active_processes[batch_id]:
                        _active_processes.pop(batch_id, None)

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
        if returncode == 0:
            return RunStatus.COMPLETED.value
        else:
            return RunStatus.FAILED.value

    except Exception as e:
        print(f"      Error executing task: {e}")
        # Cleanup on exception (thread-safe)
        if batch_id:
            with _active_processes_lock:
                if batch_id in _active_processes:
                    _active_processes[batch_id].pop(task_id, None)
                    if not _active_processes[batch_id]:
                        _active_processes.pop(batch_id, None)
        return RunStatus.FAILED.value


def _save_batch(workspace: Workspace, batch: BatchRun) -> None:
    """Save or update a batch record in the database.

    Uses a thread lock to prevent SQLite "database is locked" errors
    when multiple workers try to update batch status concurrently.
    """
    task_ids_json = json.dumps(batch.task_ids)
    results_json = json.dumps(batch.results) if batch.results else None
    completed_at = batch.completed_at.isoformat() if batch.completed_at else None

    with _batch_db_lock:
        conn = get_db_connection(workspace)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO batch_runs
                (id, workspace_id, task_ids, status, strategy, max_parallel, on_failure,
                 started_at, completed_at, results, engine)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    batch.engine,
                ),
            )
            conn.commit()
        finally:
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
        engine=row[10] if len(row) > 10 and row[10] else "plan",
    )
