"""Tests for ReactAgent conversation compaction (token budget management).

Tests the 3-tier compaction strategy, token estimation, and integration
with the ReAct loop.
"""

import os
from datetime import datetime, timezone

import pytest
from unittest.mock import patch

from codeframe.adapters.llm.base import ToolCall, ToolResult
from codeframe.adapters.llm.mock import MockProvider
from codeframe.core.agent import AgentStatus
from codeframe.core.context import TaskContext
from codeframe.core.gates import GateResult, GateCheck, GateStatus
from codeframe.core.tasks import Task, TaskStatus
from codeframe.core.workspace import Workspace

pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    """Create a minimal workspace for testing."""
    state_dir = tmp_path / ".codeframe"
    state_dir.mkdir()
    return Workspace(
        id="ws-test",
        repo_path=tmp_path,
        state_dir=state_dir,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        tech_stack="Python with uv",
    )


@pytest.fixture
def mock_task():
    """Create a minimal task."""
    _ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Task(
        id="task-1",
        workspace_id="ws-test",
        prd_id=None,
        title="Add hello function",
        description="Create a hello() function that returns 'Hello, World!'",
        status=TaskStatus.IN_PROGRESS,
        priority=1,
        created_at=_ts,
        updated_at=_ts,
    )


@pytest.fixture
def mock_context(mock_task):
    """Create a minimal TaskContext."""
    return TaskContext(task=mock_task)


@pytest.fixture
def provider():
    """Create a MockProvider."""
    return MockProvider()


def _gate_passed():
    """Return a GateResult that passed."""
    return GateResult(
        passed=True,
        checks=[GateCheck(name="ruff", status=GateStatus.PASSED)],
    )


# ---------------------------------------------------------------------------
# Tests: Module-level constants
# ---------------------------------------------------------------------------


class TestCompactionConstants:
    """Tests for module-level compaction constants."""

    def test_default_compaction_threshold_exists(self):
        """DEFAULT_COMPACTION_THRESHOLD should be 0.85."""
        from codeframe.core.react_agent import DEFAULT_COMPACTION_THRESHOLD

        assert DEFAULT_COMPACTION_THRESHOLD == 0.85

    def test_preserve_recent_pairs_exists(self):
        """PRESERVE_RECENT_PAIRS should be 5."""
        from codeframe.core.react_agent import PRESERVE_RECENT_PAIRS

        assert PRESERVE_RECENT_PAIRS == 5

    def test_default_context_window_exists(self):
        """DEFAULT_CONTEXT_WINDOW should be 200_000."""
        from codeframe.core.react_agent import DEFAULT_CONTEXT_WINDOW

        assert DEFAULT_CONTEXT_WINDOW == 200_000


# ---------------------------------------------------------------------------
# Tests: __init__ attributes
# ---------------------------------------------------------------------------


class TestCompactionInitAttributes:
    """Tests for compaction-related attributes on ReactAgent.__init__."""

    def test_default_context_window_size(self, workspace, provider):
        """ReactAgent should default _context_window_size to 200_000."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        assert agent._context_window_size == 200_000

    def test_default_compaction_threshold(self, workspace, provider):
        """ReactAgent should default _compaction_threshold to 0.85."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        assert agent._compaction_threshold == 0.85

    def test_compaction_threshold_from_env(self, workspace, provider):
        """ReactAgent should read CODEFRAME_REACT_COMPACT_THRESHOLD from env."""
        from codeframe.core.react_agent import ReactAgent

        with patch.dict(os.environ, {"CODEFRAME_REACT_COMPACT_THRESHOLD": "0.7"}):
            agent = ReactAgent(workspace=workspace, llm_provider=provider)
            assert agent._compaction_threshold == 0.7

    def test_compaction_threshold_clamped_low(self, workspace, provider):
        """Threshold below 0.5 should be clamped to 0.5."""
        from codeframe.core.react_agent import ReactAgent

        with patch.dict(os.environ, {"CODEFRAME_REACT_COMPACT_THRESHOLD": "0.1"}):
            agent = ReactAgent(workspace=workspace, llm_provider=provider)
            assert agent._compaction_threshold == 0.5

    def test_compaction_threshold_clamped_high(self, workspace, provider):
        """Threshold above 0.95 should be clamped to 0.95."""
        from codeframe.core.react_agent import ReactAgent

        with patch.dict(os.environ, {"CODEFRAME_REACT_COMPACT_THRESHOLD": "0.99"}):
            agent = ReactAgent(workspace=workspace, llm_provider=provider)
            assert agent._compaction_threshold == 0.95

    def test_compaction_threshold_invalid_env_uses_default(self, workspace, provider):
        """Invalid env var value should fall back to default 0.85."""
        from codeframe.core.react_agent import ReactAgent

        with patch.dict(os.environ, {"CODEFRAME_REACT_COMPACT_THRESHOLD": "not_a_number"}):
            agent = ReactAgent(workspace=workspace, llm_provider=provider)
            assert agent._compaction_threshold == 0.85

    def test_total_tokens_used_initialized(self, workspace, provider):
        """_total_tokens_used should start at 0."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        assert agent._total_tokens_used == 0

    def test_compaction_count_initialized(self, workspace, provider):
        """_compaction_count should start at 0."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        assert agent._compaction_count == 0


