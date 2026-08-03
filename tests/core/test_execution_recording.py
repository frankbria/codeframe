"""Tests for execution recording in ReactAgent.

Tests that when ReactAgent runs with an ExecutionRecorder:
1. An ExecutionStep is recorded for each react loop iteration
2. An LLMInteraction is recorded for each LLM call
3. A FileOperation is recorded for each file create/edit tool execution
4. ReactAgent works fine without a recorder (backward compat)
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from codeframe.adapters.llm.base import ToolCall, ToolResult
from codeframe.adapters.llm.mock import MockProvider
from codeframe.core.agent import AgentStatus
from codeframe.core.context import TaskContext
from codeframe.core.gates import GateCheck, GateResult, GateStatus
from codeframe.core.replay import (
    ExecutionRecorder,
    get_execution_steps,
    get_file_operations,
    get_llm_interactions,
)
from codeframe.core.tasks import Task, TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


#: Every run id these tests hand to ExecutionRecorder. They are literals rather
#: than fixtures because each test names its own, and the recorder writes
#: execution_steps / llm_interactions / file_operations rows against them.
_RUN_IDS = (
    "run-1",
    "run-cmp-1",
    "run-edit-1",
    "run-fop-1",
    "run-llm-1",
    "run-noop-1",
    "run-rec-1",
)


@pytest.fixture
def workspace(tmp_path):
    """A workspace whose run rows actually exist (#1061).

    Foreign keys are enforced now, so a recorder writing against ``run-1`` needs
    a real ``runs`` row parented by a real ``tasks`` row — otherwise every row it
    records is an orphan, which is what they were in production. Seeding the
    literal ids here keeps each test reading as it did, rather than threading a
    fixture through 10 call sites.
    """
    from codeframe.core import tasks
    from codeframe.core.workspace import get_db_connection

    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    ws = create_or_load_workspace(repo_path)

    task = tasks.create(ws, title="recording fixture", description="")
    conn = get_db_connection(ws)
    try:
        for run_id in _RUN_IDS:
            conn.execute(
                "INSERT INTO runs (id, workspace_id, task_id, status, started_at)"
                " VALUES (?,?,?,?,?)",
                (run_id, ws.id, task.id, "RUNNING", "2026-01-01T00:00:00+00:00"),
            )
        conn.commit()
    finally:
        conn.close()
    return ws


@pytest.fixture
def mock_task():
    """Create a minimal task."""
    _ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Task(
        id="task-1",
        workspace_id="ws-test",
        prd_id=None,
        title="Add hello function",
        description="Create a hello() function that returns 'Hello, World!'",
        status=TaskStatus.IN_PROGRESS,
        priority=1,
        created_at=_ts,
        updated_at=_ts,
    )


@pytest.fixture
def mock_context(mock_task):
    """Create a minimal TaskContext."""
    return TaskContext(task=mock_task)


@pytest.fixture
def provider():
    """Create a MockProvider."""
    return MockProvider()


def _gate_passed():
    return GateResult(
        passed=True,
        checks=[GateCheck(name="ruff", status=GateStatus.PASSED)],
    )


# ---------------------------------------------------------------------------
# ExecutionRecorder unit tests
# ---------------------------------------------------------------------------


class TestExecutionRecorder:
    """Tests for the ExecutionRecorder class itself."""

    def test_record_iteration_saves_step(self, workspace):
        recorder = ExecutionRecorder(workspace=workspace, run_id="run-1")
        step_id = recorder.record_iteration(
            step_number=1,
            tool_names=["read_file"],
            llm_response_summary="Reading file a.py",
        )
        recorder.flush()

        steps = get_execution_steps(workspace, "run-1")
        assert len(steps) == 1
        assert steps[0].id == step_id
        assert steps[0].step_number == 1
        assert steps[0].step_type == "tool_call"
        assert steps[0].status == "completed"
        assert "read_file" in steps[0].description

    def test_record_llm_call_saves_interaction(self, workspace):
        recorder = ExecutionRecorder(workspace=workspace, run_id="run-1")
        # A real parent step, via the same call production makes (#1061).
        # llm_interactions FKs to execution_steps(id), so a literal "step-1" is
        # an orphan the schema now refuses.
        step_id = recorder.record_iteration(
            step_number=1, tool_names=["read_file"], llm_response_summary="read"
        )
        recorder.flush()
        recorder.record_llm_call(
            step_id=step_id,
            prompt_summary="System: CodeFRAME agent | User: implement task",
            response_summary="Tool calls: read_file(a.py)",
            model="claude-sonnet-4-20250514",
            tokens_used=1500,
            purpose="execution",
        )
        recorder.flush()

        interactions = get_llm_interactions(workspace, "run-1")
        assert len(interactions) == 1
        assert interactions[0].step_id == step_id
        assert interactions[0].tokens_used == 1500
        assert interactions[0].model == "claude-sonnet-4-20250514"

    def test_record_file_operation_saves_op(self, workspace):
        recorder = ExecutionRecorder(workspace=workspace, run_id="run-1")
        # file_operations FKs to execution_steps(id) — a real parent (#1061).
        step_id = recorder.record_iteration(
            step_number=1, tool_names=["edit_file"], llm_response_summary="edit"
        )
        recorder.flush()
        recorder.record_file_operation(
            step_id=step_id,
            op_type="create",
            path="src/main.py",
            before=None,
            after="print('hello')",
        )
        recorder.flush()

        ops = get_file_operations(workspace, "run-1")
        assert len(ops) == 1
        assert ops[0].operation_type == "create"
        assert ops[0].file_path == "src/main.py"
        assert ops[0].content_after == "print('hello')"

    def test_flush_writes_buffered_records(self, workspace):
        recorder = ExecutionRecorder(workspace=workspace, run_id="run-1")
        # Record multiple items without explicit flush
        step_id = recorder.record_iteration(step_number=1, tool_names=["read_file"], llm_response_summary="read")
        recorder.record_iteration(step_number=2, tool_names=["edit_file"], llm_response_summary="edit")
        # The buffered step and its children flush together, so the FK is
        # satisfied within the one transaction — which is the ordering
        # production relies on too (#1061).
        recorder.record_llm_call(step_id, "prompt", "response", "model", 100, "execution")
        recorder.record_file_operation(step_id, "create", "a.py", None, "content")

        # Nothing written yet (buffered)
        assert len(get_execution_steps(workspace, "run-1")) == 0

        recorder.flush()

        assert len(get_execution_steps(workspace, "run-1")) == 2
        assert len(get_llm_interactions(workspace, "run-1")) == 1
        assert len(get_file_operations(workspace, "run-1")) == 1

    def test_recorder_is_optional_on_react_agent(self, workspace, provider, mock_context):
        """ReactAgent must work without a recorder (backward compat)."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Task completed.")

        with (
            patch("codeframe.core.react_agent.TaskContextPackager") as mock_loader,
            patch("codeframe.core.react_agent.gates") as mock_gates,
        ):
            mock_loader.return_value.load_context.return_value = mock_context
            mock_gates.run.return_value = _gate_passed()

            agent = ReactAgent(workspace=workspace, llm_provider=provider)
            status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED


