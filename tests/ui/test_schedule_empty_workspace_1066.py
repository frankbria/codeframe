"""#1066 — an empty workspace is not a missing one.

All three schedule endpoints mapped `ValueError("No tasks found in workspace")`
to 404, so a brand-new workspace — the first state every client meets — got
"not found" for a schedule that is simply empty. A client could not tell that
apart from asking for a workspace that does not exist without string-matching
the detail.

`core/schedule.py` is consumed only by this router (the CLI uses a different
scheduler), so the fix is in core: an empty workspace yields an empty result.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import schedule, tasks
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def client(workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import schedule_v2

    app = FastAPI()
    app.include_router(schedule_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    return TestClient(app)


class TestTheCoreReturnsEmptyResults:
    """Fixed in core so every surface benefits, not just this router."""

    def test_schedule_is_empty_not_an_error(self, workspace):
        result = schedule.get_schedule(workspace)
        assert result.task_assignments == []
        assert result.total_duration == 0.0
        assert result.agents_used == 0

    def test_bottlenecks_are_empty_not_an_error(self, workspace):
        assert schedule.get_bottlenecks(workspace) == []

    def test_prediction_reports_nothing_outstanding(self, workspace):
        result = schedule.predict_completion(workspace)
        assert result.remaining_hours == 0.0
        # 100, not 0: zero remaining hours at 0% complete is self-contradictory.
        assert result.completed_percentage == 100.0

    def test_no_value_error_is_raised_for_an_empty_workspace(self, workspace):
        """The old contract; pinned so it cannot come back by accident."""
        for call in (
            schedule.get_schedule,
            schedule.get_bottlenecks,
            schedule.predict_completion,
        ):
            call(workspace)  # must not raise


class TestAllThreeEndpointsAgree:
    """AC: predict and bottlenecks checked for the same over-broad mapping."""

    @pytest.mark.parametrize(
        "path", ["/api/v2/schedule", "/api/v2/schedule/predict", "/api/v2/schedule/bottlenecks"]
    )
    def test_an_empty_workspace_is_not_a_404(self, client, path):
        res = client.get(path)
        assert res.status_code == 200, res.text

    def test_the_empty_schedule_has_no_assignments(self, client):
        body = client.get("/api/v2/schedule").json()
        assert body["task_assignments"] == []

    def test_the_empty_bottlenecks_list_is_empty(self, client):
        assert client.get("/api/v2/schedule/bottlenecks").json() == []


class TestAPopulatedWorkspaceStillWorks:
    """The empty case must not have been special-cased into breaking the real one."""

    def test_tasks_are_scheduled(self, client, workspace):
        for i in range(3):
            tasks.create(workspace, title=f"t{i}", description="", estimated_hours=2.0)

        res = client.get("/api/v2/schedule")

        assert res.status_code == 200, res.text
        assert len(res.json()["task_assignments"]) == 3
        assert res.json()["total_duration"] > 0
