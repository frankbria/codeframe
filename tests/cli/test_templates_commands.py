"""Tests for templates CLI commands.

TDD tests for the template-related CLI commands:
- cf templates list - List available templates
- cf templates show <id> - Show template details
- cf templates apply <id> - Apply template to create tasks
"""

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.mark.unit
class TestTemplatesListCommand:
    """Test cf templates list command."""

    def test_templates_list_shows_templates(self):
        """Test templates list shows available templates."""
        result = runner.invoke(app, ["templates", "list"])

        assert result.exit_code == 0
        # Should show builtin templates
        assert "api-endpoint" in result.output or "API" in result.output

    def test_templates_list_with_category_filter(self):
        """Test templates list filters by category."""
        result = runner.invoke(app, ["templates", "list", "--category", "backend"])

        assert result.exit_code == 0
        # Should show backend templates
        assert "backend" in result.output.lower() or "api" in result.output.lower()

    def test_templates_list_shows_categories(self):
        """Test templates list shows categories option."""
        result = runner.invoke(app, ["templates", "list", "--categories"])

        assert result.exit_code == 0
        assert "backend" in result.output.lower()
        assert "frontend" in result.output.lower()


@pytest.mark.unit
class TestTemplatesShowCommand:
    """Test cf templates show command."""

    def test_templates_show_displays_template_details(self):
        """Test templates show displays template information."""
        result = runner.invoke(app, ["templates", "show", "api-endpoint"])

        assert result.exit_code == 0
        assert "API" in result.output or "endpoint" in result.output.lower()

    def test_templates_show_displays_tasks(self):
        """Test templates show displays template tasks."""
        result = runner.invoke(app, ["templates", "show", "api-endpoint"])

        assert result.exit_code == 0
        # Should show the tasks in the template
        assert "task" in result.output.lower() or "Define" in result.output

    def test_templates_show_unknown_template_error(self):
        """Test templates show with unknown template shows error."""
        result = runner.invoke(app, ["templates", "show", "nonexistent-template"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()


@pytest.mark.unit
class TestTemplatesApplyCommand:
    """Test cf templates apply command."""

    def test_templates_apply_requires_workspace(self, tmp_path):
        """Test templates apply requires initialized workspace."""
        result = runner.invoke(app, ["templates", "apply", "api-endpoint", "-w", str(tmp_path)])

        # Should fail without workspace
        assert result.exit_code != 0

    def test_templates_apply_creates_tasks(self, tmp_path):
        """Test templates apply creates tasks in workspace."""
        from codeframe.core.workspace import create_or_load_workspace
        from codeframe.core import prd

        # Create workspace
        workspace_path = tmp_path / "test_project"
        workspace_path.mkdir()
        workspace = create_or_load_workspace(workspace_path)

        # Add a PRD using v2 API
        prd_file = workspace_path / "test.md"
        prd_file.write_text("# Test PRD\nA test project.")
        prd.store(workspace, prd.load_file(prd_file), source_path=prd_file)

        result = runner.invoke(
            app,
            ["templates", "apply", "api-endpoint", "-w", str(workspace_path)],
        )

        assert result.exit_code == 0
        assert "created" in result.output.lower() or "task" in result.output.lower()
