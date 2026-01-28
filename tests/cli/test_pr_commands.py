"""Tests for CLI PR commands.

TDD approach: Write tests first, then implement.
These tests cover the `codeframe pr` command group for GitHub PR management.
"""

import json
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

# Mark all tests as v2
pytestmark = pytest.mark.v2


runner = CliRunner()


@pytest.fixture
def mock_github_token(monkeypatch):
    """Set up mock GitHub token for tests."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token_12345")
    monkeypatch.setenv("GITHUB_REPO", "testowner/testrepo")


@pytest.fixture
def mock_pr_details():
    """Mock PRDetails response from GitHub API."""
    from codeframe.git.github_integration import PRDetails

    return PRDetails(
        number=42,
        url="https://github.com/testowner/testrepo/pull/42",
        state="open",
        title="Add new feature",
        body="This PR adds a new feature.\n\n## Summary\n- Added feature X",
        created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        merged_at=None,
        head_branch="feature/new-feature",
        base_branch="main",
    )


class TestPRCreateCommand:
    """Tests for 'codeframe pr create' command."""

    def test_create_pr_success(self, mock_github_token, mock_pr_details, tmp_path):
        """Create PR should call GitHub API and display success."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.create_pull_request = AsyncMock(return_value=mock_pr_details)
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            with patch(
                "codeframe.cli.pr_commands.get_current_branch",
                return_value="feature/new-feature",
            ):
                result = runner.invoke(
                    pr_app,
                    ["create", "--title", "Add new feature", "--no-auto-description"],
                )

        assert result.exit_code == 0
        assert "#42" in result.output or "42" in result.output
        assert "github.com" in result.output.lower() or "created" in result.output.lower()

    def test_create_pr_with_explicit_branch(self, mock_github_token, mock_pr_details):
        """Create PR with explicit branch name."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.create_pull_request = AsyncMock(return_value=mock_pr_details)
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(
                pr_app,
                [
                    "create",
                    "--branch", "feature/explicit-branch",
                    "--title", "My PR",
                    "--base", "develop",
                    "--no-auto-description",
                ],
            )

        assert result.exit_code == 0
        mock_gh.create_pull_request.assert_called_once()
        call_args = mock_gh.create_pull_request.call_args
        assert call_args.kwargs.get("base") == "develop" or call_args[1].get("base") == "develop"

    def test_create_pr_no_github_token_shows_error(self, monkeypatch):
        """Create PR without GitHub token should show helpful error."""
        from codeframe.cli.pr_commands import pr_app

        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_REPO", raising=False)

        result = runner.invoke(
            pr_app,
            ["create", "--title", "Test", "--no-auto-description"],
        )

        assert result.exit_code != 0
        assert "github" in result.output.lower() or "token" in result.output.lower()

    def test_create_pr_with_body(self, mock_github_token, mock_pr_details):
        """Create PR with explicit body content."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.create_pull_request = AsyncMock(return_value=mock_pr_details)
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            with patch(
                "codeframe.cli.pr_commands.get_current_branch",
                return_value="feature/new-feature",
            ):
                result = runner.invoke(
                    pr_app,
                    [
                        "create",
                        "--title", "My Feature",
                        "--body", "This is the PR description",
                        "--no-auto-description",
                    ],
                )

        assert result.exit_code == 0
        call_args = mock_gh.create_pull_request.call_args
        assert "This is the PR description" in str(call_args)


class TestPRListCommand:
    """Tests for 'codeframe pr list' command."""

    def test_list_prs_success(self, mock_github_token, mock_pr_details):
        """List PRs should display table of PRs."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.list_pull_requests = AsyncMock(return_value=[mock_pr_details])
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["list"])

        assert result.exit_code == 0
        assert "42" in result.output
        assert "Add new feature" in result.output or "new-feature" in result.output.lower()

    def test_list_prs_with_status_filter(self, mock_github_token, mock_pr_details):
        """List PRs with status filter."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.list_pull_requests = AsyncMock(return_value=[mock_pr_details])
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["list", "--status", "closed"])

        assert result.exit_code == 0
        mock_gh.list_pull_requests.assert_called_once_with(state="closed")

    def test_list_prs_json_format(self, mock_github_token, mock_pr_details):
        """List PRs with JSON output format."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.list_pull_requests = AsyncMock(return_value=[mock_pr_details])
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["list", "--format", "json"])

        assert result.exit_code == 0
        # Should contain valid JSON
        try:
            output_json = json.loads(result.output)
            assert isinstance(output_json, list)
        except json.JSONDecodeError:
            pytest.fail("Output should be valid JSON")

    def test_list_prs_empty(self, mock_github_token):
        """List PRs when none exist."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.list_pull_requests = AsyncMock(return_value=[])
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["list"])

        assert result.exit_code == 0
        assert "no" in result.output.lower() or "empty" in result.output.lower() or "0" in result.output


