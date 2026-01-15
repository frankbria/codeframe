"""Tests for batch execution conductor."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from codeframe.core.conductor import (
    BatchStatus,
    BatchRun,
    OnFailure,
    start_batch,
    get_batch,
    list_batches,
    cancel_batch,
    _save_batch,
    _row_to_batch,
)
from codeframe.core.workspace import create_or_load_workspace
from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for testing."""
    workspace = create_or_load_workspace(tmp_path)
    return workspace


@pytest.fixture
def workspace_with_tasks(temp_workspace):
    """Create a workspace with some tasks."""
    # Create a few test tasks
    task1 = tasks.create(
        temp_workspace,
        title="Task 1",
        description="First task",
        status=TaskStatus.READY,
    )
    task2 = tasks.create(
        temp_workspace,
        title="Task 2",
        description="Second task",
        status=TaskStatus.READY,
    )
    task3 = tasks.create(
        temp_workspace,
        title="Task 3",
        description="Third task",
        status=TaskStatus.READY,
    )
    return temp_workspace, [task1, task2, task3]


class TestBatchStatus:
    """Tests for BatchStatus enum."""

    def test_all_statuses_exist(self):
        """All expected statuses should exist."""
        assert BatchStatus.PENDING == "PENDING"
        assert BatchStatus.RUNNING == "RUNNING"
        assert BatchStatus.COMPLETED == "COMPLETED"
        assert BatchStatus.PARTIAL == "PARTIAL"
        assert BatchStatus.FAILED == "FAILED"
        assert BatchStatus.CANCELLED == "CANCELLED"


class TestOnFailure:
    """Tests for OnFailure enum."""

    def test_continue_option(self):
        assert OnFailure.CONTINUE == "continue"

    def test_stop_option(self):
        assert OnFailure.STOP == "stop"


class TestBatchRun:
    """Tests for BatchRun dataclass."""

    def test_create_batch_run(self, temp_workspace):
        """Should create a BatchRun with all fields."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        batch = BatchRun(
            id="test-batch-123",
            workspace_id=temp_workspace.id,
            task_ids=["task-1", "task-2"],
            status=BatchStatus.PENDING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=None,
            results={},
        )

        assert batch.id == "test-batch-123"
        assert batch.task_ids == ["task-1", "task-2"]
        assert batch.status == BatchStatus.PENDING
        assert batch.strategy == "serial"
        assert batch.on_failure == OnFailure.CONTINUE

    def test_batch_run_with_results(self, temp_workspace):
        """Should store results dict."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        batch = BatchRun(
            id="test-batch",
            workspace_id=temp_workspace.id,
            task_ids=["task-1", "task-2"],
            status=BatchStatus.PARTIAL,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=now,
            results={"task-1": "COMPLETED", "task-2": "FAILED"},
        )

        assert batch.results["task-1"] == "COMPLETED"
        assert batch.results["task-2"] == "FAILED"


