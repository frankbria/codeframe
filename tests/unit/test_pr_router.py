"""Unit tests for PR router (TDD - written before implementation)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.ui.routers.prs import router
from codeframe.git.github_integration import PRDetails, MergeResult, GitHubAPIError


@pytest.fixture
def app():
    """Create test FastAPI app with PR router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def mock_db():
    """Create mock database with PR repository."""
    db = MagicMock()
    db.get_project.return_value = {"id": 1, "name": "Test Project"}
    db.user_has_project_access.return_value = True

    # Mock PR repository
    db.pull_requests = MagicMock()
    db.pull_requests.create_pr.return_value = 1
    db.pull_requests.get_pr.return_value = {
        "id": 1,
        "project_id": 1,
        "pr_number": 42,
        "pr_url": "https://github.com/owner/repo/pull/42",
        "title": "Test PR",
        "body": "Test body",
        "status": "open",
        "branch_name": "feature/test",
        "base_branch": "main",
        "head_branch": "feature/test",
        "created_at": datetime.now(UTC).isoformat(),
    }
    db.pull_requests.list_prs.return_value = [
        {
            "id": 1,
            "pr_number": 42,
            "title": "PR 1",
            "status": "open",
        },
        {
            "id": 2,
            "pr_number": 43,
            "title": "PR 2",
            "status": "open",
        },
    ]
    db.pull_requests.get_pr_by_number.return_value = {
        "id": 1,
        "pr_number": 42,
        "title": "Test PR",
        "status": "open",
    }

    return db


@pytest.fixture
def mock_user():
    """Create mock authenticated user."""
    user = MagicMock()
    user.id = 1
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_github_config():
    """Mock GlobalConfig with GitHub credentials."""
    config = MagicMock()
    config.github_token = "ghp_test_token"
    config.github_repo = "owner/test-repo"
    return config


@pytest.fixture
def client(app, mock_db, mock_user, mock_github_config):
    """Create test client with dependencies overridden."""
    from codeframe.ui.dependencies import get_db
    from codeframe.auth import get_current_user

    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Mock the config
    with patch("codeframe.ui.routers.prs.get_global_config", return_value=mock_github_config):
        yield TestClient(app)


