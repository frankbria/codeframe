"""#1279 — Stop must stop the agent, its delegated CLI and the CLI's children.

`stop_run` used to flip the run to FAILED and nothing else: the ReAct loop
and the adapters never looked, and every kill path signalled only the direct
child, so a delegated CLI and its children ran on. These tests assert
outcomes: a process that is gone, an LLM call that never happened, and a
restart that is refused and then accepted.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codeframe.adapters.llm.base import LLMResponse, ToolCall
from codeframe.core import run_control, runtime, tasks
from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter
from codeframe.core.agent import AgentStatus
from codeframe.core.react_agent import ReactAgent
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = [
    pytest.mark.v2,
    pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX"),
]

# A delegated CLI that forks a long-lived child, records its pid, and waits.
_FORKS_A_GRANDCHILD = 'sleep 300 & echo $! > "$PIDFILE"; wait'


def _alive(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/status").read_text()
    except FileNotFoundError:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    return "\nState:\tZ" not in state  # a zombie is dead, merely unreaped


def _gone_within(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


def _wait_for_pid(pidfile: Path, seconds: float = 10) -> int:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        text = pidfile.read_text().strip() if pidfile.exists() else ""
        if text:
            return int(text)
        time.sleep(0.05)
    raise AssertionError("the grandchild never started")


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


@pytest.fixture
def pidfile(tmp_path, monkeypatch):
    path = tmp_path / "grandchild.pid"
    monkeypatch.setenv("PIDFILE", str(path))
    return path


def _adapter(timeout_s=None):
    adapter = SubprocessAdapter("sh", cli_args=["-c", _FORKS_A_GRANDCHILD], timeout_s=timeout_s)
    # The #996 env allowlist would drop PIDFILE; the child needs it.
    adapter.get_env = lambda _path: {"PIDFILE": os.environ["PIDFILE"]}
    return adapter


# ---------------------------------------------------------------------------
# Process trees
# ---------------------------------------------------------------------------


class TestProcessTrees:
    def test_sigterm_to_a_worker_takes_its_delegated_cli_with_it(self, tmp_path, pidfile):
        """AC: SIGTERM a worker that has a grandchild; the grandchild is gone."""
        worker = tmp_path / "worker.py"
        worker.write_text(textwrap.dedent(f"""
            import os, sys
            from pathlib import Path
            from codeframe.core import run_control
            from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter
            run_control.exit_on_sigterm()
            a = SubprocessAdapter("sh", cli_args=["-c", {_FORKS_A_GRANDCHILD!r}])
            a.get_env = lambda _p: {{"PIDFILE": os.environ["PIDFILE"]}}
            a.run("t", "", Path({str(tmp_path)!r}))
        """))
        proc = subprocess.Popen([sys.executable, str(worker)], **run_control.new_session_kwargs())
        try:
            grandchild = _wait_for_pid(pidfile)
            run_control.terminate_tree(proc, grace_s=10)
            assert _gone_within(grandchild, 5), "the delegated CLI's child outlived its worker"
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_an_adapter_timeout_kills_the_whole_tree(self, tmp_path, pidfile):
        result = _adapter(timeout_s=1).run("t", "", tmp_path)

        assert result.status == "failed" and "timed out" in (result.error or "")
        assert _gone_within(_wait_for_pid(pidfile), 5)


# ---------------------------------------------------------------------------
# The cancellation signal
# ---------------------------------------------------------------------------


def _start(ws):
    task = tasks.create(ws, title="t", status=TaskStatus.READY)
    return task, runtime.start_task_run(ws, task.id)


class TestCancellation:
    def test_a_stopped_adapter_returns_and_kills_its_tree(self, ws, tmp_path, pidfile):
        task, run = _start(ws)
        out: dict = {}

        def work():
            with run_control.supervise(ws, run):
                out["result"] = _adapter().run(task.id, "", tmp_path)

        t = threading.Thread(target=work)
        t.start()
        grandchild = _wait_for_pid(pidfile)
        runtime.stop_run(ws, task.id)
        t.join(timeout=15)

        assert not t.is_alive(), "the adapter ignored the stop"
        assert out["result"].status == "failed"
        assert "stopped" in (out["result"].error or "").lower()
        assert _gone_within(grandchild, 5)

    def test_the_react_loop_makes_no_llm_call_after_a_stop(self, ws, monkeypatch):
        """AC: a stopped run's agent exits instead of continuing to spend."""
        from codeframe.core.tools import ToolResult

        task, run = _start(ws)
        provider = MagicMock()
        calls = {"n": 0}

        def complete(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                runtime.stop_run(ws, task.id)  # the user presses Stop mid-call
            n = calls["n"]
            return LLMResponse(
                content="working",
                tool_calls=[ToolCall(id=f"t{n}", name="run_command", input={"command": f"echo {n}"})],
                stop_reason="tool_use", input_tokens=1, output_tokens=1,
            )

        provider.complete.side_effect = complete
        agent = ReactAgent(workspace=ws, llm_provider=provider, max_iterations=5)
        agent._current_task_id = task.id
        monkeypatch.setattr(agent, "_execute_tool_with_lint", lambda tc: ToolResult(tool_call_id=tc.id, content="ok"))

        with run_control.supervise(ws, run):
            status = agent._react_loop("system prompt")

        assert status == AgentStatus.FAILED
        assert calls["n"] == 1, "the loop kept calling the LLM after Stop"


# ---------------------------------------------------------------------------
# Restart while the old agent is alive
# ---------------------------------------------------------------------------


class TestRestart:
    def test_a_restart_is_refused_until_the_stopped_agent_exits(self, ws):
        task, run = _start(ws)
        control = run_control.start(ws, run)
        try:
            runtime.stop_run(ws, task.id)
            with pytest.raises(ValueError, match="still"):
                runtime.start_task_run(ws, task.id)
        finally:
            control.stop()

        assert runtime.start_task_run(ws, task.id).status == runtime.RunStatus.RUNNING

    def test_a_crashed_worker_does_not_wedge_the_task(self, ws, monkeypatch):
        """A heartbeat that stopped beating is not a live agent."""
        task, run = _start(ws)
        control = run_control.start(ws, run)
        try:
            control._stop_heartbeat()  # the process died; its file stays behind
            runtime.stop_run(ws, task.id)
            monkeypatch.setattr(run_control, "STALE_AFTER_S", 0)

            assert runtime.start_task_run(ws, task.id).status == runtime.RunStatus.RUNNING
        finally:
            control.stop()  # unbind, or every later test on this thread reads "stopped"


class TestExecuteAgentAfterAStop:
    def test_the_run_is_not_transitioned_again(self, ws, monkeypatch):
        """stop_run already failed the run; the agent finishing afterwards must
        not complete, fail or block it a second time (complete_run used to
        raise on a stopped run)."""
        from codeframe.adapters.llm.mock import MockProvider

        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "mock")
        task, run = _start(ws)
        real_complete = MockProvider.complete

        def complete(self, *args, **kwargs):
            runtime.stop_run(ws, task.id)  # Stop lands during the LLM call
            return real_complete(self, *args, **kwargs)  # text-only: "done"

        monkeypatch.setattr(MockProvider, "complete", complete)
        # Record, never assert, inside: execute_agent's `except Exception`
        # would swallow an AssertionError and turn this test green (#1254).
        transitions: list[str] = []
        for name in ("complete_run", "fail_run", "block_run"):
            monkeypatch.setattr(
                runtime, name, lambda *a, _n=name, **k: transitions.append(_n)
            )

        state = runtime.execute_agent(ws, run)

        assert transitions == []
        assert state.status == AgentStatus.FAILED
        assert tasks.get(ws, task.id).status == TaskStatus.READY


