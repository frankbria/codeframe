"""Tests for CLI replay commands: cf work replay, cf work diff, cf work export-trace.

Uses CliRunner to test command output without requiring a real workspace.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.workspace import create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def workspace(tmp_path: Path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return create_or_load_workspace(repo_path)


@pytest.fixture
def seeded_workspace(workspace):
    """Workspace with a run, task, and 3-step execution trace."""
    from codeframe.core.replay import (
        ExecutionStep,
        FileOperation,
        LLMInteraction,
        save_execution_step,
        save_file_operation,
        save_llm_interaction,
    )

    task_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    # Insert a task
    conn = get_db_connection(workspace)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO tasks (id, workspace_id, title, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, workspace.id, "Test task", "A test task", "DONE", now, now),
        )
        conn.execute(
            "INSERT INTO runs (id, workspace_id, task_id, status, started_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, workspace.id, task_id, "COMPLETED", now, now),
        )
        conn.commit()
    finally:
        conn.close()

    base = datetime.now(timezone.utc)
    step_ids = [str(uuid.uuid4()) for _ in range(3)]

    for i, (desc, op_type, path, before, after) in enumerate([
        ("Create main.py", "create", "src/main.py", None, "print('hello')"),
        ("Edit main.py", "edit", "src/main.py", "print('hello')", "print('world')"),
        ("Create utils.py", "create", "src/utils.py", None, "def helper(): pass"),
    ]):
        save_execution_step(
            workspace,
            ExecutionStep(
                id=step_ids[i],
                run_id=run_id,
                step_number=i + 1,
                step_type="tool_call",
                description=desc,
                started_at=base + timedelta(seconds=i * 2),
                completed_at=base + timedelta(seconds=i * 2 + 1),
                status="completed",
            ),
        )
        save_file_operation(
            workspace,
            FileOperation(
                id=str(uuid.uuid4()),
                run_id=run_id,
                step_id=step_ids[i],
                operation_type=op_type,
                file_path=path,
                content_before=before,
                content_after=after,
                timestamp=base + timedelta(seconds=i * 2 + 1),
            ),
        )
        if i < 2:  # LLM interactions for first two steps
            save_llm_interaction(
                workspace,
                LLMInteraction(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    step_id=step_ids[i],
                    prompt=f"Do step {i + 1}",
                    response=f"Done with step {i + 1}",
                    model="claude-sonnet",
                    tokens_used=500,
                    timestamp=base + timedelta(seconds=i * 2 + 1),
                    purpose="execution",
                ),
            )

    return workspace, task_id, run_id


class TestWorkReplay:
    """Tests for cf work replay <run-id>."""

    def test_replay_shows_steps(self, seeded_workspace):
        workspace, task_id, run_id = seeded_workspace
        result = runner.invoke(
            app, ["work", "replay", run_id, "--workspace", str(workspace.repo_path)]
        )
        assert result.exit_code == 0
        assert "Create main.py" in result.output
        assert "Edit main.py" in result.output
        assert "Create utils.py" in result.output

    def test_replay_specific_step(self, seeded_workspace):
        workspace, task_id, run_id = seeded_workspace
        result = runner.invoke(
            app,
            ["work", "replay", run_id, "--step", "2", "--workspace", str(workspace.repo_path)],
        )
        assert result.exit_code == 0
        assert "Edit main.py" in result.output

    def test_replay_with_show_llm(self, seeded_workspace):
        workspace, task_id, run_id = seeded_workspace
        result = runner.invoke(
            app,
            ["work", "replay", run_id, "--show-llm", "--workspace", str(workspace.repo_path)],
        )
        assert result.exit_code == 0
        assert "Do step 1" in result.output or "LLM" in result.output

    def test_replay_nonexistent_run(self, workspace):
        result = runner.invoke(
            app,
            ["work", "replay", "nonexistent-id", "--workspace", str(workspace.repo_path)],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "no trace" in result.output.lower()


class TestWorkDiff:
    """Tests for cf work diff <run-id>."""

    def test_diff_shows_all_changes(self, seeded_workspace):
        workspace, task_id, run_id = seeded_workspace
        result = runner.invoke(
            app, ["work", "diff", run_id, "--workspace", str(workspace.repo_path)]
        )
        assert result.exit_code == 0
        assert "src/main.py" in result.output
        assert "src/utils.py" in result.output

    def test_diff_between_steps(self, seeded_workspace):
        workspace, task_id, run_id = seeded_workspace
        result = runner.invoke(
            app,
            [
                "work", "diff", run_id,
                "--from-step", "1", "--to-step", "3",
                "--workspace", str(workspace.repo_path),
            ],
        )
        assert result.exit_code == 0
        assert "src/main.py" in result.output

    def test_diff_nonexistent_run(self, workspace):
        result = runner.invoke(
            app,
            ["work", "diff", "nonexistent-id", "--workspace", str(workspace.repo_path)],
        )
        assert result.exit_code == 1


class TestWorkExportTrace:
    """Tests for cf work export-trace <run-id>."""

    def test_export_json_to_stdout(self, seeded_workspace):
        workspace, task_id, run_id = seeded_workspace
        result = runner.invoke(
            app,
            [
                "work", "export-trace", run_id,
                "--format", "json",
                "--workspace", str(workspace.repo_path),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["run_id"] == run_id
        assert data["summary"]["total_steps"] == 3

    def test_export_markdown_to_stdout(self, seeded_workspace):
        workspace, task_id, run_id = seeded_workspace
        result = runner.invoke(
            app,
            [
                "work", "export-trace", run_id,
                "--format", "markdown",
                "--workspace", str(workspace.repo_path),
            ],
        )
        assert result.exit_code == 0
        assert "# Execution Trace" in result.output
        assert run_id in result.output

    def test_export_json_to_file(self, seeded_workspace, tmp_path):
        workspace, task_id, run_id = seeded_workspace
        output_file = tmp_path / "trace.json"
        result = runner.invoke(
            app,
            [
                "work", "export-trace", run_id,
                "--format", "json",
                "--output", str(output_file),
                "--workspace", str(workspace.repo_path),
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["run_id"] == run_id

    def test_export_nonexistent_run(self, workspace):
        result = runner.invoke(
            app,
            [
                "work", "export-trace", "nonexistent-id",
                "--format", "json",
                "--workspace", str(workspace.repo_path),
            ],
        )
        assert result.exit_code == 1
