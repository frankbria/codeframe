"""A real run records an execution trace (#1300).

ReactAgent records only when it is handed an ExecutionRecorder, and no
production path ever built one, so `cf work replay/diff/export-trace/rerun`
always answered "No trace found". test_replay_integration.py seeds the
recorder by hand, which is how CI never saw the gap. This drives the real
runtime with the mock provider and reads the trace back.
"""

import subprocess

import pytest

from codeframe.core import runtime, tasks
from codeframe.core.replay import load_execution_trace
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def ws(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "mock")
    return create_or_load_workspace(tmp_path)


def test_a_react_run_records_a_trace_replay_can_load(ws):
    task = tasks.create(ws, title="Say hello", description="Reply with a greeting.", status=TaskStatus.READY)
    run = runtime.start_task_run(ws, task.id)

    runtime.execute_agent(ws, run, engine="react")

    trace = load_execution_trace(ws, run.id)
    assert trace is not None, "no trace recorded for a real run"
    assert trace.steps, "trace has no steps"
    assert trace.llm_interactions, "trace has no LLM interactions"


def _steps(ws, run_id):
    from codeframe.core.replay import get_execution_steps

    return [s.step_number for s in get_execution_steps(ws, run_id)]


def test_a_resumed_run_continues_its_step_numbers(ws):
    """`cf work resume` re-executes the same run id with a fresh agent whose
    iteration count restarts at 1; its steps must not reuse 1..N, or the
    two attempts interleave in replay, jump and diff (review)."""
    from codeframe.core.replay import ExecutionRecorder

    task = tasks.create(ws, title="t", status=TaskStatus.READY)
    run = runtime.start_task_run(ws, task.id)
    for attempt in range(2):
        rec = ExecutionRecorder(ws, run.id)
        for iteration in (1, 2):
            rec.record_iteration(iteration, [], f"attempt {attempt}")
        rec.flush()
    assert _steps(ws, run.id) == [1, 2, 3, 4]


def test_a_stall_retry_on_a_shared_recorder_continues_its_step_numbers(ws):
    from codeframe.core.replay import ExecutionRecorder

    task = tasks.create(ws, title="t", status=TaskStatus.READY)
    run = runtime.start_task_run(ws, task.id)
    rec = ExecutionRecorder(ws, run.id)
    for _attempt in range(2):  # a new agent per attempt, same recorder
        rec.record_iteration(1, [], "x")
    rec.flush()
    assert _steps(ws, run.id) == [1, 2]
