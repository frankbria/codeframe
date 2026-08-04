"""Workers must honor an externally-recorded completion (#1032).

#921 added ``_record_task_result`` so a reconciler-recorded COMPLETED survives
the worker's own verdict — but tested the helper in isolation and never checked
that the executors call it. They mostly did not: of the five sites that wrote
``batch.results[task_id]``, exactly one used the guard, and the one that did was
the *parallel* path. On the default ``--strategy serial`` the guard was dead
code, so the GitHub reconciliation added by #1032 would:

* run a task whose linked issue was already closed before it started, and
* overwrite the COMPLETED with FAILED when the reconciler killed the subprocess
  mid-run and the worker saw the non-zero exit.

These tests drive the real executors with a stubbed subprocess.
"""

import pytest

from codeframe.core import conductor

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return create_or_load_workspace(ws_dir)


def _make_batch(workspace, task_ids, results=None):
    batch = conductor.create_batch(workspace, task_ids, strategy="serial")
    batch.results.update(results or {})
    return batch


@pytest.fixture
def three_tasks(workspace):
    from codeframe.core import tasks
    from codeframe.core.state_machine import TaskStatus

    return [
        tasks.create(
            workspace, title=f"task {i}", description="", status=TaskStatus.READY
        ).id
        for i in range(3)
    ]


class TestSerialSkipsAnExternallyCompletedTask:
    def test_a_task_already_recorded_COMPLETED_is_not_executed(
        self, workspace, three_tasks, monkeypatch
    ):
        """Its linked GitHub issue closed before the batch reached it."""
        executed = []

        def fake_subprocess(ws, task_id, batch_id, **kwargs):
            executed.append(task_id)
            return "COMPLETED"

        monkeypatch.setattr(
            conductor, "_execute_task_subprocess", fake_subprocess
        )
        monkeypatch.setattr(conductor, "_start_reconciliation_thread",
                            lambda *a, **k: __import__("threading").Event())

        batch = _make_batch(workspace, three_tasks, {three_tasks[1]: "COMPLETED"})
        conductor._execute_serial(workspace, batch)

        assert three_tasks[1] not in executed, (
            "ran a task that was already completed outside the batch"
        )
        assert executed == [three_tasks[0], three_tasks[2]]

    def test_the_skipped_task_stays_COMPLETED(
        self, workspace, three_tasks, monkeypatch
    ):
        monkeypatch.setattr(
            conductor, "_execute_task_subprocess",
            lambda ws, tid, bid, **kw: "COMPLETED",
        )
        monkeypatch.setattr(conductor, "_start_reconciliation_thread",
                            lambda *a, **k: __import__("threading").Event())

        batch = _make_batch(workspace, three_tasks, {three_tasks[1]: "COMPLETED"})
        conductor._execute_serial(workspace, batch)

        assert batch.results[three_tasks[1]] == "COMPLETED"


class TestSerialDoesNotOverwriteAnExternalCompletion:
    def test_a_completion_recorded_mid_run_survives_the_workers_failure(
        self, workspace, three_tasks, monkeypatch
    ):
        """The reconciler kills the subprocess, so the worker reports FAILED.
        The external COMPLETED must win — this is exactly what #921's helper
        was for, and the serial path was not calling it."""
        target = three_tasks[0]

        def fake_subprocess(ws, task_id, batch_id, **kwargs):
            if task_id == target:
                # Reconciliation recorded the external completion while the
                # subprocess was running, then terminated it.
                ws_batch.results[task_id] = "COMPLETED"
                return "FAILED"
            return "COMPLETED"

        monkeypatch.setattr(conductor, "_execute_task_subprocess", fake_subprocess)
        monkeypatch.setattr(conductor, "_start_reconciliation_thread",
                            lambda *a, **k: __import__("threading").Event())

        ws_batch = _make_batch(workspace, three_tasks)
        conductor._execute_serial(workspace, ws_batch)

        assert ws_batch.results[target] == "COMPLETED", (
            "the external completion was reverted and counted as a failure"
        )


