"""Tests for CLI tasks tree and recursive generate commands.

TDD approach: Write tests first, then implement.
"""

import pytest
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()


class TestTasksGenerateRecursiveFlag:
    """Tests for --recursive flag on 'cf tasks generate'."""

    def test_tasks_generate_recursive_flag_exists(self, tmp_path):
        """Verify --recursive flag is accepted without error."""
        # The flag should be parsed even if the command fails for other reasons
        # (e.g., no workspace). We just need to confirm the flag doesn't cause
        # a "no such option" error.
        result = runner.invoke(app, ["tasks", "generate", "--recursive", "-w", str(tmp_path)])
        # Should NOT fail with "No such option: --recursive"
        assert "No such option" not in result.output

    def test_tasks_generate_max_depth_flag_exists(self, tmp_path):
        """Verify --max-depth flag is accepted."""
        result = runner.invoke(app, ["tasks", "generate", "--max-depth", "2", "-w", str(tmp_path)])
        assert "No such option" not in result.output

    def test_tasks_generate_recursive_calls_task_tree(self, tmp_path):
        """When --recursive is passed, should call generate_task_tree."""
        # Set up workspace
        state_dir = tmp_path / ".codeframe"
        state_dir.mkdir()

        mock_workspace = MagicMock()
        mock_workspace.repo_path = tmp_path
        mock_workspace.state_dir = state_dir

        mock_prd = MagicMock()
        mock_prd.id = "prd-1"
        mock_prd.title = "Test PRD"
        mock_prd.content = "Build a calculator"

        mock_tree = {
            "title": "Build a calculator",
            "description": "Build a calculator",
            "is_leaf": False,
            "children": [],
            "lineage": [],
        }

        mock_task = MagicMock()
        mock_task.title = "Build a calculator"
        mock_task.description = "Build a calculator"

        with (
            patch("codeframe.core.workspace.get_workspace", return_value=mock_workspace),
            patch("codeframe.core.prd.get_latest", return_value=mock_prd),
            patch("codeframe.cli.validators.require_anthropic_api_key"),
            patch("codeframe.adapters.llm.get_provider") as mock_get_provider,
            patch("codeframe.core.task_tree.generate_task_tree", return_value=mock_tree) as mock_gen_tree,
            patch("codeframe.core.task_tree.flatten_task_tree", return_value=[mock_task]) as mock_flatten,
            patch("codeframe.core.events.emit_for_workspace"),
        ):
            result = runner.invoke(
                app,
                ["tasks", "generate", "--recursive", "-w", str(tmp_path)],
            )

            mock_gen_tree.assert_called_once()
            mock_flatten.assert_called_once()

    def test_tasks_generate_without_recursive_uses_existing_behavior(self, tmp_path):
        """Without --recursive, should use the existing generate_from_prd path."""
        state_dir = tmp_path / ".codeframe"
        state_dir.mkdir()

        mock_workspace = MagicMock()
        mock_workspace.repo_path = tmp_path
        mock_workspace.state_dir = state_dir

        mock_prd = MagicMock()
        mock_prd.id = "prd-1"
        mock_prd.title = "Test PRD"
        mock_prd.content = "Build something"

        mock_task = MagicMock()
        mock_task.title = "Task 1"
        mock_task.description = "Do thing"

        with (
            patch("codeframe.core.workspace.get_workspace", return_value=mock_workspace),
            patch("codeframe.core.prd.get_latest", return_value=mock_prd),
            patch("codeframe.cli.validators.require_anthropic_api_key"),
            patch("codeframe.core.tasks.generate_from_prd", return_value=[mock_task]) as mock_gen,
            patch("codeframe.core.events.emit_for_workspace"),
        ):
            result = runner.invoke(
                app,
                ["tasks", "generate", "-w", str(tmp_path)],
            )

            mock_gen.assert_called_once()


class TestTasksTreeCommand:
    """Tests for 'cf tasks tree' command."""

    def test_tasks_tree_no_workspace(self, tmp_path):
        """Shows error when no workspace exists."""
        result = runner.invoke(app, ["tasks", "tree", "-w", str(tmp_path)])
        assert result.exit_code != 0

    def test_tasks_tree_empty(self, tmp_path):
        """Shows 'No tasks found' when workspace has no tasks."""
        mock_workspace = MagicMock()
        mock_workspace.repo_path = tmp_path

        with (
            patch("codeframe.core.workspace.get_workspace", return_value=mock_workspace),
            patch("codeframe.core.task_tree.display_task_tree", return_value=""),
        ):
            result = runner.invoke(app, ["tasks", "tree", "-w", str(tmp_path)])
            assert "No tasks found" in result.output

    def test_tasks_tree_with_data(self, tmp_path):
        """Shows tree output when tasks exist."""
        mock_workspace = MagicMock()
        mock_workspace.repo_path = tmp_path

        tree_output = (
            "1. Build calculator [composite] \u25cb\n"
            "    \u2514\u2500\u2500 1.1. Add numbers [atomic] \u25cb\n"
            "    \u2514\u2500\u2500 1.2. Subtract numbers [atomic] \u25cb"
        )

        with (
            patch("codeframe.core.workspace.get_workspace", return_value=mock_workspace),
            patch("codeframe.core.task_tree.display_task_tree", return_value=tree_output),
        ):
            result = runner.invoke(app, ["tasks", "tree", "-w", str(tmp_path)])
            assert "Build calculator" in result.output
            assert "Add numbers" in result.output
            assert "Subtract numbers" in result.output
