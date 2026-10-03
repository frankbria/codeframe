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
        control._stop_heartbeat()  # the process died without cleaning up
        runtime.stop_run(ws, task.id)
        monkeypatch.setattr(run_control, "STALE_AFTER_S", 0)

        assert runtime.start_task_run(ws, task.id).status == runtime.RunStatus.RUNNING
