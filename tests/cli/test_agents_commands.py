"""Tests for CLI agents commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from codeframe.cli.agents_commands import agents_app


runner = CliRunner()


class TestAgentsListCommand:
    """Tests for 'codeframe agents list' command."""

    def test_list_agents_success(self, tmp_path):
        """List should display agents assigned to project."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"agent_id": "lead-agent", "role": "lead", "status": "active", "assigned_at": "2024-01-01T00:00:00Z"},
            {"agent_id": "worker-1", "role": "worker", "status": "idle", "assigned_at": "2024-01-01T01:00:00Z"},
        ]

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(agents_app, ["list", "1"])

        assert result.exit_code == 0
        assert "lead-agent" in result.output
        assert "worker-1" in result.output

    def test_list_agents_empty(self, tmp_path):
        """List with no agents should show helpful message."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(agents_app, ["list", "1"])

        assert result.exit_code == 0
        assert "no agents" in result.output.lower()


class TestAgentsAssignCommand:
    """Tests for 'codeframe agents assign' command."""

    def test_assign_agent_success(self, tmp_path):
        """Assign should add agent to project."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "agent_id": "worker-2",
            "project_id": 1,
            "role": "worker",
            "status": "idle",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(agents_app, ["assign", "1", "worker-2"])

        assert result.exit_code == 0
        assert "assigned" in result.output.lower()

    def test_assign_agent_with_role(self, tmp_path):
        """Assign with --role should set agent role."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "agent_id": "specialist-1",
            "project_id": 1,
            "role": "specialist",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response) as mock_request:
                result = runner.invoke(agents_app, ["assign", "1", "specialist-1", "--role", "specialist"])

        assert result.exit_code == 0
        # Verify role was sent
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"]["role"] == "specialist"


class TestAgentsRemoveCommand:
    """Tests for 'codeframe agents remove' command."""

    def test_remove_agent_success(self, tmp_path):
        """Remove should unassign agent from project."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(agents_app, ["remove", "1", "worker-1", "--force"])

        assert result.exit_code == 0
        assert "removed" in result.output.lower()

    def test_remove_agent_prompts_without_force(self, tmp_path):
        """Remove without --force should prompt for confirmation."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(agents_app, ["remove", "1", "worker-1"], input="y\n")

        assert result.exit_code == 0


class TestAgentsStatusCommand:
    """Tests for 'codeframe agents status' command."""

    def test_status_success(self, tmp_path):
        """Status should display agent details."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"project_id": 1, "project_name": "My Project", "role": "lead", "assigned_at": "2024-01-01T00:00:00Z"},
            {"project_id": 2, "project_name": "Another Project", "role": "worker", "assigned_at": "2024-01-02T00:00:00Z"},
        ]

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(agents_app, ["status", "lead-agent"])

        assert result.exit_code == 0
        assert "My Project" in result.output


class TestAgentsRoleCommand:
    """Tests for 'codeframe agents role' command."""

    def test_role_update_success(self, tmp_path):
        """Role update should change agent role."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agent_id": "worker-1",
            "project_id": 1,
            "role": "specialist",
            "updated_at": "2024-01-01T12:00:00Z",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(agents_app, ["role", "1", "worker-1", "specialist"])

        assert result.exit_code == 0
        assert "specialist" in result.output.lower()
