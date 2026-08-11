"""#1146 — POST /api/v2/tasks/approve silently approved everything.

`ApproveTasksRequest` was exclusion-shaped: `excluded_task_ids`, no `task_ids`.
Pydantic's default is to DROP unknown fields, so the intuitive inclusion payload

    {"task_ids": ["<one-task>"]}

returned **200** and transitioned every BACKLOG task to READY — the exact
inverse of what the caller asked for, in silence.

Found while writing the #1068 API lifecycle driver, which did exactly this. The
test that "covered" scoped approval passed anyway: the chosen task *was* READY,
and so was everything else. That is the failure mode worth pinning — a wrong
result that looks right.

Options 1 and 2 from the issue, together: accept the inclusion shape properly,
and forbid unknown fields so the next mis-shaped payload is a 422 rather than a
silent inversion.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import tasks as core_tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path):
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def client(workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import tasks_v2

    app = FastAPI()
    app.include_router(tasks_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def three_tasks(workspace):
    return [
        core_tasks.create(workspace, title=f"Task {i}", description="d")
        for i in range(3)
    ]


def _statuses(workspace) -> dict:
    # limit=None: list_tasks defaults to 100, so the >100 cases below would
    # otherwise assert about a page rather than the backlog.
    return {t.id: t.status for t in core_tasks.list_tasks(workspace, limit=None)}


class TestTheInclusionShapeApprovesExactlyThose:
    """The bug, from the caller's side."""

    def test_only_the_named_task_becomes_ready(self, client, workspace, three_tasks):
        chosen = three_tasks[0].id

        res = client.post("/api/v2/tasks/approve", json={"task_ids": [chosen]})

        assert res.status_code == 200, res.text
        statuses = _statuses(workspace)
        assert statuses[chosen] == TaskStatus.READY
        # The assertion the old suite never made — and the reason it passed.
        assert [statuses[t.id] for t in three_tasks[1:]] == [
            TaskStatus.BACKLOG,
            TaskStatus.BACKLOG,
        ]

    def test_the_response_reports_what_it_actually_did(self, client, three_tasks):
        chosen = three_tasks[0].id

        body = client.post(
            "/api/v2/tasks/approve", json={"task_ids": [chosen]}
        ).json()

        assert body["approved_task_ids"] == [chosen]
        assert body["approved_count"] == 1
        assert body["excluded_count"] == 2


class TestTheExclusionShapeIsUnchanged:
    """The original contract still has callers; #1146 adds, it does not replace."""

    def test_everything_but_the_excluded_is_approved(self, client, workspace, three_tasks):
        skipped = three_tasks[2].id

        res = client.post(
            "/api/v2/tasks/approve", json={"excluded_task_ids": [skipped]}
        )

        assert res.status_code == 200, res.text
        statuses = _statuses(workspace)
        assert statuses[skipped] == TaskStatus.BACKLOG
        assert [statuses[t.id] for t in three_tasks[:2]] == [
            TaskStatus.READY,
            TaskStatus.READY,
        ]

    def test_an_empty_body_still_approves_the_whole_backlog(
        self, client, workspace, three_tasks
    ):
        assert client.post("/api/v2/tasks/approve", json={}).status_code == 200

        assert set(_statuses(workspace).values()) == {TaskStatus.READY}


