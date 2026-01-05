"""Tests for CLI tasks commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from codeframe.cli.tasks_commands import tasks_app


runner = CliRunner()


class TestTasksListCommand:
    """Tests for 'codeframe tasks list' command."""

    def test_list_tasks_success(self, tmp_path):
        """List should display tasks for project."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tasks": [
                {"id": 1, "title": "Set up project", "status": "completed", "priority": 1},
                {"id": 2, "title": "Implement auth", "status": "in_progress", "priority": 2},
                {"id": 3, "title": "Add tests", "status": "pending", "priority": 3},
            ],
            "total": 3,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(tasks_app, ["list", "1"])

        assert result.exit_code == 0
        assert "Set up project" in result.output
        assert "Implement auth" in result.output

    def test_list_tasks_with_status_filter(self, tmp_path):
        """List with --status should filter tasks."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tasks": [], "total": 0}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response) as mock_request:
                result = runner.invoke(tasks_app, ["list", "1", "--status", "pending"])

        assert result.exit_code == 0
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs.get("params", {}).get("status") == "pending"


class TestTasksCreateCommand:
    """Tests for 'codeframe tasks create' command."""

    def test_create_task_success(self, tmp_path):
        """Create should add a new task."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 4,
            "project_id": 1,
            "title": "New feature",
            "status": "pending",
            "priority": 3,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(tasks_app, ["create", "1", "New feature"])

        assert result.exit_code == 0
        assert "created" in result.output.lower()

    def test_create_task_with_options(self, tmp_path):
        """Create with options should set priority and description."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 5, "title": "High priority task"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response) as mock_request:
                result = runner.invoke(
                    tasks_app,
                    ["create", "1", "High priority task", "--priority", "1", "--description", "Urgent work"],
                )

        assert result.exit_code == 0
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["priority"] == 1
        assert call_kwargs["json"]["description"] == "Urgent work"


class TestTasksGetCommand:
    """Tests for 'codeframe tasks get' command."""

    def test_get_task_success(self, tmp_path):
        """Get should display task details."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "project_id": 1,
            "title": "Implement authentication",
            "description": "Add user login and registration",
            "status": "in_progress",
            "priority": 1,
            "created_at": "2024-01-01T00:00:00Z",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(tasks_app, ["get", "1"])

        assert result.exit_code == 0
        assert "Implement authentication" in result.output

    def test_get_task_not_found(self, tmp_path):
        """Get with invalid ID should show error."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.json.return_value = {"detail": "Task not found"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(tasks_app, ["get", "999"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestTasksUpdateCommand:
    """Tests for 'codeframe tasks update' command."""

    def test_update_task_status(self, tmp_path):
        """Update should change task status."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "status": "completed",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(tasks_app, ["update", "1", "--status", "completed"])

        assert result.exit_code == 0
        assert "updated" in result.output.lower()
