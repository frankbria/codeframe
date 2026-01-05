"""Tests for CLI context commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from codeframe.cli.context_commands import context_app


runner = CliRunner()


class TestContextGetCommand:
    """Tests for 'codeframe context get' command."""

    def test_get_context_success(self, tmp_path):
        """Get should display context information."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agent_id": "lead-agent",
            "total_tokens": 45000,
            "items_count": 25,
            "tiers": {
                "hot": 10,
                "warm": 8,
                "cold": 7,
            },
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(context_app, ["get", "lead-agent"])

        assert result.exit_code == 0
        assert "lead-agent" in result.output


class TestContextStatsCommand:
    """Tests for 'codeframe context stats' command."""

    def test_stats_success(self, tmp_path):
        """Stats should display context statistics."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agent_id": "lead-agent",
            "total_items": 50,
            "total_tokens": 75000,
            "hot_tier": {"count": 15, "tokens": 30000},
            "warm_tier": {"count": 20, "tokens": 25000},
            "cold_tier": {"count": 15, "tokens": 20000},
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(context_app, ["stats", "lead-agent"])

        assert result.exit_code == 0
        assert "50" in result.output or "75000" in result.output


class TestContextFlashSaveCommand:
    """Tests for 'codeframe context flash-save' command."""

    def test_flash_save_success(self, tmp_path):
        """Flash save should create checkpoint."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "checkpoint_id": "cp-123",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(context_app, ["flash-save", "lead-agent"])

        assert result.exit_code == 0
        assert "checkpoint" in result.output.lower() or "saved" in result.output.lower()


class TestContextCheckpointsCommand:
    """Tests for 'codeframe context checkpoints' command."""

    def test_checkpoints_list_success(self, tmp_path):
        """Checkpoints should list context checkpoints."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "checkpoints": [
                {"id": "cp-1", "timestamp": "2024-01-01T10:00:00Z", "items_count": 20},
                {"id": "cp-2", "timestamp": "2024-01-01T11:00:00Z", "items_count": 25},
            ]
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(context_app, ["checkpoints", "lead-agent"])

        assert result.exit_code == 0
        assert "cp-1" in result.output or "cp-2" in result.output
