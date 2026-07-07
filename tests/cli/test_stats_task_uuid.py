"""Regression tests for `cf stats --task <uuid>` (issue #744 / P1.17).

Before the fix, `tokens(task: Optional[int])` and `export_data(task: Optional[int])`
typed the option as `int`, so Typer rejected a v2 UUID task ID at coercion time
(exit code 2) and per-task cost/token reporting/export was broken for every real
v2 task. These tests lock in that a UUID string flows through the CLI and the
repository returns the saved UUID-keyed row.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.stats_commands import stats_app
from codeframe.core.models import CallType, TokenUsage
from codeframe.core.workspace import create_or_load_workspace
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2

TASK_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


@pytest.fixture
def workspace_with_row(tmp_path: Path, monkeypatch) -> str:
    """A workspace at cwd with one saved UUID-keyed token_usage row."""
    repo = tmp_path / "repo"
    repo.mkdir()
    ws = create_or_load_workspace(repo)
    db = Database(str(ws.db_path))
    db.initialize()
    try:
        db.save_token_usage(
            TokenUsage(
                task_id=TASK_UUID,  # v2 UUID string, not int
                agent_id="react-agent",
                project_id=0,
                model_name="claude-sonnet-4-5",
                input_tokens=1000,
                output_tokens=500,
                estimated_cost_usd=0.0105,
                call_type=CallType.TASK_EXECUTION,
                timestamp=datetime.now(timezone.utc),
            )
        )
    finally:
        db.close()
    # stats_commands._get_db() looks for .codeframe/state.db relative to cwd.
    monkeypatch.chdir(repo)
    return TASK_UUID


def test_stats_tokens_accepts_uuid_and_returns_saved_row(workspace_with_row: str):
    result = CliRunner().invoke(stats_app, ["tokens", "--task", workspace_with_row])
    assert result.exit_code == 0, result.output
    assert "1,500" in result.output  # total tokens
    assert "1,000" in result.output  # input tokens
    assert "500" in result.output  # output tokens
    assert "$0.0105" in result.output


def test_stats_export_accepts_uuid(workspace_with_row: str, tmp_path: Path):
    out = tmp_path / "task.csv"
    result = CliRunner().invoke(
        stats_app,
        ["export", "--format", "csv", "--output", str(out), "--task", workspace_with_row],
    )
    assert result.exit_code == 0, result.output
    assert "Exported 1 records" in result.output
    assert out.exists()


def test_repository_get_task_token_summary_by_uuid(tmp_path: Path):
    """The repo layer returns the aggregated row for a UUID task_id."""
    repo = tmp_path / "repo"
    repo.mkdir()
    ws = create_or_load_workspace(repo)
    db = Database(str(ws.db_path))
    db.initialize()
    try:
        db.save_token_usage(
            TokenUsage(
                task_id=TASK_UUID,
                agent_id="react-agent",
                project_id=0,
                model_name="claude-sonnet-4-5",
                input_tokens=1000,
                output_tokens=500,
                estimated_cost_usd=0.0105,
                call_type=CallType.TASK_EXECUTION,
                timestamp=datetime.now(timezone.utc),
            )
        )
        summary = db.get_task_token_summary(TASK_UUID)
    finally:
        db.close()

    assert summary["task_id"] == TASK_UUID
    assert summary["total_tokens"] == 1500
    assert summary["call_count"] == 1