class TestAccountingFollowsTheGuardedResult:
    """Preserving the result is only half of it — the tally must agree.

    Otherwise the reconciler's COMPLETED sits in ``batch.results`` while
    ``failed_count`` counts the worker's discarded FAILED, and the batch
    finalizes as FAILED/PARTIAL with a full set of COMPLETED results.
    """

    def test_serial_batch_does_not_finish_FAILED_with_a_completed_result(
        self, workspace, three_tasks, monkeypatch
    ):
        target = three_tasks[0]

        def fake_subprocess(ws, task_id, batch_id, **kwargs):
            if task_id == target:
                batch.results[task_id] = "COMPLETED"  # reconciler, mid-run
                return "FAILED"
            return "COMPLETED"

        monkeypatch.setattr(conductor, "_execute_task_subprocess", fake_subprocess)
        monkeypatch.setattr(conductor, "_start_reconciliation_thread",
                            lambda *a, **k: __import__("threading").Event())

        batch = _make_batch(workspace, three_tasks)
        conductor._execute_serial(workspace, batch)

        assert set(batch.results.values()) == {"COMPLETED"}
        final = conductor.get_batch(workspace, batch.id)
        assert final.status.value == "COMPLETED", (
            f"every task recorded COMPLETED but the batch finalized as "
            f"{final.status.value}"
        )


class TestSingleTaskGroupsAreSkippedToo:
    def test_execute_single_task_skips_an_external_completion(
        self, workspace, three_tasks, monkeypatch
    ):
        """_execute_parallel routes dependency groups of size 1 through
        _execute_single_task, which bypassed the parallel worker's guard."""
        executed = []

        def fake_subprocess(ws, task_id, batch_id, **kwargs):
            executed.append(task_id)
            return "COMPLETED"

        monkeypatch.setattr(conductor, "_execute_task_subprocess", fake_subprocess)

        target = three_tasks[0]
        batch = _make_batch(workspace, three_tasks, {target: "COMPLETED"})

        result = conductor._execute_single_task(
            workspace, batch, target, 1, len(three_tasks)
        )

        assert executed == [], "launched an agent run for finished work"
        assert result == "COMPLETED"


class TestForcedResumeStillOverwritesCompletedResults:
    """The guard must not swallow `cf work batch resume --force`.

    Force re-runs every task, including completed ones. Their stale COMPLETED
    is the batch's own earlier verdict, not an external completion — if the
    rerun fails, the batch must say so rather than keep the old success.
    """

    def test_a_forced_rerun_that_fails_replaces_the_old_COMPLETED(
        self, workspace, three_tasks, monkeypatch
    ):
        from codeframe.core.conductor import BatchStatus

        monkeypatch.setattr(
            conductor, "_execute_task_subprocess",
            lambda ws, tid, bid, **kw: "FAILED",
        )
        monkeypatch.setattr(conductor, "_start_reconciliation_thread",
                            lambda *a, **k: __import__("threading").Event())

        batch = _make_batch(workspace, three_tasks, {t: "COMPLETED" for t in three_tasks})
        batch.status = BatchStatus.PARTIAL
        conductor._save_batch(workspace, batch)

        resumed = conductor.resume_batch(workspace, batch.id, force=True)

        assert set(resumed.results.values()) == {"FAILED"}, (
            "a forced rerun kept its stale COMPLETED results"
        )

    def test_an_external_completion_during_a_forced_rerun_is_still_protected(
        self, workspace, three_tasks, monkeypatch
    ):
        """Clearing stale results must not reopen the hole the guard closed."""
        from codeframe.core.conductor import BatchStatus

        target = three_tasks[0]

        # resume_batch reloads the batch, so the reconciler stand-in has to
        # mutate *that* object, not the fixture's. Capture it on the way in.
        live = []
        real_resume_exec = conductor._execute_serial_resume

        def capture(ws, b, task_ids, on_event=None):
            live.append(b)
            return real_resume_exec(ws, b, task_ids, on_event)

        def fake_subprocess(ws, task_id, batch_id, **kwargs):
            if task_id == target:
                live[0].results[task_id] = "COMPLETED"  # reconciler, mid-rerun
                return "FAILED"
            return "FAILED"

        monkeypatch.setattr(conductor, "_execute_serial_resume", capture)
        monkeypatch.setattr(conductor, "_execute_task_subprocess", fake_subprocess)
        monkeypatch.setattr(conductor, "_start_reconciliation_thread",
                            lambda *a, **k: __import__("threading").Event())

        batch = _make_batch(workspace, three_tasks, {t: "COMPLETED" for t in three_tasks})
        batch.status = BatchStatus.PARTIAL
        conductor._save_batch(workspace, batch)

        resumed = conductor.resume_batch(workspace, batch.id, force=True)

        assert resumed.results[target] == "COMPLETED"


