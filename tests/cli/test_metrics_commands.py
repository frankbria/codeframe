"""Tests for CLI metrics commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from codeframe.cli.metrics_commands import metrics_app


runner = CliRunner()


class TestMetricsTokensCommand:
    """Tests for 'codeframe metrics tokens' command."""

    def test_tokens_success(self, tmp_path):
        """Tokens should display token usage metrics."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "project_id": 1,
            "total_tokens": 150000,
            "input_tokens": 100000,
            "output_tokens": 50000,
            "by_agent": [
                {"agent_id": "lead-agent", "tokens": 80000},
                {"agent_id": "worker-1", "tokens": 70000},
            ],
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(metrics_app, ["tokens", "1"])

        assert result.exit_code == 0
        assert "150000" in result.output or "150,000" in result.output


class TestMetricsCostsCommand:
    """Tests for 'codeframe metrics costs' command."""

    def test_costs_success(self, tmp_path):
        """Costs should display cost metrics."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "project_id": 1,
            "total_cost_usd": 12.50,
            "input_cost_usd": 8.00,
            "output_cost_usd": 4.50,
            "by_day": [
                {"date": "2024-01-01", "cost_usd": 5.25},
                {"date": "2024-01-02", "cost_usd": 7.25},
            ],
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(metrics_app, ["costs", "1"])

        assert result.exit_code == 0
        assert "12.50" in result.output or "$12" in result.output


class TestMetricsAgentCommand:
    """Tests for 'codeframe metrics agent' command."""

    def test_agent_metrics_success(self, tmp_path):
        """Agent metrics should display agent-specific stats."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agent_id": "lead-agent",
            "total_tokens": 80000,
            "total_cost_usd": 5.00,
            "tasks_completed": 15,
            "average_tokens_per_task": 5333,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(metrics_app, ["agent", "lead-agent"])

        assert result.exit_code == 0
        assert "lead-agent" in result.output or "80000" in result.output
