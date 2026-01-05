"""Tests for CLI session commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from codeframe.cli.session_commands import session_app


runner = CliRunner()


class TestSessionGetCommand:
    """Tests for 'codeframe session get' command."""

    def test_get_session_success(self, tmp_path):
        """Get should display session state."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "project_id": 1,
            "session_id": "abc123",
            "started_at": "2024-01-01T00:00:00Z",
            "last_activity": "2024-01-01T01:00:00Z",
            "status": "active",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(session_app, ["get", "1"])

        assert result.exit_code == 0
        assert "active" in result.output.lower()

    def test_get_session_not_found(self, tmp_path):
        """Get with no active session should show message."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.json.return_value = {"detail": "No active session"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(session_app, ["get", "1"])

        assert result.exit_code != 0
        assert "no" in result.output.lower() or "not found" in result.output.lower()
