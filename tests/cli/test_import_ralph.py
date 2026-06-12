"""CLI tests for `cf import ralph` (issue #615)."""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ralph_project"


@pytest.fixture
def ralph_project(tmp_path: Path) -> Path:
    dest = tmp_path / "ralph-project"
    shutil.copytree(FIXTURE, dest)
    return dest


class TestImportRalphCli:
    def test_help_lists_ralph_command(self):
        result = runner.invoke(app, ["import", "--help"])
        assert result.exit_code == 0
        assert "ralph" in result.output

    def test_dry_run_prints_report_without_changes(self, ralph_project: Path):
        result = runner.invoke(
            app, ["import", "ralph", str(ralph_project), "--dry-run"]
        )
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        assert "fix_plan.md" in result.output
        # Mapping summary: 7 tasks, 5 READY / 2 BACKLOG
        assert "7" in result.output
        # No files created
        assert not (ralph_project / ".codeframe").exists()
        assert not (ralph_project / "AGENTS.md").exists()

    def test_import_creates_workspace_and_reports(self, ralph_project: Path):
        result = runner.invoke(app, ["import", "ralph", str(ralph_project)])
        assert result.exit_code == 0
        assert (ralph_project / ".codeframe").exists()
        assert (ralph_project / "AGENTS.md").exists()
        assert "7" in result.output

    def test_rerun_reports_already_imported(self, ralph_project: Path):
        runner.invoke(app, ["import", "ralph", str(ralph_project)])
        result = runner.invoke(app, ["import", "ralph", str(ralph_project)])
        assert result.exit_code == 0
        assert "already imported" in result.output.lower()

    def test_missing_ralph_dir_errors(self, tmp_path: Path):
        result = runner.invoke(app, ["import", "ralph", str(tmp_path)])
        assert result.exit_code == 1
        assert "no ralph project" in result.output.lower()

    def test_workspace_option_targets_other_directory(
        self, ralph_project: Path, tmp_path: Path
    ):
        target = tmp_path / "target-ws"
        target.mkdir()
        result = runner.invoke(
            app,
            ["import", "ralph", str(ralph_project), "--workspace", str(target)],
        )
        assert result.exit_code == 0
        assert (target / ".codeframe").exists()
        assert not (ralph_project / ".codeframe").exists()