class TestAmbiguousOrWrongRequestsAreRefused:
    def test_both_lists_at_once_is_422(self, client, three_tasks):
        res = client.post(
            "/api/v2/tasks/approve",
            json={
                "task_ids": [three_tasks[0].id],
                "excluded_task_ids": [three_tasks[1].id],
            },
        )

        assert res.status_code == 422, res.text

    def test_neither_list_is_silently_honoured(self, client, workspace, three_tasks):
        """Ambiguity must not resolve into a mutation."""
        client.post(
            "/api/v2/tasks/approve",
            json={
                "task_ids": [three_tasks[0].id],
                "excluded_task_ids": [three_tasks[1].id],
            },
        )

        assert set(_statuses(workspace).values()) == {TaskStatus.BACKLOG}

    def test_an_unknown_task_id_is_422_not_a_partial_approval(
        self, client, workspace, three_tasks
    ):
        """Approving fewer tasks than named, quietly, is the same class of bug."""
        res = client.post(
            "/api/v2/tasks/approve",
            json={"task_ids": [three_tasks[0].id, "no-such-task"]},
        )

        assert res.status_code == 422, res.text
        assert set(_statuses(workspace).values()) == {TaskStatus.BACKLOG}

    def test_an_unknown_field_is_422_rather_than_dropped(self, client, three_tasks):
        """The general form of the bug: `extra="forbid"` so the next
        mis-shaped payload cannot be silently reinterpreted."""
        res = client.post(
            "/api/v2/tasks/approve", json={"taskIds": [three_tasks[0].id]}
        )

        assert res.status_code == 422, res.text

    def test_nothing_is_approved_when_an_unknown_field_is_rejected(
        self, client, workspace, three_tasks
    ):
        client.post("/api/v2/tasks/approve", json={"taskIds": [three_tasks[0].id]})

        assert set(_statuses(workspace).values()) == {TaskStatus.BACKLOG}


class TestABacklogLargerThanThePageSize:
    """Review finding, and the exclusion path had it too.

    `tasks.list_tasks` defaults to `limit=100` (#743). `approve_tasks` used that
    default, so "approve everything" silently approved the first 100 of a bigger
    backlog — and the new inclusion path would have 422'd a valid id that sorted
    past the cap, which is precisely the "quietly does less than asked" failure
    this PR exists to remove.
    """

    #: One past the default page size. Keeping it just over the boundary keeps
    #: the test fast while still crossing it.
    COUNT = 105

    @pytest.fixture
    def many_tasks(self, workspace):
        return [
            core_tasks.create(workspace, title=f"Bulk {i:03d}", description="d")
            for i in range(self.COUNT)
        ]

    def test_approving_everything_reaches_past_the_page_size(
        self, client, workspace, many_tasks
    ):
        res = client.post("/api/v2/tasks/approve", json={})

        assert res.status_code == 200, res.text
        assert res.json()["approved_count"] == self.COUNT
        assert set(_statuses(workspace).values()) == {TaskStatus.READY}

    def test_a_task_past_the_page_size_can_be_named(self, client, workspace, many_tasks):
        chosen = many_tasks[-1].id

        res = client.post("/api/v2/tasks/approve", json={"task_ids": [chosen]})

        assert res.status_code == 200, res.text
        assert res.json()["approved_task_ids"] == [chosen]
        assert _statuses(workspace)[chosen] == TaskStatus.READY

    def test_the_excluded_count_covers_the_whole_backlog(
        self, client, many_tasks
    ):
        body = client.post(
            "/api/v2/tasks/approve", json={"task_ids": [many_tasks[0].id]}
        ).json()

        assert body["excluded_count"] == self.COUNT - 1


class TestTheCoreFunctionCarriesTheRule:
    """Core-first: the semantics live in runtime, not in the router, so the CLI
    and any other surface get the same behaviour."""

    def test_included_task_ids_approves_exactly_those(self, workspace, three_tasks):
        from codeframe.core import runtime

        result = runtime.approve_tasks(
            workspace, included_task_ids=[three_tasks[1].id]
        )

        assert result.approved_task_ids == [three_tasks[1].id]
        assert result.excluded_count == 2

    def test_both_arguments_raise(self, workspace, three_tasks):
        from codeframe.core import runtime

        with pytest.raises(ValueError, match="not both"):
            runtime.approve_tasks(
                workspace,
                excluded_task_ids=[three_tasks[0].id],
                included_task_ids=[three_tasks[1].id],
            )

    def test_an_already_ready_task_is_not_silently_skipped(self, workspace, three_tasks):
        """Only BACKLOG tasks are approvable. Naming one that is already READY
        would otherwise approve nothing and report success."""
        from codeframe.core import runtime

        core_tasks.update_status(workspace, three_tasks[0].id, TaskStatus.READY)

        with pytest.raises(ValueError, match="not approvable"):
            runtime.approve_tasks(workspace, included_task_ids=[three_tasks[0].id])
