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
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from codeframe.core import blockers, tasks
from codeframe.core.state_machine import TaskStatus

if TYPE_CHECKING:
    from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)

#: How long an **open** answer is trusted. Two reconciliation ticks: long
#: enough to halve the call rate, short enough that a closure is noticed before
#: a serial batch works through much of its queue. A longer window (300s was
#: the first cut) makes the feature mostly decorative — the issue closes, the
#: cached "open" hides it, and the executor launches the agent anyway.
#:
#: Cost, worst case: one call per linked task per 60s. A batch with 20 imported
#: tasks running an hour is ~1200 calls against GitHub's 5000/hour authenticated
#: limit, and the first failure disables the checker entirely.
_ISSUE_STATE_OPEN_TTL_SECONDS = 60.0

#: Bound on distinct issues cached per batch. Reconciliation only ever asks
#: about the batch's own tasks, so this is a runaway guard, not a tuning knob.
_ISSUE_STATE_CACHE_MAX = 512


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


def _default_fetch_issue_state(pat: str, repo: str, number: int) -> str:
    """Fetch one issue's ``"open"``/``"closed"`` state from GitHub.

    Runs the async service call to completion on this thread — reconciliation
    is a plain daemon thread with no event loop of its own.
    """
    import asyncio

    from codeframe.core.github_issues_service import get_issue

    issue = asyncio.run(get_issue(pat, repo, number))
    return issue["state"]


def _default_pat() -> Optional[str]:
    """Resolve the machine-wide GitHub PAT, or ``None`` if there is none.

    Same source and same limitation as the auto-close path (``tasks.
    _dispatch_github_autoclose``): reconciliation runs on a background thread
    with no request-scoped user, so per-user stored PATs are not reachable here.
    """
    try:
        from codeframe.core.credentials import CredentialManager, CredentialProvider

        return CredentialManager().get_credential(CredentialProvider.GIT_GITHUB)
    except Exception:  # noqa: BLE001 - never break a batch over credential lookup
        logger.debug("GitHub PAT lookup failed for reconciliation", exc_info=True)
        return None


