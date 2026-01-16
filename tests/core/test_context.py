"""Tests for task context loader."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from codeframe.core.context import (
    ContextLoader,
    TaskContext,
    FileInfo,
    FileContent,
    DEFAULT_IGNORE_PATTERNS,
    CODE_EXTENSIONS,
    CHARS_PER_TOKEN,
)
from codeframe.core.tasks import Task, TaskStatus
from codeframe.core.prd import PrdRecord
from codeframe.core.blockers import Blocker, BlockerStatus
from codeframe.core.config import EnvironmentConfig
from datetime import datetime, timezone


def _utc_now():
    return datetime.now(timezone.utc)


class TestFileInfo:
    """Tests for FileInfo dataclass."""

    def test_default_relevance_score(self):
        """Default relevance score is 0."""
        info = FileInfo(path="test.py", size_bytes=100, extension=".py")
        assert info.relevance_score == 0.0

    def test_custom_relevance_score(self):
        """Can set custom relevance score."""
        info = FileInfo(
            path="test.py", size_bytes=100, extension=".py", relevance_score=0.8
        )
        assert info.relevance_score == 0.8


class TestTaskContext:
    """Tests for TaskContext dataclass."""

    @pytest.fixture
    def sample_task(self):
        return Task(
            id="task-1",
            workspace_id="ws-1",
            prd_id="prd-1",
            title="Implement login",
            description="Add user authentication",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )

    @pytest.fixture
    def sample_prd(self):
        return PrdRecord(
            id="prd-1",
            workspace_id="ws-1",
            title="Auth System",
            content="# Requirements\n- Login form\n- Session management",
            metadata={},
            created_at=_utc_now(),
        )

    def test_has_prd_false(self, sample_task):
        """has_prd is False when no PRD."""
        ctx = TaskContext(task=sample_task)
        assert not ctx.has_prd

    def test_has_prd_true(self, sample_task, sample_prd):
        """has_prd is True when PRD loaded."""
        ctx = TaskContext(task=sample_task, prd=sample_prd)
        assert ctx.has_prd

    def test_has_blockers_false(self, sample_task):
        """has_blockers is False when empty."""
        ctx = TaskContext(task=sample_task)
        assert not ctx.has_blockers

    def test_has_blockers_true(self, sample_task):
        """has_blockers is True when blockers present."""
        blocker = Blocker(
            id="b-1",
            workspace_id="ws-1",
            task_id="task-1",
            question="What auth provider?",
            answer=None,
            status=BlockerStatus.OPEN,
            created_at=_utc_now(),
            answered_at=None,
        )
        ctx = TaskContext(task=sample_task, blockers=[blocker])
        assert ctx.has_blockers

    def test_has_environment_config_false(self, sample_task):
        """has_environment_config returns False by default."""
        ctx = TaskContext(task=sample_task)
        assert ctx.has_environment_config is False

    def test_has_environment_config_true(self, sample_task):
        """has_environment_config returns True when config exists."""
        config = EnvironmentConfig(package_manager="uv", test_framework="pytest")
        ctx = TaskContext(task=sample_task, environment_config=config)
        assert ctx.has_environment_config is True

    def test_open_blockers_filter(self, sample_task):
        """open_blockers returns only OPEN blockers."""
        blockers = [
            Blocker(
                id="b-1",
                workspace_id="ws-1",
                task_id="task-1",
                question="Q1",
                answer=None,
                status=BlockerStatus.OPEN,
                created_at=_utc_now(),
                answered_at=None,
            ),
            Blocker(
                id="b-2",
                workspace_id="ws-1",
                task_id="task-1",
                question="Q2",
                answer="A2",
                status=BlockerStatus.ANSWERED,
                created_at=_utc_now(),
                answered_at=_utc_now(),
            ),
        ]
        ctx = TaskContext(task=sample_task, blockers=blockers)
        assert len(ctx.open_blockers) == 1
        assert ctx.open_blockers[0].id == "b-1"

    def test_answered_blockers_filter(self, sample_task):
        """answered_blockers returns only ANSWERED blockers."""
        blockers = [
            Blocker(
                id="b-1",
                workspace_id="ws-1",
                task_id="task-1",
                question="Q1",
                answer=None,
                status=BlockerStatus.OPEN,
                created_at=_utc_now(),
                answered_at=None,
            ),
            Blocker(
                id="b-2",
                workspace_id="ws-1",
                task_id="task-1",
                question="Q2",
                answer="A2",
                status=BlockerStatus.ANSWERED,
                created_at=_utc_now(),
                answered_at=_utc_now(),
            ),
        ]
        ctx = TaskContext(task=sample_task, blockers=blockers)
        assert len(ctx.answered_blockers) == 1
        assert ctx.answered_blockers[0].id == "b-2"

    def test_tokens_remaining(self, sample_task):
        """tokens_remaining calculates correctly."""
        ctx = TaskContext(task=sample_task, max_tokens=10000, total_tokens=3000)
        assert ctx.tokens_remaining() == 7000

    def test_tokens_remaining_at_limit(self, sample_task):
        """tokens_remaining returns 0 at limit."""
        ctx = TaskContext(task=sample_task, max_tokens=5000, total_tokens=5000)
        assert ctx.tokens_remaining() == 0

    def test_tokens_remaining_over_limit(self, sample_task):
        """tokens_remaining returns 0 if over limit."""
        ctx = TaskContext(task=sample_task, max_tokens=5000, total_tokens=6000)
        assert ctx.tokens_remaining() == 0

    def test_to_prompt_context_basic(self, sample_task):
        """to_prompt_context generates formatted output."""
        ctx = TaskContext(task=sample_task)
        output = ctx.to_prompt_context()
        assert "## Task" in output
        assert "Implement login" in output
        assert "IN_PROGRESS" in output

    def test_to_prompt_context_with_prd(self, sample_task, sample_prd):
        """to_prompt_context includes PRD when present."""
        ctx = TaskContext(task=sample_task, prd=sample_prd)
        output = ctx.to_prompt_context()
        assert "## Requirements (PRD)" in output
        assert "Auth System" in output

    def test_to_prompt_context_with_environment_config(self, sample_task):
        """to_prompt_context includes environment config when present."""
        config = EnvironmentConfig(
            package_manager="uv",
            test_framework="pytest",
            lint_tools=["ruff", "mypy"],
            python_version="3.11",
        )
        ctx = TaskContext(task=sample_task, environment_config=config)
        output = ctx.to_prompt_context()
        assert "## Project Environment" in output
        assert "Package Manager:" in output
        assert "uv" in output
        assert "Test Framework:" in output
        assert "pytest" in output
        assert "Lint Tools:" in output
        assert "ruff" in output
        assert "Python Version:" in output
        assert "3.11" in output


class TestContextLoaderKeywords:
    """Tests for keyword extraction logic."""

    def test_extract_keywords_basic(self, tmp_path):
        """Extracts meaningful keywords."""
        # Create minimal mock workspace
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        loader = ContextLoader(workspace)
        keywords = loader._extract_keywords("Implement user authentication system")

        assert "implement" in keywords
        assert "user" in keywords
        assert "authentication" in keywords
        assert "system" in keywords

    def test_extract_keywords_filters_stopwords(self, tmp_path):
        """Filters common stopwords."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        loader = ContextLoader(workspace)
        keywords = loader._extract_keywords("the user is in the system")

        assert "the" not in keywords
        assert "is" not in keywords
        assert "in" not in keywords
        assert "user" in keywords
        assert "system" in keywords

    def test_extract_keywords_handles_markdown(self, tmp_path):
        """Strips markdown formatting."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        loader = ContextLoader(workspace)
        keywords = loader._extract_keywords("# Header\n- **bold** item\n`code`")

        assert "#" not in keywords
        assert "**" not in keywords
        assert "header" in keywords
        assert "bold" in keywords


class TestContextLoaderRelevance:
    """Tests for file relevance scoring."""

    def test_relevance_path_keyword_match(self, tmp_path):
        """Files with keywords in path score higher."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        loader = ContextLoader(workspace)

        file_with_match = FileInfo(path="auth/login.py", size_bytes=1000, extension=".py")
        file_without_match = FileInfo(path="utils/helpers.py", size_bytes=1000, extension=".py")

        keywords = {"auth", "login", "user"}

        score_with = loader._calculate_relevance(file_with_match, keywords)
        score_without = loader._calculate_relevance(file_without_match, keywords)

        assert score_with > score_without

    def test_relevance_python_boost(self, tmp_path):
        """Python files get a small boost."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        loader = ContextLoader(workspace)

        py_file = FileInfo(path="module.py", size_bytes=1000, extension=".py")
        txt_file = FileInfo(path="module.txt", size_bytes=1000, extension=".txt")

        score_py = loader._calculate_relevance(py_file, set())
        score_txt = loader._calculate_relevance(txt_file, set())

        assert score_py > score_txt

    def test_relevance_readme_boost(self, tmp_path):
        """README files get boosted."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        loader = ContextLoader(workspace)

        readme = FileInfo(path="README.md", size_bytes=1000, extension=".md")
        other = FileInfo(path="notes.md", size_bytes=1000, extension=".md")

        score_readme = loader._calculate_relevance(readme, set())
        score_other = loader._calculate_relevance(other, set())

        assert score_readme > score_other

    def test_relevance_large_file_penalty(self, tmp_path):
        """Large files get penalized."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        loader = ContextLoader(workspace)

        small = FileInfo(path="auth/login.py", size_bytes=5000, extension=".py")
        large = FileInfo(path="auth/login.py", size_bytes=60000, extension=".py")

        keywords = {"auth", "login"}

        score_small = loader._calculate_relevance(small, keywords)
        score_large = loader._calculate_relevance(large, keywords)

        assert score_small > score_large


class TestContextLoaderFileScan:
    """Tests for file tree scanning."""

    def test_scan_ignores_git(self, tmp_path):
        """Ignores .git directory."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        # Create files
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# main")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("config")

        loader = ContextLoader(workspace)
        files = loader._scan_file_tree()

        paths = [f.path for f in files]
        assert "src/main.py" in paths
        assert ".git/config" not in paths

    def test_scan_ignores_node_modules(self, tmp_path):
        """Ignores node_modules directory."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        # Create files
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("// app")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "package").mkdir()
        (tmp_path / "node_modules" / "package" / "index.js").write_text("// pkg")

        loader = ContextLoader(workspace)
        files = loader._scan_file_tree()

        paths = [f.path for f in files]
        assert "src/app.ts" in paths
        assert not any("node_modules" in p for p in paths)

    def test_scan_filters_by_extension(self, tmp_path):
        """Only includes code file extensions."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        # Create files
        (tmp_path / "main.py").write_text("# python")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "data.bin").write_bytes(b"\x00\x01")

        loader = ContextLoader(workspace)
        files = loader._scan_file_tree()

        paths = [f.path for f in files]
        assert "main.py" in paths
        assert "image.png" not in paths
        assert "data.bin" not in paths


class TestTokenEstimation:
    """Tests for token counting."""

    def test_estimate_tokens(self, tmp_path):
        """Estimates tokens based on character count."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        loader = ContextLoader(workspace)

        # 100 characters should be ~25 tokens with CHARS_PER_TOKEN=4
        text = "a" * 100
        estimate = loader._estimate_tokens(text)

        assert estimate == 100 // CHARS_PER_TOKEN