class TestPRGetCommand:
    """Tests for 'codeframe pr get' command."""

    def test_get_pr_success(self, mock_github_token, mock_pr_details):
        """Get PR should display full PR details."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.get_pull_request = AsyncMock(return_value=mock_pr_details)
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["get", "42"])

        assert result.exit_code == 0
        assert "42" in result.output
        assert "Add new feature" in result.output
        assert "open" in result.output.lower()

    def test_get_pr_not_found(self, mock_github_token):
        """Get PR with invalid number should show error."""
        from codeframe.cli.pr_commands import pr_app
        from codeframe.git.github_integration import GitHubAPIError

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.get_pull_request = AsyncMock(
                side_effect=GitHubAPIError(404, "Not Found")
            )
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["get", "9999"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "404" in result.output

    def test_get_pr_json_format(self, mock_github_token, mock_pr_details):
        """Get PR with JSON output format."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.get_pull_request = AsyncMock(return_value=mock_pr_details)
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["get", "42", "--format", "json"])

        assert result.exit_code == 0
        try:
            output_json = json.loads(result.output)
            assert output_json["number"] == 42
        except json.JSONDecodeError:
            pytest.fail("Output should be valid JSON")


class TestPRMergeCommand:
    """Tests for 'codeframe pr merge' command."""

    def test_merge_pr_success(self, mock_github_token, mock_pr_details):
        """Merge PR should call GitHub API."""
        from codeframe.cli.pr_commands import pr_app
        from codeframe.git.github_integration import MergeResult

        merge_result = MergeResult(
            sha="abc123def456",
            merged=True,
            message="Pull Request successfully merged",
        )

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.get_pull_request = AsyncMock(return_value=mock_pr_details)
            mock_gh.merge_pull_request = AsyncMock(return_value=merge_result)
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["merge", "42"])

        assert result.exit_code == 0
        assert "merged" in result.output.lower()
        mock_gh.merge_pull_request.assert_called_once()

    def test_merge_pr_with_strategy(self, mock_github_token, mock_pr_details):
        """Merge PR with specific strategy."""
        from codeframe.cli.pr_commands import pr_app
        from codeframe.git.github_integration import MergeResult

        merge_result = MergeResult(
            sha="abc123def456",
            merged=True,
            message="PR merged via rebase",
        )

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.get_pull_request = AsyncMock(return_value=mock_pr_details)
            mock_gh.merge_pull_request = AsyncMock(return_value=merge_result)
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["merge", "42", "--strategy", "rebase"])

        assert result.exit_code == 0
        mock_gh.merge_pull_request.assert_called_once_with(42, method="rebase")

    def test_merge_pr_not_found(self, mock_github_token):
        """Merge PR that doesn't exist shows error."""
        from codeframe.cli.pr_commands import pr_app
        from codeframe.git.github_integration import GitHubAPIError

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.get_pull_request = AsyncMock(
                side_effect=GitHubAPIError(404, "Not Found")
            )
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["merge", "9999"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_merge_pr_already_merged(self, mock_github_token, mock_pr_details):
        """Merge PR that's already merged shows appropriate message."""
        from codeframe.cli.pr_commands import pr_app
        from codeframe.git.github_integration import PRDetails

        already_merged_pr = PRDetails(
            number=42,
            url="https://github.com/testowner/testrepo/pull/42",
            state="closed",
            title="Already merged",
            body="",
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            merged_at=datetime(2024, 1, 16, 10, 30, 0, tzinfo=UTC),
            head_branch="feature/done",
            base_branch="main",
        )

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.get_pull_request = AsyncMock(return_value=already_merged_pr)
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["merge", "42"])

        # Should fail or show message that PR is already merged
        assert "merged" in result.output.lower() or "closed" in result.output.lower()


