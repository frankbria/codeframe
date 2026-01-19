"""Unit tests for PRD CLI commands.

Tests for codeframe prd subcommands:
- prd add <file>
- prd show [--full] [prd_id]
- prd list
- prd delete <prd_id>
- prd export <prd_id> <file>
"""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import workspace, prd


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary directory to use as a repo."""
    repo = tmp_path / "test-project"
    repo.mkdir()
    return repo


@pytest.fixture
def initialized_workspace(temp_repo: Path):
    """Create an initialized workspace."""
    return workspace.create_or_load_workspace(temp_repo)


@pytest.fixture
def sample_prd_file(temp_repo: Path) -> Path:
    """Create a sample PRD file."""
    prd_path = temp_repo / "requirements.md"
    prd_path.write_text("""# Todo App MVP

Build a simple todo application.

## Features

- Create new todo items
- Mark todos as complete
- Delete todo items
""")
    return prd_path


@pytest.fixture
def second_prd_file(temp_repo: Path) -> Path:
    """Create a second PRD file."""
    prd_path = temp_repo / "phase2.md"
    prd_path.write_text("""# Phase 2 Features

Advanced features for the todo app.

## Features

- Subtasks
- Due dates
""")
    return prd_path


class TestPrdAdd:
    """Tests for prd add command."""

    def test_add_prd_success(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should add a PRD file to workspace."""
        result = runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "PRD added" in result.stdout
        assert "Todo App MVP" in result.stdout

    def test_add_prd_nonexistent_file(self, runner, initialized_workspace, temp_repo):
        """Should fail for nonexistent file."""
        result = runner.invoke(app, ["prd", "add", "/nonexistent/file.md", "-w", str(temp_repo)])

        assert result.exit_code != 0

    def test_add_prd_suggests_next_step(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should suggest running tasks generate."""
        result = runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "tasks generate" in result.stdout


class TestPrdShow:
    """Tests for prd show command."""

    def test_show_latest_prd(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should show the latest PRD."""
        # First add a PRD
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        # Then show it
        result = runner.invoke(app, ["prd", "show", "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "Todo App MVP" in result.stdout

    def test_show_no_prd(self, runner, initialized_workspace, temp_repo):
        """Should show message when no PRD exists."""
        result = runner.invoke(app, ["prd", "show", "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "No PRD found" in result.stdout

    def test_show_full_content(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should show full content with --full flag."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        result = runner.invoke(app, ["prd", "show", "--full", "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "Create new todo items" in result.stdout


# ============================================================================
# Tests for NEW CLI commands to be implemented
# ============================================================================


class TestPrdList:
    """Tests for prd list command - NEW."""

    def test_list_no_prds(self, runner, initialized_workspace, temp_repo):
        """Should show empty message when no PRDs."""
        result = runner.invoke(app, ["prd", "list", "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "No PRDs found" in result.stdout

    def test_list_single_prd(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should list one PRD."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        result = runner.invoke(app, ["prd", "list", "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "Todo App MVP" in result.stdout

    def test_list_multiple_prds(self, runner, initialized_workspace, sample_prd_file, second_prd_file, temp_repo):
        """Should list multiple PRDs."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])
        runner.invoke(app, ["prd", "add", str(second_prd_file), "-w", str(temp_repo)])

        result = runner.invoke(app, ["prd", "list", "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "Todo App MVP" in result.stdout
        assert "Phase 2 Features" in result.stdout

    def test_list_shows_ids(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should show PRD IDs in listing."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        result = runner.invoke(app, ["prd", "list", "-w", str(temp_repo)])

        assert result.exit_code == 0
        # IDs are shown truncated: 8 hex chars followed by ...
        import re
        truncated_id_pattern = r"[0-9a-f]{8}\.\.\."
        assert re.search(truncated_id_pattern, result.stdout)


class TestPrdDelete:
    """Tests for prd delete command - NEW."""

    def test_delete_existing_prd(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should delete a PRD by ID."""
        # Add PRD
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        # Get the ID
        ws = workspace.get_workspace(temp_repo)
        record = prd.get_latest(ws)
        prd_id = record.id

        # Delete it (provide 'y' for confirmation)
        result = runner.invoke(app, ["prd", "delete", prd_id, "-w", str(temp_repo)], input="y\n")

        assert result.exit_code == 0
        assert "deleted" in result.stdout.lower()

        # Verify it's gone
        assert prd.get_by_id(ws, prd_id) is None

    def test_delete_nonexistent_prd(self, runner, initialized_workspace, temp_repo):
        """Should show error for nonexistent PRD."""
        result = runner.invoke(app, ["prd", "delete", "fake-id-123", "-w", str(temp_repo)])

        assert result.exit_code != 0 or "not found" in result.stdout.lower()

    def test_delete_with_confirmation(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should require confirmation by default."""
        # Add PRD
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        record = prd.get_latest(ws)

        # Try delete without confirmation (input 'n')
        result = runner.invoke(app, ["prd", "delete", record.id, "-w", str(temp_repo)], input="n\n")

        # PRD should still exist
        assert prd.get_by_id(ws, record.id) is not None

    def test_delete_force_skips_confirmation(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should skip confirmation with --force."""
        # Add PRD
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        record = prd.get_latest(ws)

        # Delete with --force
        result = runner.invoke(app, ["prd", "delete", record.id, "--force", "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert prd.get_by_id(ws, record.id) is None


class TestPrdExport:
    """Tests for prd export command - NEW."""

    def test_export_to_file(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should export PRD to a file."""
        # Add PRD
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        record = prd.get_latest(ws)

        export_path = temp_repo / "exported.md"

        result = runner.invoke(app, ["prd", "export", record.id, str(export_path), "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert export_path.exists()
        assert "Todo App MVP" in export_path.read_text()

    def test_export_latest(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should export latest PRD when using 'latest' as ID."""
        # Add PRD
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        export_path = temp_repo / "exported.md"

        result = runner.invoke(app, ["prd", "export", "latest", str(export_path), "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert export_path.exists()

    def test_export_nonexistent_prd(self, runner, initialized_workspace, temp_repo):
        """Should fail for nonexistent PRD."""
        export_path = temp_repo / "output.md"

        result = runner.invoke(app, ["prd", "export", "fake-id", str(export_path), "-w", str(temp_repo)])

        assert result.exit_code != 0 or "not found" in result.stdout.lower()
        assert not export_path.exists()

    def test_export_overwrite_protection(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should not overwrite existing file by default."""
        # Add PRD
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        record = prd.get_latest(ws)

        export_path = temp_repo / "existing.md"
        export_path.write_text("original content")

        result = runner.invoke(app, ["prd", "export", record.id, str(export_path), "-w", str(temp_repo)])

        # Should fail or warn
        assert "exists" in result.stdout.lower() or result.exit_code != 0
        # Original content preserved
        assert export_path.read_text() == "original content"

    def test_export_force_overwrites(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should overwrite with --force."""
        # Add PRD
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        record = prd.get_latest(ws)

        export_path = temp_repo / "existing.md"
        export_path.write_text("original content")

        result = runner.invoke(app, ["prd", "export", record.id, str(export_path), "--force", "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "Todo App MVP" in export_path.read_text()


class TestPrdShowById:
    """Tests for prd show <id> - enhancement to show specific PRD."""

    def test_show_by_id(self, runner, initialized_workspace, sample_prd_file, second_prd_file, temp_repo):
        """Should show specific PRD by ID."""
        # Add two PRDs
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])
        runner.invoke(app, ["prd", "add", str(second_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        all_prds = prd.list_all(ws)
        first_prd = all_prds[1]  # Older one (list is newest first)

        # Show the first PRD by ID (not the latest)
        result = runner.invoke(app, ["prd", "show", first_prd.id, "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "Todo App MVP" in result.stdout

    def test_show_nonexistent_id(self, runner, initialized_workspace, temp_repo):
        """Should show error for nonexistent ID."""
        result = runner.invoke(app, ["prd", "show", "fake-id-123", "-w", str(temp_repo)])

        assert "not found" in result.stdout.lower() or result.exit_code != 0


# ============================================================================
# Tests for PRD VERSIONING CLI commands
# ============================================================================


class TestPrdVersions:
    """Tests for prd versions command."""

    def test_versions_shows_single_version(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should show version 1 for a newly added PRD."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        record = prd.get_latest(ws)

        result = runner.invoke(app, ["prd", "versions", record.id, "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "v1" in result.stdout.lower() or "version 1" in result.stdout.lower()

    def test_versions_shows_multiple_versions(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should show all versions after creating new versions."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        v1 = prd.get_latest(ws)

        # Create more versions directly via core module
        prd.create_new_version(ws, v1.id, "v2 content", "second version")
        prd.create_new_version(ws, v1.id, "v3 content", "third version")

        result = runner.invoke(app, ["prd", "versions", v1.id, "-w", str(temp_repo)])

        assert result.exit_code == 0
        # Should show all versions
        assert "1" in result.stdout
        assert "2" in result.stdout

    def test_versions_nonexistent_prd(self, runner, initialized_workspace, temp_repo):
        """Should show error for nonexistent PRD."""
        result = runner.invoke(app, ["prd", "versions", "fake-id", "-w", str(temp_repo)])

        assert "not found" in result.stdout.lower() or result.exit_code != 0

    def test_versions_shows_change_summaries(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should show change summaries for versions."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        v1 = prd.get_latest(ws)

        prd.create_new_version(ws, v1.id, "updated content", "Added new feature section")

        result = runner.invoke(app, ["prd", "versions", v1.id, "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "Added new feature section" in result.stdout


class TestPrdDiff:
    """Tests for prd diff command."""

    def test_diff_shows_changes(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should show diff between two versions."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        v1 = prd.get_latest(ws)
        v1_content = prd.load_file(sample_prd_file)

        prd.create_new_version(ws, v1.id, v1_content + "\n## Added Section\n", "added section")

        result = runner.invoke(app, ["prd", "diff", v1.id, "1", "2", "-w", str(temp_repo)])

        assert result.exit_code == 0
        assert "Added Section" in result.stdout
        assert "+" in result.stdout  # Addition marker

    def test_diff_invalid_version(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should show error for invalid version numbers."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        v1 = prd.get_latest(ws)

        result = runner.invoke(app, ["prd", "diff", v1.id, "1", "99", "-w", str(temp_repo)])

        assert "not found" in result.stdout.lower() or result.exit_code != 0

    def test_diff_nonexistent_prd(self, runner, initialized_workspace, temp_repo):
        """Should show error for nonexistent PRD."""
        result = runner.invoke(app, ["prd", "diff", "fake-id", "1", "2", "-w", str(temp_repo)])

        assert "not found" in result.stdout.lower() or result.exit_code != 0


class TestPrdUpdate:
    """Tests for prd update command - create new version from CLI."""

    def test_update_creates_new_version(self, runner, initialized_workspace, sample_prd_file, temp_repo):
        """Should create a new version when updating content."""
        runner.invoke(app, ["prd", "add", str(sample_prd_file), "-w", str(temp_repo)])

        ws = workspace.get_workspace(temp_repo)
        v1 = prd.get_latest(ws)

        # Create an updated file
        updated_file = temp_repo / "updated.md"
        updated_file.write_text("# Updated PRD\n\nNew content here.")

        result = runner.invoke(
            app,
            ["prd", "update", v1.id, str(updated_file), "-m", "Updated requirements", "-w", str(temp_repo)]
        )

        assert result.exit_code == 0
        assert "version" in result.stdout.lower()

        # Verify version was created
        versions = prd.get_versions(ws, v1.id)
        assert len(versions) == 2

    def test_update_nonexistent_prd(self, runner, initialized_workspace, temp_repo):
        """Should show error for nonexistent PRD."""
        updated_file = temp_repo / "updated.md"
        updated_file.write_text("content")

        result = runner.invoke(
            app,
            ["prd", "update", "fake-id", str(updated_file), "-m", "changes", "-w", str(temp_repo)]
        )

        assert "not found" in result.stdout.lower() or result.exit_code != 0
