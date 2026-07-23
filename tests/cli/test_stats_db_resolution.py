"""Regression tests for `cf stats` DB resolution (issue #777 / P3.6).

Before the fix, `stats_commands._get_db()` hardcoded `.codeframe/state.db`
relative to the current directory, so `cf stats` failed from any subdirectory
of a workspace and ignored the `DATABASE_PATH` env var honored elsewhere
(e.g. `core/config.py`). These tests lock in the walk-up from cwd and the
`DATABASE_PATH` override.
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


def _make_workspace_with_row(repo: Path) -> Path:
    """Create a workspace at ``repo`` with one token_usage row; return db path."""
    ws = create_or_load_workspace(repo)
    db = Database(str(ws.db_path))
    db.initialize()
    try:
        db.save_token_usage(
            TokenUsage(
                task_id="task-1",
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
    return ws.db_path


def test_stats_tokens_walks_up_from_subdirectory(tmp_path: Path, monkeypatch):
    """`cf stats tokens` finds the workspace DB from a nested subdirectory."""
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_workspace_with_row(repo)

    subdir = repo / "src" / "pkg"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)

    result = CliRunner().invoke(stats_app, ["tokens"])
    assert result.exit_code == 0, result.output
    assert "1,500" in result.output


def test_stats_tokens_honors_database_path_env(tmp_path: Path, monkeypatch):
    """DATABASE_PATH points at the DB directly, regardless of cwd."""
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = _make_workspace_with_row(repo)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    result = CliRunner().invoke(stats_app, ["tokens"])
    assert result.exit_code == 0, result.output
    assert "1,500" in result.output


def test_stats_tokens_errors_when_no_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    empty = tmp_path / "empty"
    empty.mkdir()
    # The walk-up is unbounded; guard against a stray DB above tmp_path.
    if any((p / ".codeframe" / "state.db").exists() for p in (empty, *empty.parents)):
        pytest.skip("stray .codeframe/state.db above tmp_path")
    monkeypatch.chdir(empty)

    result = CliRunner().invoke(stats_app, ["tokens"])
    assert result.exit_code == 1
    assert "No workspace found" in result.output


@pytest.mark.parametrize("target", ["nope.db", "."])
def test_stats_tokens_errors_when_database_path_invalid(
    tmp_path: Path, monkeypatch, target: str
):
    """DATABASE_PATH pointing at a missing file or a directory errors out."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / target))

    result = CliRunner().invoke(stats_app, ["tokens"])
    assert result.exit_code == 1
    assert "DATABASE_PATH does not point to a database file" in result.output
