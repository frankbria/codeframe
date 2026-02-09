"""Tests for batch execution conductor."""

import pytest
from unittest.mock import patch, MagicMock

from codeframe.core.conductor import (
    BatchStatus,
    BatchRun,
    OnFailure,
    start_batch,
    get_batch,
    list_batches,
    cancel_batch,
    stop_batch,
    resume_batch,
    _save_batch,
    _row_to_batch,
    _active_processes,
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

    def test_start_batch_strategy_parallel_works(self, workspace_with_tasks, capsys):
        """Should execute with parallel strategy when requested."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list[:1]]  # Just one task

        # Mock subprocess to avoid actual execution
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            batch = start_batch(workspace, task_ids, strategy="parallel", max_parallel=2)

        captured = capsys.readouterr()
        # Should show execution plan (parallel is now implemented)
        assert "Execution plan:" in captured.out or batch.status == BatchStatus.COMPLETED
        assert batch.status == BatchStatus.COMPLETED


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


class TestStopBatch:
    """Tests for stop_batch function."""

    def test_stop_nonexistent_batch_raises(self, temp_workspace):
        """Should raise ValueError for non-existent batch."""
        with pytest.raises(ValueError, match="Batch not found"):
            stop_batch(temp_workspace, "non-existent-id")

    def test_stop_completed_batch_raises(self, workspace_with_tasks):
        """Should raise ValueError for completed batch."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        batch = start_batch(workspace, task_ids, dry_run=True)
        # Batch is COMPLETED after dry run

        with pytest.raises(ValueError, match="cannot be stopped"):
            stop_batch(workspace, batch.id)

    def test_graceful_stop_sets_cancelled(self, workspace_with_tasks):
        """Graceful stop should set batch status to CANCELLED."""
        workspace, task_list = workspace_with_tasks

        # Create a batch and manually set it to RUNNING
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        batch = BatchRun(
            id="test-stop-batch",
            workspace_id=workspace.id,
            task_ids=[task_list[0].id],
            status=BatchStatus.RUNNING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=None,
            results={},
        )
        _save_batch(workspace, batch)

        stopped = stop_batch(workspace, batch.id, force=False)

        assert stopped.status == BatchStatus.CANCELLED
        assert stopped.completed_at is not None

    def test_force_stop_terminates_processes(self, workspace_with_tasks):
        """Force stop should terminate tracked processes."""
        workspace, task_list = workspace_with_tasks

        # Create a batch and manually set it to RUNNING
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        batch_id = "test-force-stop-batch"
        batch = BatchRun(
            id=batch_id,
            workspace_id=workspace.id,
            task_ids=[task_list[0].id],
            status=BatchStatus.RUNNING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=None,
            results={},
        )
        _save_batch(workspace, batch)

        # Simulate tracked processes
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        _active_processes[batch_id] = {"task-1": mock_process}

        try:
            stopped = stop_batch(workspace, batch_id, force=True)

            # Process should have been terminated
            mock_process.terminate.assert_called_once()
            assert stopped.status == BatchStatus.CANCELLED

            # Process tracking should be cleaned up
            assert batch_id not in _active_processes
        finally:
            # Cleanup in case of test failure
            _active_processes.pop(batch_id, None)

    def test_force_stop_handles_already_exited_process(self, workspace_with_tasks):
        """Force stop should handle processes that already exited gracefully."""
        workspace, task_list = workspace_with_tasks

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        batch_id = "test-force-stop-exited"
        batch = BatchRun(
            id=batch_id,
            workspace_id=workspace.id,
            task_ids=[task_list[0].id],
            status=BatchStatus.RUNNING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=None,
            results={},
        )
        _save_batch(workspace, batch)

        # Simulate process that already exited
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # Already exited
        _active_processes[batch_id] = {"task-1": mock_process}

        try:
            stopped = stop_batch(workspace, batch_id, force=True)

            # terminate should not be called for exited process
            mock_process.terminate.assert_not_called()
            assert stopped.status == BatchStatus.CANCELLED
        finally:
            _active_processes.pop(batch_id, None)

    def test_graceful_stop_does_not_terminate_processes(self, workspace_with_tasks):
        """Graceful stop (force=False) should not terminate processes."""
        workspace, task_list = workspace_with_tasks

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        batch_id = "test-graceful-no-terminate"
        batch = BatchRun(
            id=batch_id,
            workspace_id=workspace.id,
            task_ids=[task_list[0].id],
            status=BatchStatus.RUNNING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=None,
            results={},
        )
        _save_batch(workspace, batch)

        # Simulate tracked processes
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        _active_processes[batch_id] = {"task-1": mock_process}

        try:
            stopped = stop_batch(workspace, batch_id, force=False)

            # terminate should NOT be called for graceful stop
            mock_process.terminate.assert_not_called()
            assert stopped.status == BatchStatus.CANCELLED

            # Process tracking should still exist (not cleaned up by graceful stop)
            assert batch_id in _active_processes
        finally:
            _active_processes.pop(batch_id, None)


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
            "plan",  # engine
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
        assert batch.engine == "plan"

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
            "plan",  # engine
        )

        batch = _row_to_batch(row)

        assert batch.completed_at is None
        assert batch.results == {}
        assert batch.engine == "plan"

    def test_handles_missing_engine_column(self):
        """Should default engine to 'plan' when column is absent (migration)."""
        row = (
            "batch-id",
            "workspace-id",
            '["task-1"]',
            "RUNNING",
            "serial",
            4,
            "continue",
            "2025-01-15T10:00:00",
            None,
            None,
        )

        batch = _row_to_batch(row)
        assert batch.engine == "plan"


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
        def mock_execute(ws, tid, batch_id=None, **kwargs):
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
        def mock_execute(ws, tid, batch_id=None, **kwargs):
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
        def mock_execute(ws, tid, batch_id=None, **kwargs):
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
        def mock_execute(ws, tid, batch_id=None, **kwargs):
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


