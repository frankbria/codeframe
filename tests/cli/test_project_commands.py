"""Tests for CLI project commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from codeframe.cli.project_commands import projects_app


runner = CliRunner()


class TestProjectListCommand:
    """Tests for 'codeframe projects list' command."""

    def test_list_projects_success(self, tmp_path):
        """List should display projects in table format."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "projects": [
                {"id": 1, "name": "Project A", "status": "active", "phase": "development", "created_at": "2024-01-01T00:00:00Z"},
                {"id": 2, "name": "Project B", "status": "paused", "phase": "planning", "created_at": "2024-01-02T00:00:00Z"},
            ]
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["list"])

        assert result.exit_code == 0
        assert "Project A" in result.output
        assert "Project B" in result.output
        assert "active" in result.output.lower()

    def test_list_projects_empty(self, tmp_path):
        """List with no projects should show helpful message."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"projects": []}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["list"])

        assert result.exit_code == 0
        assert "no projects" in result.output.lower() or "0 projects" in result.output.lower()

    def test_list_projects_json_format(self, tmp_path):
        """List with --format json should output JSON."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "projects": [{"id": 1, "name": "Test"}]
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["list", "--format", "json"])

        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert "projects" in data


class TestProjectCreateCommand:
    """Tests for 'codeframe projects create' command."""

    def test_create_project_success(self, tmp_path):
        """Create should display created project details."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 1,
            "name": "New Project",
            "status": "created",
            "phase": "discovery",
            "created_at": "2024-01-01T00:00:00Z",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["create", "New Project"])

        assert result.exit_code == 0
        assert "New Project" in result.output
        assert "created" in result.output.lower() or "success" in result.output.lower()

    def test_create_project_with_options(self, tmp_path):
        """Create with options should pass them to API."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 1, "name": "My Project"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response) as mock_request:
                result = runner.invoke(
                    projects_app,
                    ["create", "My Project", "--description", "Test description", "--source-type", "git_repo"],
                )

        assert result.exit_code == 0
        # Verify API was called with correct data
        call_kwargs = mock_request.call_args.kwargs
        assert "json" in call_kwargs
        assert call_kwargs["json"]["name"] == "My Project"
        assert call_kwargs["json"]["description"] == "Test description"

    def test_create_project_conflict(self, tmp_path):
        """Create with duplicate name should show error."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.text = "Conflict"
        mock_response.json.return_value = {"detail": "Project with name 'Existing' already exists"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["create", "Existing"])

        assert result.exit_code != 0
        assert "exists" in result.output.lower() or "already" in result.output.lower()


class TestProjectGetCommand:
    """Tests for 'codeframe projects get' command."""

    def test_get_project_success(self, tmp_path):
        """Get should display project details."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "name": "Test Project",
            "description": "A test project",
            "status": "active",
            "phase": "development",
            "created_at": "2024-01-01T00:00:00Z",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["get", "1"])

        assert result.exit_code == 0
        assert "Test Project" in result.output
        assert "development" in result.output.lower()

    def test_get_project_not_found(self, tmp_path):
        """Get with invalid ID should show error."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.json.return_value = {"detail": "Project 999 not found"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["get", "999"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestProjectStatusCommand:
    """Tests for 'codeframe projects status' command."""

    def test_status_success(self, tmp_path):
        """Status should display progress and metrics."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "project_id": 1,
            "name": "Test Project",
            "status": "active",
            "phase": "development",
            "progress": {
                "total_tasks": 10,
                "completed_tasks": 7,
                "completion_percentage": 70.0,
            },
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["status", "1"])

        assert result.exit_code == 0
        assert "Test Project" in result.output
        assert "70" in result.output  # Progress percentage


class TestProjectTasksCommand:
    """Tests for 'codeframe projects tasks' command."""

    def test_tasks_list_success(self, tmp_path):
        """Tasks should display task list."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tasks": [
                {"id": 1, "title": "Task A", "status": "completed", "priority": 1},
                {"id": 2, "title": "Task B", "status": "in_progress", "priority": 2},
            ],
            "total": 2,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["tasks", "1"])

        assert result.exit_code == 0
        assert "Task A" in result.output
        assert "Task B" in result.output

    def test_tasks_filter_by_status(self, tmp_path):
        """Tasks with --status should filter results."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tasks": [], "total": 0}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response) as mock_request:
                result = runner.invoke(projects_app, ["tasks", "1", "--status", "completed"])

        assert result.exit_code == 0
        # Verify status filter was passed
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs.get("params", {}).get("status") == "completed"


class TestProjectActivityCommand:
    """Tests for 'codeframe projects activity' command."""

    def test_activity_success(self, tmp_path):
        """Activity should display recent activity log."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "activity": [
                {"timestamp": "2024-01-01T12:00:00Z", "action": "task_completed", "details": "Task A completed"},
                {"timestamp": "2024-01-01T11:00:00Z", "action": "task_started", "details": "Task B started"},
            ]
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["activity", "1"])

        assert result.exit_code == 0
        assert "task_completed" in result.output.lower() or "completed" in result.output.lower()


class TestProjectStartPauseResumeCommands:
    """Tests for project lifecycle commands."""

    def test_start_project(self, tmp_path):
        """Start should call start endpoint."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "active", "message": "Project started"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["start", "1"])

        assert result.exit_code == 0
        assert "started" in result.output.lower()

    def test_pause_project(self, tmp_path):
        """Pause should call pause endpoint."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "paused", "message": "Project paused"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["pause", "1"])

        assert result.exit_code == 0
        assert "paused" in result.output.lower()

    def test_resume_project(self, tmp_path):
        """Resume should call resume endpoint."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "active", "message": "Project resumed"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(projects_app, ["resume", "1"])

        assert result.exit_code == 0
        assert "resumed" in result.output.lower()
