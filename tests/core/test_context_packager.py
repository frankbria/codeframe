"""Tests for TaskContextPackager."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.context_packager import TaskContextPackager, PackagedContext
from codeframe.core.context import TaskContext


@pytest.fixture
def mock_workspace():
    ws = MagicMock()
    ws.repo_path = Path("/tmp/test-repo")
    ws.state_dir = Path("/tmp/test-repo/.codeframe")
    return ws


@pytest.fixture
def mock_task_context():
    ctx = MagicMock(spec=TaskContext)
    ctx.to_prompt_context.return_value = (
        "## Task\n**Title:** Fix the bug\n**Description:** Fix it\n"
    )
    return ctx


class TestPackagedContext:
    """Tests for the PackagedContext dataclass."""

    def test_stores_prompt_and_context(self, mock_task_context):
        pc = PackagedContext(prompt="hello", context=mock_task_context)
        assert pc.prompt == "hello"
        assert pc.context is mock_task_context


class TestTaskContextPackager:
    """Tests for TaskContextPackager."""

    def test_build_returns_packaged_context(self, mock_workspace, mock_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            assert isinstance(result, PackagedContext)
            assert isinstance(result.prompt, str)
            assert result.context is mock_task_context

    def test_build_includes_base_context(self, mock_workspace, mock_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            assert "Fix the bug" in result.prompt

    def test_build_includes_default_gates(self, mock_workspace, mock_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            assert "pytest" in result.prompt
            assert "ruff" in result.prompt
            assert "Verification Gates" in result.prompt

    def test_build_with_custom_gates(self, mock_workspace, mock_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1", gate_names=["pytest", "ruff", "mypy"])

            assert "mypy" in result.prompt
            assert "Must pass" in result.prompt

    def test_build_with_only_custom_gates_omits_defaults(
        self, mock_workspace, mock_task_context
    ):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1", gate_names=["mypy"])

            assert "mypy" in result.prompt
            # Default gates should NOT appear since we overrode
            assert "ruff" not in result.prompt

    def test_build_includes_execution_instructions(
        self, mock_workspace, mock_task_context
    ):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            assert "Execution Instructions" in result.prompt
            assert "Do not modify unrelated files" in result.prompt

    def test_build_calls_loader_with_task_id(self, mock_workspace, mock_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            packager.build("task-42")

            MockLoader.return_value.load.assert_called_once_with("task-42")

    def test_prompt_ordering(self, mock_workspace, mock_task_context):
        """Verify the prompt sections appear in the correct order."""
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            base_pos = result.prompt.index("Fix the bug")
            gates_pos = result.prompt.index("Verification Gates")
            instr_pos = result.prompt.index("Execution Instructions")

            assert base_pos < gates_pos < instr_pos

    def test_empty_gate_list(self, mock_workspace, mock_task_context):
        """An empty gate list should still produce a valid prompt."""
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1", gate_names=[])

            assert "Verification Gates" in result.prompt
            assert isinstance(result.prompt, str)