# ---------------------------------------------------------------------------
# Integration: ReactAgent + ExecutionRecorder
# ---------------------------------------------------------------------------


class TestReactAgentRecording:
    """Tests that ReactAgent records execution traces when given a recorder."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_records_step_per_iteration(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Each iteration of the react loop records an ExecutionStep."""
        from codeframe.core.react_agent import ReactAgent

        # Two iterations: tool call then text completion
        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "a.py"})]
        )
        provider.add_text_response("Done implementing the task.")

        mock_ctx_loader.return_value.load_context.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="file contents")
        mock_gates.run.return_value = _gate_passed()

        recorder = ExecutionRecorder(workspace=workspace, run_id="run-rec-1")
        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            execution_recorder=recorder,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED

        steps = get_execution_steps(workspace, "run-rec-1")
        # Iteration 1 (tool call) + iteration 2 (text completion) = 2 steps
        assert len(steps) == 2
        assert steps[0].step_number == 1
        assert steps[1].step_number == 2

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_records_llm_interaction_per_call(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Each LLM call records an LLMInteraction."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "a.py"})],
        )
        provider.add_text_response("All done.")

        mock_ctx_loader.return_value.load_context.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="contents")
        mock_gates.run.return_value = _gate_passed()

        recorder = ExecutionRecorder(workspace=workspace, run_id="run-llm-1")
        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            execution_recorder=recorder,
        )
        agent.run("task-1")

        interactions = get_llm_interactions(workspace, "run-llm-1")
        assert len(interactions) == 2  # one per LLM call
        assert interactions[0].purpose == "execution"

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_records_file_operation_for_create(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """create_file tool execution records a FileOperation."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="create_file", input={"path": "hello.py", "content": "print('hi')"})]
        )
        provider.add_text_response("Created the file.")

        mock_ctx_loader.return_value.load_context.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="File created: hello.py")
        mock_gates.run.return_value = _gate_passed()

        recorder = ExecutionRecorder(workspace=workspace, run_id="run-fop-1")
        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            execution_recorder=recorder,
        )
        agent.run("task-1")

        ops = get_file_operations(workspace, "run-fop-1")
        assert len(ops) == 1
        assert ops[0].operation_type == "create"
        assert ops[0].file_path == "hello.py"
        assert ops[0].content_after == "print('hi')"

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_records_file_operation_for_edit(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """edit_file tool execution records a FileOperation."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="edit_file", input={
                "path": "main.py",
                "old_text": "old code",
                "new_text": "new code",
            })]
        )
        provider.add_text_response("Edited the file.")

        mock_ctx_loader.return_value.load_context.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="Edit applied")
        mock_gates.run.return_value = _gate_passed()

        recorder = ExecutionRecorder(workspace=workspace, run_id="run-edit-1")
        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            execution_recorder=recorder,
        )
        agent.run("task-1")

        ops = get_file_operations(workspace, "run-edit-1")
        assert len(ops) == 1
        assert ops[0].operation_type == "edit"
        assert ops[0].file_path == "main.py"

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_no_file_operation_for_read_tool(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """read_file tool does NOT record a FileOperation."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "a.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load_context.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="contents")
        mock_gates.run.return_value = _gate_passed()

        recorder = ExecutionRecorder(workspace=workspace, run_id="run-noop-1")
        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            execution_recorder=recorder,
        )
        agent.run("task-1")

        ops = get_file_operations(workspace, "run-noop-1")
        assert len(ops) == 0

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_recording_does_not_affect_agent_status(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Agent returns the same status with or without a recorder."""
        from codeframe.core.react_agent import ReactAgent

        # Setup for a simple completion
        def setup_mocks():
            provider.reset()
            provider.add_text_response("Task completed successfully.")
            mock_ctx_loader.return_value.load_context.return_value = mock_context
            mock_gates.run.return_value = _gate_passed()

        # Without recorder
        setup_mocks()
        agent_no_rec = ReactAgent(workspace=workspace, llm_provider=provider)
        status_no_rec = agent_no_rec.run("task-1")

        # With recorder
        setup_mocks()
        recorder = ExecutionRecorder(workspace=workspace, run_id="run-cmp-1")
        agent_with_rec = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            execution_recorder=recorder,
        )
        status_with_rec = agent_with_rec.run("task-1")

        assert status_no_rec == status_with_rec == AgentStatus.COMPLETED
