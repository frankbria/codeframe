"""Checkpoint restore leaves MERGED tasks and live runs alone (#1306).

It wrote raw statuses back, which revived MERGED tasks (a terminal state) and
stranded a running agent under a task now marked READY. And it reported the
snapshot's task count rather than how many rows it actually changed.
"""

import pytest

from codeframe.core import checkpoints, runtime, tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


def _walk(ws, task_id, *statuses):
    for s in statuses:
        tasks.update_status(ws, task_id, s)


@pytest.fixture
def ws(tmp_path):
    return create_or_load_workspace(tmp_path)


def test_restore_skips_merged_and_running_tasks_and_counts_real_updates(ws):
    plain = tasks.create(ws, title="plain")
    merged = tasks.create(ws, title="merged")
    running = tasks.create(ws, title="running")
    gone = tasks.create(ws, title="deleted later")
    same = tasks.create(ws, title="unchanged since")
    for t in (plain, merged, running, gone, same):
        _walk(ws, t.id, TaskStatus.READY)
    cp = checkpoints.create(ws, "before", include_git_ref=False)

    _walk(ws, plain.id, TaskStatus.IN_PROGRESS)
    _walk(ws, merged.id, TaskStatus.IN_PROGRESS, TaskStatus.DONE, TaskStatus.MERGED)
    runtime.start_task_run(ws, running.id)  # IN_PROGRESS with a RUNNING run
    tasks.delete(ws, gone.id)

    result = checkpoints.restore(ws, cp.id)

    assert tasks.get(ws, plain.id).status == TaskStatus.READY
    assert tasks.get(ws, merged.id).status == TaskStatus.MERGED
    assert tasks.get(ws, running.id).status == TaskStatus.IN_PROGRESS
    assert tasks.get(ws, same.id).status == TaskStatus.READY
    assert result.restored == 1  # `same` matched but did not change
    assert set(result.skipped) == {merged.id, running.id}
