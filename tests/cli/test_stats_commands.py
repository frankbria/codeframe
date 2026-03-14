"""Tests for CLI stats commands (headless token/cost tracking).

TDD approach: Write tests first, then implement.
Tests the `cf stats tokens`, `cf stats costs`, and `cf stats export` commands.
"""

import csv
import json
import os
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from codeframe.cli.stats_commands import stats_app
from codeframe.core.models import CallType, TokenUsage
from codeframe.persistence.database import Database

pytestmark = pytest.mark.v2

runner = CliRunner()


def _seed_project_and_tasks(db):
    """Create a project and tasks to satisfy FK constraints."""
    cursor = db.conn.cursor()
    cursor.execute(
        "INSERT INTO projects (name, description, source_type, source_branch, workspace_path) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test-project", "Test project", "empty", "main", "/tmp/test"),
    )
    cursor.execute(
        "INSERT INTO tasks (project_id, title, description, status, priority) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "Task 1", "First task", "in_progress", 0),
    )
    cursor.execute(
        "INSERT INTO tasks (project_id, title, description, status, priority) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "Task 2", "Second task", "in_progress", 0),
    )
    db.conn.commit()


@pytest.fixture
def workspace_with_tokens(tmp_path):
    """Create a workspace with seeded token usage data."""
    codeframe_dir = tmp_path / ".codeframe"
    codeframe_dir.mkdir()
    db = Database(codeframe_dir / "state.db")
    db.initialize()

    _seed_project_and_tasks(db)

    records = [
        TokenUsage(
            task_id=1,
            agent_id="react-agent",
            project_id=1,
            model_name="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=500,
            estimated_cost_usd=0.0105,
            call_type=CallType.TASK_EXECUTION,
            timestamp=datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc),
        ),
        TokenUsage(
            task_id=1,
            agent_id="react-agent",
            project_id=1,
            model_name="claude-sonnet-4-5",
            input_tokens=2000,
            output_tokens=800,
            estimated_cost_usd=0.018,
            call_type=CallType.TASK_EXECUTION,
            timestamp=datetime(2026, 3, 10, 11, 0, 0, tzinfo=timezone.utc),
        ),
        TokenUsage(
            task_id=2,
            agent_id="react-agent",
            project_id=1,
            model_name="claude-haiku-4",
            input_tokens=500,
            output_tokens=200,
            estimated_cost_usd=0.0012,
            call_type=CallType.CODE_REVIEW,
            timestamp=datetime(2026, 3, 12, 10, 0, 0, tzinfo=timezone.utc),
        ),
    ]

    for record in records:
        db.save_token_usage(record)

    db.close()
    return tmp_path


@pytest.fixture
def empty_workspace(tmp_path):
    """Create a workspace with initialized DB but no token data."""
    codeframe_dir = tmp_path / ".codeframe"
    codeframe_dir.mkdir()
    db = Database(codeframe_dir / "state.db")
    db.initialize()
    db.close()
    return tmp_path


# =============================================================================
# cf stats tokens
# =============================================================================


