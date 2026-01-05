"""Tests for CLI checkpoint commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from codeframe.cli.checkpoint_commands import checkpoints_app


runner = CliRunner()


class TestCheckpointListCommand:
    """Tests for 'codeframe checkpoints list' command."""

    def test_list_checkpoints_success(self, tmp_path):
        """List should display checkpoints in table format."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "checkpoints": [
                {"id": 1, "name": "Before refactor", "trigger": "manual", "git_commit": "abc123", "created_at": "2024-01-01T00:00:00Z"},
                {"id": 2, "name": "Phase complete", "trigger": "automatic", "git_commit": "def456", "created_at": "2024-01-02T00:00:00Z"},
            ]
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(checkpoints_app, ["list", "1"])

        assert result.exit_code == 0
        assert "Before refactor" in result.output
        assert "Phase complete" in result.output

    def test_list_checkpoints_empty(self, tmp_path):
        """List with no checkpoints should show helpful message."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"checkpoints": []}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(checkpoints_app, ["list", "1"])

        assert result.exit_code == 0
        assert "no checkpoints" in result.output.lower()


class TestCheckpointCreateCommand:
    """Tests for 'codeframe checkpoints create' command."""

    def test_create_checkpoint_success(self, tmp_path):
        """Create should display created checkpoint details."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 3,
            "project_id": 1,
            "name": "Safety checkpoint",
            "trigger": "manual",
            "git_commit": "abc123def",
            "created_at": "2024-01-01T12:00:00Z",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(checkpoints_app, ["create", "1", "Safety checkpoint"])

        assert result.exit_code == 0
        assert "Safety checkpoint" in result.output
        assert "created" in result.output.lower()

    def test_create_checkpoint_with_description(self, tmp_path):
        """Create with --description should pass it to API."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 1, "name": "Test"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response) as mock_request:
                result = runner.invoke(
                    checkpoints_app,
                    ["create", "1", "Test", "--description", "Before major refactor"],
                )

        assert result.exit_code == 0
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["description"] == "Before major refactor"


class TestCheckpointGetCommand:
    """Tests for 'codeframe checkpoints get' command."""

    def test_get_checkpoint_success(self, tmp_path):
        """Get should display checkpoint details."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "project_id": 1,
            "name": "Before refactor",
            "description": "Safety checkpoint",
            "trigger": "manual",
            "git_commit": "abc123def456",
            "metadata": {
                "tasks_completed": 5,
                "tasks_total": 10,
                "total_cost_usd": 1.25,
            },
            "created_at": "2024-01-01T12:00:00Z",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(checkpoints_app, ["get", "1", "1"])

        assert result.exit_code == 0
        assert "Before refactor" in result.output
        assert "abc123" in result.output

    def test_get_checkpoint_not_found(self, tmp_path):
        """Get with invalid ID should show error."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.json.return_value = {"detail": "Checkpoint not found"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(checkpoints_app, ["get", "1", "999"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestCheckpointDeleteCommand:
    """Tests for 'codeframe checkpoints delete' command."""

    def test_delete_checkpoint_with_confirm(self, tmp_path):
        """Delete with --force should delete immediately."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(checkpoints_app, ["delete", "1", "5", "--force"])

        assert result.exit_code == 0
        assert "deleted" in result.output.lower()

    def test_delete_checkpoint_prompts_without_force(self, tmp_path):
        """Delete without --force should prompt for confirmation."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                # Simulate 'y' confirmation
                result = runner.invoke(checkpoints_app, ["delete", "1", "5"], input="y\n")

        assert result.exit_code == 0


class TestCheckpointRestoreCommand:
    """Tests for 'codeframe checkpoints restore' command."""

    def test_restore_preview_without_confirm(self, tmp_path):
        """Restore without --confirm should show diff preview."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "checkpoint_name": "Before refactor",
            "diff": "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(checkpoints_app, ["restore", "1", "5"])

        assert result.exit_code == 0
        assert "diff" in result.output.lower() or "preview" in result.output.lower()

    def test_restore_with_confirm(self, tmp_path):
        """Restore with --confirm should perform restore."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "success": True,
            "checkpoint_name": "Before refactor",
            "git_commit": "abc123",
            "items_restored": 15,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(checkpoints_app, ["restore", "1", "5", "--confirm"])

        assert result.exit_code == 0
        assert "restored" in result.output.lower()


class TestCheckpointDiffCommand:
    """Tests for 'codeframe checkpoints diff' command."""

    def test_diff_success(self, tmp_path):
        """Diff should display changes since checkpoint."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "files_changed": 5,
            "insertions": 100,
            "deletions": 50,
            "diff": "diff --git a/file.py...",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(checkpoints_app, ["diff", "1", "5"])

        assert result.exit_code == 0
        assert "5" in result.output  # files changed
        assert "100" in result.output  # insertions
