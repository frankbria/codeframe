"""Tests for GET /api/v2/pr/status endpoint (pr_v2 router).

These tests verify the PR status endpoint by mocking GitHubIntegration
so no real GitHub API calls are made.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.git.github_integration import CICheck

# Mark all tests as v2
pytestmark = pytest.mark.v2


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_ws"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    workspace = create_or_load_workspace(workspace_path)

    yield workspace

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    from codeframe.ui.routers import pr_v2
    from codeframe.ui.dependencies import get_v2_workspace

    app = FastAPI()
    app.include_router(pr_v2.router)

    def get_test_workspace():
        return test_workspace

    app.dependency_overrides[get_v2_workspace] = get_test_workspace
    return TestClient(app, raise_server_exceptions=False)


def _make_mock_client(
    pr_raw: dict | None = None,
    ci_checks: list[CICheck] | None = None,
    review_status: str = "pending",
    raise_error: Exception | None = None,
) -> MagicMock:
    """Build a mock GitHubIntegration with configurable responses."""
    client = MagicMock()

    default_pr_raw = {
        "head": {"sha": "abc123def456"},
        "html_url": "https://github.com/owner/repo/pull/42",
        "state": "open",
        "merged_at": None,
    }
    pr_data = pr_raw if pr_raw is not None else default_pr_raw

    if raise_error:
        client._make_request = AsyncMock(side_effect=raise_error)
    else:
        client._make_request = AsyncMock(return_value=pr_data)

    client.get_pr_ci_checks = AsyncMock(
        return_value=ci_checks if ci_checks is not None else []
    )
    client.get_pr_review_status = AsyncMock(return_value=review_status)
    client.owner = "owner"
    client.repo_name = "repo"
    return client


# ── Tests ─────────────────────────────────────────────────────────────────


class TestGetPrStatusSuccess:
    """Happy-path tests for GET /api/v2/pr/status."""

    def test_returns_200_with_open_pr_no_checks(self, test_client):
        """Open PR with no CI checks returns a valid 200 response."""
        mock_client = _make_mock_client(review_status="pending")

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/status?workspace_path=/tmp&pr_number=42")

        assert resp.status_code == 200
        body = resp.json()
        assert body["merge_state"] == "open"
        assert body["review_status"] == "pending"
        assert body["ci_checks"] == []
        assert body["pr_url"] == "https://github.com/owner/repo/pull/42"
        assert body["pr_number"] == 42

    def test_ci_checks_in_response(self, test_client):
        """CI checks list populates correctly."""
        checks = [
            CICheck(name="lint", status="completed", conclusion="success"),
            CICheck(name="tests", status="in_progress", conclusion=None),
        ]
        mock_client = _make_mock_client(ci_checks=checks)

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/status?workspace_path=/tmp&pr_number=7")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["ci_checks"]) == 2
        assert body["ci_checks"][0] == {
            "name": "lint",
            "status": "completed",
            "conclusion": "success",
        }
        assert body["ci_checks"][1] == {
            "name": "tests",
            "status": "in_progress",
            "conclusion": None,
        }

    def test_merged_pr(self, test_client):
        """PR with merged_at set returns merge_state=merged."""
        pr_raw = {
            "head": {"sha": "deadbeef"},
            "html_url": "https://github.com/owner/repo/pull/5",
            "state": "closed",
            "merged_at": "2026-04-10T12:00:00Z",
        }
        mock_client = _make_mock_client(pr_raw=pr_raw, review_status="approved")

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/status?workspace_path=/tmp&pr_number=5")

        assert resp.status_code == 200
        assert resp.json()["merge_state"] == "merged"
        assert resp.json()["review_status"] == "approved"

    def test_closed_pr(self, test_client):
        """PR with state=closed and no merged_at returns merge_state=closed."""
        pr_raw = {
            "head": {"sha": "cafebabe"},
            "html_url": "https://github.com/owner/repo/pull/3",
            "state": "closed",
            "merged_at": None,
        }
        mock_client = _make_mock_client(pr_raw=pr_raw)

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/status?workspace_path=/tmp&pr_number=3")

        assert resp.status_code == 200
        assert resp.json()["merge_state"] == "closed"

    def test_review_status_changes_requested(self, test_client):
        """changes_requested review status propagates to response."""
        mock_client = _make_mock_client(review_status="changes_requested")

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/status?workspace_path=/tmp&pr_number=10")

        assert resp.status_code == 200
        assert resp.json()["review_status"] == "changes_requested"

    def test_head_sha_forwarded_to_ci_checks(self, test_client):
        """The head SHA extracted from the PR raw data is passed to get_pr_ci_checks."""
        pr_raw = {
            "head": {"sha": "mysha123"},
            "html_url": "https://github.com/owner/repo/pull/1",
            "state": "open",
            "merged_at": None,
        }
        mock_client = _make_mock_client(pr_raw=pr_raw)

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            test_client.get("/api/v2/pr/status?workspace_path=/tmp&pr_number=1")

        mock_client.get_pr_ci_checks.assert_awaited_once_with(1, head_sha="mysha123")


class TestGetPrStatusErrors:
    """Error-handling tests for GET /api/v2/pr/status."""

    def test_missing_pr_number_returns_422(self, test_client):
        """Omitting pr_number returns 422 Unprocessable Entity."""
        resp = test_client.get("/api/v2/pr/status?workspace_path=/tmp")
        assert resp.status_code == 422

    def test_github_not_configured_returns_400(self, test_client):
        """When GitHub isn't configured, _get_github_client raises, returning 400."""
        from fastapi import HTTPException

        with patch(
            "codeframe.ui.routers.pr_v2._get_github_client",
            side_effect=HTTPException(status_code=400, detail="GitHub not configured"),
        ):
            resp = test_client.get("/api/v2/pr/status?workspace_path=/tmp&pr_number=1")

        assert resp.status_code == 400

    def test_pr_not_found_returns_404(self, test_client):
        """GitHub 404 for the PR propagates as HTTP 404."""
        from codeframe.git.github_integration import GitHubAPIError

        mock_client = _make_mock_client(raise_error=GitHubAPIError(404, "Not Found"))

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/status?workspace_path=/tmp&pr_number=9999")

        assert resp.status_code == 404

    def test_github_api_error_propagates_status_code(self, test_client):
        """GitHub 503 propagates as HTTP 503."""
        from codeframe.git.github_integration import GitHubAPIError

        mock_client = _make_mock_client(raise_error=GitHubAPIError(503, "Service Unavailable"))

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/status?workspace_path=/tmp&pr_number=42")

        assert resp.status_code == 503