class TestStatsTokens:
    """Tests for 'cf stats tokens' command."""

    def test_stats_tokens_no_workspace(self, tmp_path, monkeypatch):
        """Should show error when no workspace exists."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(stats_app, ["tokens"])
        assert result.exit_code == 1
        assert "No workspace found" in result.output

    def test_stats_tokens_empty(self, empty_workspace, monkeypatch):
        """Should show zeros when no token data exists."""
        monkeypatch.chdir(empty_workspace)
        result = runner.invoke(stats_app, ["tokens"])
        assert result.exit_code == 0
        assert "0" in result.output

    def test_stats_tokens_with_data(self, workspace_with_tokens, monkeypatch):
        """Should show correct summary with seeded data."""
        monkeypatch.chdir(workspace_with_tokens)
        result = runner.invoke(stats_app, ["tokens"])
        assert result.exit_code == 0
        # Total tokens: 1000+500 + 2000+800 + 500+200 = 5000
        assert "5,000" in result.output or "5000" in result.output
        # Should show input/output breakdown
        assert "Input" in result.output
        assert "Output" in result.output

    def test_stats_tokens_task_filter(self, workspace_with_tokens, monkeypatch):
        """Should show per-task breakdown when --task is provided."""
        monkeypatch.chdir(workspace_with_tokens)
        result = runner.invoke(stats_app, ["tokens", "--task", "1"])
        assert result.exit_code == 0
        # Task 1 tokens: 1000+500 + 2000+800 = 4300
        assert "4,300" in result.output or "4300" in result.output


# =============================================================================
# cf stats costs
# =============================================================================


class TestStatsCosts:
    """Tests for 'cf stats costs' command."""

    def test_stats_costs_no_workspace(self, tmp_path, monkeypatch):
        """Should show error when no workspace exists."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(stats_app, ["costs"])
        assert result.exit_code == 1
        assert "No workspace found" in result.output

    def test_stats_costs_default(self, workspace_with_tokens, monkeypatch):
        """Should show all-time costs."""
        monkeypatch.chdir(workspace_with_tokens)
        result = runner.invoke(stats_app, ["costs"])
        assert result.exit_code == 0
        assert "$" in result.output
        # Total cost: 0.0105 + 0.018 + 0.0012 = 0.0297
        assert "0.0297" in result.output

    def test_stats_costs_period_month(self, workspace_with_tokens, monkeypatch):
        """Should respect period filter for 'month'."""
        monkeypatch.chdir(workspace_with_tokens)
        result = runner.invoke(stats_app, ["costs", "--period", "month"])
        assert result.exit_code == 0
        assert "$" in result.output

    def test_stats_costs_period_week(self, workspace_with_tokens, monkeypatch):
        """Should respect period filter for 'week'."""
        monkeypatch.chdir(workspace_with_tokens)
        result = runner.invoke(stats_app, ["costs", "--period", "week"])
        assert result.exit_code == 0

    def test_stats_costs_period_day(self, workspace_with_tokens, monkeypatch):
        """Should respect period filter for 'day'."""
        monkeypatch.chdir(workspace_with_tokens)
        result = runner.invoke(stats_app, ["costs", "--period", "day"])
        assert result.exit_code == 0


# =============================================================================
# cf stats export
# =============================================================================


class TestStatsExport:
    """Tests for 'cf stats export' command."""

    def test_stats_export_no_workspace(self, tmp_path, monkeypatch):
        """Should show error when no workspace exists."""
        monkeypatch.chdir(tmp_path)
        output_file = str(tmp_path / "out.csv")
        result = runner.invoke(stats_app, ["export", "--format", "csv", "--output", output_file])
        assert result.exit_code == 1

    def test_stats_export_csv(self, workspace_with_tokens, monkeypatch):
        """Should create a valid CSV file."""
        monkeypatch.chdir(workspace_with_tokens)
        output_file = str(workspace_with_tokens / "tokens.csv")
        result = runner.invoke(stats_app, ["export", "--format", "csv", "--output", output_file])
        assert result.exit_code == 0
        assert os.path.exists(output_file)

        with open(output_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 3
        assert "input_tokens" in rows[0]

    def test_stats_export_json(self, workspace_with_tokens, monkeypatch):
        """Should create a valid JSON file."""
        monkeypatch.chdir(workspace_with_tokens)
        output_file = str(workspace_with_tokens / "tokens.json")
        result = runner.invoke(stats_app, ["export", "--format", "json", "--output", output_file])
        assert result.exit_code == 0
        assert os.path.exists(output_file)

        with open(output_file) as f:
            data = json.load(f)
        assert "records" in data
        assert len(data["records"]) == 3

    def test_stats_export_csv_task_filter(self, workspace_with_tokens, monkeypatch):
        """Should export only records for a specific task."""
        monkeypatch.chdir(workspace_with_tokens)
        output_file = str(workspace_with_tokens / "task1.csv")
        result = runner.invoke(
            stats_app, ["export", "--format", "csv", "--output", output_file, "--task", "1"]
        )
        assert result.exit_code == 0
        assert os.path.exists(output_file)

        with open(output_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        # Task 1 has 2 records
        assert len(rows) == 2
