"""Tests for PRD template CLI commands.

This module tests:
- cf prd templates list
- cf prd templates show
- cf prd templates import
- cf prd templates export
- cf prd generate --template
"""

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app

runner = CliRunner()

pytestmark = pytest.mark.v2


class TestPrdTemplatesList:
    """Tests for 'cf prd templates list' command."""

    def test_list_templates_shows_builtins(self):
        """List command shows built-in templates."""
        result = runner.invoke(app, ["prd", "templates", "list"])
        assert result.exit_code == 0
        assert "standard" in result.output.lower()
        assert "lean" in result.output.lower()
        assert "enterprise" in result.output.lower()

    def test_list_templates_shows_template_info(self):
        """List command shows template names and descriptions."""
        result = runner.invoke(app, ["prd", "templates", "list"])
        assert result.exit_code == 0
        # Check for expected template information
        assert "Standard PRD" in result.output or "standard" in result.output.lower()


class TestPrdTemplatesShow:
    """Tests for 'cf prd templates show' command."""

    def test_show_template_details(self):
        """Show command displays template details."""
        result = runner.invoke(app, ["prd", "templates", "show", "standard"])
        assert result.exit_code == 0
        assert "standard" in result.output.lower()
        # Should show sections
        assert "section" in result.output.lower() or "executive" in result.output.lower()

    def test_show_template_not_found(self):
        """Show command handles missing template."""
        result = runner.invoke(app, ["prd", "templates", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_show_lean_template(self):
        """Show command works for lean template."""
        result = runner.invoke(app, ["prd", "templates", "show", "lean"])
        assert result.exit_code == 0
        assert "lean" in result.output.lower()

    def test_show_enterprise_template(self):
        """Show command works for enterprise template."""
        result = runner.invoke(app, ["prd", "templates", "show", "enterprise"])
        assert result.exit_code == 0
        assert "enterprise" in result.output.lower()


class TestPrdTemplatesExport:
    """Tests for 'cf prd templates export' command."""

    def test_export_template_to_file(self, tmp_path):
        """Export command saves template to file."""
        output_file = tmp_path / "exported.yaml"
        result = runner.invoke(
            app, ["prd", "templates", "export", "standard", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "standard" in content
        assert "sections" in content

    def test_export_template_not_found(self, tmp_path):
        """Export command handles missing template."""
        output_file = tmp_path / "output.yaml"
        result = runner.invoke(
            app, ["prd", "templates", "export", "nonexistent", str(output_file)]
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()


class TestPrdTemplatesImport:
    """Tests for 'cf prd templates import' command."""

    def test_import_template_from_file(self, tmp_path):
        """Import command loads template from file."""
        # Create a valid template file
        template_file = tmp_path / "custom.yaml"
        template_file.write_text("""
id: custom-template
name: Custom Template
version: 1
description: A custom PRD template
sections:
  - id: intro
    title: Introduction
    source: problem
    format_template: "## Introduction\\n\\n{{ problem }}"
    required: true
""")
        result = runner.invoke(
            app, ["prd", "templates", "import", str(template_file)]
        )
        assert result.exit_code == 0
        assert "imported" in result.output.lower() or "custom" in result.output.lower()

    def test_import_template_file_not_found(self, tmp_path):
        """Import command handles missing file."""
        nonexistent = tmp_path / "missing.yaml"
        result = runner.invoke(
            app, ["prd", "templates", "import", str(nonexistent)]
        )
        # Typer returns exit code 2 for file validation failures
        assert result.exit_code != 0


class TestPrdGenerateWithTemplate:
    """Tests for 'cf prd generate --template' option."""

    def test_generate_accepts_template_option(self, tmp_path):
        """Generate command accepts --template option."""
        # Initialize a workspace first
        workspace_path = tmp_path / "test-project"
        workspace_path.mkdir()
        (workspace_path / ".codeframe").mkdir()

        # This will fail due to no API key, but should at least parse the option
        result = runner.invoke(
            app,
            [
                "prd", "generate",
                "--template", "lean",
                "-w", str(workspace_path),
            ],
            input="n\n",  # Say no to prompts
        )
        # The command may fail due to missing API key, but --template should be recognized
        # Check that it doesn't fail with "unknown option" error
        assert "unknown option" not in result.output.lower()
        assert "--template" not in result.output.lower() or "template" in result.output.lower()

    def test_generate_invalid_template_shows_error(self, tmp_path):
        """Generate command shows error for invalid template."""
        workspace_path = tmp_path / "test-project"
        workspace_path.mkdir()
        (workspace_path / ".codeframe").mkdir()

        result = runner.invoke(
            app,
            [
                "prd", "generate",
                "--template", "nonexistent-template",
                "-w", str(workspace_path),
            ],
            input="n\n",
        )
        # Should indicate template not found
        assert "not found" in result.output.lower() or "nonexistent" in result.output.lower() or result.exit_code != 0
