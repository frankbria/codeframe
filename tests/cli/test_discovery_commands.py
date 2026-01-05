"""Tests for CLI discovery commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from codeframe.cli.discovery_commands import discovery_app


runner = CliRunner()


class TestDiscoveryStartCommand:
    """Tests for 'codeframe discovery start' command."""

    def test_start_discovery_success(self, tmp_path):
        """Start should trigger discovery and show success message."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "message": "Starting discovery for project 1",
            "status": "starting",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["start", "1"])

        assert result.exit_code == 0
        assert "discovery" in result.output.lower()
        assert "start" in result.output.lower()

    def test_start_discovery_already_running(self, tmp_path):
        """Start on already running discovery should show info."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.text = "Conflict"
        mock_response.json.return_value = {
            "detail": "Discovery already in progress",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["start", "1"])

        assert result.exit_code != 0
        assert "already" in result.output.lower() or "error" in result.output.lower()


class TestDiscoveryProgressCommand:
    """Tests for 'codeframe discovery progress' command."""

    def test_progress_discovering_state(self, tmp_path):
        """Progress should show current question and percentage."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "project_id": 1,
            "phase": "discovery",
            "discovery": {
                "state": "discovering",
                "progress_percentage": 40.0,
                "answered_count": 4,
                "total_required": 10,
                "remaining_count": 6,
                "current_question": {
                    "id": "q5",
                    "question": "What is your target audience?",
                    "category": "market",
                },
            },
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["progress", "1"])

        assert result.exit_code == 0
        assert "40" in result.output  # progress percentage
        assert "target audience" in result.output.lower()

    def test_progress_idle_state(self, tmp_path):
        """Progress with idle discovery should prompt to start."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "project_id": 1,
            "phase": "discovery",
            "discovery": None,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["progress", "1"])

        assert result.exit_code == 0
        assert "not started" in result.output.lower() or "start" in result.output.lower()

    def test_progress_completed_state(self, tmp_path):
        """Progress with completed discovery should show completion."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "project_id": 1,
            "phase": "planning",
            "discovery": {
                "state": "completed",
                "progress_percentage": 100.0,
                "answered_count": 10,
                "total_required": 10,
                "structured_data": {"project_type": "web_app"},
            },
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["progress", "1"])

        assert result.exit_code == 0
        assert "100" in result.output or "complete" in result.output.lower()


class TestDiscoveryAnswerCommand:
    """Tests for 'codeframe discovery answer' command."""

    def test_answer_success(self, tmp_path):
        """Answer should submit and show next question."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "next_question": "What technologies will you use?",
            "is_complete": False,
            "current_index": 5,
            "total_questions": 10,
            "progress_percentage": 50.0,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["answer", "1", "Web application for e-commerce"])

        assert result.exit_code == 0
        assert "technologies" in result.output.lower()
        assert "50" in result.output  # progress percentage

    def test_answer_completes_discovery(self, tmp_path):
        """Answer completing discovery should show completion message."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "next_question": None,
            "is_complete": True,
            "current_index": 10,
            "total_questions": 10,
            "progress_percentage": 100.0,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["answer", "1", "Final answer"])

        assert result.exit_code == 0
        assert "complete" in result.output.lower()

    def test_answer_discovery_not_active(self, tmp_path):
        """Answer when discovery is not active should show error."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.json.return_value = {
            "detail": "Discovery is not active. Current state: idle",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["answer", "1", "My answer"])

        assert result.exit_code != 0
        assert "not active" in result.output.lower() or "error" in result.output.lower()


class TestDiscoveryRestartCommand:
    """Tests for 'codeframe discovery restart' command."""

    def test_restart_success(self, tmp_path):
        """Restart should reset discovery and show success."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "Discovery has been reset. You can now start discovery again.",
            "state": "idle",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["restart", "1", "--force"])

        assert result.exit_code == 0
        assert "reset" in result.output.lower()

    def test_restart_prompts_without_force(self, tmp_path):
        """Restart without --force should prompt for confirmation."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "Discovery has been reset.",
            "state": "idle",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["restart", "1"], input="y\n")

        assert result.exit_code == 0

    def test_restart_already_completed(self, tmp_path):
        """Restart on completed discovery should show error."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.json.return_value = {
            "detail": "Discovery is already completed. Cannot restart completed discovery.",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["restart", "1", "--force"])

        assert result.exit_code != 0
        assert "completed" in result.output.lower() or "error" in result.output.lower()


class TestDiscoveryGeneratePrdCommand:
    """Tests for 'codeframe discovery generate-prd' command."""

    def test_generate_prd_success(self, tmp_path):
        """Generate PRD should trigger background generation."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "PRD generation has been started. Watch for WebSocket updates.",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["generate-prd", "1"])

        assert result.exit_code == 0
        assert "prd" in result.output.lower()
        assert "started" in result.output.lower()

    def test_generate_prd_discovery_not_completed(self, tmp_path):
        """Generate PRD before discovery completes should show error."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.json.return_value = {
            "detail": "Discovery must be completed before generating PRD. Current state: discovering",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(discovery_app, ["generate-prd", "1"])

        assert result.exit_code != 0
        assert "complete" in result.output.lower() or "error" in result.output.lower()