class TestStartBatch:
    """Tests for start_batch function."""

    def test_start_batch_empty_task_ids_raises(self, temp_workspace):
        """Should raise ValueError for empty task list."""
        with pytest.raises(ValueError, match="cannot be empty"):
            start_batch(temp_workspace, [], dry_run=True)

    def test_start_batch_invalid_task_raises(self, temp_workspace):
        """Should raise ValueError for non-existent task."""
        with pytest.raises(ValueError, match="Task not found"):
            start_batch(temp_workspace, ["non-existent-task"], dry_run=True)

    def test_start_batch_dry_run(self, workspace_with_tasks):
        """Dry run should create batch without executing."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        batch = start_batch(workspace, task_ids, dry_run=True)

        assert batch.status == BatchStatus.COMPLETED
        assert batch.task_ids == task_ids
        assert batch.strategy == "serial"
        assert batch.results == {}  # No execution in dry run

    def test_start_batch_saves_to_database(self, workspace_with_tasks):
        """Should persist batch to database."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        batch = start_batch(workspace, task_ids, dry_run=True)

        # Retrieve from database
        loaded = get_batch(workspace, batch.id)
        assert loaded is not None
        assert loaded.id == batch.id
        assert loaded.task_ids == task_ids

    def test_start_batch_strategy_parallel_warns(self, workspace_with_tasks, capsys):
        """Should warn when parallel strategy is requested but not implemented."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list[:1]]  # Just one task

        # Mock subprocess to avoid actual execution
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            batch = start_batch(workspace, task_ids, strategy="parallel", max_parallel=2)

        captured = capsys.readouterr()
        assert "Parallel execution not yet implemented" in captured.out


class TestGetBatch:
    """Tests for get_batch function."""

    def test_get_existing_batch(self, workspace_with_tasks):
        """Should retrieve an existing batch."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        created = start_batch(workspace, task_ids, dry_run=True)
        retrieved = get_batch(workspace, created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.status == created.status

    def test_get_nonexistent_batch(self, temp_workspace):
        """Should return None for non-existent batch."""
        result = get_batch(temp_workspace, "non-existent-id")
        assert result is None


class TestListBatches:
    """Tests for list_batches function."""

    def test_list_empty_workspace(self, temp_workspace):
        """Should return empty list for workspace with no batches."""
        result = list_batches(temp_workspace)
        assert result == []

    def test_list_batches_returns_all(self, workspace_with_tasks):
        """Should return all batches."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Create two batches
        batch1 = start_batch(workspace, task_ids[:1], dry_run=True)
        batch2 = start_batch(workspace, task_ids[1:2], dry_run=True)

        result = list_batches(workspace)
        assert len(result) == 2
        # Should be newest first
        assert result[0].id == batch2.id
        assert result[1].id == batch1.id

    def test_list_batches_filter_by_status(self, workspace_with_tasks):
        """Should filter by status."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Create batches
        batch = start_batch(workspace, task_ids[:1], dry_run=True)

        # Filter by COMPLETED status
        completed = list_batches(workspace, status=BatchStatus.COMPLETED)
        assert len(completed) == 1
        assert completed[0].id == batch.id

        # Filter by RUNNING status (should be empty)
        running = list_batches(workspace, status=BatchStatus.RUNNING)
        assert len(running) == 0

    def test_list_batches_respects_limit(self, workspace_with_tasks):
        """Should respect limit parameter."""
        workspace, task_list = workspace_with_tasks

        # Create several batches
        for task in task_list:
            start_batch(workspace, [task.id], dry_run=True)

        result = list_batches(workspace, limit=2)
        assert len(result) == 2


class TestCancelBatch:
    """Tests for cancel_batch function."""

    def test_cancel_nonexistent_batch_raises(self, temp_workspace):
        """Should raise ValueError for non-existent batch."""
        with pytest.raises(ValueError, match="Batch not found"):
            cancel_batch(temp_workspace, "non-existent-id")

    def test_cancel_completed_batch_raises(self, workspace_with_tasks):
        """Should raise ValueError for completed batch."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        batch = start_batch(workspace, task_ids, dry_run=True)
        # Batch is COMPLETED after dry run

        with pytest.raises(ValueError, match="cannot be cancelled"):
            cancel_batch(workspace, batch.id)

    def test_cancel_pending_batch(self, workspace_with_tasks):
        """Should cancel a pending batch."""
        workspace, task_list = workspace_with_tasks

        # Create a batch and manually set it to PENDING
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        batch = BatchRun(
            id="test-cancel-batch",
            workspace_id=workspace.id,
            task_ids=[task_list[0].id],
            status=BatchStatus.PENDING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=None,
            results={},
        )
        _save_batch(workspace, batch)

        cancelled = cancel_batch(workspace, batch.id)

        assert cancelled.status == BatchStatus.CANCELLED
        assert cancelled.completed_at is not None


class TestRowToBatch:
    """Tests for _row_to_batch function."""

    def test_converts_row_correctly(self):
        """Should convert database row to BatchRun."""
        row = (
            "batch-id-123",  # id
            "workspace-123",  # workspace_id
            '["task-1", "task-2"]',  # task_ids (JSON)
            "COMPLETED",  # status
            "serial",  # strategy
            4,  # max_parallel
            "continue",  # on_failure
            "2025-01-15T10:00:00",  # started_at
            "2025-01-15T10:30:00",  # completed_at
            '{"task-1": "COMPLETED", "task-2": "COMPLETED"}',  # results (JSON)
        )

        batch = _row_to_batch(row)

        assert batch.id == "batch-id-123"
        assert batch.workspace_id == "workspace-123"
        assert batch.task_ids == ["task-1", "task-2"]
        assert batch.status == BatchStatus.COMPLETED
        assert batch.strategy == "serial"
        assert batch.max_parallel == 4
        assert batch.on_failure == OnFailure.CONTINUE
        assert batch.results == {"task-1": "COMPLETED", "task-2": "COMPLETED"}

    def test_handles_null_completed_at(self):
        """Should handle NULL completed_at."""
        row = (
            "batch-id",
            "workspace-id",
            '["task-1"]',
            "RUNNING",
            "serial",
            4,
            "continue",
            "2025-01-15T10:00:00",
            None,  # completed_at is NULL
            None,  # results is NULL
        )

        batch = _row_to_batch(row)

        assert batch.completed_at is None
        assert batch.results == {}


class TestBatchExecution:
    """Integration tests for batch execution with various failure scenarios."""

    def test_all_tasks_succeed(self, workspace_with_tasks):
        """Batch should be COMPLETED when all tasks succeed."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            batch = start_batch(workspace, task_ids)

        assert batch.status == BatchStatus.COMPLETED
        assert len(batch.results) == 3
        assert all(status == "COMPLETED" for status in batch.results.values())

    def test_some_tasks_fail_continue(self, workspace_with_tasks):
        """Batch should be PARTIAL when some tasks fail with on_failure=continue."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # First task succeeds, second fails, third succeeds
        def mock_execute(ws, tid):
            if tid == task_ids[1]:
                return "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, on_failure="continue")

        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[0]] == "COMPLETED"
        assert batch.results[task_ids[1]] == "FAILED"
        assert batch.results[task_ids[2]] == "COMPLETED"

    def test_task_fails_stop(self, workspace_with_tasks, capsys):
        """Batch should stop immediately when task fails with on_failure=stop."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # First task succeeds, second fails
        def mock_execute(ws, tid):
            if tid == task_ids[1]:
                return "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, on_failure="stop")

        # Should stop after second task fails
        assert batch.status == BatchStatus.PARTIAL
        assert len(batch.results) == 2  # Only 2 tasks executed
        assert batch.results[task_ids[0]] == "COMPLETED"
        assert batch.results[task_ids[1]] == "FAILED"
        assert task_ids[2] not in batch.results  # Third task never ran

        captured = capsys.readouterr()
        assert "Stopping batch due to --on-failure=stop" in captured.out

    def test_all_tasks_fail(self, workspace_with_tasks):
        """Batch should be FAILED when all tasks fail."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "FAILED"
            batch = start_batch(workspace, task_ids, on_failure="continue")

        assert batch.status == BatchStatus.FAILED
        assert len(batch.results) == 3
        assert all(status == "FAILED" for status in batch.results.values())

    def test_task_blocked(self, workspace_with_tasks):
        """Batch should handle BLOCKED tasks and continue."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Second task becomes blocked
        def mock_execute(ws, tid):
            if tid == task_ids[1]:
                return "BLOCKED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, on_failure="continue")

        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[0]] == "COMPLETED"
        assert batch.results[task_ids[1]] == "BLOCKED"
        assert batch.results[task_ids[2]] == "COMPLETED"

    def test_mixed_results(self, workspace_with_tasks):
        """Batch should track mixed COMPLETED, FAILED, and BLOCKED results."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Task 1: COMPLETED, Task 2: BLOCKED, Task 3: FAILED
        def mock_execute(ws, tid):
            if tid == task_ids[0]:
                return "COMPLETED"
            elif tid == task_ids[1]:
                return "BLOCKED"
            else:
                return "FAILED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, on_failure="continue")

        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[0]] == "COMPLETED"
        assert batch.results[task_ids[1]] == "BLOCKED"
        assert batch.results[task_ids[2]] == "FAILED"

    def test_first_task_fails_stop(self, workspace_with_tasks):
        """Batch should stop after first task if it fails with on_failure=stop."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "FAILED"
            batch = start_batch(workspace, task_ids, on_failure="stop")

        # Only one task should have been executed
        assert batch.status == BatchStatus.FAILED
        assert len(batch.results) == 1
        assert batch.results[task_ids[0]] == "FAILED"

    def test_batch_completed_at_set(self, workspace_with_tasks):
        """Batch should have completed_at timestamp after execution."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list[:1]]

        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            batch = start_batch(workspace, task_ids)

        assert batch.completed_at is not None
        assert batch.completed_at >= batch.started_at

    def test_on_event_callback_called(self, workspace_with_tasks):
        """on_event callback should be called during execution."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list[:2]]

        events_received = []
        def on_event(event_type, payload):
            events_received.append((event_type, payload))

        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            batch = start_batch(workspace, task_ids, on_event=on_event)

        # Should have batch_started + 2x (task_started + task_completed)
        event_types = [e[0] for e in events_received]
        assert "batch_started" in event_types
        assert event_types.count("batch_task_started") == 2
        assert event_types.count("batch_task_completed") == 2


