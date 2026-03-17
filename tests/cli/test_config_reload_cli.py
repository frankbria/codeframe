"""Tests for config reload display in batch status CLI output.

Verifies that config reload timestamps stored in batch results
are displayed in the batch status command output.
"""

from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import conductor
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture()
def workspace_with_batch(tmp_path):
    """Create a workspace with a batch that has config reload timestamps."""
    workspace = create_or_load_workspace(tmp_path)

    # Create a batch record directly via the database
    batch = conductor.BatchRun(
        id="test-batch-reload-001",
        workspace_id=workspace.id,
        task_ids=["task-1"],
        status=conductor.BatchStatus.COMPLETED,
        strategy="serial",
        max_parallel=1,
        on_failure=conductor.OnFailure.CONTINUE,
        started_at=datetime(2026, 3, 17, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 3, 17, 10, 5, 0, tzinfo=timezone.utc),
        results={
            "task-1": "COMPLETED",
            "__config_reloads__": [
                "2026-03-17T10:01:30+00:00",
                "2026-03-17T10:03:45+00:00",
            ],
        },
    )
    conductor._save_batch(workspace, batch)
    return tmp_path


@pytest.fixture()
def workspace_with_batch_no_reloads(tmp_path):
    """Create a workspace with a batch that has no config reloads."""
    workspace = create_or_load_workspace(tmp_path)

    batch = conductor.BatchRun(
        id="test-batch-noreload-001",
        workspace_id=workspace.id,
        task_ids=["task-1"],
        status=conductor.BatchStatus.COMPLETED,
        strategy="serial",
        max_parallel=1,
        on_failure=conductor.OnFailure.CONTINUE,
        started_at=datetime(2026, 3, 17, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 3, 17, 10, 5, 0, tzinfo=timezone.utc),
        results={"task-1": "COMPLETED"},
    )
    conductor._save_batch(workspace, batch)
    return tmp_path


class TestBatchStatusConfigReloads:
    """Tests for config reload display in batch status output."""

    def test_batch_status_shows_config_reloads(self, workspace_with_batch):
        """Batch status should show config reload timestamps when present."""
        result = runner.invoke(
            app,
            [
                "work", "batch", "status", "test-batch-reload-001",
                "-w", str(workspace_with_batch),
            ],
        )
        assert result.exit_code == 0
        assert "Config reloaded at 10:01:30" in result.output
        assert "Config reloaded at 10:03:45" in result.output

    def test_batch_status_shows_config_reloads_header(self, workspace_with_batch):
        """Batch status should show the Config Reloads section header."""
        result = runner.invoke(
            app,
            [
                "work", "batch", "status", "test-batch-reload-001",
                "-w", str(workspace_with_batch),
            ],
        )
        assert result.exit_code == 0
        assert "Config Reloads" in result.output

    def test_batch_status_no_reloads_no_section(self, workspace_with_batch_no_reloads):
        """Batch status should not show config reload section when none occurred."""
        result = runner.invoke(
            app,
            [
                "work", "batch", "status", "test-batch-noreload-001",
                "-w", str(workspace_with_batch_no_reloads),
            ],
        )
        assert result.exit_code == 0
        assert "Config reloaded at" not in result.output
        assert "Config Reloads" not in result.output
