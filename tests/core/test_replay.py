"""Tests for the replay module — execution trace recording and replay.

Tests cover:
- Data model creation (ExecutionStep, LLMInteraction, FileOperation, ExecutionTrace)
- Database CRUD operations for execution trace tables
- Trace loading and state reconstruction
- Step snapshot generation
- Diff computation between steps
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codeframe.core.workspace import create_or_load_workspace, get_db_connection


@pytest.fixture
def workspace(tmp_path: Path):
    """Create a temporary workspace for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return create_or_load_workspace(repo_path)


@pytest.fixture
def run_id():
    return str(uuid.uuid4())


@pytest.fixture
def task_id():
    return str(uuid.uuid4())


# =============================================================================
# Step 1: Data model tests
# =============================================================================


class TestExecutionStepModel:
    """Tests for ExecutionStep dataclass."""

    def test_create_step(self):
        from codeframe.core.replay import ExecutionStep

        step = ExecutionStep(
            id="step-1",
            run_id="run-1",
            step_number=1,
            step_type="tool_call",
            description="Read file main.py",
            started_at=datetime.now(timezone.utc),
        )
        assert step.step_number == 1
        assert step.step_type == "tool_call"
        assert step.completed_at is None
        assert step.status == "started"
        assert step.metadata == {}

    def test_step_with_all_fields(self):
        from codeframe.core.replay import ExecutionStep

        now = datetime.now(timezone.utc)
        step = ExecutionStep(
            id="step-2",
            run_id="run-1",
            step_number=2,
            step_type="verification",
            description="Run pytest",
            started_at=now,
            completed_at=now,
            status="completed",
            input_context="pytest tests/",
            output_result="5 passed",
            metadata={"gate": "pytest"},
        )
        assert step.status == "completed"
        assert step.output_result == "5 passed"
        assert step.metadata["gate"] == "pytest"


class TestLLMInteractionModel:
    """Tests for LLMInteraction dataclass."""

    def test_create_interaction(self):
        from codeframe.core.replay import LLMInteraction

        interaction = LLMInteraction(
            id="llm-1",
            run_id="run-1",
            step_id="step-1",
            prompt="Implement the feature",
            response="I'll start by reading the file...",
            model="claude-sonnet-4-20250514",
            tokens_used=1500,
            timestamp=datetime.now(timezone.utc),
            purpose="execution",
        )
        assert interaction.model == "claude-sonnet-4-20250514"
        assert interaction.tokens_used == 1500
        assert interaction.purpose == "execution"


class TestFileOperationModel:
    """Tests for FileOperation dataclass."""

    def test_create_operation(self):
        from codeframe.core.replay import FileOperation

        op = FileOperation(
            id="fop-1",
            run_id="run-1",
            step_id="step-1",
            operation_type="create",
            file_path="src/main.py",
            content_before=None,
            content_after="print('hello')",
            timestamp=datetime.now(timezone.utc),
        )
        assert op.operation_type == "create"
        assert op.content_before is None
        assert op.content_after == "print('hello')"


class TestExecutionTraceModel:
    """Tests for ExecutionTrace dataclass."""

    def test_create_trace(self):
        from codeframe.core.replay import ExecutionTrace

        trace = ExecutionTrace(
            run_id="run-1",
            task_id="task-1",
            started_at=datetime.now(timezone.utc),
            status="COMPLETED",
            steps=[],
            llm_interactions=[],
            file_operations=[],
        )
        assert trace.run_id == "run-1"
        assert trace.steps == []
        assert trace.completed_at is None

    def test_trace_summary(self):
        from codeframe.core.replay import ExecutionStep, ExecutionTrace, LLMInteraction

        now = datetime.now(timezone.utc)
        trace = ExecutionTrace(
            run_id="run-1",
            task_id="task-1",
            started_at=now,
            status="COMPLETED",
            steps=[
                ExecutionStep(
                    id="s1", run_id="run-1", step_number=1,
                    step_type="tool_call", description="read", started_at=now,
                ),
                ExecutionStep(
                    id="s2", run_id="run-1", step_number=2,
                    step_type="tool_call", description="edit", started_at=now,
                ),
            ],
            llm_interactions=[
                LLMInteraction(
                    id="l1", run_id="run-1", step_id="s1",
                    prompt="p", response="r", model="claude",
                    tokens_used=100, timestamp=now, purpose="execution",
                ),
            ],
            file_operations=[],
        )
        summary = trace.summary()
        assert summary["total_steps"] == 2
        assert summary["llm_calls"] == 1
        assert summary["total_tokens"] == 100
        assert summary["files_modified"] == 0