class TestAStopDuringTheGates:
    def test_no_correction_run_follows(self, ws, tmp_path, monkeypatch):
        """Stop lands while the gates run and they fail: no quick fix, no
        blocker and no second agent run may follow (codex review)."""
        from codeframe.core.adapters.agent_adapter import AgentResult
        from codeframe.core.adapters.verification_wrapper import VerificationWrapper

        task, run = _start(ws)
        runs: list[str] = []

        class Inner:
            name = "inner"

            def run(self, task_id, prompt, workspace_path, on_event=None):
                runs.append(prompt)
                return AgentResult(status="completed", output="done")

        def gates_that_fail_after_a_stop(*a, **k):
            runtime.stop_run(ws, task.id)
            return MagicMock(passed=False)

        monkeypatch.setattr(
            "codeframe.core.adapters.verification_wrapper.run_gates",
            gates_that_fail_after_a_stop,
        )
        with run_control.supervise(ws, run):
            result = VerificationWrapper(Inner(), ws, max_correction_rounds=3).run(
                task.id, "do it", tmp_path
            )

        assert len(runs) == 1, "a correction run started after Stop"
        assert result.status == "failed" and "stopped" in (result.error or "").lower()


class TestNoChildOutlivesItsParent:
    """Children run in their own session, so the terminal's Ctrl+C and close no
    longer reach them; the parent has to pass them on (#1279 review)."""

    @pytest.mark.parametrize("ending", ["sys.exit(0)", "raise KeyboardInterrupt"])
    def test_a_registered_child_is_stopped_when_the_parent_exits(
        self, tmp_path, pidfile, ending
    ):
        script = tmp_path / "parent.py"
        script.write_text(textwrap.dedent(f"""
            import os, subprocess, sys
            from codeframe.core import run_control
            p = subprocess.Popen(["sh", "-c", {_FORKS_A_GRANDCHILD!r}],
                                 **run_control.new_session_kwargs())
            run_control.register_child(p)
            while not (os.path.exists(os.environ["PIDFILE"])
                       and open(os.environ["PIDFILE"]).read().strip()):
                pass
            {ending}
        """))
        subprocess.run([sys.executable, str(script)], capture_output=True, timeout=60)
        assert _gone_within(_wait_for_pid(pidfile), 5)

    def test_sighup_to_a_worker_takes_its_delegated_cli_with_it(self, tmp_path, pidfile):
        """Closing the terminal: the worker's own session never hears it."""
        import signal

        worker = tmp_path / "worker.py"
        worker.write_text(textwrap.dedent(f"""
            import os
            from pathlib import Path
            from codeframe.core import run_control
            from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter
            run_control.exit_on_sigterm()
            a = SubprocessAdapter("sh", cli_args=["-c", {_FORKS_A_GRANDCHILD!r}])
            a.get_env = lambda _p: {{"PIDFILE": os.environ["PIDFILE"]}}
            a.run("t", "", Path({str(tmp_path)!r}))
        """))
        proc = subprocess.Popen([sys.executable, str(worker)], **run_control.new_session_kwargs())
        try:
            grandchild = _wait_for_pid(pidfile)
            os.kill(proc.pid, signal.SIGHUP)  # our own child, by pid
            proc.wait(timeout=30)
            assert _gone_within(grandchild, 5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


class TestRetriesLeaveAStoppedTaskAlone:
    def test_a_stopped_task_is_not_retried_but_a_failed_one_is(self, ws):
        from datetime import datetime, timezone

        from codeframe.core import conductor

        stopped, _ = _start(ws)
        runtime.stop_run(ws, stopped.id)  # READY again
        failed, failed_run = _start(ws)
        runtime.fail_run(ws, failed_run.id)  # FAILED

        epoch = datetime.min.replace(tzinfo=timezone.utc)
        assert conductor._stopped_by_user(ws, stopped.id, since=epoch) is True
        assert conductor._stopped_by_user(ws, failed.id, since=epoch) is False

    def test_the_retry_loop_reruns_only_the_real_failure(self, ws, monkeypatch):
        from datetime import datetime, timezone

        from codeframe.core import conductor
        from codeframe.core.conductor import BatchRun, BatchStatus, OnFailure

        batch_started = datetime.now(timezone.utc)  # the runs below are this batch's
        stopped, _ = _start(ws)
        runtime.stop_run(ws, stopped.id)
        failed, failed_run = _start(ws)
        runtime.fail_run(ws, failed_run.id)
        batch = BatchRun(
            id="b-1279", workspace_id=ws.id, task_ids=[stopped.id, failed.id],
            status=BatchStatus.RUNNING, strategy="serial", max_parallel=1,
            on_failure=OnFailure.CONTINUE, started_at=batch_started,
            completed_at=None, results={stopped.id: "FAILED", failed.id: "FAILED"},
        )
        conductor._save_batch(ws, batch)
        rerun: list[str] = []
        monkeypatch.setattr(
            conductor, "_execute_task_subprocess",
            lambda _ws, task_id, *a, **k: rerun.append(task_id) or "COMPLETED",
        )

        conductor._run_retries(ws, batch, max_retries=1)

        assert rerun == [failed.id]

    def test_a_task_whose_worker_never_started_is_still_retried(self, ws, monkeypatch):
        """READY with no run (a spawn failure) is a failure, not a stop."""
        from datetime import datetime, timezone

        from codeframe.core import conductor
        from codeframe.core.conductor import BatchRun, BatchStatus, OnFailure

        never_ran = tasks.create(ws, title="t", status=TaskStatus.READY)
        batch = BatchRun(
            id="b-1279-spawn", workspace_id=ws.id, task_ids=[never_ran.id],
            status=BatchStatus.RUNNING, strategy="serial", max_parallel=1,
            on_failure=OnFailure.CONTINUE, started_at=datetime.now(timezone.utc),
            completed_at=None, results={never_ran.id: "FAILED"},
        )
        conductor._save_batch(ws, batch)
        rerun: list[str] = []
        monkeypatch.setattr(
            conductor, "_execute_task_subprocess",
            lambda _ws, task_id, *a, **k: rerun.append(task_id) or "COMPLETED",
        )

        conductor._run_retries(ws, batch, max_retries=1)

        assert rerun == [never_ran.id]

    def test_an_old_stop_does_not_suppress_a_later_spawn_failure(self, ws, monkeypatch):
        """The task was stopped in some earlier run; in this batch its worker
        never started, so there is no new run row (GLM review)."""
        from datetime import datetime, timedelta, timezone

        from codeframe.core import conductor
        from codeframe.core.conductor import BatchRun, BatchStatus, OnFailure

        task, _ = _start(ws)
        runtime.stop_run(ws, task.id)  # long ago
        batch = BatchRun(
            id="b-1279-stale", workspace_id=ws.id, task_ids=[task.id],
            status=BatchStatus.RUNNING, strategy="serial", max_parallel=1,
            on_failure=OnFailure.CONTINUE,
            started_at=datetime.now(timezone.utc) + timedelta(seconds=1),
            completed_at=None, results={task.id: "FAILED"},
        )
        conductor._save_batch(ws, batch)
        rerun: list[str] = []
        monkeypatch.setattr(
            conductor, "_execute_task_subprocess",
            lambda _ws, task_id, *a, **k: rerun.append(task_id) or "COMPLETED",
        )

        conductor._run_retries(ws, batch, max_retries=1)

        assert rerun == [task.id]


class TestThePlanEngineStopsToo:
    def test_no_step_starts_after_a_stop(self, ws):
        from codeframe.core.agent import Agent
        from codeframe.core.planner import ImplementationPlan, PlanStep, StepType

        task, run = _start(ws)
        events: list[str] = []
        agent = Agent(ws, MagicMock(), on_event=lambda name, data: events.append(name))
        agent.state.task_id = task.id
        agent.state.plan = ImplementationPlan(
            task_id=task.id, summary="s",
            steps=[PlanStep(index=1, type=StepType.FILE_CREATE, description="d", target="a.py")],
        )
        runtime.stop_run(ws, task.id)
        with run_control.supervise(ws, run):
            agent._execute_plan_until_stopped()

        assert "step_started" not in events
        assert agent.state.status == AgentStatus.FAILED


class TestNoCorrectionAfterAStop:
    """A Stop during a step or the gates must not lead into the correction
    loops: more LLM calls, more edits, more gate runs (codex review)."""

    def test_react_final_verification_makes_no_fix_call(self, ws, monkeypatch):
        task, run = _start(ws)
        provider = MagicMock()
        agent = ReactAgent(workspace=ws, llm_provider=provider, max_iterations=5)
        agent._current_task_id = task.id

        def gates_that_fail_after_a_stop(_ws, *a, **k):
            runtime.stop_run(ws, task.id)
            return MagicMock(passed=False, summary="lint failed")

        monkeypatch.setattr("codeframe.core.react_agent.gates.run", gates_that_fail_after_a_stop)
        with run_control.supervise(ws, run):
            passed, reason = agent._run_final_verification("system prompt")

        assert (passed, reason) == (False, "stopped_by_user")
        provider.complete.assert_not_called()

    def test_the_plan_engine_does_not_self_correct_a_stopped_step(self, ws, monkeypatch):
        from codeframe.core import blockers
        from codeframe.core.agent import Agent
        from codeframe.core.executor import ExecutionStatus, StepResult
        from codeframe.core.planner import ImplementationPlan, PlanStep, StepType

        task, run = _start(ws)

        class StoppedMidStep:
            def __init__(self, *a, **k):
                pass

            def execute_step(self, step, context):
                runtime.stop_run(ws, task.id)  # Stop lands during the step
                return StepResult(step=step, status=ExecutionStatus.FAILED, error="boom")

        monkeypatch.setattr("codeframe.core.agent.Executor", StoppedMidStep)
        llm = MagicMock()
        agent = Agent(ws, llm)
        agent.state.task_id = task.id
        agent.state.plan = ImplementationPlan(
            task_id=task.id, summary="s",
            steps=[PlanStep(index=1, type=StepType.FILE_CREATE, description="d", target="a.py")],
        )
        with run_control.supervise(ws, run):
            agent._execute_plan_until_stopped()

        assert agent.state.status == AgentStatus.FAILED
        llm.complete.assert_not_called()  # no self-correction call
        assert blockers.list_open(ws) == []  # a stop needs no answer


class TestTheConductorUnwindsOnTerminalClose:
    def test_sighup_during_a_batch_unwinds_instead_of_killing_it(self, tmp_path):
        """Workers are in their own sessions; only the conductor hears SIGHUP.
        Dying on the spot would skip the code that stops them. Run in a
        subprocess: without the fix, the SIGHUP kills whoever receives it."""
        script = tmp_path / "conductor.py"
        script.write_text(textwrap.dedent("""
            import os, signal, time
            from types import SimpleNamespace
            from codeframe.core import conductor

            def batch_that_hears_sighup(*a, **k):
                os.kill(os.getpid(), signal.SIGHUP)
                time.sleep(10)

            conductor._execute_batch = batch_that_hears_sighup
            conductor.execute_batch(SimpleNamespace(), SimpleNamespace(id="b"))
        """))
        r = subprocess.run([sys.executable, str(script)], capture_output=True, timeout=60)
        assert r.returncode == 128 + 1, (r.returncode, r.stderr[-500:])  # SystemExit, not -SIGHUP


class TestOnlyAnInterruptStopsTheParallelGroup:
    """The parallel group's workers are stopped on an interrupt, wherever it
    lands, and on nothing else (claude-review, GLM review)."""

    @pytest.fixture
    def killed(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(run_control, "terminate_trees", lambda procs, **k: calls.append(procs))
        return calls

    def test_a_failing_task_does_not_kill_its_siblings(self, killed):
        from codeframe.core import conductor

        with pytest.raises(ValueError):
            with conductor._stop_workers_on_interrupt("b"):
                raise ValueError("this task failed")
        assert killed == []

    @pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
    def test_an_interrupt_in_the_loop_body_stops_them(self, killed, interrupt):
        """Not only while blocked in as_completed: in the body, a generator
        wrapper only ever saw GeneratorExit and the executor then waited on
        every worker (GLM review)."""
        from codeframe.core import conductor

        with pytest.raises(interrupt):
            with conductor._stop_workers_on_interrupt("b"):
                raise interrupt()
        assert len(killed) == 1

    def test_it_runs_before_the_executor_waits(self, killed):
        """Exits before ThreadPoolExecutor.shutdown(wait=True)."""
        import threading
        from concurrent.futures import ThreadPoolExecutor

        from codeframe.core import conductor

        release = threading.Event()
        with pytest.raises(KeyboardInterrupt):
            with ThreadPoolExecutor(max_workers=1) as ex, conductor._stop_workers_on_interrupt("b"):
                ex.submit(release.wait, 30)
                # A real kill would end the worker; stand in for it here.
                conductor.run_control.terminate_trees = (
                    lambda procs, **k: (killed.append(procs), release.set())
                )
                raise KeyboardInterrupt
        assert killed, "the executor waited before the workers were stopped"


class TestNestedSignalHandlers:
    def test_restores_in_any_order_leave_the_original_handler(self):
        """A second install must not record our own override as 'previous':
        restored after the outer one, it would reinstall the override."""
        import signal

        original = signal.getsignal(signal.SIGTERM)
        outer = run_control.exit_on_sigterm()
        inner = run_control.exit_on_sigterm()
        run_control.restore_signal_handlers(outer)  # outer finishes first
        run_control.restore_signal_handlers(inner)
        assert signal.getsignal(signal.SIGTERM) is original
