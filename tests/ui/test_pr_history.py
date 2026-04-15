"""Tests for PR v2 router endpoints: history and files.

These tests verify the PR history and PR files endpoints by mocking
GitHubIntegration so no real GitHub API calls are made.
"""

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.git.github_integration import PRDetails

# Mark all tests as v2
pytestmark = pytest.mark.v2


# -- Fixtures ----------------------------------------------------------------


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


def _make_pr(
    number: int,
    title: str = "Test PR",
    state: str = "closed",
    merged_at: datetime | None = None,
    author: str | None = None,
) -> PRDetails:
    """Build a PRDetails with sensible defaults."""
    return PRDetails(
        number=number,
        url=f"https://github.com/owner/repo/pull/{number}",
        state=state,
        title=title,
        body="body",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        merged_at=merged_at,
        head_branch="feature",
        base_branch="main",
        author=author,
    )


def _make_mock_client(
    prs: list[PRDetails] | None = None,
    raise_error: Exception | None = None,
) -> MagicMock:
    """Build a mock GitHubIntegration with configurable responses."""
    client = MagicMock()

    if raise_error:
        client.list_pull_requests = AsyncMock(side_effect=raise_error)
    else:
        client.list_pull_requests = AsyncMock(return_value=prs or [])

    client.close = AsyncMock()
    client.owner = "owner"
    client.repo_name = "repo"
    return client


# -- Tests -------------------------------------------------------------------


class TestGetPrHistory:
    """Tests for GET /api/v2/pr/history."""

    def test_returns_merged_prs_with_proof_snapshot(self, test_client, test_workspace):
        """Merged PR with a saved proof snapshot appears in response."""
        from codeframe.core.proof.ledger import (
            init_proof_tables,
            save_pr_proof_snapshot,
        )

        init_proof_tables(test_workspace)

        merged_pr = _make_pr(
            number=10,
            title="Merged PR",
            merged_at=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
            author="alice",
        )
        unmerged_pr = _make_pr(number=11, title="Closed but not merged")

        save_pr_proof_snapshot(
            test_workspace,
            pr_number=10,
            gates_passed=7,
            gates_total=9,
            gate_breakdown=[
                {"gate": "unit_test", "status": "satisfied"},
                {"gate": "lint", "status": "failed"},
            ],
        )

        mock_client = _make_mock_client(prs=[merged_pr, unmerged_pr])

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/history?workspace_path=/tmp")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["pull_requests"]) == 1

        pr_item = body["pull_requests"][0]
        assert pr_item["number"] == 10
        assert pr_item["title"] == "Merged PR"
        assert pr_item["author"] == "alice"
        assert pr_item["proof_snapshot"] is not None
        assert pr_item["proof_snapshot"]["gates_passed"] == 7
        assert pr_item["proof_snapshot"]["gates_total"] == 9
        assert len(pr_item["proof_snapshot"]["gate_breakdown"]) == 2

    def test_returns_empty_when_no_merged_prs(self, test_client):
        """Closed PRs with no merged_at yield empty list."""
        unmerged = _make_pr(number=1)
        mock_client = _make_mock_client(prs=[unmerged])

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/history?workspace_path=/tmp")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["pull_requests"] == []

    def test_limit_parameter(self, test_client):
        """Limit parameter restricts the number of returned PRs."""
        prs = [
            _make_pr(
                number=i,
                merged_at=datetime(2026, 4, i, tzinfo=timezone.utc),
            )
            for i in range(1, 4)
        ]
        mock_client = _make_mock_client(prs=prs)

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/history?workspace_path=/tmp&limit=2")

        assert resp.status_code == 200
        assert len(resp.json()["pull_requests"]) == 2

    def test_pr_without_snapshot_has_null(self, test_client, test_workspace):
        """Merged PR with no saved snapshot has proof_snapshot=null."""
        from codeframe.core.proof.ledger import init_proof_tables

        init_proof_tables(test_workspace)

        merged_pr = _make_pr(
            number=5,
            merged_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
        )
        mock_client = _make_mock_client(prs=[merged_pr])

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/history?workspace_path=/tmp")

        assert resp.status_code == 200
        pr_item = resp.json()["pull_requests"][0]
        assert pr_item["proof_snapshot"] is None

    def test_sorted_by_merged_at_descending(self, test_client):
        """PRs are returned newest-first by merged_at."""
        old_pr = _make_pr(
            number=1,
            title="Old PR",
            merged_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        new_pr = _make_pr(
            number=2,
            title="New PR",
            merged_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
        )
        # Return in wrong order — endpoint should re-sort.
        mock_client = _make_mock_client(prs=[old_pr, new_pr])

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/history?workspace_path=/tmp")

        assert resp.status_code == 200
        items = resp.json()["pull_requests"]
        assert items[0]["number"] == 2
        assert items[1]["number"] == 1

    def test_github_error_returns_error(self, test_client):
        """GitHubAPIError propagates as appropriate HTTP error."""
        from codeframe.git.github_integration import GitHubAPIError

        mock_client = _make_mock_client(
            raise_error=GitHubAPIError(503, "Service Unavailable"),
        )

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/history?workspace_path=/tmp")

        assert resp.status_code == 503

    def test_client_close_called(self, test_client):
        """Client.close() is always called."""
        mock_client = _make_mock_client(prs=[])

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            test_client.get("/api/v2/pr/history?workspace_path=/tmp")

        mock_client.close.assert_awaited_once()

    def test_author_included(self, test_client):
        """PR author field appears in the response."""
        pr = _make_pr(
            number=7,
            merged_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
            author="bob",
        )
        mock_client = _make_mock_client(prs=[pr])

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/history?workspace_path=/tmp")

        assert resp.status_code == 200
        assert resp.json()["pull_requests"][0]["author"] == "bob"


class TestGetPrFiles:
    """Tests for GET /api/v2/pr/{pr_number}/files."""

    def test_returns_file_list(self, test_client):
        """Endpoint returns the list of changed files for a PR."""
        mock_client = _make_mock_client()
        mock_client.get_pr_files = AsyncMock(return_value=["src/app.py", "tests/test_app.py"])

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/42/files?workspace_path=/tmp")

        assert resp.status_code == 200
        body = resp.json()
        assert body["files"] == ["src/app.py", "tests/test_app.py"]

    def test_returns_empty_list(self, test_client):
        """Endpoint returns empty list when PR has no file changes."""
        mock_client = _make_mock_client()
        mock_client.get_pr_files = AsyncMock(return_value=[])

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/1/files?workspace_path=/tmp")

        assert resp.status_code == 200
        assert resp.json()["files"] == []

    def test_pr_not_found(self, test_client):
        """Endpoint returns 404 when PR does not exist."""
        from codeframe.git.github_integration import GitHubAPIError

        mock_client = _make_mock_client()
        mock_client.get_pr_files = AsyncMock(
            side_effect=GitHubAPIError(404, "Not Found"),
        )

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            resp = test_client.get("/api/v2/pr/99999/files?workspace_path=/tmp")

        assert resp.status_code == 404

    def test_client_close_called(self, test_client):
        """Client.close() is always called."""
        mock_client = _make_mock_client()
        mock_client.get_pr_files = AsyncMock(return_value=[])

        with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=mock_client):
            test_client.get("/api/v2/pr/1/files?workspace_path=/tmp")

        mock_client.close.assert_awaited_once()
