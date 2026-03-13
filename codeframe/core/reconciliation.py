"""Continuous reconciliation engine for batch execution.

Periodically checks if tasks have been externally modified (GitHub issue
closed, task manually completed, blocker resolved) and adjusts the running
batch accordingly.

This module is headless (no FastAPI, no HTTP). It exposes a standalone
ReconciliationEngine that can be driven by a background thread in the
conductor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from codeframe.core import blockers, tasks
from codeframe.core.state_machine import TaskStatus

if TYPE_CHECKING:
    from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


@dataclass
class ExternalStateChange:
    """A detected external change to a task's state."""

    task_id: str
    change_type: str  # "completed", "closed", "blocker_resolved"
    source: str  # "manual", "github"
    details: dict = field(default_factory=dict)


@dataclass
class ReconciliationResult:
    """Accumulated result from a reconciliation check."""

    changes_detected: list[ExternalStateChange] = field(default_factory=list)
    tasks_skipped: list[str] = field(default_factory=list)
    tasks_requeued: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ReconciliationEngine:
    """Checks tasks for external state changes and applies adjustments.

    The engine is stateless per invocation — call check_all_active() to scan,
    then apply_changes() to act on the results.

    Args:
        workspace: The workspace to check tasks in.
        github_checker: Optional callable(task_id, task) -> list[ExternalStateChange]
            for GitHub issue state sync. If None, GitHub checks are skipped.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        github_checker: Optional[Callable] = None,
    ) -> None:
        self._workspace = workspace
        self._github_checker = github_checker

    def check_task(self, task_id: str) -> list[ExternalStateChange]:
        """Check a single task for external state changes.

        Returns a list of detected changes (may be empty).
        """
        task = tasks.get(self._workspace, task_id)
        if task is None:
            return []

        changes: list[ExternalStateChange] = []

        # Task was completed externally (e.g., manually marked DONE)
        if task.status == TaskStatus.DONE:
            changes.append(ExternalStateChange(
                task_id=task_id,
                change_type="completed",
                source="manual",
                details={"status": task.status.value},
            ))

        # Task is blocked but all blockers have been answered
        elif task.status == TaskStatus.BLOCKED:
            task_blockers = blockers.list_for_task(self._workspace, task_id)
            if task_blockers and all(
                b.status.value in ("ANSWERED", "RESOLVED") for b in task_blockers
            ):
                changes.append(ExternalStateChange(
                    task_id=task_id,
                    change_type="blocker_resolved",
                    source="manual",
                    details={"blockers_resolved": len(task_blockers)},
                ))

        # Check GitHub issue state if checker is available
        if self._github_checker:
            try:
                gh_changes = self._github_checker(task_id, task)
                changes.extend(gh_changes)
            except Exception as exc:
                logger.warning("GitHub check failed for task %s: %s", task_id, exc)

        return changes

    def check_all_active(
        self, active_task_ids: list[str]
    ) -> ReconciliationResult:
        """Check all active tasks for external state changes.

        Individual task check failures are caught and logged — a single
        failure never crashes the entire reconciliation pass.
        """
        result = ReconciliationResult()

        for task_id in active_task_ids:
            try:
                changes = self.check_task(task_id)
                result.changes_detected.extend(changes)
            except Exception as exc:
                error_msg = f"Reconciliation check failed for {task_id}: {exc}"
                result.errors.append(error_msg)
                logger.warning(error_msg)

        return result

    def apply_changes(
        self,
        result: ReconciliationResult,
        batch: object,
        active_processes: dict,
    ) -> None:
        """Apply detected changes to the batch and running processes.

        For completed/closed tasks: terminate the subprocess and skip.
        For blocker_resolved tasks: mark for re-queue.

        All exceptions are caught and appended to result.errors.
        """
        for change in result.changes_detected:
            try:
                if change.change_type in ("completed", "closed"):
                    # Terminate subprocess if running
                    proc = active_processes.get(change.task_id)
                    if proc is not None:
                        try:
                            proc.terminate()
                        except OSError:
                            pass  # Process already dead

                    result.tasks_skipped.append(change.task_id)

                    # Update batch results
                    if hasattr(batch, "results"):
                        status = "COMPLETED" if change.change_type == "completed" else "FAILED"
                        batch.results[change.task_id] = status

                    logger.info(
                        "Task %s %s externally (%s) — skipped in batch",
                        change.task_id, change.change_type, change.source,
                    )

                elif change.change_type == "blocker_resolved":
                    result.tasks_requeued.append(change.task_id)

                    # Update batch results to signal re-queue
                    if hasattr(batch, "results"):
                        batch.results[change.task_id] = "READY"

                    logger.info(
                        "Task %s blocker resolved — re-queued",
                        change.task_id,
                    )

            except Exception as exc:
                error_msg = f"Failed to apply change for {change.task_id}: {exc}"
                result.errors.append(error_msg)
                logger.warning(error_msg)
