"""Regression tests for #778 — `batch follow` double-counted completed tasks.

`batch follow` seeds its progress counters from ``batch.results`` and then
tails the event log. It computed ``since_id`` from the *oldest* recent batch
event (``list_recent`` is newest-first but the code indexed ``[-1]``), so
every historical batch event was replayed into the already-seeded counters —
completed tasks counted twice. The fix resumes from the newest event.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import events
from codeframe.core.conductor import BatchRun, BatchStatus, OnFailure, _save_batch
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def running_batch(tmp_path):
    """A RUNNING batch whose one task already completed (reflected in results)."""
    ws = create_or_load_workspace(tmp_path)
    task_id = str(uuid.uuid4())
    batch = BatchRun(
        id=str(uuid.uuid4()),
        workspace_id=ws.id,
        task_ids=[task_id],
        status=BatchStatus.RUNNING,
        strategy="serial",
        max_parallel=1,
        on_failure=OnFailure.CONTINUE,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        results={task_id: "COMPLETED"},
    )
    _save_batch(ws, batch)
    return ws, batch, task_id


def test_follow_resumes_from_newest_event(running_batch):
    """since_id must be the newest event id, not oldest-batch-event minus one."""
    ws, batch, task_id = running_batch

    # Historical events whose outcome is already reflected in batch.results.
    events.emit_for_workspace(
        ws,
        events.EventType.BATCH_TASK_STARTED,
        {"batch_id": batch.id, "task_id": task_id},
        print_event=False,
    )
    events.emit_for_workspace(
        ws,
        events.EventType.BATCH_TASK_COMPLETED,
        {"batch_id": batch.id, "task_id": task_id},
        print_event=False,
    )
    newest = events.list_recent(ws, limit=1)[0]

    captured = {}

    def fake_tail(workspace, since_id=0):
        captured["since_id"] = since_id
        yield events.Event(
            id=newest.id + 1,
            workspace_id=ws.id,
            event_type=events.EventType.BATCH_COMPLETED,
            payload={"batch_id": batch.id, "completed": 1, "total": 1},
            created_at=datetime.now(timezone.utc),
        )

    with patch("codeframe.core.events.tail", side_effect=fake_tail):
        result = runner.invoke(
            app,
            [
                "work", "batch", "follow", batch.id[:8],
                "--no-progress", "-w", str(ws.repo_path),
            ],
        )

    assert result.exit_code == 0, result.output
    # Resuming below the newest event replays history into counters that were
    # already seeded from batch.results — the #778 double count.
    assert captured["since_id"] == newest.id


def test_follow_seeds_in_flight_tasks_from_started_events(tmp_path):
    """Tasks already running at attach time must show as running, not pending.

    batch.results only records terminal states, so the running count is
    reconstructed from BATCH_TASK_STARTED events without a terminal result.
    """
    from codeframe.core.progress import BatchProgress

    ws = create_or_load_workspace(tmp_path)
    done_task = str(uuid.uuid4())
    running_task = str(uuid.uuid4())
    batch = BatchRun(
        id=str(uuid.uuid4()),
        workspace_id=ws.id,
        task_ids=[done_task, running_task],
        status=BatchStatus.RUNNING,
        strategy="serial",
        max_parallel=1,
        on_failure=OnFailure.CONTINUE,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        results={done_task: "COMPLETED"},
    )
    _save_batch(ws, batch)

    for task_id in (done_task, running_task):
        events.emit_for_workspace(
            ws,
            events.EventType.BATCH_TASK_STARTED,
            {"batch_id": batch.id, "task_id": task_id},
            print_event=False,
        )
    events.emit_for_workspace(
        ws,
        events.EventType.BATCH_TASK_COMPLETED,
        {"batch_id": batch.id, "task_id": done_task},
        print_event=False,
    )
    newest = events.list_recent(ws, limit=1)[0]

    created = []
    orig_progress = BatchProgress

    def capture(*args, **kwargs):
        p = orig_progress(*args, **kwargs)
        created.append(p)
        return p

    def fake_tail(workspace, since_id=0):
        yield events.Event(
            id=newest.id + 1,
            workspace_id=ws.id,
            event_type=events.EventType.BATCH_COMPLETED,
            payload={"batch_id": batch.id, "completed": 2, "total": 2},
            created_at=datetime.now(timezone.utc),
        )

    with (
        patch("codeframe.core.progress.BatchProgress", side_effect=capture),
        patch("codeframe.core.events.tail", side_effect=fake_tail),
    ):
        result = runner.invoke(
            app,
            [
                "work", "batch", "follow", batch.id[:8],
                "--no-progress", "-w", str(ws.repo_path),
            ],
        )

    assert result.exit_code == 0, result.output
    assert len(created) == 1
    progress = created[0]
    # Completed count seeded from results exactly once (no event replay)
    assert progress.completed_tasks == 1
    # The in-flight task is seeded as running; the completed one is not
    assert set(progress.task_start_times) == {running_task}
