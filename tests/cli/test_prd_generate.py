"""CLI integration tests for `cf prd generate` command.

Tests the AI-driven interactive PRD discovery CLI workflow.
Uses mocked LLM responses to avoid actual API calls.
"""

import json
import os
import re
import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from codeframe.cli.app import app
from codeframe.core.workspace import create_or_load_workspace


pytestmark = pytest.mark.v2

runner = CliRunner()


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_pattern.sub('', text)


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    """Create a test workspace directory."""
    create_or_load_workspace(tmp_path)
    return tmp_path


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider for CLI tests."""
    mock = MagicMock()
    call_count = [0]

    def complete_side_effect(messages, **kwargs):
        content = messages[0]["content"] if messages else ""
        response = MagicMock()

        if "opening question" in content.lower():
            response.content = "What problem are you trying to solve?"
        elif "assess the current coverage" in content.lower():
            call_count[0] += 1
            if call_count[0] >= 3:
                response.content = json.dumps({
                    "scores": {"problem": 80, "users": 75, "features": 70, "constraints": 65, "tech_stack": 60},
                    "average": 70,
                    "ready_for_prd": True,
                    "weakest_category": "tech_stack",
                    "reasoning": "Ready"
                })
            else:
                response.content = json.dumps({
                    "scores": {"problem": 50, "users": 40, "features": 30, "constraints": 20, "tech_stack": 10},
                    "average": 30,
                    "ready_for_prd": False,
                    "weakest_category": "tech_stack",
                    "reasoning": "Need more"
                })
        elif "evaluate whether this answer" in content.lower():
            response.content = json.dumps({"adequate": True, "reason": "Good"})
        elif "generate the next discovery question" in content.lower():
            if call_count[0] >= 3:
                response.content = "DISCOVERY_COMPLETE"
            else:
                response.content = "Tell me about the users?"
        elif "generate a product requirements document" in content.lower():
            response.content = """# Test Project

## Overview
A test project.

## Target Users
Testers.

## Core Features
1. Testing

## Technical Requirements
Python

## Constraints & Considerations
None.

## Success Criteria
Tests pass.

## Out of Scope (MVP)
Nothing."""
        else:
            response.content = "Default response"
        return response

    mock.complete.side_effect = complete_side_effect
    return mock


class TestPrdGenerateCommand:
    """Tests for the prd generate CLI command."""

    def test_help_shows_usage(self):
        """Help should display command usage and options."""
        result = runner.invoke(app, ["prd", "generate", "--help"])
        output = strip_ansi(result.output)

        assert result.exit_code == 0
        assert "AI-driven Socratic discovery" in output
        assert "--resume" in output
        assert "ANTHROPIC_API_KEY" in output

    def test_no_api_key_shows_error(self, workspace_dir: Path, monkeypatch):
        """Running without API key should show helpful error."""
        monkeypatch.chdir(workspace_dir)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=True):
            result = runner.invoke(
                app,
                ["prd", "generate", "-w", str(workspace_dir)],
            )

        assert result.exit_code == 1
        assert "ANTHROPIC_API_KEY" in result.output

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_command_starts_discovery(
        self, mock_provider_class, workspace_dir: Path, monkeypatch, mock_llm_provider
    ):
        """Command should start interactive discovery in workspace."""
        mock_provider_class.return_value = mock_llm_provider
        monkeypatch.chdir(workspace_dir)

        # Simulate user input - answer then quit
        user_input = [
            "A task management app for development teams",
            "/quit",
            "y",  # confirm quit
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(user_input) + "\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        # Should start discovery
        assert "AI-driven" in result.output or "discovery" in result.output.lower()

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_existing_prd_prompts_confirmation(
        self, mock_provider_class, workspace_dir: Path, monkeypatch, mock_llm_provider
    ):
        """Should ask before overwriting existing PRD."""
        mock_provider_class.return_value = mock_llm_provider

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
            input="n\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        assert "Cancelled" in result.output or "existing" in result.output.lower()

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_help_command_shows_commands(
        self, mock_provider_class, workspace_dir: Path, monkeypatch, mock_llm_provider
    ):
        """The /help command should display available commands."""
        mock_provider_class.return_value = mock_llm_provider
        monkeypatch.chdir(workspace_dir)

        user_input = [
            "/help",
            "/quit",
            "y",
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(user_input) + "\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        assert "/pause" in result.output
        assert "/quit" in result.output

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_pause_saves_progress(
        self, mock_provider_class, workspace_dir: Path, monkeypatch, mock_llm_provider
    ):
        """The /pause command should save progress and create blocker."""
        mock_provider_class.return_value = mock_llm_provider
        monkeypatch.chdir(workspace_dir)

        user_input = [
            "A task management app for teams",
            "/pause",
            "Need to check with team",
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(user_input) + "\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        assert "paused" in result.output.lower()
        assert "resume" in result.output.lower()


class TestPrdGenerateResume:
    """Tests for resuming paused discovery sessions."""

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_resume_with_invalid_blocker(
        self, mock_provider_class, workspace_dir: Path, monkeypatch, mock_llm_provider
    ):
        """Resume with non-existent blocker should fail gracefully."""
        mock_provider_class.return_value = mock_llm_provider
        monkeypatch.chdir(workspace_dir)

        result = runner.invoke(
            app,
            ["prd", "generate", "--resume", "nonexistent-blocker-id"],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()


class TestPrdGenerateComplete:
    """Tests for completing discovery and generating PRD."""

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_complete_discovery_generates_prd(
        self, mock_provider_class, workspace_dir: Path, monkeypatch
    ):
        """Completing discovery should generate PRD."""
        mock = MagicMock()
        call_count = [0]

        def complete_side_effect(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            response = MagicMock()

            if "opening question" in content.lower():
                response.content = "What problem are you solving?"
            elif "assess the current coverage" in content.lower():
                call_count[0] += 1
                response.content = json.dumps({
                    "scores": {"problem": 80, "users": 75, "features": 70, "constraints": 65, "tech_stack": 60},
                    "average": 70,
                    "ready_for_prd": True,
                    "weakest_category": "tech_stack",
                    "reasoning": "Ready"
                })
            elif "evaluate whether this answer" in content.lower():
                response.content = json.dumps({"adequate": True, "reason": "Good"})
            elif "generate the next discovery question" in content.lower():
                response.content = "DISCOVERY_COMPLETE"
            elif "generate a product requirements document" in content.lower():
                response.content = """# Task Manager

