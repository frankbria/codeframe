"""Integration tests for engine parameter on task execution endpoints.

Tests that the engine parameter is correctly validated, defaulted, and
passed through to conductor.start_batch() and runtime.execute_agent()
on all three execution endpoints:
- POST /api/v2/tasks/execute
- POST /api/v2/tasks/approve
- POST /api/v2/tasks/{task_id}/start
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.conductor import BatchRun, BatchStatus, OnFailure
from codeframe.core.runtime import ApprovalResult, AssignmentResult, Run, RunStatus
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace
from codeframe.ui.routers import tasks_v2

pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with just the tasks_v2 router."""
    app = FastAPI()
    app.include_router(tasks_v2.router)
    return app


def _make_workspace(tmp_path):
    """Create a v2 workspace in a temp directory."""
    return create_or_load_workspace(tmp_path)


def _make_task(workspace, title="Test task", status=TaskStatus.READY):
    """Create a task in the workspace with the given status."""
    from codeframe.core import tasks

    task = tasks.create(workspace, title=title, description="test desc", status=TaskStatus.BACKLOG)
    if status != TaskStatus.BACKLOG:
        tasks.update_status(workspace, task.id, status)
    return task


def _make_batch_run(workspace_id, task_ids, engine="plan"):
    """Build a BatchRun stub for mock return values."""
    return BatchRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        task_ids=task_ids,
        status=BatchStatus.RUNNING,
        strategy="serial",
        max_parallel=4,
        on_failure=OnFailure.CONTINUE,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        results={},
        engine=engine,
    )


def _make_run(workspace_id, task_id):
    """Build a Run stub for mock return values."""
    return Run(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        task_id=task_id,
        status=RunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
    )


def _assignment_ok():
    """Return an AssignmentResult that allows assignment."""
    return AssignmentResult(
        pending_count=1,
        executing_count=0,
        can_assign=True,
        reason="Tasks available",
    )


@pytest.fixture()
def client():
    """Lightweight TestClient with just the tasks_v2 router."""
    app = _make_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /api/v2/tasks/execute
# ---------------------------------------------------------------------------