class TestSaveBatch:
    """Tests for _save_batch function."""

    def test_save_new_batch(self, workspace_with_tasks):
        """Should save a new batch to database."""
        workspace, task_list = workspace_with_tasks
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        batch = BatchRun(
            id="new-batch-123",
            workspace_id=workspace.id,
            task_ids=[task_list[0].id],
            status=BatchStatus.PENDING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=None,
            results={},
        )

        _save_batch(workspace, batch)

        # Verify saved
        loaded = get_batch(workspace, "new-batch-123")
        assert loaded is not None
        assert loaded.status == BatchStatus.PENDING

    def test_update_existing_batch(self, workspace_with_tasks):
        """Should update an existing batch."""
        workspace, task_list = workspace_with_tasks
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        batch = BatchRun(
            id="update-batch-123",
            workspace_id=workspace.id,
            task_ids=[task_list[0].id],
            status=BatchStatus.PENDING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=None,
            results={},
        )

        _save_batch(workspace, batch)

        # Update the batch
        batch.status = BatchStatus.COMPLETED
        batch.completed_at = datetime.now(timezone.utc)
        batch.results = {task_list[0].id: "COMPLETED"}

        _save_batch(workspace, batch)

        # Verify updated
        loaded = get_batch(workspace, "update-batch-123")
        assert loaded.status == BatchStatus.COMPLETED
        assert loaded.results[task_list[0].id] == "COMPLETED"