class TestPRCloseCommand:
    """Tests for 'codeframe pr close' command."""

    def test_close_pr_success(self, mock_github_token, mock_pr_details):
        """Close PR should call GitHub API."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.get_pull_request = AsyncMock(return_value=mock_pr_details)
            mock_gh.close_pull_request = AsyncMock(return_value=True)
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["close", "42"])

        assert result.exit_code == 0
        assert "closed" in result.output.lower()
        mock_gh.close_pull_request.assert_called_once_with(42)

    def test_close_pr_not_found(self, mock_github_token):
        """Close PR that doesn't exist shows error."""
        from codeframe.cli.pr_commands import pr_app
        from codeframe.git.github_integration import GitHubAPIError

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.get_pull_request = AsyncMock(
                side_effect=GitHubAPIError(404, "Not Found")
            )
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["close", "9999"])

        assert result.exit_code != 0


class TestPRStatusCommand:
    """Tests for 'codeframe pr status' command."""

    def test_status_shows_current_branch_pr(self, mock_github_token, mock_pr_details):
        """Status should show PR for current branch if one exists."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.list_pull_requests = AsyncMock(return_value=[mock_pr_details])
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            with patch(
                "codeframe.cli.pr_commands.get_current_branch",
                return_value="feature/new-feature",
            ):
                result = runner.invoke(pr_app, ["status"])

        assert result.exit_code == 0
        # Should find the PR for the current branch
        assert "42" in result.output or "open" in result.output.lower()

    def test_status_no_pr_for_branch(self, mock_github_token):
        """Status when no PR exists for current branch."""
        from codeframe.cli.pr_commands import pr_app

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.list_pull_requests = AsyncMock(return_value=[])
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            with patch(
                "codeframe.cli.pr_commands.get_current_branch",
                return_value="feature/no-pr",
            ):
                result = runner.invoke(pr_app, ["status"])

        assert result.exit_code == 0
        assert "no" in result.output.lower() or "none" in result.output.lower()


class TestGitHelpers:
    """Tests for git helper functions used by PR commands."""

    def test_get_current_branch_normal(self, tmp_path):
        """Get current branch from normal git repo."""
        import subprocess

        # Create a temporary git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        # Test the helper function
        from codeframe.cli.pr_commands import get_current_branch

        with patch("codeframe.cli.pr_commands.Path.cwd", return_value=tmp_path):
            branch = get_current_branch(tmp_path)

        assert branch == "main"

    def test_get_git_diff_stats(self, tmp_path):
        """Get diff stats between branches."""
        import subprocess

        # Create a temporary git repo with two branches
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        # Create feature branch with changes
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=tmp_path, capture_output=True)
        (tmp_path / "new_file.py").write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add feature"], cwd=tmp_path, capture_output=True)

        # Test the helper function
        from codeframe.cli.pr_commands import get_git_diff_stats

        stats = get_git_diff_stats(tmp_path, "main", "feature")

        assert "new_file.py" in stats or "1 file" in stats


class TestErrorHandling:
    """Tests for error handling in PR commands."""

    def test_network_error_shows_message(self, mock_github_token):
        """Network errors should show user-friendly message."""
        from codeframe.cli.pr_commands import pr_app
        from codeframe.git.github_integration import GitHubAPIError

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.list_pull_requests = AsyncMock(
                side_effect=GitHubAPIError(500, "Internal Server Error")
            )
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["list"])

        assert result.exit_code != 0
        assert "error" in result.output.lower()

    def test_rate_limit_shows_message(self, mock_github_token):
        """Rate limit errors should show helpful message."""
        from codeframe.cli.pr_commands import pr_app
        from codeframe.git.github_integration import GitHubAPIError

        with patch(
            "codeframe.cli.pr_commands.GitHubIntegration"
        ) as MockGH:
            mock_gh = AsyncMock()
            mock_gh.list_pull_requests = AsyncMock(
                side_effect=GitHubAPIError(403, "rate limit exceeded")
            )
            mock_gh.close = AsyncMock()
            MockGH.return_value = mock_gh

            result = runner.invoke(pr_app, ["list"])

        assert result.exit_code != 0
        assert "rate" in result.output.lower() or "limit" in result.output.lower() or "error" in result.output.lower()
