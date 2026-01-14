"""Unit tests for GitHubIntegration (TDD - written before implementation)."""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch

from codeframe.git.github_integration import (
    GitHubIntegration,
    PRDetails,
    MergeResult,
    GitHubAPIError,
)


class TestPRDetails:
    """Tests for PRDetails data class."""

    def test_pr_details_creation(self):
        """Test creating a PRDetails object."""
        pr = PRDetails(
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

        assert pr.number == 42
        assert pr.state == "open"
        assert pr.title == "Test PR"
        assert pr.merged_at is None


class TestMergeResult:
    """Tests for MergeResult data class."""

    def test_merge_result_success(self):
        """Test creating a successful MergeResult."""
        result = MergeResult(
            sha="abc123def456",
            merged=True,
            message="Pull Request successfully merged",
        )

        assert result.merged is True
        assert result.sha == "abc123def456"

    def test_merge_result_failure(self):
        """Test creating a failed MergeResult."""
        result = MergeResult(
            sha=None,
            merged=False,
            message="Pull Request is not mergeable",
        )

        assert result.merged is False
        assert result.sha is None


class TestGitHubIntegration:
    """Tests for GitHubIntegration class."""

    @pytest.fixture
    def github(self):
        """Create GitHubIntegration instance."""
        return GitHubIntegration(
            token="ghp_test_token_12345",
            repo="owner/test-repo",
        )

    def test_init_parses_repo_correctly(self, github):
        """Test that repo is parsed correctly."""
        assert github.owner == "owner"
        assert github.repo_name == "test-repo"

    def test_init_with_invalid_repo_format(self):
        """Test that invalid repo format raises error."""
        with pytest.raises(ValueError, match="Invalid repo format"):
            GitHubIntegration(token="token", repo="invalid-format")

    @pytest.mark.asyncio
    async def test_create_pull_request_success(self, github):
        """Test successful PR creation."""
        mock_response = {
            "number": 42,
            "html_url": "https://github.com/owner/test-repo/pull/42",
            "state": "open",
            "title": "Test PR",
            "body": "Test body",
            "created_at": "2024-01-15T10:30:00Z",
            "merged_at": None,
            "head": {"ref": "feature/test"},
            "base": {"ref": "main"},
        }

        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            pr_details = await github.create_pull_request(
                branch="feature/test",
                title="Test PR",
                body="Test body",
                base="main",
            )

            assert pr_details.number == 42
            assert pr_details.state == "open"
            assert pr_details.title == "Test PR"

            # Verify API was called correctly
            mock_request.assert_called_once()
            call_kwargs = mock_request.call_args.kwargs
            assert call_kwargs["method"] == "POST"
            assert "pulls" in call_kwargs["endpoint"]

    @pytest.mark.asyncio
    async def test_create_pull_request_api_error(self, github):
        """Test PR creation with API error."""
        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = GitHubAPIError(
                status_code=422,
                message="Validation Failed",
            )

            with pytest.raises(GitHubAPIError) as exc_info:
                await github.create_pull_request(
                    branch="feature/test",
                    title="Test PR",
                    body="Test body",
                )

            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_get_pull_request_success(self, github):
        """Test getting PR details."""
        mock_response = {
            "number": 42,
            "html_url": "https://github.com/owner/test-repo/pull/42",
            "state": "open",
            "title": "Test PR",
            "body": "Test body",
            "created_at": "2024-01-15T10:30:00Z",
            "merged_at": None,
            "head": {"ref": "feature/test"},
            "base": {"ref": "main"},
        }

        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            pr_details = await github.get_pull_request(42)

            assert pr_details.number == 42
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pull_request_not_found(self, github):
        """Test getting non-existent PR."""
        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = GitHubAPIError(
                status_code=404,
                message="Not Found",
            )

            with pytest.raises(GitHubAPIError) as exc_info:
                await github.get_pull_request(99999)

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_pull_requests_success(self, github):
        """Test listing PRs."""
        mock_response = [
            {
                "number": 1,
                "html_url": "https://github.com/owner/test-repo/pull/1",
                "state": "open",
                "title": "PR 1",
                "body": "Body 1",
                "created_at": "2024-01-15T10:30:00Z",
                "merged_at": None,
                "head": {"ref": "feature/1"},
                "base": {"ref": "main"},
            },
            {
                "number": 2,
                "html_url": "https://github.com/owner/test-repo/pull/2",
                "state": "open",
                "title": "PR 2",
                "body": "Body 2",
                "created_at": "2024-01-16T10:30:00Z",
                "merged_at": None,
                "head": {"ref": "feature/2"},
                "base": {"ref": "main"},
            },
        ]

        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            prs = await github.list_pull_requests(state="open")

            assert len(prs) == 2
            assert prs[0].number == 1
            assert prs[1].number == 2

    @pytest.mark.asyncio
    async def test_merge_pull_request_success(self, github):
        """Test successful PR merge."""
        mock_response = {
            "sha": "abc123def456",
            "merged": True,
            "message": "Pull Request successfully merged",
        }

        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await github.merge_pull_request(42, method="squash")

            assert result.merged is True
            assert result.sha == "abc123def456"

            # Verify merge method was passed
            mock_request.assert_called_once()
            call_kwargs = mock_request.call_args.kwargs
            assert "merge" in call_kwargs["endpoint"]

    @pytest.mark.asyncio
    async def test_merge_pull_request_not_mergeable(self, github):
        """Test merge with non-mergeable PR."""
        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = GitHubAPIError(
                status_code=405,
                message="Pull Request is not mergeable",
            )

            with pytest.raises(GitHubAPIError) as exc_info:
                await github.merge_pull_request(42)

            assert exc_info.value.status_code == 405

    @pytest.mark.asyncio
    async def test_close_pull_request_success(self, github):
        """Test closing a PR."""
        mock_response = {
            "number": 42,
            "html_url": "https://github.com/owner/test-repo/pull/42",
            "state": "closed",
            "title": "Test PR",
            "body": "Test body",
            "created_at": "2024-01-15T10:30:00Z",
            "merged_at": None,
            "head": {"ref": "feature/test"},
            "base": {"ref": "main"},
        }

        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await github.close_pull_request(42)

            assert result is True
            mock_request.assert_called_once()
            call_kwargs = mock_request.call_args.kwargs
            assert call_kwargs["method"] == "PATCH"

    @pytest.mark.asyncio
    async def test_authentication_error(self, github):
        """Test handling of authentication errors."""
        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = GitHubAPIError(
                status_code=401,
                message="Bad credentials",
            )

            with pytest.raises(GitHubAPIError) as exc_info:
                await github.get_pull_request(42)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, github):
        """Test handling of rate limit errors."""
        with patch.object(github, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = GitHubAPIError(
                status_code=403,
                message="API rate limit exceeded",
            )

            with pytest.raises(GitHubAPIError) as exc_info:
                await github.get_pull_request(42)

            assert exc_info.value.status_code == 403


class TestGitHubAPIError:
    """Tests for GitHubAPIError exception."""

    def test_error_message(self):
        """Test error message formatting."""
        error = GitHubAPIError(status_code=404, message="Not Found")

        assert "404" in str(error)
        assert "Not Found" in str(error)

    def test_error_with_details(self):
        """Test error with additional details."""
        error = GitHubAPIError(
            status_code=422,
            message="Validation Failed",
            details={"errors": [{"field": "title", "code": "missing"}]},
        )

        assert error.details is not None
        assert "title" in str(error.details)
