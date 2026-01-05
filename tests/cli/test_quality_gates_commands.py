"""Tests for CLI quality-gates commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from codeframe.cli.quality_gates_commands import quality_gates_app


runner = CliRunner()


class TestQualityGatesGetCommand:
    """Tests for 'codeframe quality-gates get' command."""

    def test_get_quality_gates_success(self, tmp_path):
        """Get should display quality gate status for task."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "task_id": 1,
            "gates": [
                {"name": "tests", "status": "passed", "details": "42/42 tests passed"},
                {"name": "type_check", "status": "passed", "details": "No type errors"},
                {"name": "coverage", "status": "warning", "details": "Coverage: 78%"},
                {"name": "review", "status": "pending", "details": "Awaiting review"},
            ],
            "overall_status": "warning",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(quality_gates_app, ["get", "1"])

        assert result.exit_code == 0
        assert "tests" in result.output.lower()
        assert "passed" in result.output.lower()

    def test_get_quality_gates_not_found(self, tmp_path):
        """Get with invalid task ID should show error."""
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
                result = runner.invoke(quality_gates_app, ["get", "999"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestQualityGatesRunCommand:
    """Tests for 'codeframe quality-gates run' command."""

    def test_run_quality_gates_success(self, tmp_path):
        """Run should trigger quality checks and show results."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "task_id": 1,
            "status": "running",
            "message": "Quality gates check started",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(quality_gates_app, ["run", "1"])

        assert result.exit_code == 0
        assert "started" in result.output.lower() or "running" in result.output.lower()

    def test_run_quality_gates_with_gate_filter(self, tmp_path):
        """Run with --gate should run specific gate only."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"status": "running"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response) as mock_request:
                result = runner.invoke(quality_gates_app, ["run", "1", "--gate", "tests"])

        assert result.exit_code == 0
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"].get("gate") == "tests"