class TestForcedResumeCanActuallyRerunADoneTask:
    """`resume --force` never really re-ran a completed task.

    Pre-existing, not caused by this branch: the row is DONE, and
    ``runtime.start_task_run`` needs DONE -> IN_PROGRESS, which the state
    machine forbids (DONE allows only READY, MERGED). So a forced rerun failed
    before the agent started. Found while reviewing the results-clearing above,
    which sits on the same path.
    """

    def test_a_done_task_is_runnable_again_after_a_forced_resume(
        self, workspace, three_tasks, monkeypatch
    ):
        from codeframe.core import runtime, tasks as tasks_mod
        from codeframe.core.conductor import BatchStatus
        from codeframe.core.state_machine import TaskStatus

        for tid in three_tasks:
            tasks_mod.update_status(workspace, tid, TaskStatus.IN_PROGRESS)
            tasks_mod.update_status(workspace, tid, TaskStatus.DONE)

        started = []

        def fake_subprocess(ws, task_id, batch_id, **kwargs):
            # What the real subprocess does first: claim the task.
            runtime.start_task_run(ws, task_id)
            started.append(task_id)
            return "COMPLETED"

        monkeypatch.setattr(conductor, "_execute_task_subprocess", fake_subprocess)
        monkeypatch.setattr(conductor, "_start_reconciliation_thread",
                            lambda *a, **k: __import__("threading").Event())

        batch = _make_batch(workspace, three_tasks, {t: "COMPLETED" for t in three_tasks})
        batch.status = BatchStatus.PARTIAL
        conductor._save_batch(workspace, batch)

        conductor.resume_batch(workspace, batch.id, force=True)

        assert started == three_tasks, (
            "forced resume could not re-run completed tasks — DONE -> IN_PROGRESS "
            "is refused by the state machine"
        )


class TestTheFirstTaskIsCheckedBeforeItStarts:
    """The reconciliation thread waits a full interval before its first pass.

    So "the issue was already closed when the batch started" — the likeliest
    case of all — was missed for every task the serial loop reached inside the
    first 30 seconds, which in practice means the first one.
    """

    def test_a_pass_runs_before_the_loop_launches_anything(
        self, workspace, three_tasks, monkeypatch
    ):
        executed = []
        monkeypatch.setattr(
            conductor, "_execute_task_subprocess",
            lambda ws, tid, bid, **kw: executed.append(tid) or "COMPLETED",
        )

        # A reconciler that would find the first task's issue closed. Real
        # thread start is left intact except for the interval, so this pins the
        # *synchronous* pass, not a lucky race with the daemon.
        from codeframe.core.reconciliation import ExternalStateChange

        target = three_tasks[0]

        class StubEngine:
            def __init__(self, workspace):
                pass

            def check_all_active(self, ids):
                from codeframe.core.reconciliation import ReconciliationResult

                r = ReconciliationResult()
                if target in ids:
                    r.changes_detected.append(
                        ExternalStateChange(target, "completed", "github", {})
                    )
                return r

            def apply_changes(self, result, batch, procs):
                for c in result.changes_detected:
                    batch.results[c.task_id] = "COMPLETED"
                    result.tasks_skipped.append(c.task_id)

        monkeypatch.setattr(
            "codeframe.core.reconciliation.ReconciliationEngine", StubEngine
        )

        batch = _make_batch(workspace, three_tasks)
        conductor._execute_serial(workspace, batch)

        assert target not in executed, (
            "the first task ran before reconciliation ever looked at it"
        )
        assert batch.results[target] == "COMPLETED"


class TestEveryWriteSiteUsesTheGuard:
    def test_no_executor_writes_batch_results_directly(self):
        """A guard that four of five call sites bypass guards nothing.

        Pinned at source level because each bypass is a distinct code path with
        its own expensive end-to-end setup; the behavioral tests above cover
        the default serial path specifically.
        """
        import re
        from pathlib import Path

        lines = Path(conductor.__file__).read_text(encoding="utf-8").splitlines()
        # The one legitimate direct write is inside _record_task_result itself.
        guard_start = next(
            i for i, ln in enumerate(lines)
            if ln.startswith("def _record_task_result(")
        )
        guard_end = next(
            i for i, ln in enumerate(lines[guard_start + 1:], guard_start + 1)
            if ln.startswith("def ")
        )
        direct = [
            f"line {i + 1}: {ln.strip()}"
            for i, ln in enumerate(lines)
            if re.match(r"^\s*batch\.results\[[^\]]+\]\s*=", ln)
            and not (guard_start <= i < guard_end)
        ]
        assert direct == [], (
            "these bypass _record_task_result and can revert an external "
            f"completion: {direct}"
        )
