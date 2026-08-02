"""Batch reconciliation writes states nothing consumes (#921 / P1.3).

Three defects, each verified against the code before being fixed:

1. **The requeue marker is dead.** ``apply_changes`` wrote the literal
   ``"READY"`` into ``batch.results`` for a blocker-resolved task. ``RunStatus``
   has no such value, and ``resume_batch``'s retryable set is
   ``{"FAILED", "BLOCKED", "RUNNING"}`` — and the task *is* in ``results``, so
   the ``tid not in batch.results`` fallback does not save it either. The task
   is permanently ineligible for ``cf work batch resume`` while
   ``RECONCILIATION_TASK_REQUEUED`` tells the user it will re-run.

2. **An external completion is overwritten.** The reconciler kills the
   subprocess and records ``COMPLETED``; the worker then sees the non-zero exit
   and unconditionally does ``batch.results[task_id] = result_status``. The
   user's manual DONE is silently reverted and counted as a failure.
   ``fail_run`` compounds it by transitioning DONE → READY.

3. **``github_checker`` is advertised but unwired.** Neither
   ``_start_reconciliation_thread`` call site passes it.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return create_or_load_workspace(ws_dir)


def _batch_with(results: dict, task_ids: list[str]):
    """A minimal stand-in carrying just what the code under test touches."""
    class _Batch:
        pass

    b = _Batch()
    b.id = "batch-921"
    b.task_ids = list(task_ids)
    b.results = dict(results)
    return b


def _change(task_id: str, change_type: str):
    from codeframe.core.reconciliation import ExternalStateChange

    return ExternalStateChange(
        task_id=task_id,
        change_type=change_type,
        source="test",
        details={},
    )


# ---------------------------------------------------------------------------
# 1. batch.results must only hold RunStatus values
# ---------------------------------------------------------------------------


class TestRequeueMarker:
    def test_no_non_runstatus_value_is_written(self, workspace):
        """AC1. 'READY' is not a RunStatus — nothing downstream consumes it."""
        from codeframe.core.reconciliation import (
            ReconciliationEngine,
            ReconciliationResult,
        )
        from codeframe.core.runtime import RunStatus

        engine = ReconciliationEngine(workspace)
        batch = _batch_with({"t1": "RUNNING"}, ["t1"])
        result = ReconciliationResult()
        result.changes_detected.append(_change("t1", "blocker_resolved"))

        engine.apply_changes(result, batch, active_processes={})

        valid = {s.value for s in RunStatus}
        for task_id, value in batch.results.items():
            assert value in valid, f"{task_id} holds {value!r}, not a RunStatus"

    def test_a_requeued_task_is_resume_eligible(self, workspace):
        """AC2. The user is told it will re-run, so resume must pick it up."""
        from codeframe.core.reconciliation import (
            ReconciliationEngine,
            ReconciliationResult,
        )

        engine = ReconciliationEngine(workspace)
        batch = _batch_with({"t1": "RUNNING", "t2": "COMPLETED"}, ["t1", "t2"])
        result = ReconciliationResult()
        result.changes_detected.append(_change("t1", "blocker_resolved"))

        engine.apply_changes(result, batch, active_processes={})

        retryable = {"FAILED", "BLOCKED", "RUNNING"}
        eligible = [
            tid for tid in batch.task_ids
            if batch.results.get(tid) in retryable or tid not in batch.results
        ]
        assert "t1" in eligible, (
            "a re-queued task is permanently ineligible for `cf work batch resume`"
        )
        assert "t2" not in eligible, "a completed task must stay done"

    def test_the_requeue_is_still_reported(self, workspace):
        """The fix must not silently drop the signal it was meant to carry."""
        from codeframe.core.reconciliation import (
            ReconciliationEngine,
            ReconciliationResult,
        )

        engine = ReconciliationEngine(workspace)
        batch = _batch_with({"t1": "RUNNING"}, ["t1"])
        result = ReconciliationResult()
        result.changes_detected.append(_change("t1", "blocker_resolved"))

        engine.apply_changes(result, batch, active_processes={})

        assert "t1" in result.tasks_requeued


# ---------------------------------------------------------------------------
# 2. An external completion must survive the worker
# ---------------------------------------------------------------------------


class TestExternalCompletionSurvives:
    def test_a_completed_result_is_not_overwritten_by_a_failure(self, workspace):
        """AC3. The reconciler kills the subprocess, the worker sees the
        non-zero exit and reports FAILED — the manual DONE must win."""
        from codeframe.core.conductor import _record_task_result

        batch = _batch_with({"t1": "COMPLETED"}, ["t1"])

        _record_task_result(batch, "t1", "FAILED")

        assert batch.results["t1"] == "COMPLETED", (
            "the user's manual DONE was reverted and counted as a failure"
        )

    def test_an_ordinary_result_is_recorded(self, workspace):
        from codeframe.core.conductor import _record_task_result

        batch = _batch_with({}, ["t1"])

        _record_task_result(batch, "t1", "FAILED")

        assert batch.results["t1"] == "FAILED"

    def test_a_running_placeholder_is_replaced(self, workspace):
        """Only terminal results are protected — RUNNING must still resolve."""
        from codeframe.core.conductor import _record_task_result

        batch = _batch_with({"t1": "RUNNING"}, ["t1"])

        _record_task_result(batch, "t1", "COMPLETED")

        assert batch.results["t1"] == "COMPLETED"

    def test_fail_run_does_not_disturb_a_done_task(self, workspace):
        """Pins the guarantee, which turned out to come from the state machine.

        The issue expected fail_run to revert the manual DONE via a permitted
        DONE -> READY transition. It does not: fail_run transitions the task to
        *FAILED*, and DONE only permits {READY, MERGED}, so the state machine
        refuses it. The damage was entirely in the batch accounting above.

        fail_run should nonetheless not leave that refusal as an escaping
        exception after it has already written the run row.
        """
        from codeframe.core import runtime, tasks
        from codeframe.core.state_machine import TaskStatus

        task = tasks.create(workspace, title="t", description="d",
                            status=TaskStatus.READY)
        run = runtime.start_task_run(workspace, task.id)
        tasks.update_status(workspace, task.id, TaskStatus.DONE)

        runtime.fail_run(workspace, run.id, reason="subprocess killed")

        assert tasks.get(workspace, task.id).status == TaskStatus.DONE
        assert runtime.get_run(workspace, run.id).status.value == "FAILED"

    def test_fail_run_still_fails_a_running_task(self, workspace):
        """The ordinary path must keep working."""
        from codeframe.core import runtime, tasks
        from codeframe.core.state_machine import TaskStatus

        task = tasks.create(workspace, title="t", description="d",
                            status=TaskStatus.READY)
        run = runtime.start_task_run(workspace, task.id)

        runtime.fail_run(workspace, run.id, reason="boom")

        assert tasks.get(workspace, task.id).status == TaskStatus.FAILED


# ---------------------------------------------------------------------------
# 3. No advertised-but-unwired parameter
# ---------------------------------------------------------------------------


class TestNoDeadGithubChecker:
    def test_the_parameter_is_gone(self):
        """AC4. It was passed at neither call site, so it advertised a
        capability that did not exist. Removed rather than half-built; a real
        issue-state check is its own feature, with its own auth and rate limits.
        """
        import inspect

        from codeframe.core import conductor
        from codeframe.core.reconciliation import ReconciliationEngine

        assert "github_checker" not in inspect.signature(
            ReconciliationEngine.__init__
        ).parameters
        assert "github_checker" not in inspect.signature(
            conductor._start_reconciliation_thread
        ).parameters

    def test_no_reference_survives(self):
        """A leftover branch or docstring claim is the same lie."""
        from pathlib import Path

        for module in ("core/reconciliation.py", "core/conductor.py"):
            text = Path("codeframe") / module
            assert "github_checker" not in text.read_text(), (
                f"{module} still references github_checker"
            )
