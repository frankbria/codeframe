"""CLI integration tests for `cf prd generate` command.

Tests the interactive PRD discovery CLI workflow.
"""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.workspace import create_or_load_workspace


pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    """Create a test workspace directory."""
    create_or_load_workspace(tmp_path)
    return tmp_path


class TestPrdGenerateCommand:
    """Tests for the prd generate CLI command."""

    def test_help_shows_usage(self):
        """Help should display command usage and options."""
        result = runner.invoke(app, ["prd", "generate", "--help"])

        assert result.exit_code == 0
        assert "Generate a PRD through interactive Socratic discovery" in result.output
        assert "--resume" in result.output
        assert "--skip-optional" in result.output

    def test_invalid_workspace_path_shows_error(self):
        """Running with invalid workspace path should show helpful error."""
        result = runner.invoke(
            app,
            ["prd", "generate", "-w", "/nonexistent/path/that/does/not/exist"],
        )

        # Should fail gracefully
        assert result.exit_code == 1
        assert "error" in result.output.lower()

    def test_command_starts_discovery(self, workspace_dir: Path, monkeypatch):
        """Command should start interactive discovery in workspace."""
        monkeypatch.chdir(workspace_dir)

        # Simulate user input - answer questions then quit
        user_input = [
            "A task management app for development teams",  # q1
            "/quit",  # quit
            "y",  # confirm quit
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(user_input) + "\n",
        )

        # Should start discovery
        assert "interactive" in result.output.lower() or "discovery" in result.output.lower()

    def test_existing_prd_prompts_confirmation(self, workspace_dir: Path, monkeypatch):
        """Should ask before overwriting existing PRD."""
        from codeframe.core.workspace import get_workspace
        from codeframe.core import prd

        monkeypatch.chdir(workspace_dir)

        # Add existing PRD
        workspace = get_workspace(workspace_dir)
        prd.store(workspace, "# Existing PRD\n\nSome content", title="Existing PRD")

        # Say no to overwrite
        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="n\n",  # No, don't overwrite
        )

        assert "Cancelled" in result.output or "existing" in result.output.lower()

    def test_help_command_shows_commands(self, workspace_dir: Path, monkeypatch):
        """The /help command should display available commands."""
        monkeypatch.chdir(workspace_dir)

        # Input: answer, /help, then quit
        user_input = [
            "/help",
            "/quit",
            "y",  # confirm quit
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(user_input) + "\n",
        )

        assert "/pause" in result.output
        assert "/skip" in result.output
        assert "/quit" in result.output

    def test_pause_saves_progress(self, workspace_dir: Path, monkeypatch):
        """The /pause command should save progress and create blocker."""
        monkeypatch.chdir(workspace_dir)

        user_input = [
            "A task management app for teams",  # answer q1
            "/pause",
            "Need to check with team",  # pause reason
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(user_input) + "\n",
        )

        assert "paused" in result.output.lower()
        assert "resume" in result.output.lower()


class TestPrdGenerateResume:
    """Tests for resuming paused discovery sessions."""

    def test_resume_with_invalid_blocker(self, workspace_dir: Path, monkeypatch):
        """Resume with non-existent blocker should fail gracefully."""
        monkeypatch.chdir(workspace_dir)

        result = runner.invoke(
            app,
            ["prd", "generate", "--resume", "nonexistent-blocker-id"],
        )

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()


class TestPrdGenerateComplete:
    """Tests for completing discovery and generating PRD."""

    def test_complete_discovery_generates_prd(self, workspace_dir: Path, monkeypatch):
        """Completing all questions should generate PRD."""
        from codeframe.core.workspace import get_workspace
        from codeframe.core import prd

        monkeypatch.chdir(workspace_dir)

        # Provide answers for all 5 required questions
        answers = [
            "A project management tool for agile software teams",  # problem
            "Software developers and project managers",  # users
            "Sprint planning, task boards, burndown charts",  # features
            "Must integrate with GitHub, support SSO",  # constraints
            "React frontend with Python FastAPI backend",  # tech_stack
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(answers) + "\n",
        )

        # Should show success
        assert "generated" in result.output.lower() or "prd" in result.output.lower()

        # Verify PRD was stored
        workspace = get_workspace(workspace_dir)
        prd_record = prd.get_latest(workspace)
        assert prd_record is not None
        assert "Overview" in prd_record.content

    def test_generated_prd_shows_preview(self, workspace_dir: Path, monkeypatch):
        """After generation, should show PRD preview."""
        monkeypatch.chdir(workspace_dir)

        answers = [
            "A CI/CD pipeline visualization tool for DevOps",
            "DevOps engineers and platform teams",
            "Pipeline visualization, alerts, metrics dashboard",
            "Self-hosted, support Kubernetes",
            "Go backend with React frontend",
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(answers) + "\n",
        )

        # Should show preview and next steps
        assert "preview" in result.output.lower() or "overview" in result.output.lower()
        assert "tasks generate" in result.output.lower()


class TestPrdGenerateValidation:
    """Tests for input validation during discovery."""

    def test_short_answer_rejected(self, workspace_dir: Path, monkeypatch):
        """Short answers should be rejected with helpful message."""
        monkeypatch.chdir(workspace_dir)

        user_input = [
            "hi",  # too short
            "A comprehensive task management system for teams",  # valid
            "/quit",
            "y",
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(user_input) + "\n",
        )

        assert "short" in result.output.lower() or "minimum" in result.output.lower()

    def test_invalid_pattern_rejected(self, workspace_dir: Path, monkeypatch):
        """Invalid answers like 'n/a' should be rejected."""
        monkeypatch.chdir(workspace_dir)

        user_input = [
            "none",  # invalid pattern
            "A real answer about the problem we're solving",  # valid
            "/quit",
            "y",
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(user_input) + "\n",
        )

        assert "substantive" in result.output.lower() or "invalid" in result.output.lower()