class GitHubIssueState:
    """Answers "has this task's linked GitHub issue been closed?" (#1032).

    #921 removed an injectable issue-check parameter because it was wired at no
    call site. The hard part it skipped is cost: reconciliation ticks every 30s
    over every active task, so the naive version is one API call per task per
    tick against a single machine-wide PAT. Three things bound that, and each
    one is a test in ``test_github_issue_reconciliation_1032.py``:

    * A task with no ``github_issue_number`` (or no source URL to name a repo)
      never reaches the network. Most tasks are not imported from GitHub.
    * Answers are cached per ``(repo, number)``. **Closed** is cached for the
      life of the checker — it is terminal for a batch's purposes. **Open** is
      cached only briefly (``open_ttl_seconds``), because an open answer is
      exactly the one that goes stale in a way that matters: cache it for
      minutes and the issue closes, the batch reaches the task, and the agent
      runs anyway.
    * The first missing PAT or GitHub failure **disables the checker for the
      rest of the batch** and logs once. A GitHub outage must never fail a
      batch, and retrying every 30s through one is how you get rate-limited —
      so this doubles as the back-off.

    The repo comes from the task's own ``external_url``, not the workspace's
    current connection, matching auto-close (#565): a workspace may have been
    reconnected to a different repository since the task was imported.
    """

    def __init__(
        self,
        *,
        fetch: Optional[Callable[[str, str, int], str]] = None,
        pat: Optional[str] = None,
        open_ttl_seconds: float = _ISSUE_STATE_OPEN_TTL_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch if fetch is not None else _default_fetch_issue_state
        self._pat = pat
        self._pat_resolved = pat is not None
        self._open_ttl = open_ttl_seconds
        self._now = now
        #: Issues known closed. Never re-fetched — closed is terminal here.
        self._closed: set[tuple[str, int]] = set()
        #: Issues seen open, with the time the answer stops being trusted.
        self._open_until: dict[tuple[str, int], float] = {}
        self._disabled = False

    def is_closed(self, task) -> bool:
        """Whether the task's linked issue is closed on GitHub.

        Returns ``False`` — never raises — for every "don't know" case: no
        linked issue, no PAT, GitHub unreachable, checker already disabled.
        Reconciliation acts on a ``True`` only, so an unknown state leaves the
        task running, which is the safe direction.
        """
        if self._disabled:
            return False

        # Type-check rather than trust: this runs on a background thread, and
        # anything raising here would surface as a reconciliation *error* on an
        # otherwise healthy tick. ``_repo_from_issue_url`` only guards against
        # ValueError/AttributeError, so a non-str URL would escape it.
        number = getattr(task, "github_issue_number", None)
        url = getattr(task, "external_url", None)
        if not isinstance(number, int) or not isinstance(url, str):
            return False
        repo = tasks._repo_from_issue_url(url)
        if repo is None:
            return False

        key = (repo, number)
        if key in self._closed:
            return True
        if self._open_until.get(key, 0.0) > self._now():
            return False

        pat = self._resolve_pat()
        if pat is None:
            self._disable("no GitHub PAT is configured")
            return False

        try:
            state = self._fetch(pat, repo, int(number))
        except Exception as exc:  # noqa: BLE001 - an outage must not fail a batch
            self._disable(f"GitHub issue lookup failed ({exc})")
            return False

        if len(self._closed) + len(self._open_until) >= _ISSUE_STATE_CACHE_MAX:
            self._open_until.clear()  # the cheap half to rebuild

        if str(state).lower() == "closed":
            self._closed.add(key)
            return True
        self._open_until[key] = self._now() + self._open_ttl
        return False

    def _resolve_pat(self) -> Optional[str]:
        if not self._pat_resolved:
            self._pat = _default_pat()
            self._pat_resolved = True
        return self._pat

    def _disable(self, reason: str) -> None:
        """Stop checking for the rest of this batch, saying why exactly once."""
        self._disabled = True
        logger.warning(
            "GitHub issue reconciliation disabled for this batch: %s", reason
        )


class ReconciliationEngine:
    """Checks tasks for external state changes and applies adjustments.

    The engine is stateless per invocation — call check_all_active() to scan,
    then apply_changes() to act on the results.

    Args:
        workspace: The workspace to check tasks in.
        issue_state: GitHub issue-state checker. Constructed by default, so
            both conductor call sites get it without passing anything — unlike
            the parameter #921 removed, which was passed at neither. Injected
            by tests.
    """

    def __init__(
        self,
        workspace: Workspace,
        issue_state: Optional[GitHubIssueState] = None,
    ) -> None:
        self._workspace = workspace
        self._issue_state = issue_state if issue_state is not None else GitHubIssueState()

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

        # The task's linked GitHub issue was closed by someone outside this
        # batch — an external completion, exactly like a task marked DONE in
        # the UI (#1032).
        #
        # Deliberately NOT an `elif` off the blocker branch: a BLOCKED task
        # whose blockers are still unanswered falls through both branches
        # above, and that task is exactly the one worth asking about — the
        # human may have resolved the work on GitHub instead of answering.
        #
        # Guarded on `not changes` so it costs nothing when a local signal
        # already fired, and on `not DONE` because the first branch has already
        # handled those — otherwise it would be a wasted call every tick for
        # the rest of the run. GitHubIssueState never raises and answers False
        # when it does not know, so an outage leaves the batch as it was.
        if not changes and task.status != TaskStatus.DONE and self._issue_state.is_closed(task):
            changes.append(ExternalStateChange(
                task_id=task_id,
                change_type="completed",
                source="github",
                details={
                    "issue_number": task.github_issue_number,
                    "issue_url": task.external_url,
                },
            ))

        return changes

    def _mark_task_done(self, task_id: str) -> None:
        """Bring the local task row in line with the closed issue (#1032).

        The ``source="manual"`` path needs nothing here: the row is *already*
        DONE, which is how the change was detected. A GitHub closure sets
        nothing, so without this the batch records COMPLETED while the board
        still shows the task READY — and the next batch picks it up again.

        Nothing goes straight to DONE: the state machine only allows it from
        IN_PROGRESS, and only READY from BACKLOG. So this walks the same path a
        real run takes — and it must start from BACKLOG, because that is what
        ``tasks.create`` defaults to and therefore what the GitHub importer
        (#565) produces. Imported tasks sitting in BACKLOG are the *primary*
        case for this feature, not an edge one.

        Best-effort throughout: the batch-level record stands on its own, so a
        refused or failing transition is logged, not raised.
        """
        walk = {
            TaskStatus.BACKLOG: (TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.DONE),
            TaskStatus.READY: (TaskStatus.IN_PROGRESS, TaskStatus.DONE),
            TaskStatus.BLOCKED: (TaskStatus.IN_PROGRESS, TaskStatus.DONE),
            TaskStatus.FAILED: (TaskStatus.IN_PROGRESS, TaskStatus.DONE),
            TaskStatus.IN_PROGRESS: (TaskStatus.DONE,),
        }
        try:
            task = tasks.get(self._workspace, task_id)
            if task is None:
                return
            steps = walk.get(task.status)
            if steps is None:  # already DONE, or MERGED (terminal)
                return
            for step in steps:
                # The final DONE fires the auto-close dispatch (#565) when the
                # task opted in. The issue is already closed, so that PATCH is
                # a no-op — not worth a special path to avoid.
                tasks.update_status(self._workspace, task_id, step)
        except Exception as exc:  # noqa: BLE001 - accounting must not break
            logger.warning(
                "Could not mark task %s DONE after its GitHub issue closed: %s",
                task_id, exc,
            )

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
                if change.source == "github" and change.change_type == "completed":
                    self._mark_task_done(change.task_id)

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

                    # Clear any recorded outcome instead of writing "READY".
                    # RunStatus has no such value, and resume_batch's retryable
                    # set is {FAILED, BLOCKED, RUNNING} — so the marker made the
                    # task permanently ineligible for `cf work batch resume`
                    # while RECONCILIATION_TASK_REQUEUED told the user it would
                    # re-run. With no entry at all, resume's `tid not in
                    # batch.results` branch picks it up, which is what
                    # "re-queued" means. (#921)
                    if hasattr(batch, "results"):
                        batch.results.pop(change.task_id, None)

                    logger.info(
                        "Task %s blocker resolved — re-queued",
                        change.task_id,
                    )

            except Exception as exc:
                error_msg = f"Failed to apply change for {change.task_id}: {exc}"
                result.errors.append(error_msg)
                logger.warning(error_msg)