class TestExecuteEndpointEngine:
    """Tests for POST /api/v2/tasks/execute engine parameter."""

    def test_execute_default_engine(self, tmp_path, client):
        """Default engine should be 'plan' when not specified."""
        ws = _make_workspace(tmp_path)
        task = _make_task(ws)

        with (
            patch("codeframe.ui.routers.tasks_v2.runtime.check_assignment_status", return_value=_assignment_ok()),
            patch("codeframe.ui.routers.tasks_v2.runtime.get_ready_task_ids", return_value=[task.id]),
            patch("codeframe.ui.routers.tasks_v2.conductor.start_batch", return_value=_make_batch_run(ws.id, [task.id])) as mock_batch,
        ):
            resp = client.post(
                "/api/v2/tasks/execute",
                json={"task_ids": [task.id]},
                params={"workspace_path": str(ws.repo_path)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_batch.assert_called_once()
        _, kwargs = mock_batch.call_args
        assert kwargs["engine"] == "plan"

    def test_execute_with_react_engine(self, tmp_path, client):
        """Passing engine='react' should forward it to conductor."""
        ws = _make_workspace(tmp_path)
        task = _make_task(ws)

        with (
            patch("codeframe.ui.routers.tasks_v2.runtime.check_assignment_status", return_value=_assignment_ok()),
            patch("codeframe.ui.routers.tasks_v2.runtime.get_ready_task_ids", return_value=[task.id]),
            patch("codeframe.ui.routers.tasks_v2.conductor.start_batch", return_value=_make_batch_run(ws.id, [task.id], engine="react")) as mock_batch,
        ):
            resp = client.post(
                "/api/v2/tasks/execute",
                json={"task_ids": [task.id], "engine": "react"},
                params={"workspace_path": str(ws.repo_path)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_batch.assert_called_once()
        _, kwargs = mock_batch.call_args
        assert kwargs["engine"] == "react"

    def test_execute_invalid_engine(self, tmp_path, client):
        """Invalid engine value should return 422 (Pydantic validation)."""
        ws = _make_workspace(tmp_path)

        resp = client.post(
            "/api/v2/tasks/execute",
            json={"engine": "invalid"},
            params={"workspace_path": str(ws.repo_path)},
        )

        assert resp.status_code == 422

    def test_engine_response_field(self, tmp_path, client):
        """Response body should include the engine field."""
        ws = _make_workspace(tmp_path)
        task = _make_task(ws)

        with (
            patch("codeframe.ui.routers.tasks_v2.runtime.check_assignment_status", return_value=_assignment_ok()),
            patch("codeframe.ui.routers.tasks_v2.runtime.get_ready_task_ids", return_value=[task.id]),
            patch("codeframe.ui.routers.tasks_v2.conductor.start_batch", return_value=_make_batch_run(ws.id, [task.id], engine="react")),
        ):
            resp = client.post(
                "/api/v2/tasks/execute",
                json={"task_ids": [task.id], "engine": "react"},
                params={"workspace_path": str(ws.repo_path)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"] == "react"


# ---------------------------------------------------------------------------
# POST /api/v2/tasks/{task_id}/start
# ---------------------------------------------------------------------------


class TestStartSingleTaskEngine:
    """Tests for POST /api/v2/tasks/{task_id}/start engine parameter."""

    def test_start_single_default_engine(self, tmp_path, client):
        """Default engine should be 'plan' when query param not provided."""
        ws = _make_workspace(tmp_path)
        task = _make_task(ws)
        run = _make_run(ws.id, task.id)

        with patch("codeframe.ui.routers.tasks_v2.runtime.start_task_run", return_value=run):
            resp = client.post(
                f"/api/v2/tasks/{task.id}/start",
                params={"workspace_path": str(ws.repo_path)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_start_single_with_react_engine(self, tmp_path, client):
        """Passing engine=react should forward to runtime.execute_agent()."""
        import time

        ws = _make_workspace(tmp_path)
        task = _make_task(ws)
        run = _make_run(ws.id, task.id)

        with (
            patch("codeframe.ui.routers.tasks_v2.runtime.start_task_run", return_value=run),
            patch("codeframe.ui.routers.tasks_v2.runtime.execute_agent") as mock_exec,
        ):
            resp = client.post(
                f"/api/v2/tasks/{task.id}/start",
                params={
                    "workspace_path": str(ws.repo_path),
                    "execute": "true",
                    "engine": "react",
                },
            )

            assert resp.status_code == 200
            # Give background thread a moment to invoke mock
            time.sleep(1.0)
            mock_exec.assert_called_once()
            _, kwargs = mock_exec.call_args
            assert kwargs["engine"] == "react"

    def test_start_single_invalid_engine(self, tmp_path, client):
        """Invalid engine value in query param should return 422 (Literal validation)."""
        ws = _make_workspace(tmp_path)
        task = _make_task(ws)

        resp = client.post(
            f"/api/v2/tasks/{task.id}/start",
            params={
                "workspace_path": str(ws.repo_path),
                "engine": "invalid",
            },
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v2/tasks/approve
# ---------------------------------------------------------------------------


class TestApproveEndpointEngine:
    """Tests for POST /api/v2/tasks/approve engine parameter."""

    def test_approve_with_engine(self, tmp_path, client):
        """Engine should be passed to conductor when start_execution=true."""
        ws = _make_workspace(tmp_path)
        task = _make_task(ws, status=TaskStatus.BACKLOG)

        approval = ApprovalResult(
            approved_count=1,
            excluded_count=0,
            approved_task_ids=[task.id],
            excluded_task_ids=[],
        )

        with (
            patch("codeframe.ui.routers.tasks_v2.runtime.approve_tasks", return_value=approval),
            patch("codeframe.ui.routers.tasks_v2.conductor.start_batch", return_value=_make_batch_run(ws.id, [task.id], engine="react")) as mock_batch,
        ):
            resp = client.post(
                "/api/v2/tasks/approve",
                json={
                    "start_execution": True,
                    "engine": "react",
                },
                params={"workspace_path": str(ws.repo_path)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["batch_id"] is not None
        mock_batch.assert_called_once()
        _, kwargs = mock_batch.call_args
        assert kwargs["engine"] == "react"

    def test_approve_invalid_engine(self, tmp_path, client):
        """Invalid engine in approve request should return 422."""
        ws = _make_workspace(tmp_path)

        resp = client.post(
            "/api/v2/tasks/approve",
            json={
                "start_execution": True,
                "engine": "invalid",
            },
            params={"workspace_path": str(ws.repo_path)},
        )

        assert resp.status_code == 422

    def test_approve_without_execution_skips_engine(self, tmp_path, client):
        """Engine should be irrelevant when start_execution=False (no batch started)."""
        ws = _make_workspace(tmp_path)
        _make_task(ws, status=TaskStatus.BACKLOG)

        approval = ApprovalResult(
            approved_count=1,
            excluded_count=0,
            approved_task_ids=["dummy"],
            excluded_task_ids=[],
        )

        with (
            patch("codeframe.ui.routers.tasks_v2.runtime.approve_tasks", return_value=approval),
            patch("codeframe.ui.routers.tasks_v2.conductor.start_batch") as mock_batch,
        ):
            resp = client.post(
                "/api/v2/tasks/approve",
                json={
                    "start_execution": False,
                    "engine": "react",
                },
                params={"workspace_path": str(ws.repo_path)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["batch_id"] is None
        mock_batch.assert_not_called()
