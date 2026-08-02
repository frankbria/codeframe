"""update_status must be a compare-and-set, not read-then-blind-write (#930).

`update_status` read the task, validated the transition, then UPDATEd on
`(workspace_id, id)` only — no guard on the status it had just validated against
and no transaction spanning the read and the write. Two writers could each pass
validation against stale state and both commit, and two racing DONE transitions
each fired the GitHub auto-close.

The race is exercised deterministically (a stale read is injected) rather than
with threads: timing-based concurrency tests in this repo flake under full-suite
load — see #976 and #1038.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core import tasks
from codeframe.core.state_machine import InvalidTransitionError
from codeframe.core.tasks import TaskStatus
from codeframe.core.workspace import Workspace, create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def task(workspace: Workspace):
    return tasks.create(
        workspace, title="Race me", description="d", status=TaskStatus.READY
    )


def _db_status(workspace: Workspace, task_id: str) -> str:
    conn = get_db_connection(workspace)
    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return row[0]


class TestUpdateStatusIsCompareAndSet:
    def test_stale_writer_loses_and_changes_nothing(self, workspace, task):
        """The second of two writers that both validated against READY must fail."""
        stale = tasks.get(workspace, task.id)  # snapshot at READY

        tasks.update_status(workspace, task.id, TaskStatus.IN_PROGRESS)  # writer A wins
        assert _db_status(workspace, task.id) == TaskStatus.IN_PROGRESS.value

        # Writer B validated against the same stale READY snapshot.
        with patch.object(tasks, "get", return_value=stale):
            with pytest.raises(InvalidTransitionError):
                tasks.update_status(workspace, task.id, TaskStatus.IN_PROGRESS)

        assert _db_status(workspace, task.id) == TaskStatus.IN_PROGRESS.value

    def test_loser_does_not_rewrite_updated_at(self, workspace, task):
        stale = tasks.get(workspace, task.id)
        tasks.update_status(workspace, task.id, TaskStatus.IN_PROGRESS)
        before = tasks.get(workspace, task.id).updated_at

        with patch.object(tasks, "get", return_value=stale):
            with pytest.raises(InvalidTransitionError):
                tasks.update_status(workspace, task.id, TaskStatus.IN_PROGRESS)

        assert tasks.get(workspace, task.id).updated_at == before

    def test_normal_transition_still_works(self, workspace, task):
        tasks.update_status(workspace, task.id, TaskStatus.IN_PROGRESS)
        result = tasks.update_status(workspace, task.id, TaskStatus.DONE)

        assert result.status == TaskStatus.DONE
        assert _db_status(workspace, task.id) == TaskStatus.DONE.value

    def test_missing_task_still_raises_value_error(self, workspace):
        with pytest.raises(ValueError, match="not found"):
            tasks.update_status(workspace, "no-such-task", TaskStatus.DONE)


class TestGithubAutocloseFiresOnce:
    def test_racing_done_transitions_close_the_issue_once(self, workspace, task):
        tasks.update_status(workspace, task.id, TaskStatus.IN_PROGRESS)
        stale = tasks.get(workspace, task.id)  # snapshot at IN_PROGRESS

        with patch.object(tasks, "_dispatch_github_autoclose") as dispatch:
            tasks.update_status(workspace, task.id, TaskStatus.DONE)  # writer A

            with patch.object(tasks, "get", return_value=stale):
                with pytest.raises(InvalidTransitionError):
                    tasks.update_status(workspace, task.id, TaskStatus.DONE)  # writer B

        assert dispatch.call_count == 1, (
            "the losing DONE transition still fired the GitHub auto-close"
        )

    def test_autoclose_still_fires_on_a_normal_done(self, workspace, task):
        tasks.update_status(workspace, task.id, TaskStatus.IN_PROGRESS)

        with patch.object(tasks, "_dispatch_github_autoclose") as dispatch:
            tasks.update_status(workspace, task.id, TaskStatus.DONE)

        assert dispatch.call_count == 1
