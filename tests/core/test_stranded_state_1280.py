"""#1280: run, task and batch state left stranded by errors, interrupts and stops.

Each case once left something RUNNING or IN_PROGRESS with nothing behind it,
so the next start, resume or run refused it, or re-ran work that was done.
The tests assert the persisted state afterwards, not which function was called.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from codeframe.core import conductor, runtime, tasks
from codeframe.core.conductor import BatchRun, BatchStatus, OnFailure
from codeframe.core.runtime import RunStatus
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


def _task(ws, title="t", depends_on=None):
    return tasks.create(ws, title=title, status=TaskStatus.READY, depends_on=depends_on or [])


def _batch(ws, task_ids, results=None, strategy="serial"):
    batch = BatchRun(
        id=f"b-{task_ids[0][:8]}", workspace_id=ws.id, task_ids=task_ids,
        status=BatchStatus.RUNNING, strategy=strategy, max_parallel=2,
        on_failure=OnFailure.CONTINUE, started_at=datetime.now(timezone.utc),
        completed_at=None, results=results or {},
    )
    conductor._save_batch(ws, batch)
    return batch


# 1. A pre-start error -------------------------------------------------------


class TestAPreStartErrorLeavesNoOrphanRun:
    def test_a_bad_provider_fails_the_run_and_a_restart_works(self, ws):
        task = _task(ws)
        run = runtime.start_task_run(ws, task.id)

        with pytest.raises(ValueError):
            runtime.execute_agent(ws, run, llm_provider="claude")  # a typo

        assert runtime.get_run(ws, run.id).status == RunStatus.FAILED
        assert runtime.get_active_run(ws, task.id) is None
        assert runtime.start_task_run(ws, task.id).status == RunStatus.RUNNING


# 2. Ctrl+C --------------------------------------------------------------------


class TestCtrlC:
    def test_an_interrupted_agent_fails_its_run(self, ws, monkeypatch):
        from codeframe.adapters.llm.mock import MockProvider

        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "mock")

        def interrupted(self, *a, **k):
            raise KeyboardInterrupt

        monkeypatch.setattr(MockProvider, "complete", interrupted)
        task = _task(ws)
        run = runtime.start_task_run(ws, task.id)

        with pytest.raises(KeyboardInterrupt):
            runtime.execute_agent(ws, run)

        assert runtime.get_run(ws, run.id).status == RunStatus.FAILED
        assert runtime.get_active_run(ws, task.id) is None

    @pytest.mark.parametrize("strategy", ["serial", "parallel"])
    def test_an_interrupted_batch_is_cancelled_not_left_running(self, ws, monkeypatch, strategy):
        a, b = _task(ws, "a"), _task(ws, "b")
        batch = _batch(ws, [a.id, b.id], strategy=strategy)

        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(conductor, "_execute_task_subprocess", interrupted)
        run_batch = conductor._execute_serial if strategy == "serial" else conductor._execute_parallel

        with pytest.raises(KeyboardInterrupt):
            run_batch(ws, batch)

        assert conductor.get_batch(ws, batch.id).status == BatchStatus.CANCELLED

    def test_an_interrupted_resume_is_cancelled_not_left_running(self, ws, monkeypatch):
        a = _task(ws, "a")
        batch = _batch(ws, [a.id], results={a.id: "FAILED"})

        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(conductor, "_execute_task_subprocess", interrupted)
        with pytest.raises(KeyboardInterrupt):
            conductor._execute_serial_resume(ws, batch, [a.id])

        assert conductor.get_batch(ws, batch.id).status == BatchStatus.CANCELLED


# 3. Graceful stop -------------------------------------------------------------


class TestAGracefulStopKeepsTheInFlightResult:
    def test_the_finished_task_is_not_rerun_on_resume(self, ws):
        a, b = _task(ws, "a"), _task(ws, "b")
        batch = _batch(ws, [a.id, b.id])
        conductor.stop_batch(ws, batch.id)  # graceful: the in-flight task finishes

        batch.results[a.id] = RunStatus.COMPLETED.value  # ...and its worker saves
        conductor._save_batch(ws, batch)

        stored = conductor.get_batch(ws, batch.id)
        assert stored.status == BatchStatus.CANCELLED  # the cancel still wins
        assert stored.results.get(a.id) == RunStatus.COMPLETED.value
        assert conductor.resumable_task_ids(stored) == [b.id]


# 4. Failed dependencies -------------------------------------------------------


class TestADependentOfAFailedTaskIsNotRun:
    @pytest.mark.parametrize("strategy", ["serial", "parallel"])
    def test_b_is_skipped_and_recorded_blocked_after_a_fails(self, ws, monkeypatch, strategy):
        a = _task(ws, "a")
        b = _task(ws, "b", depends_on=[a.id])
        batch = _batch(ws, [a.id, b.id], strategy=strategy)
        ran: list[str] = []

        def execute(_ws, task_id, *args, **kwargs):
            ran.append(task_id)
            return RunStatus.FAILED.value

        monkeypatch.setattr(conductor, "_execute_task_subprocess", execute)
        run_batch = conductor._execute_serial if strategy == "serial" else conductor._execute_parallel
        run_batch(ws, batch)

        assert ran == [a.id], "B ran although A failed"
        # SKIPPED, not BLOCKED: nobody has a question to answer, so the web UI
        # must not announce a blocker (review).
        assert conductor.get_batch(ws, batch.id).results[b.id] == conductor.SKIPPED

    def test_a_retry_round_recovers_the_chain(self, ws, monkeypatch):
        """A fails once, then succeeds on --retry; B and C must get their turn
        rather than stay skipped (review)."""
        a = _task(ws, "a")
        b = _task(ws, "b", depends_on=[a.id])
        c = _task(ws, "c", depends_on=[b.id])
        batch = _batch(ws, [a.id, b.id, c.id])
        ran: list[str] = []

        def execute(_ws, task_id, *args, **kwargs):
            ran.append(task_id)
            first_try = ran.count(task_id) == 1
            return RunStatus.FAILED.value if task_id == a.id and first_try else RunStatus.COMPLETED.value

        monkeypatch.setattr(conductor, "_execute_task_subprocess", execute)
        conductor._execute_serial(ws, batch)
        conductor._run_retries(ws, batch, max_retries=1)

        assert ran == [a.id, a.id, b.id, c.id]
        assert set(conductor.get_batch(ws, batch.id).results.values()) == {RunStatus.COMPLETED.value}

    def test_a_dependency_cycle_still_runs(self, ws, monkeypatch):
        """No order satisfies a cycle; the serial fallback runs it as before
        instead of skipping every member (review)."""
        a = _task(ws, "a")
        b = _task(ws, "b", depends_on=[a.id])
        tasks.update_depends_on(ws, a.id, [b.id])
        batch = _batch(ws, [a.id, b.id])
        ran: list[str] = []

        def execute(_ws, task_id, *args, **kwargs):
            ran.append(task_id)
            return RunStatus.COMPLETED.value

        monkeypatch.setattr(conductor, "_execute_task_subprocess", execute)
        conductor._execute_serial(ws, batch)

        assert sorted(ran) == sorted([a.id, b.id])


class TestDependencyOrderNotListOrder:
    """A batch listed as [B, A] with B needing A must still run A first, not
    skip B as blocked before A has run (codex review)."""

    def _ok(self, monkeypatch, ran):
        def execute(_ws, task_id, *args, **kwargs):
            ran.append(task_id)
            return RunStatus.COMPLETED.value

        monkeypatch.setattr(conductor, "_execute_task_subprocess", execute)

    def test_serial(self, ws, monkeypatch):
        a = _task(ws, "a")
        b = _task(ws, "b", depends_on=[a.id])
        batch = _batch(ws, [b.id, a.id])
        ran: list[str] = []
        self._ok(monkeypatch, ran)

        conductor._execute_serial(ws, batch)

        assert ran == [a.id, b.id]
        assert conductor.get_batch(ws, batch.id).results[b.id] == RunStatus.COMPLETED.value

    def test_resume(self, ws, monkeypatch):
        a = _task(ws, "a")
        b = _task(ws, "b", depends_on=[a.id])
        batch = _batch(ws, [b.id, a.id], results={a.id: "FAILED", b.id: "BLOCKED"})
        ran: list[str] = []
        self._ok(monkeypatch, ran)

        conductor._execute_serial_resume(ws, batch, [b.id, a.id])

        assert ran == [a.id, b.id]


class TestALateErrorDoesNotUndoAStop:
    def test_a_gracefully_stopped_batch_stays_cancelled(self, ws):
        """The in-flight task's error arrives after the user's graceful stop."""
        a = _task(ws, "a")
        batch = _batch(ws, [a.id])
        conductor.stop_batch(ws, batch.id)

        conductor._record_batch_aborted(ws, batch, ValueError("cleanup failed"), strategy="serial")

        assert conductor.get_batch(ws, batch.id).status == BatchStatus.CANCELLED


# 5. The CLI resume pre-check ----------------------------------------------------


class TestTheCliResumePreCheckMatchesCore:
    def test_never_started_tasks_are_resumable_from_the_cli(self, ws, monkeypatch):
        from typer.testing import CliRunner

        from codeframe.cli.app import app

        a, b = _task(ws, "a"), _task(ws, "b")
        batch = _batch(ws, [a.id, b.id], results={a.id: RunStatus.COMPLETED.value})
        batch.status = BatchStatus.CANCELLED
        conductor._save_batch(ws, batch, preserve_terminal_cancel=False)
        resumed: list[str] = []
        monkeypatch.setattr(
            conductor, "resume_batch",
            lambda _ws, batch_id, force=False: resumed.append(batch_id) or batch,
        )

        result = CliRunner().invoke(
            app, ["work", "batch", "resume", batch.id[:8], "-w", str(ws.repo_path)]
        )

        assert resumed == [batch.id], result.output
        assert conductor.resumable_task_ids(batch) == [b.id]


# 6. The active-run error says how to get out -------------------------------------


def test_the_active_run_error_names_the_stop_command(ws):
    task = _task(ws)
    runtime.start_task_run(ws, task.id)
    with pytest.raises(ValueError, match="cf work stop"):
        runtime.start_task_run(ws, task.id)