## Overview
A project management tool.

## Target Users
Developers.

## Core Features
1. Tasks

## Technical Requirements
Python

## Constraints & Considerations
None

## Success Criteria
Works

## Out of Scope (MVP)
Mobile"""
            else:
                response.content = "Default"
            return response

        mock.complete.side_effect = complete_side_effect
        mock_provider_class.return_value = mock

        from codeframe.core.workspace import get_workspace
        from codeframe.core import prd

        monkeypatch.chdir(workspace_dir)

        # Single answer triggers completion
        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="A project management tool for agile teams\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        # Should show success
        assert "generated" in result.output.lower() or "prd" in result.output.lower()

        # Verify PRD was stored
        workspace = get_workspace(workspace_dir)
        prd_record = prd.get_latest(workspace)
        assert prd_record is not None

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_generated_prd_shows_preview(
        self, mock_provider_class, workspace_dir: Path, monkeypatch
    ):
        """After generation, should show PRD preview."""
        mock = MagicMock()

        def complete_side_effect(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            response = MagicMock()

            if "opening question" in content.lower():
                response.content = "What problem?"
            elif "assess the current coverage" in content.lower():
                response.content = json.dumps({
                    "scores": {"problem": 80, "users": 75, "features": 70, "constraints": 65, "tech_stack": 60},
                    "average": 70,
                    "ready_for_prd": True,
                    "weakest_category": "tech_stack",
                    "reasoning": "Ready"
                })
            elif "evaluate whether this answer" in content.lower():
                response.content = json.dumps({"adequate": True, "reason": "Good"})
            elif "generate the next discovery question" in content.lower():
                response.content = "DISCOVERY_COMPLETE"
            elif "generate a product requirements document" in content.lower():
                response.content = """# CI/CD Tool

## Overview
Pipeline visualization for DevOps.

## Target Users
DevOps engineers.

## Core Features
1. Pipeline view

## Technical Requirements
Go, React

## Constraints & Considerations
Kubernetes

## Success Criteria
Deploys work

## Out of Scope (MVP)
Rollback"""
            else:
                response.content = "Default"
            return response

        mock.complete.side_effect = complete_side_effect
        mock_provider_class.return_value = mock

        monkeypatch.chdir(workspace_dir)

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="A CI/CD pipeline visualization tool\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        # Should show preview and next steps
        assert "preview" in result.output.lower() or "overview" in result.output.lower()
        assert "tasks generate" in result.output.lower()


class TestPrdGenerateValidation:
    """Tests for AI validation during discovery."""

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_ai_rejects_vague_answer(
        self, mock_provider_class, workspace_dir: Path, monkeypatch
    ):
        """AI should reject vague answers with feedback."""
        mock = MagicMock()

        def complete_side_effect(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            response = MagicMock()

            if "opening question" in content.lower():
                response.content = "What problem are you solving?"
            elif "evaluate whether this answer" in content.lower():
                # First answer is vague, second is good
                if "stuff" in content.lower():
                    response.content = json.dumps({
                        "adequate": False,
                        "reason": "Answer is too vague to be useful",
                        "follow_up": "Can you be more specific about the problem?"
                    })
                else:
                    response.content = json.dumps({"adequate": True, "reason": "Good"})
            elif "assess the current coverage" in content.lower():
                response.content = json.dumps({
                    "scores": {"problem": 80, "users": 75, "features": 70, "constraints": 65, "tech_stack": 60},
                    "average": 70,
                    "ready_for_prd": True,
                    "weakest_category": "tech_stack",
                    "reasoning": "Ready"
                })
            elif "generate the next discovery question" in content.lower():
                response.content = "DISCOVERY_COMPLETE"
            elif "generate a product requirements document" in content.lower():
                response.content = "# Project\n\n## Overview\nTest"
            else:
                response.content = "Default"
            return response

        mock.complete.side_effect = complete_side_effect
        mock_provider_class.return_value = mock

        monkeypatch.chdir(workspace_dir)

        user_input = [
            "stuff",  # vague - should be rejected
            "A comprehensive task management system for development teams",  # better
        ]

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input="\n".join(user_input) + "\n",
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        # Should show feedback about vague answer
        assert "vague" in result.output.lower() or "specific" in result.output.lower()
