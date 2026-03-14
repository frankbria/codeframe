"""Tests for CLI engine stats and compare commands.

Tests the `cf engines stats` and `cf engines compare` commands.
"""

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()


SAMPLE_STATS = {
    "react": {
        "tasks_attempted": 10.0,
        "tasks_completed": 8.0,
        "tasks_failed": 2.0,
        "gate_pass_rate": 75.0,
        "self_correction_rate": 30.0,
        "avg_duration_ms": 5000.0,
        "total_tokens": 12000.0,
        "avg_tokens_per_task": 1500.0,
    },
    "plan": {
        "tasks_attempted": 5.0,
        "tasks_completed": 3.0,
        "tasks_failed": 2.0,
        "gate_pass_rate": 60.0,
        "self_correction_rate": 40.0,
        "avg_duration_ms": 8000.0,
        "total_tokens": 9000.0,
        "avg_tokens_per_task": 3000.0,
    },
}


class TestEnginesStats:
    """Tests for 'cf engines stats' command."""

    def test_engines_stats_no_workspace(self, tmp_path, monkeypatch):
        """Should show error when no workspace exists."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["engines", "stats"])
        assert result.exit_code == 1
        assert "No workspace found" in result.output or "Error" in result.output

    @patch("codeframe.cli.engines_commands.engine_stats")
    @patch("codeframe.cli.engines_commands.get_workspace")
    def test_engines_stats_empty(self, mock_get_ws, mock_es, tmp_path, monkeypatch):
        """Should show 'no stats' message when empty."""
        monkeypatch.chdir(tmp_path)
        mock_get_ws.return_value = "fake-ws"
        mock_es.get_engine_stats.return_value = {}

        result = runner.invoke(app, ["engines", "stats"])
        assert result.exit_code == 0
        assert "No engine stats recorded yet" in result.output

    @patch("codeframe.cli.engines_commands.engine_stats")
    @patch("codeframe.cli.engines_commands.get_workspace")
    def test_engines_stats_with_data(self, mock_get_ws, mock_es, tmp_path, monkeypatch):
        """Should show Rich table with engine data."""
        monkeypatch.chdir(tmp_path)
        mock_get_ws.return_value = "fake-ws"
        mock_es.get_engine_stats.return_value = SAMPLE_STATS

        result = runner.invoke(app, ["engines", "stats"])
        assert result.exit_code == 0
        assert "react" in result.output
        assert "80.0" in result.output  # success rate: 8/10 * 100

    @patch("codeframe.cli.engines_commands.engine_stats")
    @patch("codeframe.cli.engines_commands.get_workspace")
    def test_engines_stats_json_format(self, mock_get_ws, mock_es, tmp_path, monkeypatch):
        """Should output valid JSON when --format json."""
        monkeypatch.chdir(tmp_path)
        mock_get_ws.return_value = "fake-ws"
        mock_es.get_engine_stats.return_value = SAMPLE_STATS

        result = runner.invoke(app, ["engines", "stats", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "react" in data
        assert "plan" in data

    @patch("codeframe.cli.engines_commands.engine_stats")
    @patch("codeframe.cli.engines_commands.get_workspace")
    def test_engines_stats_filter_engine(self, mock_get_ws, mock_es, tmp_path, monkeypatch):
        """Should pass engine filter to get_engine_stats."""
        monkeypatch.chdir(tmp_path)
        mock_get_ws.return_value = "fake-ws"
        mock_es.get_engine_stats.return_value = {
            "react": SAMPLE_STATS["react"],
        }

        result = runner.invoke(app, ["engines", "stats", "--engine", "react"])
        assert result.exit_code == 0
        mock_es.get_engine_stats.assert_called_once_with("fake-ws", engine="react")


class TestEnginesCompare:
    """Tests for 'cf engines compare' command."""

    def test_engines_compare_no_workspace(self, tmp_path, monkeypatch):
        """Should show error when no workspace exists."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["engines", "compare"])
        assert result.exit_code == 1

    @patch("codeframe.cli.engines_commands.engine_stats")
    @patch("codeframe.cli.engines_commands.get_workspace")
    def test_engines_compare_empty(self, mock_get_ws, mock_es, tmp_path, monkeypatch):
        """Should show message when no stats exist."""
        monkeypatch.chdir(tmp_path)
        mock_get_ws.return_value = "fake-ws"
        mock_es.get_engine_stats.return_value = {}

        result = runner.invoke(app, ["engines", "compare"])
        assert result.exit_code == 0
        assert "No engine stats recorded yet" in result.output

    @patch("codeframe.cli.engines_commands.engine_stats")
    @patch("codeframe.cli.engines_commands.get_workspace")
    def test_engines_compare_with_data(self, mock_get_ws, mock_es, tmp_path, monkeypatch):
        """Should show comparison table sorted by success rate."""
        monkeypatch.chdir(tmp_path)
        mock_get_ws.return_value = "fake-ws"
        mock_es.get_engine_stats.return_value = SAMPLE_STATS

        result = runner.invoke(app, ["engines", "compare"])
        assert result.exit_code == 0
        assert "react" in result.output
        assert "plan" in result.output
        # react (80%) should appear before plan (60%) in sorted output
        react_pos = result.output.index("react")
        plan_pos = result.output.index("plan")
        assert react_pos < plan_pos
