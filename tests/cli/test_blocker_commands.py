"""Tests for CLI blocker commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from codeframe.cli.blocker_commands import blockers_app


runner = CliRunner()


class TestBlockerListCommand:
    """Tests for 'codeframe blockers list' command."""

    def test_list_blockers_success(self, tmp_path):
        """List should display blockers in table format."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "blockers": [
                {"id": 1, "question": "What framework?", "status": "PENDING", "created_at": "2024-01-01T00:00:00Z"},
                {"id": 2, "question": "Database choice?", "status": "RESOLVED", "created_at": "2024-01-01T01:00:00Z"},
            ],
            "total": 2,
            "pending_count": 1,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(blockers_app, ["list", "1"])

        assert result.exit_code == 0
        assert "What framework" in result.output
        assert "PENDING" in result.output

    def test_list_blockers_empty(self, tmp_path):
        """List with no blockers should show helpful message."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blockers": [], "total": 0, "pending_count": 0}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(blockers_app, ["list", "1"])

        assert result.exit_code == 0
        assert "no blockers" in result.output.lower()

    def test_list_blockers_filter_status(self, tmp_path):
        """List with --status should filter."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"blockers": [], "total": 0}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response) as mock_request:
                result = runner.invoke(blockers_app, ["list", "1", "--status", "PENDING"])

        assert result.exit_code == 0
        # Verify status was passed to API
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs.get("params", {}).get("status") == "PENDING"


class TestBlockerGetCommand:
    """Tests for 'codeframe blockers get' command."""

    def test_get_blocker_success(self, tmp_path):
        """Get should display blocker details."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "question": "What database should we use?",
            "status": "PENDING",
            "blocker_type": "SYNC",
            "context": "Need to choose database for user data",
            "created_at": "2024-01-01T00:00:00Z",
            "agent_id": "lead-agent",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(blockers_app, ["get", "1"])

        assert result.exit_code == 0
        assert "What database" in result.output
        assert "PENDING" in result.output

    def test_get_blocker_not_found(self, tmp_path):
        """Get with invalid ID should show error."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.json.return_value = {"detail": "Blocker 999 not found"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(blockers_app, ["get", "999"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestBlockerResolveCommand:
    """Tests for 'codeframe blockers resolve' command."""

    def test_resolve_blocker_success(self, tmp_path):
        """Resolve should submit answer and show success."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "blocker_id": 1,
            "status": "RESOLVED",
            "resolved_at": "2024-01-01T12:00:00Z",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(blockers_app, ["resolve", "1", "Use PostgreSQL"])

        assert result.exit_code == 0
        assert "resolved" in result.output.lower()

    def test_resolve_blocker_already_resolved(self, tmp_path):
        """Resolve already-resolved blocker should show info."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.text = "Conflict"
        mock_response.json.return_value = {
            "error": "Blocker already resolved",
            "blocker_id": 1,
            "resolved_at": "2024-01-01T10:00:00Z",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(blockers_app, ["resolve", "1", "My answer"])

        assert result.exit_code != 0
        assert "already" in result.output.lower()

    def test_resolve_blocker_not_found(self, tmp_path):
        """Resolve non-existent blocker should show error."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.json.return_value = {"detail": "Blocker not found"}

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(blockers_app, ["resolve", "999", "Answer"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestBlockerMetricsCommand:
    """Tests for 'codeframe blockers metrics' command."""

    def test_metrics_success(self, tmp_path):
        """Metrics should display blocker analytics."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "avg_resolution_time_seconds": 3600,
            "expiration_rate_percent": 5.0,
            "total_blockers": 20,
            "resolved_count": 18,
            "expired_count": 1,
            "pending_count": 1,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(blockers_app, ["metrics", "1"])

        assert result.exit_code == 0
        assert "20" in result.output  # total blockers
        assert "18" in result.output or "resolved" in result.output.lower()