# =============================================================================
# Step 1: Database schema tests
# =============================================================================


class TestReplaySchemaCreation:
    """Tests that replay tables are created during workspace init."""

    def test_execution_steps_table_exists(self, workspace):
        conn = get_db_connection(workspace)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='execution_steps'"
            )
            assert cursor.fetchone() is not None
        finally:
            conn.close()

    def test_llm_interactions_table_exists(self, workspace):
        conn = get_db_connection(workspace)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_interactions'"
            )
            assert cursor.fetchone() is not None
        finally:
            conn.close()

    def test_file_operations_table_exists(self, workspace):
        conn = get_db_connection(workspace)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='file_operations'"
            )
            assert cursor.fetchone() is not None
        finally:
            conn.close()


# =============================================================================
# Step 1: Database CRUD tests
# =============================================================================


class TestExecutionStepCRUD:
    """Tests for saving and loading execution steps."""

    def test_save_and_load_step(self, workspace, run_id, task_id):
        from codeframe.core.replay import (
            ExecutionStep,
            save_execution_step,
            get_execution_steps,
        )

        now = datetime.now(timezone.utc)
        step = ExecutionStep(
            id="step-1",
            run_id=run_id,
            step_number=1,
            step_type="tool_call",
            description="Read main.py",
            started_at=now,
            status="completed",
            output_result="file contents here",
        )
        save_execution_step(workspace, step)
        steps = get_execution_steps(workspace, run_id)
        assert len(steps) == 1
        assert steps[0].id == "step-1"
        assert steps[0].step_type == "tool_call"
        assert steps[0].description == "Read main.py"

    def test_steps_ordered_by_step_number(self, workspace, run_id):
        from codeframe.core.replay import (
            ExecutionStep,
            save_execution_step,
            get_execution_steps,
        )

        now = datetime.now(timezone.utc)
        for i in [3, 1, 2]:
            save_execution_step(
                workspace,
                ExecutionStep(
                    id=f"step-{i}",
                    run_id=run_id,
                    step_number=i,
                    step_type="tool_call",
                    description=f"Step {i}",
                    started_at=now,
                ),
            )
        steps = get_execution_steps(workspace, run_id)
        assert [s.step_number for s in steps] == [1, 2, 3]


class TestLLMInteractionCRUD:
    """Tests for saving and loading LLM interactions."""

    def test_save_and_load_interaction(self, workspace, run_id):
        from codeframe.core.replay import (
            LLMInteraction,
            save_llm_interaction,
            get_llm_interactions,
        )

        now = datetime.now(timezone.utc)
        interaction = LLMInteraction(
            id="llm-1",
            run_id=run_id,
            step_id="step-1",
            prompt="Implement feature X",
            response="I'll read the file first...",
            model="claude-sonnet-4-20250514",
            tokens_used=2000,
            timestamp=now,
            purpose="execution",
        )
        save_llm_interaction(workspace, interaction)
        interactions = get_llm_interactions(workspace, run_id)
        assert len(interactions) == 1
        assert interactions[0].prompt == "Implement feature X"
        assert interactions[0].tokens_used == 2000


class TestFileOperationCRUD:
    """Tests for saving and loading file operations."""

    def test_save_and_load_file_op(self, workspace, run_id):
        from codeframe.core.replay import (
            FileOperation,
            save_file_operation,
            get_file_operations,
        )

        now = datetime.now(timezone.utc)
        op = FileOperation(
            id="fop-1",
            run_id=run_id,
            step_id="step-1",
            operation_type="create",
            file_path="src/main.py",
            content_before=None,
            content_after="print('hello')",
            timestamp=now,
        )
        save_file_operation(workspace, op)
        ops = get_file_operations(workspace, run_id)
        assert len(ops) == 1
        assert ops[0].file_path == "src/main.py"
        assert ops[0].content_after == "print('hello')"

    def test_file_ops_ordered_by_timestamp(self, workspace, run_id):
        from codeframe.core.replay import (
            FileOperation,
            save_file_operation,
            get_file_operations,
        )

        from datetime import timedelta

        base = datetime.now(timezone.utc)
        for i in [2, 0, 1]:
            save_file_operation(
                workspace,
                FileOperation(
                    id=f"fop-{i}",
                    run_id=run_id,
                    step_id=f"step-{i}",
                    operation_type="edit",
                    file_path=f"file{i}.py",
                    content_before="old",
                    content_after="new",
                    timestamp=base + timedelta(seconds=i),
                ),
            )
        ops = get_file_operations(workspace, run_id)
        assert [op.file_path for op in ops] == ["file0.py", "file1.py", "file2.py"]