class TestCreatePR:
    """Tests for POST /api/projects/{project_id}/prs."""

    def test_create_pr_success(self, client, mock_db):
        """Test successful PR creation."""
        mock_pr_details = PRDetails(
            number=42,
            url="https://github.com/owner/repo/pull/42",
            state="open",
            title="Test PR",
            body="Test body",
            created_at=datetime.now(UTC),
            merged_at=None,
            head_branch="feature/test",
            base_branch="main",
        )

        with patch("codeframe.ui.routers.prs.GitHubIntegration") as MockGH:
            mock_gh_instance = AsyncMock()
            mock_gh_instance.create_pull_request.return_value = mock_pr_details
            MockGH.return_value = mock_gh_instance

            response = client.post(
                "/api/projects/1/prs",
                json={
                    "branch": "feature/test",
                    "title": "Test PR",
                    "body": "Test body",
                    "base": "main",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["pr_number"] == 42
            assert data["pr_url"] == "https://github.com/owner/repo/pull/42"
            assert data["status"] == "open"

    def test_create_pr_project_not_found(self, client, mock_db):
        """Test PR creation with non-existent project."""
        mock_db.get_project.return_value = None

        response = client.post(
            "/api/projects/999/prs",
            json={
                "branch": "feature/test",
                "title": "Test PR",
                "body": "Test body",
            },
        )

        assert response.status_code == 404

    def test_create_pr_access_denied(self, client, mock_db):
        """Test PR creation without project access."""
        mock_db.user_has_project_access.return_value = False

        response = client.post(
            "/api/projects/1/prs",
            json={
                "branch": "feature/test",
                "title": "Test PR",
                "body": "Test body",
            },
        )

        assert response.status_code == 403

    def test_create_pr_github_not_configured(self, app, mock_db, mock_user):
        """Test PR creation when GitHub is not configured."""
        from codeframe.ui.dependencies import get_db
        from codeframe.auth import get_current_user

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: mock_user

        # Mock missing GitHub config
        mock_config = MagicMock()
        mock_config.github_token = None
        mock_config.github_repo = None

        with patch("codeframe.ui.routers.prs.get_global_config", return_value=mock_config):
            client = TestClient(app)
            response = client.post(
                "/api/projects/1/prs",
                json={
                    "branch": "feature/test",
                    "title": "Test PR",
                    "body": "Test body",
                },
            )

            assert response.status_code == 400
            assert "GitHub" in response.json()["detail"]

    def test_create_pr_github_api_error(self, client, mock_db):
        """Test PR creation with GitHub API error."""
        with patch("codeframe.ui.routers.prs.GitHubIntegration") as MockGH:
            mock_gh_instance = AsyncMock()
            mock_gh_instance.create_pull_request.side_effect = GitHubAPIError(
                status_code=422,
                message="Validation Failed",
            )
            MockGH.return_value = mock_gh_instance

            response = client.post(
                "/api/projects/1/prs",
                json={
                    "branch": "feature/test",
                    "title": "Test PR",
                    "body": "Test body",
                },
            )

            assert response.status_code == 422


class TestListPRs:
    """Tests for GET /api/projects/{project_id}/prs."""

    def test_list_prs_success(self, client, mock_db):
        """Test listing PRs successfully."""
        response = client.get("/api/projects/1/prs")

        assert response.status_code == 200
        data = response.json()
        assert "prs" in data
        assert len(data["prs"]) == 2
        assert data["total"] == 2

    def test_list_prs_with_status_filter(self, client, mock_db):
        """Test listing PRs with status filter."""
        mock_db.pull_requests.list_prs.return_value = [
            {"id": 1, "pr_number": 42, "title": "Open PR", "status": "open"}
        ]

        response = client.get("/api/projects/1/prs?status=open")

        assert response.status_code == 200
        mock_db.pull_requests.list_prs.assert_called_with(1, status="open")

    def test_list_prs_project_not_found(self, client, mock_db):
        """Test listing PRs for non-existent project."""
        mock_db.get_project.return_value = None

        response = client.get("/api/projects/999/prs")

        assert response.status_code == 404


class TestGetPR:
    """Tests for GET /api/projects/{project_id}/prs/{pr_number}."""

    def test_get_pr_success(self, client, mock_db):
        """Test getting PR details successfully."""
        response = client.get("/api/projects/1/prs/42")

        assert response.status_code == 200
        data = response.json()
        assert data["pr_number"] == 42
        assert data["title"] == "Test PR"

    def test_get_pr_not_found(self, client, mock_db):
        """Test getting non-existent PR."""
        mock_db.pull_requests.get_pr_by_number.return_value = None

        response = client.get("/api/projects/1/prs/999")

        assert response.status_code == 404


class TestMergePR:
    """Tests for POST /api/projects/{project_id}/prs/{pr_number}/merge."""

    def test_merge_pr_success(self, client, mock_db):
        """Test successful PR merge."""
        mock_merge_result = MergeResult(
            sha="abc123def456",
            merged=True,
            message="Pull Request successfully merged",
        )

        with patch("codeframe.ui.routers.prs.GitHubIntegration") as MockGH:
            mock_gh_instance = AsyncMock()
            mock_gh_instance.merge_pull_request.return_value = mock_merge_result
            MockGH.return_value = mock_gh_instance

            response = client.post(
                "/api/projects/1/prs/42/merge",
                json={"method": "squash"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["merged"] is True
            assert data["merge_commit_sha"] == "abc123def456"

    def test_merge_pr_not_mergeable(self, client, mock_db):
        """Test merging non-mergeable PR."""
        with patch("codeframe.ui.routers.prs.GitHubIntegration") as MockGH:
            mock_gh_instance = AsyncMock()
            mock_gh_instance.merge_pull_request.side_effect = GitHubAPIError(
                status_code=405,
                message="Pull Request is not mergeable",
            )
            MockGH.return_value = mock_gh_instance

            response = client.post(
                "/api/projects/1/prs/42/merge",
                json={"method": "squash"},
            )

            assert response.status_code == 422


class TestClosePR:
    """Tests for POST /api/projects/{project_id}/prs/{pr_number}/close."""

    def test_close_pr_success(self, client, mock_db):
        """Test closing PR successfully."""
        with patch("codeframe.ui.routers.prs.GitHubIntegration") as MockGH:
            mock_gh_instance = AsyncMock()
            mock_gh_instance.close_pull_request.return_value = True
            MockGH.return_value = mock_gh_instance

            response = client.post("/api/projects/1/prs/42/close")

            assert response.status_code == 200
            data = response.json()
            assert data["closed"] is True

    def test_close_pr_not_found(self, client, mock_db):
        """Test closing non-existent PR."""
        mock_db.pull_requests.get_pr_by_number.return_value = None

        response = client.post("/api/projects/1/prs/999/close")

        assert response.status_code == 404
