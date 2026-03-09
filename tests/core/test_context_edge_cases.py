"""Edge case tests for context management system.

Covers boundary conditions, encoding fallbacks, token budget overflow,
keyword extraction with stopwords/short words, and relevance scoring
with empty keyword sets.
"""

import pytest

from codeframe.core.context import (
    ContextLoader,
    TaskContext,
    FileInfo,
)
from codeframe.core import tasks
from codeframe.core.tasks import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.edge_case


class TestContextEdgeCases:
    """Edge case tests for context management."""

    @pytest.fixture
    def workspace(self, tmp_path):
        return create_or_load_workspace(tmp_path)

    def test_context_loader_task_not_found(self, workspace):
        """ContextLoader.load raises ValueError when task ID does not exist."""
        loader = ContextLoader(workspace)
        with pytest.raises(ValueError, match="Task not found"):
            loader.load("nonexistent-id")

    def test_load_file_with_encoding_error(self, workspace, tmp_path):
        """Files with invalid UTF-8 bytes are loaded using errors='replace' without crashing."""
        bad_file = tmp_path / "bad_encoding.py"
        bad_file.write_bytes(b"# header\n\x80\x81\x82\nprint('hello')\n")

        loader = ContextLoader(workspace)
        file_info = FileInfo(
            path="bad_encoding.py",
            size_bytes=bad_file.stat().st_size,
            extension=".py",
            relevance_score=0.5,
        )

        result = loader._load_file(file_info)

        assert result is not None
        assert "header" in result.content
        assert "hello" in result.content
        assert result.tokens_estimate > 0

    def test_tokens_remaining_when_over_budget(self):
        """tokens_remaining returns 0 when total_tokens exceeds max_tokens."""
        task_stub = tasks.Task(
            id="t-1",
            workspace_id="ws-1",
            prd_id=None,
            title="stub",
            description="stub",
            status=TaskStatus.BACKLOG,
            priority=0,
            created_at=None,
            updated_at=None,
        )
        context = TaskContext(
            task=task_stub,
            total_tokens=150_000,
            max_tokens=100_000,
        )

        assert context.tokens_remaining() == 0

    def test_extract_keywords_no_meaningful_words(self, workspace):
        """Text composed entirely of stopwords yields an empty keyword set."""
        loader = ContextLoader(workspace)
        result = loader._extract_keywords("the a an or and but in on at to for of")

        assert result == set()

    def test_extract_keywords_short_words_filtered(self, workspace):
        """Words with 2 or fewer characters are filtered out of keywords."""
        loader = ContextLoader(workspace)
        result = loader._extract_keywords("do it as if")

        assert result == set()

    def test_calculate_relevance_no_keywords(self, workspace):
        """Relevance score with empty keywords still reflects extension and filename bonuses."""
        loader = ContextLoader(workspace)
        py_file = FileInfo(path="src/main.py", size_bytes=500, extension=".py")

        score = loader._calculate_relevance(py_file, set())

        assert score > 0.0, "Python extension and main.py filename should contribute to score"
        expected_min = 0.1 + 0.12  # .py bonus + main.py filename bonus
        assert score >= expected_min