# ---------------------------------------------------------------------------
# Tests: Token estimation methods
# ---------------------------------------------------------------------------


class TestEstimateMessageTokens:
    """Tests for _estimate_message_tokens method."""

    def test_text_only_message(self, workspace, provider):
        """A text-only assistant message should estimate tokens as len(text)//4."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        msg = {"role": "assistant", "content": "a" * 400}
        tokens = agent._estimate_message_tokens(msg)
        assert tokens == 100  # 400 chars / 4

    def test_empty_message(self, workspace, provider):
        """An empty content message should return 0 tokens."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        msg = {"role": "assistant", "content": ""}
        tokens = agent._estimate_message_tokens(msg)
        assert tokens == 0

    def test_message_with_tool_calls(self, workspace, provider):
        """A message with tool_calls should include tokens from serialized tool_calls."""
        from codeframe.core.react_agent import ReactAgent
        import json

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        tool_calls = [{"id": "tc1", "name": "read_file", "input": {"path": "test.py"}}]
        msg = {
            "role": "assistant",
            "content": "Let me read that file.",
            "tool_calls": tool_calls,
        }
        tokens = agent._estimate_message_tokens(msg)

        expected_content_tokens = len("Let me read that file.") // 4
        expected_tool_tokens = len(json.dumps(tool_calls)) // 4
        assert tokens == expected_content_tokens + expected_tool_tokens

    def test_message_with_tool_results(self, workspace, provider):
        """A user message with tool_results should include tokens from serialized tool_results."""
        from codeframe.core.react_agent import ReactAgent
        import json

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        tool_results = [{"tool_call_id": "tc1", "content": "file contents here", "is_error": False}]
        msg = {
            "role": "user",
            "content": "",
            "tool_results": tool_results,
        }
        tokens = agent._estimate_message_tokens(msg)

        expected_content_tokens = 0  # empty content
        expected_result_tokens = len(json.dumps(tool_results)) // 4
        assert tokens == expected_content_tokens + expected_result_tokens


class TestEstimateConversationTokens:
    """Tests for _estimate_conversation_tokens method."""

    def test_empty_conversation(self, workspace, provider):
        """Empty message list should return 0."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        tokens = agent._estimate_conversation_tokens([])
        assert tokens == 0

    def test_sums_all_messages(self, workspace, provider):
        """Should sum tokens across all messages."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = [
            {"role": "assistant", "content": "a" * 400},  # 100 tokens
            {"role": "user", "content": "b" * 200},  # 50 tokens
        ]
        tokens = agent._estimate_conversation_tokens(messages)
        assert tokens == 150

    def test_updates_total_tokens_used(self, workspace, provider):
        """Should update _total_tokens_used with the result."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = [
            {"role": "assistant", "content": "a" * 400},
        ]
        agent._estimate_conversation_tokens(messages)
        assert agent._total_tokens_used == 100


class TestShouldCompact:
    """Tests for _should_compact method."""

    def test_below_threshold_returns_false(self, workspace, provider):
        """When usage is below threshold, should return False."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        # Small messages, well below 85% of 200K tokens
        messages = [{"role": "assistant", "content": "hello"}]
        assert agent._should_compact(messages) is False

    def test_above_threshold_returns_true(self, workspace, provider):
        """When usage is at or above threshold, should return True."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        # Force a small context window to trigger compaction easily
        agent._context_window_size = 100  # 100 tokens
        agent._compaction_threshold = 0.5  # 50% threshold = 50 tokens
        # 400 chars = 100 tokens, which is 100% of 100 -> above 50%
        messages = [{"role": "assistant", "content": "a" * 400}]
        assert agent._should_compact(messages) is True

    def test_exactly_at_threshold_returns_true(self, workspace, provider):
        """At exactly the threshold, should return True."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent._context_window_size = 100
        agent._compaction_threshold = 0.5
        # 200 chars = 50 tokens = exactly 50% of 100
        messages = [{"role": "assistant", "content": "a" * 200}]
        assert agent._should_compact(messages) is True
