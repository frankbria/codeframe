"""Tests for TaskContextPackager."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.context_packager import TaskContextPackager, PackagedContext
from codeframe.core.context import TaskContext, FileInfo
from codeframe.core.adapters.agent_adapter import AgentContext


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
    ctx.relevant_files = []
    return ctx


@pytest.fixture
def rich_task_context():
    """TaskContext with realistic data for testing AgentContext assembly."""
    ctx = MagicMock(spec=TaskContext)
    ctx.task = MagicMock()
    ctx.task.title = "Implement auth"
    ctx.task.description = "Add JWT authentication"
    ctx.task.id = "task-99"
    ctx.prd = MagicMock()
    ctx.prd.content = "# Auth PRD\nTokens should last 24h"
    ctx.tech_stack = "Python with FastAPI"
    ctx.preferences = MagicMock()
    ctx.preferences.has_preferences.return_value = True
    ctx.preferences.to_prompt_section.return_value = "## Prefs\n- Use ruff"
    ctx.preferences.commands = {"test": "pytest", "lint": "ruff check ."}
    ctx.preferences.never_do = ["Never modify .env files"]
    ctx.answered_blockers = [
        MagicMock(question="Which DB?", answer="PostgreSQL")
    ]
    ctx.relevant_files = [
        FileInfo(path="src/auth.py", size_bytes=500, extension=".py", relevance_score=0.9),
        FileInfo(path="tests/test_auth.py", size_bytes=300, extension=".py", relevance_score=0.8),
    ]
    ctx.loaded_files = [
        MagicMock(path="src/auth.py", content="def login(): pass"),
    ]
    ctx.to_prompt_context.return_value = (
        "## Task\n**Title:** Implement auth\n**Description:** Add JWT\n"
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


class TestLoadContext:
    """Tests for load_context() — returns raw TaskContext for internal agents."""

    def test_returns_task_context(self, mock_workspace, mock_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.load_context("task-42")

            assert ctx is mock_task_context

    def test_delegates_to_loader(self, mock_workspace, mock_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            packager.load_context("task-42")

            MockLoader.return_value.load.assert_called_once_with("task-42")

    def test_returns_same_context_as_build(self, mock_workspace, mock_task_context):
        """load_context() and build() should use the same underlying loader."""
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            raw_ctx = packager.load_context("task-42")
            packaged = packager.build("task-42")

            assert raw_ctx is packaged.context


class TestBuildAgentContext:
    """Tests for build_agent_context() — produces AgentContext from TaskContext."""

    def test_returns_agent_context(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context("task-99")

            assert isinstance(ctx, AgentContext)
            assert ctx.task_id == "task-99"
            assert ctx.task_title == "Implement auth"
            assert ctx.task_description == "Add JWT authentication"

    def test_populates_prd_content(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context("task-99")

            assert "Auth PRD" in ctx.prd_content

    def test_populates_tech_stack(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context("task-99")

            assert ctx.tech_stack == "Python with FastAPI"

    def test_populates_relevant_files(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context("task-99")

            assert "src/auth.py" in ctx.relevant_files
            assert "tests/test_auth.py" in ctx.relevant_files

    def test_populates_file_contents(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context("task-99")

            assert "src/auth.py" in ctx.file_contents
            assert ctx.file_contents["src/auth.py"] == "def login(): pass"

    def test_populates_blocker_history(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context("task-99")

            assert len(ctx.blocker_history) == 1
            assert "Which DB?" in ctx.blocker_history[0]

    def test_populates_verification_gates(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context("task-99")

            assert "pytest" in ctx.verification_gates
            assert "ruff" in ctx.verification_gates

    def test_retry_context(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context(
                "task-99",
                attempt=2,
                previous_errors=["ImportError: jwt not found"],
            )

            assert ctx.attempt == 2
            assert "ImportError: jwt not found" in ctx.previous_errors

    def test_custom_gate_names(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context(
                "task-99", gate_names=["mypy", "eslint"]
            )

            assert ctx.verification_gates == ["mypy", "eslint"]

    def test_empty_gate_names_override(self, mock_workspace, rich_task_context):
        """Explicit empty list should produce empty gates, not defaults."""
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context("task-99", gate_names=[])

            assert ctx.verification_gates == []

    def test_defaults_for_optional_fields(self, mock_workspace):
        """When TaskContext has no PRD or tech stack, those fields are None."""
        bare_ctx = MagicMock(spec=TaskContext)
        bare_ctx.task = MagicMock()
        bare_ctx.task.title = "Simple task"
        bare_ctx.task.description = "Do something"
        bare_ctx.task.id = "task-1"
        bare_ctx.prd = None
        bare_ctx.tech_stack = None
        bare_ctx.preferences = MagicMock()
        bare_ctx.preferences.has_preferences.return_value = False
        bare_ctx.preferences.to_prompt_section.return_value = ""
        bare_ctx.answered_blockers = []
        bare_ctx.relevant_files = []
        bare_ctx.loaded_files = []
        bare_ctx.to_prompt_context.return_value = "## Task\n**Title:** Simple task\n"

        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = bare_ctx

            packager = TaskContextPackager(mock_workspace)
            ctx = packager.build_agent_context("task-1")

            assert ctx.prd_content is None
            assert ctx.tech_stack is None
            assert ctx.project_preferences is None
            assert ctx.relevant_files == []


class TestBuildWithRetryContext:
    """Tests for retry support in build()."""

    def test_build_with_retry_includes_error_section(
        self, mock_workspace, mock_task_context
    ):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build(
                "task-1",
                attempt=2,
                previous_errors=["SyntaxError: unexpected indent"],
            )

            assert "Previous Attempt Errors" in result.prompt
            assert "SyntaxError: unexpected indent" in result.prompt
            assert "Attempt 2" in result.prompt

    def test_multiline_errors_collapsed(self, mock_workspace, mock_task_context):
        """Multiline errors should be collapsed to single lines in the prompt."""
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build(
                "task-1",
                attempt=1,
                previous_errors=["FAILED tests/test_foo.py\n  assert 1 == 2\nAssertionError"],
            )

            assert "Previous Attempt Errors" in result.prompt
            # Multiline error should be on a single markdown list line
            assert "\n  assert" not in result.prompt

    def test_build_first_attempt_no_retry_section(
        self, mock_workspace, mock_task_context
    ):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            assert "Previous Attempt Errors" not in result.prompt


class TestToFileList:
    """Tests for to_file_list() — extracts relevant file paths."""

    def test_returns_relevant_file_paths(self, mock_workspace, rich_task_context):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = rich_task_context

            packager = TaskContextPackager(mock_workspace)
            packaged = packager.build("task-99")
            files = packager.to_file_list(packaged)

            assert files == ["src/auth.py", "tests/test_auth.py"]

    def test_returns_empty_for_no_relevant_files(self, mock_workspace):
        bare_ctx = MagicMock(spec=TaskContext)
        bare_ctx.relevant_files = []
        bare_ctx.to_prompt_context.return_value = "## Task\n"

        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = bare_ctx

            packager = TaskContextPackager(mock_workspace)
            packaged = packager.build("task-1")
            files = packager.to_file_list(packaged)

            assert files == []


class TestToTaskFile:
    """Tests for to_task_file() — writes prompt to file."""

    def test_writes_prompt_to_file(self, mock_workspace, mock_task_context, tmp_path):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            packaged = packager.build("task-1")

            task_file = tmp_path / "task.md"
            result_path = packager.to_task_file(packaged, task_file)

            assert result_path == task_file
            assert task_file.exists()
            content = task_file.read_text()
            assert "Fix the bug" in content

    def test_creates_parent_dirs(self, mock_workspace, mock_task_context, tmp_path):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            packaged = packager.build("task-1")

            task_file = tmp_path / "nested" / "deep" / "task.md"
            result_path = packager.to_task_file(packaged, task_file)

            assert result_path == task_file
            assert task_file.exists()

    def test_content_matches_prompt(self, mock_workspace, mock_task_context, tmp_path):
        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_task_context

            packager = TaskContextPackager(mock_workspace)
            packaged = packager.build("task-1")

            task_file = tmp_path / "task.md"
            packager.to_task_file(packaged, task_file)

            assert task_file.read_text(encoding="utf-8") == packaged.prompt


class TestLineageContext:
    """Tests for lineage inclusion in build() prompt."""

    def test_context_packager_includes_lineage(self, mock_workspace):
        """Task with lineage should have 'Task Lineage' section in prompt."""
        ctx = MagicMock(spec=TaskContext)
        ctx.task = MagicMock()
        ctx.task.lineage = ["Build app", "Authentication module"]
        ctx.to_prompt_context.return_value = (
            "## Task\n**Title:** Implement JWT\n**Description:** Add tokens\n"
        )
        ctx.relevant_files = []

        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = ctx

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            assert "Task Lineage" in result.prompt
            assert "Build app" in result.prompt
            assert "Authentication module" in result.prompt

    def test_context_packager_no_lineage(self, mock_workspace):
        """Task without lineage should not have 'Task Lineage' section."""
        ctx = MagicMock(spec=TaskContext)
        ctx.task = MagicMock()
        ctx.task.lineage = []
        ctx.to_prompt_context.return_value = (
            "## Task\n**Title:** Simple task\n**Description:** Do it\n"
        )
        ctx.relevant_files = []

        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = ctx

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            assert "Task Lineage" not in result.prompt

    def test_context_packager_lineage_missing_attribute(self, mock_workspace):
        """Task without lineage attribute should not have 'Task Lineage' section."""
        ctx = MagicMock(spec=TaskContext)
        ctx.task = MagicMock(spec=["title", "description", "id"])
        # No lineage attribute on task
        ctx.to_prompt_context.return_value = (
            "## Task\n**Title:** Old task\n**Description:** Legacy\n"
        )
        ctx.relevant_files = []

        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = ctx

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            assert "Task Lineage" not in result.prompt

    def test_lineage_appears_before_gates(self, mock_workspace):
        """Lineage section should appear before Verification Gates."""
        ctx = MagicMock(spec=TaskContext)
        ctx.task = MagicMock()
        ctx.task.lineage = ["Parent task"]
        ctx.to_prompt_context.return_value = (
            "## Task\n**Title:** Child task\n"
        )
        ctx.relevant_files = []

        with patch("codeframe.core.context_packager.ContextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = ctx

            packager = TaskContextPackager(mock_workspace)
            result = packager.build("task-1")

            lineage_pos = result.prompt.index("Task Lineage")
            gates_pos = result.prompt.index("Verification Gates")
            assert lineage_pos < gates_pos
