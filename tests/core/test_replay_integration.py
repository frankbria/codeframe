"""Integration tests for the replay system.

Exercises the full flow: ExecutionRecorder records data during a mock
agent run, then load/replay/diff/export consume that recorded data.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codeframe.core.workspace import create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return create_or_load_workspace(repo_path)


@pytest.fixture
def run_with_trace(workspace):
    """Simulate a complete agent run using ExecutionRecorder."""
    from codeframe.core.replay import ExecutionRecorder

    task_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    # Insert run record
    conn = get_db_connection(workspace)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO tasks (id, workspace_id, title, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, workspace.id, "Integration test task", "Full lifecycle test", "DONE", now, now),
        )
        conn.execute(
            "INSERT INTO runs (id, workspace_id, task_id, status, started_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, workspace.id, task_id, "COMPLETED", now, now),
        )
        conn.commit()
    finally:
        conn.close()

    # Record execution using the recorder (same way ReactAgent does)
    recorder = ExecutionRecorder(workspace, run_id, flush_interval=100)

    # Iteration 1: Create a file
    step1_id = recorder.record_iteration(
        step_number=1,
        tool_names=["create_file"],
        llm_response_summary="Creating main.py with hello world",
    )
    recorder.record_llm_call(
        step_id=step1_id,
        prompt_summary="Implement the task: create a hello world script",
        response_summary="I'll create main.py",
        model="claude-sonnet-4-20250514",
        tokens_used=800,
        purpose="execution",
    )
    recorder.record_file_operation(
        step_id=step1_id,
        op_type="create",
        path="main.py",
        before=None,
        after="print('hello world')",
    )

    # Iteration 2: Edit the file
    step2_id = recorder.record_iteration(
        step_number=2,
        tool_names=["edit_file"],
        llm_response_summary="Adding error handling",
    )
    recorder.record_llm_call(
        step_id=step2_id,
        prompt_summary="The file needs error handling",
        response_summary="I'll add try/except",
        model="claude-sonnet-4-20250514",
        tokens_used=600,
        purpose="execution",
    )
    recorder.record_file_operation(
        step_id=step2_id,
        op_type="edit",
        path="main.py",
        before="print('hello world')",
        after="try:\n    print('hello world')\nexcept Exception:\n    pass",
    )

    # Iteration 3: Run tests (no file changes)
    step3_id = recorder.record_iteration(
        step_number=3,
        tool_names=["run_tests"],
        llm_response_summary="All tests pass",
    )
    recorder.record_llm_call(
        step_id=step3_id,
        prompt_summary="Run the test suite",
        response_summary="5 tests passed",
        model="claude-sonnet-4-20250514",
        tokens_used=400,
        purpose="verification",
    )

    recorder.flush()
    return workspace, task_id, run_id


class TestFullLifecycle:
    """End-to-end: record → load → replay → diff → export."""

    def test_load_recorded_trace(self, run_with_trace):
        from codeframe.core.replay import load_execution_trace

        workspace, task_id, run_id = run_with_trace
        trace = load_execution_trace(workspace, run_id)

        assert trace is not None
        assert trace.run_id == run_id
        assert trace.task_id == task_id
        assert trace.status == "COMPLETED"
        assert len(trace.steps) == 3
        assert len(trace.llm_interactions) == 3
        assert len(trace.file_operations) == 2

    def test_step_snapshots_match_recorded_state(self, run_with_trace):
        from codeframe.core.replay import get_step_snapshot

        workspace, _, run_id = run_with_trace

        # After step 1: main.py created
        snapshot1 = get_step_snapshot(workspace, run_id, 1)
        assert snapshot1 == {"main.py": "print('hello world')"}

        # After step 2: main.py edited
        snapshot2 = get_step_snapshot(workspace, run_id, 2)
        assert "try:" in snapshot2["main.py"]

        # After step 3: no file changes, same state
        snapshot3 = get_step_snapshot(workspace, run_id, 3)
        assert snapshot3 == snapshot2

    def test_diff_between_start_and_end(self, run_with_trace):
        from codeframe.core.replay import compare_steps

        workspace, _, run_id = run_with_trace
        changes = compare_steps(workspace, run_id, 0, 3)

        assert "main.py" in changes
        assert changes["main.py"]["before"] is None
        assert "try:" in changes["main.py"]["after"]

    def test_diff_step_1_to_2(self, run_with_trace):
        from codeframe.core.replay import compare_steps

        workspace, _, run_id = run_with_trace
        changes = compare_steps(workspace, run_id, 1, 2)

        assert "main.py" in changes
        assert changes["main.py"]["before"] == "print('hello world')"
        assert "try:" in changes["main.py"]["after"]

    def test_export_json_roundtrip(self, run_with_trace):
        from codeframe.core.replay import export_trace_json, load_execution_trace

        workspace, task_id, run_id = run_with_trace
        trace = load_execution_trace(workspace, run_id)
        exported = export_trace_json(trace)

        # Verify JSON serializable
        serialized = json.dumps(exported)
        roundtripped = json.loads(serialized)

        assert roundtripped["run_id"] == run_id
        assert roundtripped["task_id"] == task_id
        assert roundtripped["summary"]["total_steps"] == 3
        assert roundtripped["summary"]["llm_calls"] == 3
        assert roundtripped["summary"]["total_tokens"] == 1800
        assert roundtripped["summary"]["files_modified"] == 1

    def test_export_markdown_content(self, run_with_trace):
        from codeframe.core.replay import export_trace_markdown, load_execution_trace

        workspace, _, run_id = run_with_trace
        trace = load_execution_trace(workspace, run_id)
        md = export_trace_markdown(trace)

        assert "# Execution Trace" in md
        assert "COMPLETED" in md
        assert "main.py" in md
        assert "create_file" in md or "Creating" in md

    def test_replay_session_navigation(self, run_with_trace):
        from codeframe.core.replay import ReplaySession, load_execution_trace

        workspace, _, run_id = run_with_trace
        trace = load_execution_trace(workspace, run_id)
        session = ReplaySession(trace)

        # Start at step 1
        assert session.current_position == 1
        assert "create_file" in session.current_step.description

        # Navigate forward
        session.next()
        assert session.current_position == 2
        assert "edit_file" in session.current_step.description

        # Jump to step 3
        session.jump(3)
        assert session.current_position == 3
        assert "run_tests" in session.current_step.description

        # Go back
        session.previous()
        assert session.current_position == 2

    def test_prepare_rerun_from_step(self, run_with_trace):
        from codeframe.core.replay import prepare_rerun

        workspace, task_id, run_id = run_with_trace
        info = prepare_rerun(workspace, run_id, from_step=1)

        assert info["task_id"] == task_id
        assert info["file_state"]["main.py"] == "print('hello world')"
        assert len(info["remaining_steps"]) == 2

    def test_summary_aggregation(self, run_with_trace):
        from codeframe.core.replay import load_execution_trace

        workspace, _, run_id = run_with_trace
        trace = load_execution_trace(workspace, run_id)
        summary = trace.summary()

        assert summary["total_steps"] == 3
        assert summary["llm_calls"] == 3
        assert summary["total_tokens"] == 1800  # 800 + 600 + 400
        assert summary["files_modified"] == 1  # Only main.py
