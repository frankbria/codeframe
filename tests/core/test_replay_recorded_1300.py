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