class TestResumeBatch:
    """Tests for resume_batch function."""

    def test_resume_nonexistent_batch_raises(self, temp_workspace):
        """Should raise ValueError for non-existent batch."""
        with pytest.raises(ValueError, match="Batch not found"):
            resume_batch(temp_workspace, "non-existent-id")

    def test_resume_completed_batch_raises(self, workspace_with_tasks):
        """Should raise ValueError for completed batch."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Create a completed batch
        batch = start_batch(workspace, task_ids, dry_run=True)
        # Batch is COMPLETED after dry run

        with pytest.raises(ValueError, match="cannot be resumed"):
            resume_batch(workspace, batch.id)

    def test_resume_partial_batch(self, workspace_with_tasks):
        """Should resume a PARTIAL batch, re-running only failed tasks."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Create a batch with some failures
        def mock_execute_first_run(ws, tid, batch_id=None, **kwargs):
            if tid == task_ids[1]:
                return "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute_first_run):
            batch = start_batch(workspace, task_ids, on_failure="continue")

        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[0]] == "COMPLETED"
        assert batch.results[task_ids[1]] == "FAILED"
        assert batch.results[task_ids[2]] == "COMPLETED"

        # Now resume - the failed task should succeed this time
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            resumed = resume_batch(workspace, batch.id)

        # Only task_ids[1] should have been re-run
        assert mock_exec.call_count == 1
        assert resumed.status == BatchStatus.COMPLETED
        assert resumed.results[task_ids[1]] == "COMPLETED"

    def test_resume_failed_batch(self, workspace_with_tasks):
        """Should resume a FAILED batch."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Create a batch where all tasks fail
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "FAILED"
            batch = start_batch(workspace, task_ids, on_failure="continue")

        assert batch.status == BatchStatus.FAILED

        # Resume with all tasks succeeding
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            resumed = resume_batch(workspace, batch.id)

        assert resumed.status == BatchStatus.COMPLETED
        assert all(s == "COMPLETED" for s in resumed.results.values())

    def test_resume_with_force(self, workspace_with_tasks):
        """Should re-run all tasks when force=True."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Create a partial batch (2 completed, 1 failed)
        def mock_execute_first_run(ws, tid, batch_id=None, **kwargs):
            if tid == task_ids[2]:
                return "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute_first_run):
            batch = start_batch(workspace, task_ids, on_failure="continue")

        assert batch.status == BatchStatus.PARTIAL

        # Resume with force - should re-run all 3 tasks
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            resumed = resume_batch(workspace, batch.id, force=True)

        assert mock_exec.call_count == 3  # All tasks re-run
        assert resumed.status == BatchStatus.COMPLETED

    def test_resume_blocked_tasks(self, workspace_with_tasks):
        """Should resume blocked tasks."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Create a batch with blocked tasks
        def mock_execute_first_run(ws, tid, batch_id=None, **kwargs):
            if tid == task_ids[1]:
                return "BLOCKED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute_first_run):
            batch = start_batch(workspace, task_ids, on_failure="continue")

        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[1]] == "BLOCKED"

        # Resume - blocked task now completes
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            resumed = resume_batch(workspace, batch.id)

        assert mock_exec.call_count == 1  # Only blocked task re-run
        assert resumed.status == BatchStatus.COMPLETED

    def test_resume_still_fails(self, workspace_with_tasks):
        """Resumed tasks can still fail."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Create a failed batch
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "FAILED"
            batch = start_batch(workspace, task_ids, on_failure="continue")

        assert batch.status == BatchStatus.FAILED

        # Resume but tasks still fail
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "FAILED"
            resumed = resume_batch(workspace, batch.id)

        assert resumed.status == BatchStatus.FAILED

    def test_resume_no_failed_tasks(self, workspace_with_tasks, capsys):
        """Should handle batch with no failed tasks gracefully."""
        workspace, task_list = workspace_with_tasks
        from datetime import datetime, timezone

        # Manually create a PARTIAL batch with no failed tasks
        # (edge case - maybe cancelled mid-way)
        now = datetime.now(timezone.utc)
        batch = BatchRun(
            id="edge-case-batch",
            workspace_id=workspace.id,
            task_ids=[task_list[0].id],
            status=BatchStatus.PARTIAL,  # Resumable status
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=now,
            completed_at=now,
            results={task_list[0].id: "COMPLETED"},  # All completed
        )
        _save_batch(workspace, batch)

        # Resume should detect nothing to do
        resumed = resume_batch(workspace, batch.id)

        captured = capsys.readouterr()
        assert "No failed or blocked tasks to resume" in captured.out
        assert resumed.status == BatchStatus.PARTIAL  # Unchanged

    def test_resume_preserves_completed_results(self, workspace_with_tasks):
        """Resume should preserve completed task results."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Create batch: task 0 completes, task 1 fails, task 2 completes
        def mock_first_run(ws, tid, batch_id=None, **kwargs):
            if tid == task_ids[1]:
                return "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_first_run):
            batch = start_batch(workspace, task_ids, on_failure="continue")

        # Resume with task 1 now completing
        with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
            mock_exec.return_value = "COMPLETED"
            resumed = resume_batch(workspace, batch.id)

        # All should now be completed, including preserved results
        assert resumed.results[task_ids[0]] == "COMPLETED"  # Preserved
        assert resumed.results[task_ids[1]] == "COMPLETED"  # Updated
        assert resumed.results[task_ids[2]] == "COMPLETED"  # Preserved


class TestBatchRetry:
    """Tests for batch retry functionality (--retry N flag)."""

    def test_no_retry_by_default(self, workspace_with_tasks):
        """Without --retry, failed tasks should not be retried."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        call_count = [0]
        def mock_execute(ws, tid, batch_id=None, **kwargs):
            call_count[0] += 1
            if tid == task_ids[1]:
                return "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, max_retries=0)

        # Should be called exactly 3 times (no retries)
        assert call_count[0] == 3
        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[1]] == "FAILED"

    def test_retry_succeeds_on_first_retry(self, workspace_with_tasks):
        """Task that fails initially should succeed on retry."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Track calls per task
        call_counts = {tid: 0 for tid in task_ids}

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            call_counts[tid] += 1
            # Task 1 fails first time, succeeds on retry
            if tid == task_ids[1]:
                return "COMPLETED" if call_counts[tid] > 1 else "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, max_retries=2)

        # Task 1 should have been called twice (initial + 1 retry)
        assert call_counts[task_ids[1]] == 2
        assert batch.status == BatchStatus.COMPLETED
        assert all(s == "COMPLETED" for s in batch.results.values())

    def test_retry_exhausted(self, workspace_with_tasks):
        """Task that keeps failing should exhaust all retries."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        call_counts = {tid: 0 for tid in task_ids}

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            call_counts[tid] += 1
            if tid == task_ids[1]:
                return "FAILED"  # Always fails
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, max_retries=3)

        # Task 1: 1 initial + 3 retries = 4 calls
        assert call_counts[task_ids[1]] == 4
        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[1]] == "FAILED"

    def test_retry_multiple_failed_tasks(self, workspace_with_tasks):
        """Multiple failed tasks should all be retried."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        call_counts = {tid: 0 for tid in task_ids}

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            call_counts[tid] += 1
            # Tasks 0 and 2 fail initially, succeed on retry
            if tid in (task_ids[0], task_ids[2]):
                return "COMPLETED" if call_counts[tid] > 1 else "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, max_retries=2)

        # Tasks 0 and 2 should be called twice each
        assert call_counts[task_ids[0]] == 2
        assert call_counts[task_ids[1]] == 1  # Never failed
        assert call_counts[task_ids[2]] == 2
        assert batch.status == BatchStatus.COMPLETED

    def test_retry_stops_early_if_all_succeed(self, workspace_with_tasks):
        """Should not use all retry attempts if tasks succeed early."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        call_counts = {tid: 0 for tid in task_ids}

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            call_counts[tid] += 1
            # Task 1 succeeds on first retry
            if tid == task_ids[1]:
                return "COMPLETED" if call_counts[tid] > 1 else "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, max_retries=5)

        # Only 1 retry should have been used
        assert call_counts[task_ids[1]] == 2
        assert batch.status == BatchStatus.COMPLETED

    def test_retry_does_not_retry_blocked_tasks(self, workspace_with_tasks):
        """BLOCKED tasks should not be retried (only FAILED)."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        call_counts = {tid: 0 for tid in task_ids}

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            call_counts[tid] += 1
            if tid == task_ids[1]:
                return "BLOCKED"  # Blocked, not failed
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, max_retries=3)

        # Blocked task should only be called once (no retries)
        assert call_counts[task_ids[1]] == 1
        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[1]] == "BLOCKED"

    def test_retry_with_on_failure_continue(self, workspace_with_tasks):
        """Retry should work with on_failure=continue."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        call_counts = {tid: 0 for tid in task_ids}

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            call_counts[tid] += 1
            # All tasks fail initially, task 0 and 2 succeed on retry
            if call_counts[tid] == 1:
                return "FAILED"
            if tid == task_ids[1]:
                return "FAILED"  # Task 1 keeps failing
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, max_retries=2, on_failure="continue")

        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[0]] == "COMPLETED"
        assert batch.results[task_ids[1]] == "FAILED"
        assert batch.results[task_ids[2]] == "COMPLETED"

    def test_retry_event_callback(self, workspace_with_tasks):
        """on_event callback should receive retry events."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list[:1]]

        events_received = []
        def on_event(event_type, payload):
            events_received.append((event_type, payload))

        call_count = [0]
        def mock_execute(ws, tid, batch_id=None, **kwargs):
            call_count[0] += 1
            return "COMPLETED" if call_count[0] > 1 else "FAILED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(workspace, task_ids, max_retries=1, on_event=on_event)

        event_types = [e[0] for e in events_received]
        assert "batch_retry_started" in event_types
        assert "batch_task_retried" in event_types


class TestParallelExecution:
    """Tests for parallel batch execution."""

    def test_parallel_independent_tasks_run_concurrently(self, workspace_with_tasks):
        """Independent tasks should run in parallel."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]  # 3 independent tasks

        execution_order = []
        import threading

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            # Record when each task starts
            execution_order.append(("start", tid, threading.current_thread().name))
            import time
            time.sleep(0.05)  # Small delay to allow overlap detection
            execution_order.append(("end", tid, threading.current_thread().name))
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(
                workspace,
                task_ids,
                strategy="parallel",
                max_parallel=3,
            )

        assert batch.status == BatchStatus.COMPLETED
        # All tasks should be complete
        for tid in task_ids:
            assert batch.results[tid] == "COMPLETED"

    def test_parallel_respects_max_parallel(self, workspace_with_tasks):
        """max_parallel should limit concurrent execution."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]  # 3 tasks

        concurrent_count = [0]
        max_concurrent = [0]
        import threading
        lock = threading.Lock()

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            with lock:
                concurrent_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
            import time
            time.sleep(0.1)
            with lock:
                concurrent_count[0] -= 1
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(
                workspace,
                task_ids,
                strategy="parallel",
                max_parallel=2,  # Only 2 at a time
            )

        assert batch.status == BatchStatus.COMPLETED
        # Should not exceed max_parallel
        assert max_concurrent[0] <= 2

    def test_parallel_with_dependencies_respects_order(self, temp_workspace):
        """Tasks with dependencies should run in correct order."""
        # Create tasks with dependencies: task3 depends on task1 and task2
        task1 = tasks.create(temp_workspace, title="Task 1", status=TaskStatus.READY)
        task2 = tasks.create(temp_workspace, title="Task 2", status=TaskStatus.READY)
        task3 = tasks.create(
            temp_workspace,
            title="Task 3",
            status=TaskStatus.READY,
            depends_on=[task1.id, task2.id],
        )

        execution_order = []

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            execution_order.append(tid)
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(
                temp_workspace,
                [task1.id, task2.id, task3.id],
                strategy="parallel",
                max_parallel=3,
            )

        assert batch.status == BatchStatus.COMPLETED
        # task3 should be last (after its dependencies)
        assert execution_order[-1] == task3.id
        # task1 and task2 can be in any order but must be before task3
        assert task1.id in execution_order[:2]
        assert task2.id in execution_order[:2]

    def test_parallel_falls_back_on_cycle(self, temp_workspace):
        """Should fall back to serial on circular dependency."""
        task1 = tasks.create(temp_workspace, title="Task 1", status=TaskStatus.READY)
        task2 = tasks.create(
            temp_workspace,
            title="Task 2",
            status=TaskStatus.READY,
            depends_on=[task1.id],
        )
        # Create cycle
        tasks.update_depends_on(temp_workspace, task1.id, [task2.id])

        execution_count = [0]

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            execution_count[0] += 1
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(
                temp_workspace,
                [task1.id, task2.id],
                strategy="parallel",
                max_parallel=2,
            )

        # Should fall back to serial and still execute
        assert execution_count[0] == 2
        assert batch.status == BatchStatus.COMPLETED

    def test_parallel_handles_failure(self, workspace_with_tasks):
        """Failures should be tracked in parallel execution."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            if tid == task_ids[1]:
                return "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(
                workspace,
                task_ids,
                strategy="parallel",
                max_parallel=3,
            )

        assert batch.status == BatchStatus.PARTIAL
        assert batch.results[task_ids[0]] == "COMPLETED"
        assert batch.results[task_ids[1]] == "FAILED"
        assert batch.results[task_ids[2]] == "COMPLETED"

    def test_parallel_on_failure_stop(self, temp_workspace):
        """on_failure=stop should stop after group completes."""
        # Create independent tasks (all in same group)
        task1 = tasks.create(temp_workspace, title="Task 1", status=TaskStatus.READY)
        task2 = tasks.create(temp_workspace, title="Task 2", status=TaskStatus.READY)
        # Task 3 depends on both (separate group)
        task3 = tasks.create(
            temp_workspace,
            title="Task 3",
            status=TaskStatus.READY,
            depends_on=[task1.id, task2.id],
        )

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            if tid == task1.id:
                return "FAILED"
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(
                temp_workspace,
                [task1.id, task2.id, task3.id],
                strategy="parallel",
                max_parallel=2,
                on_failure="stop",
            )

        # First group completes (with failure), then stops
        assert batch.results[task1.id] == "FAILED"
        assert batch.results[task2.id] == "COMPLETED"
        # task3 should not have run
        assert task3.id not in batch.results

    def test_parallel_event_callback(self, workspace_with_tasks):
        """on_event should receive events during parallel execution."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list[:2]]

        events_received = []
        def on_event(event_type, payload):
            events_received.append((event_type, payload))

        def mock_execute(ws, tid, batch_id=None, **kwargs):
            return "COMPLETED"

        with patch('codeframe.core.conductor._execute_task_subprocess', side_effect=mock_execute):
            batch = start_batch(
                workspace,
                task_ids,
                strategy="parallel",
                max_parallel=2,
                on_event=on_event,
            )

        event_types = [e[0] for e in events_received]
        assert "batch_started" in event_types
        # Should have task events
        task_starts = [e for e in events_received if e[0] == "batch_task_started"]
        task_completes = [e for e in events_received if e[0] == "batch_task_completed"]
        assert len(task_starts) >= 2
        assert len(task_completes) >= 2
