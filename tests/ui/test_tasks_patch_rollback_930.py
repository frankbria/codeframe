"""PATCH /api/v2/tasks/{id} must not leave partial state on failure (#930).

The handler performed up to four independent commits — auto-close flag, status
transition (which fires the GitHub issue close), then the title/description/
priority update. A failure at the final update returned 500 with the status
change already committed and the issue possibly closed; the retry then 400'd on
DONE -> DONE.

The writes are now ordered so the irreversible one (the status transition, which
dispatches the GitHub close) happens last, and any failure restores the
reversible values captured before the first write.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import tasks
from codeframe.core.state_machine import InvalidTransitionError, TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def client_and_task():
    tmp = Path(tempfile.mkdtemp())
    ws_dir = tmp / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    ws = create_or_load_workspace(ws_dir)
    task = tasks.create(
        ws,
        title="original title",
        description="original description",
        status=TaskStatus.IN_PROGRESS,
        priority=3,
        github_issue_number=7,
        external_url="https://github.com/acme/app/issues/7",
        auto_close_github_issue=False,
    )

    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import tasks_v2

    app = FastAPI()
    app.include_router(tasks_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: ws
    yield TestClient(app, raise_server_exceptions=False), ws, task.id
    shutil.rmtree(tmp, ignore_errors=True)


class TestPatchLeavesNoPartialState:
    def test_field_update_failure_rolls_back_everything(self, client_and_task):
        """An injected failure in the field update must revert the whole PATCH."""
        client, ws, task_id = client_and_task

        with patch.object(tasks, "update", side_effect=RuntimeError("disk full")):
            response = client.patch(
                f"/api/v2/tasks/{task_id}",
                json={
                    "title": "new title",
                    "priority": 9,
                    "status": "DONE",
                    "auto_close_github_issue": True,
                },
            )

        assert response.status_code == 500

        after = tasks.get(ws, task_id)
        assert after.status == TaskStatus.IN_PROGRESS, "status change survived a failed PATCH"
        assert after.title == "original title"
        assert after.priority == 3
        assert after.auto_close_github_issue is False

    def test_failed_patch_does_not_close_the_github_issue(self, client_and_task):
        """The irreversible side effect must not fire when the PATCH fails."""
        client, ws, task_id = client_and_task

        with (
            patch.object(tasks, "update", side_effect=RuntimeError("disk full")),
            patch.object(tasks, "_dispatch_github_autoclose") as dispatch,
        ):
            client.patch(
                f"/api/v2/tasks/{task_id}",
                json={"title": "new title", "status": "DONE",
                      "auto_close_github_issue": True},
            )

        dispatch.assert_not_called()

    def test_failed_patch_is_retryable(self, client_and_task):
        """After the rollback the same PATCH must succeed, not 400 on DONE->DONE."""
        client, ws, task_id = client_and_task
        payload = {"title": "new title", "priority": 9, "status": "DONE"}

        with patch.object(tasks, "update", side_effect=RuntimeError("disk full")):
            assert client.patch(f"/api/v2/tasks/{task_id}", json=payload).status_code == 500

        with patch.object(tasks, "_dispatch_github_autoclose"):
            retry = client.patch(f"/api/v2/tasks/{task_id}", json=payload)

        assert retry.status_code == 200, retry.text
        after = tasks.get(ws, task_id)
        assert after.status == TaskStatus.DONE
        assert after.title == "new title"
        assert after.priority == 9


class TestRollbackOnlyUndoesThisRequestsWrites:
    """The rollback must not clobber a concurrent writer's fields.

    Raised by `codex review` on this PR: a status-only PATCH that loses the new
    compare-and-set race must not rewrite title/description/priority from its
    snapshot — it never wrote them, and the request that won may have.
    """

    def test_status_only_patch_losing_the_race_leaves_fields_alone(
        self, client_and_task
    ):
        """The winner must write AFTER our snapshot, or the test proves nothing."""
        client, ws, task_id = client_and_task

        def winner_lands_then_we_lose(*_args, **_kwargs):
            # Runs inside the request, after `current` was snapshotted — exactly
            # the interleaving the compare-and-set surfaces as a lost update.
            tasks.update(ws, task_id, title="winner's title", priority=1)
            raise InvalidTransitionError(TaskStatus.DONE, TaskStatus.DONE)

        with patch.object(tasks, "update_status", side_effect=winner_lands_then_we_lose):
            response = client.patch(f"/api/v2/tasks/{task_id}", json={"status": "DONE"})

        assert response.status_code == 409, response.text
        after = tasks.get(ws, task_id)
        assert after.title == "winner's title", "rollback clobbered a field it never wrote"
        assert after.priority == 1

    def test_status_only_patch_losing_the_race_leaves_auto_close_alone(
        self, client_and_task
    ):
        """Guard, not a reproduction: the flagged version skipped the auto-close
        restore for a status-only PATCH anyway (`original_auto_close` was None).
        This pins the behavior now that the skip is driven by `wrote_auto_close`.
        """
        client, ws, task_id = client_and_task

        def winner_lands_then_we_lose(*_args, **_kwargs):
            tasks.update_auto_close(ws, task_id, True)
            raise InvalidTransitionError(TaskStatus.DONE, TaskStatus.DONE)

        with patch.object(tasks, "update_status", side_effect=winner_lands_then_we_lose):
            response = client.patch(f"/api/v2/tasks/{task_id}", json={"status": "DONE"})

        assert response.status_code == 409
        assert tasks.get(ws, task_id).auto_close_github_issue is True


class TestPatchHappyPathUnchanged:
    def test_combined_status_and_fields_apply(self, client_and_task):
        client, ws, task_id = client_and_task

        with patch.object(tasks, "_dispatch_github_autoclose") as dispatch:
            response = client.patch(
                f"/api/v2/tasks/{task_id}",
                json={
                    "title": "shipped",
                    "description": "done and dusted",
                    "priority": 1,
                    "status": "DONE",
                    "auto_close_github_issue": True,
                },
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["title"] == "shipped"
        assert body["description"] == "done and dusted"
        assert body["priority"] == 1
        assert body["status"] == "DONE"
        assert body["auto_close_github_issue"] is True
        dispatch.assert_called_once()

        after = tasks.get(ws, task_id)
        assert after.status == TaskStatus.DONE
        assert after.title == "shipped"

    def test_opt_out_on_done_does_not_close(self, client_and_task):
        client, ws, task_id = client_and_task

        with patch.object(tasks, "_close_issue_background") as closer:
            response = client.patch(
                f"/api/v2/tasks/{task_id}",
                json={"status": "DONE", "auto_close_github_issue": False},
            )

        assert response.status_code == 200, response.text
        closer.assert_not_called()

    def test_fields_only_patch_does_not_touch_status(self, client_and_task):
        client, ws, task_id = client_and_task

        response = client.patch(f"/api/v2/tasks/{task_id}", json={"title": "renamed"})

        assert response.status_code == 200, response.text
        after = tasks.get(ws, task_id)
        assert after.title == "renamed"
        assert after.status == TaskStatus.IN_PROGRESS
