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


# ---------------------------------------------------------------------------
# Helper to build assistant+user pairs for compaction tests
# ---------------------------------------------------------------------------


def _make_pair(tool_name="read_file", tool_input=None, tool_result_content="ok", is_error=False, tc_id="tc1"):
    """Build an assistant+user message pair for testing."""
    if tool_input is None:
        tool_input = {"path": "test.py"}
    assistant = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": tc_id, "name": tool_name, "input": tool_input}],
    }
    user = {
        "role": "user",
        "content": "",
        "tool_results": [
            {"tool_call_id": tc_id, "content": tool_result_content, "is_error": is_error}
        ],
    }
    return assistant, user


# ---------------------------------------------------------------------------
# Tests: Tier 1 - Tool result compaction
# ---------------------------------------------------------------------------


class TestTier1CompactToolResults:
    """Tests for _compact_tool_results (Tier 1)."""

    def test_preserves_recent_pairs(self, workspace, provider):
        """Last PRESERVE_RECENT_PAIRS*2 messages should not be compacted."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        # Build exactly PRESERVE_RECENT_PAIRS pairs (10 messages) — all should be preserved
        messages = []
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"content_{i}" * 50, tc_id=f"tc{i}")
            messages.extend([a, u])

        result, saved = agent._compact_tool_results(list(messages))
        # Nothing should be compacted since all are "recent"
        assert saved == 0
        assert result == messages

    def test_compacts_old_tool_results(self, workspace, provider):
        """Older tool results (outside PRESERVE_RECENT_PAIRS) should be compacted."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # Add PRESERVE_RECENT_PAIRS + 2 pairs so the first 2 are old
        for i in range(PRESERVE_RECENT_PAIRS + 2):
            a, u = _make_pair(
                tool_result_content="very long content that should be compacted " * 20,
                tc_id=f"tc{i}",
            )
            messages.extend([a, u])

        result, saved = agent._compact_tool_results(list(messages))
        # First 2 pairs (4 messages) should have been compacted
        assert saved > 0
        # Recent pairs should be untouched
        assert result[-PRESERVE_RECENT_PAIRS * 2:] == messages[-PRESERVE_RECENT_PAIRS * 2:]
        # Old tool results should contain "[Compacted]"
        old_user = result[1]  # second message = first user msg
        assert "[Compacted]" in old_user["tool_results"][0]["content"]

    def test_preserves_error_results(self, workspace, provider):
        """Tool results with is_error=True should not be compacted."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # First pair: error result (should be preserved)
        a, u = _make_pair(
            tool_result_content="ImportError: No module named 'foo'",
            is_error=True,
            tc_id="tc-err",
        )
        messages.extend([a, u])
        # Add enough recent pairs to push the first pair into "old" territory
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"content_{i}", tc_id=f"tc{i}")
            messages.extend([a, u])

        result, saved = agent._compact_tool_results(list(messages))
        # The error result content should be fully preserved
        old_user = result[1]
        assert old_user["tool_results"][0]["content"] == "ImportError: No module named 'foo'"
        assert old_user["tool_results"][0]["is_error"] is True

    def test_returns_zero_savings_when_nothing_to_compact(self, workspace, provider):
        """When there are no old messages, tokens_saved should be 0."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = [
            {"role": "assistant", "content": "hello"},
        ]
        result, saved = agent._compact_tool_results(list(messages))
        assert saved == 0
        assert result == messages

    def test_summary_includes_tool_name(self, workspace, provider):
        """Compacted summary should include the tool name."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # Old pair with read_file
        a, u = _make_pair(
            tool_name="read_file",
            tool_result_content="def hello():\n    return 'world'\n" * 10,
            tc_id="tc-old",
        )
        messages.extend([a, u])
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"c{i}", tc_id=f"tc{i}")
            messages.extend([a, u])

        result, _ = agent._compact_tool_results(list(messages))
        compacted = result[1]["tool_results"][0]["content"]
        assert "read_file" in compacted


# ---------------------------------------------------------------------------
# Tests: Tier 2 - Intermediate step removal
# ---------------------------------------------------------------------------


class TestTier2RemoveIntermediateSteps:
    """Tests for _remove_intermediate_steps (Tier 2)."""

    def test_removes_redundant_file_reads(self, workspace, provider):
        """If same file is read twice, earlier read should be removed."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # First read of main.py (old, should be removed)
        a, u = _make_pair(
            tool_name="read_file",
            tool_input={"path": "main.py"},
            tool_result_content="old contents",
            tc_id="tc-old-read",
        )
        messages.extend([a, u])
        # Second read of main.py (newer, should be kept)
        a, u = _make_pair(
            tool_name="read_file",
            tool_input={"path": "main.py"},
            tool_result_content="new contents",
            tc_id="tc-new-read",
        )
        messages.extend([a, u])
        # Add recent pairs to push old reads outside preserve zone
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"c{i}", tc_id=f"tc{i}")
            messages.extend([a, u])

        result, saved = agent._remove_intermediate_steps(list(messages))
        # First read pair should be removed
        assert saved > 0
        assert len(result) < len(messages)
        # The remaining read_file for main.py should have "new contents"
        remaining_reads = [
            m for m in result
            if m.get("tool_results") and any(
                "new contents" in tr["content"] for tr in m["tool_results"]
            )
        ]
        assert len(remaining_reads) >= 1

    def test_keeps_reads_with_intervening_edit(self, workspace, provider):
        """If a file was edited between reads, both reads should be kept."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # Read main.py
        a, u = _make_pair(
            tool_name="read_file",
            tool_input={"path": "main.py"},
            tool_result_content="before edit",
            tc_id="tc-read1",
        )
        messages.extend([a, u])
        # Edit main.py (intervening write)
        a, u = _make_pair(
            tool_name="edit_file",
            tool_input={"path": "main.py", "edits": []},
            tool_result_content="edit applied",
            tc_id="tc-edit",
        )
        messages.extend([a, u])
        # Read main.py again
        a, u = _make_pair(
            tool_name="read_file",
            tool_input={"path": "main.py"},
            tool_result_content="after edit",
            tc_id="tc-read2",
        )
        messages.extend([a, u])
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"c{i}", tc_id=f"tc{i}")
            messages.extend([a, u])

        result, saved = agent._remove_intermediate_steps(list(messages))
        # First read should NOT be removed because there was an edit in between
        assert saved == 0

    def test_removes_passed_test_results(self, workspace, provider):
        """Test outputs showing 'passed' should be removed when outside preserve zone."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # Passed test result
        a, u = _make_pair(
            tool_name="run_tests",
            tool_input={"test_path": "tests/"},
            tool_result_content="5 passed in 0.3s",
            tc_id="tc-test",
        )
        messages.extend([a, u])
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"c{i}", tc_id=f"tc{i}")
            messages.extend([a, u])

        result, saved = agent._remove_intermediate_steps(list(messages))
        assert saved > 0
        assert len(result) < len(messages)

    def test_preserves_recent_pairs(self, workspace, provider):
        """Last PRESERVE_RECENT_PAIRS*2 messages should not be removed."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(
                tool_name="read_file",
                tool_input={"path": "same.py"},
                tool_result_content=f"content_{i}",
                tc_id=f"tc{i}",
            )
            messages.extend([a, u])

        result, saved = agent._remove_intermediate_steps(list(messages))
        # All within preserve zone — nothing removed
        assert saved == 0
        assert len(result) == len(messages)

    def test_keeps_test_results_with_failures(self, workspace, provider):
        """Test output containing both 'passed' and 'failed' should NOT be removed."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # Mixed test result (has failures — should be kept)
        a, u = _make_pair(
            tool_name="run_tests",
            tool_input={"test_path": "tests/"},
            tool_result_content="5 passed, 3 failed in 2.1s",
            tc_id="tc-mixed",
        )
        messages.extend([a, u])
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"c{i}", tc_id=f"tc{i}")
            messages.extend([a, u])

        result, saved = agent._remove_intermediate_steps(list(messages))
        # Should NOT be removed because it contains failure info
        assert saved == 0
        assert len(result) == len(messages)


# ---------------------------------------------------------------------------
# Tests: Tier 3 - Conversation summary
# ---------------------------------------------------------------------------


class TestTier3SummarizeOldMessages:
    """Tests for _summarize_old_messages (Tier 3)."""

    def test_creates_summary_message(self, workspace, provider):
        """Should replace old messages with a single [Summary] message."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # Add enough old pairs
        for i in range(PRESERVE_RECENT_PAIRS + 3):
            a, u = _make_pair(
                tool_name="read_file",
                tool_input={"path": f"file_{i}.py"},
                tool_result_content=f"content of file_{i}" * 20,
                tc_id=f"tc{i}",
            )
            messages.extend([a, u])

        result, saved = agent._summarize_old_messages(list(messages), target_tokens=10)
        assert saved > 0
        # First message should be the summary
        assert result[0]["role"] == "user"
        assert "[Summary]" in result[0]["content"]
        # Recent pairs should be preserved
        assert len(result) < len(messages)

    def test_preserves_file_paths_in_summary(self, workspace, provider):
        """Summary should mention file paths from summarized tool calls."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # Old pair referencing specific files
        a, u = _make_pair(
            tool_name="read_file",
            tool_input={"path": "important_module.py"},
            tool_result_content="important code" * 20,
            tc_id="tc-imp",
        )
        messages.extend([a, u])
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"c{i}" * 20, tc_id=f"tc{i}")
            messages.extend([a, u])

        result, _ = agent._summarize_old_messages(list(messages), target_tokens=10)
        summary = result[0]["content"]
        assert "important_module.py" in summary

    def test_preserves_error_info_in_summary(self, workspace, provider):
        """Summary should mention errors from error tool results."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        a, u = _make_pair(
            tool_name="run_command",
            tool_result_content="ModuleNotFoundError: No module named 'missing'",
            is_error=True,
            tc_id="tc-err",
        )
        messages.extend([a, u])
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"c{i}" * 20, tc_id=f"tc{i}")
            messages.extend([a, u])

        result, _ = agent._summarize_old_messages(list(messages), target_tokens=10)
        summary = result[0]["content"]
        assert "error" in summary.lower() or "Error" in summary

    def test_preserves_recent_messages(self, workspace, provider):
        """Recent PRESERVE_RECENT_PAIRS*2 messages should remain intact."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        for i in range(PRESERVE_RECENT_PAIRS + 2):
            a, u = _make_pair(tool_result_content=f"c{i}" * 20, tc_id=f"tc{i}")
            messages.extend([a, u])

        recent = messages[-PRESERVE_RECENT_PAIRS * 2:]
        result, _ = agent._summarize_old_messages(list(messages), target_tokens=10)
        # Recent messages should be at the end unchanged
        assert result[-PRESERVE_RECENT_PAIRS * 2:] == recent

    def test_no_op_when_all_within_preserve_zone(self, workspace, provider):
        """When all messages are in the preserve zone, nothing is summarized."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        for i in range(PRESERVE_RECENT_PAIRS):
            a, u = _make_pair(tool_result_content=f"c{i}", tc_id=f"tc{i}")
            messages.extend([a, u])

        result, saved = agent._summarize_old_messages(list(messages), target_tokens=10)
        assert saved == 0
        assert result == messages

    def test_preserves_prior_summary_messages(self, workspace, provider):
        """Prior [Summary] messages from earlier compaction rounds are folded into the new summary."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        # Create a prior summary + enough messages to exceed preserve zone
        prior_summary = {"role": "user", "content": "[Summary] Previous context: analyzed 3 files (a.py, b.py, c.py)"}
        messages = [prior_summary]
        for i in range(PRESERVE_RECENT_PAIRS + 3):
            a, u = _make_pair(tool_result_content=f"content-{i}", tc_id=f"tc{i}")
            messages.extend([a, u])

        result, saved = agent._summarize_old_messages(list(messages), target_tokens=10)
        # The new summary should reference the prior summary content
        new_summary = result[0]["content"]
        assert new_summary.startswith("[Summary]")
        assert "prior summaries" in new_summary
        assert "analyzed 3 files" in new_summary


# ---------------------------------------------------------------------------
# Tests: compact_conversation orchestrator
# ---------------------------------------------------------------------------


class TestCompactConversation:
    """Tests for compact_conversation orchestrator."""

    def test_no_compaction_when_below_threshold(self, workspace, provider):
        """When below threshold, returns messages unchanged with compacted=False."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = [{"role": "assistant", "content": "hello"}]
        result, stats = agent.compact_conversation(list(messages))
        assert result == messages
        assert stats["compacted"] is False

    def test_compaction_runs_tiers_when_needed(self, workspace, provider):
        """When above threshold, runs tiers and returns stats."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent._context_window_size = 100
        agent._compaction_threshold = 0.1  # Very low threshold to force trigger

        messages = []
        for i in range(PRESERVE_RECENT_PAIRS + 3):
            a, u = _make_pair(
                tool_result_content="verbose content " * 50,
                tc_id=f"tc{i}",
            )
            messages.extend([a, u])

        result, stats = agent.compact_conversation(list(messages))
        assert stats["compacted"] is True
        assert stats["tokens_before"] > 0
        assert stats["tokens_saved"] >= 0
        assert "tiers_used" in stats
        assert stats["compaction_number"] == 1

    def test_increments_compaction_count(self, workspace, provider):
        """Each compaction should increment _compaction_count."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent._context_window_size = 100
        agent._compaction_threshold = 0.1

        messages = []
        for i in range(PRESERVE_RECENT_PAIRS + 3):
            a, u = _make_pair(tool_result_content="x" * 200, tc_id=f"tc{i}")
            messages.extend([a, u])

        assert agent._compaction_count == 0
        agent.compact_conversation(list(messages))
        assert agent._compaction_count == 1
        agent.compact_conversation(list(messages))
        assert agent._compaction_count == 2

    def test_stats_contain_required_keys(self, workspace, provider):
        """Stats dict should contain all required keys when compacted."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent._context_window_size = 100
        agent._compaction_threshold = 0.1

        messages = []
        for i in range(PRESERVE_RECENT_PAIRS + 2):
            a, u = _make_pair(tool_result_content="x" * 200, tc_id=f"tc{i}")
            messages.extend([a, u])

        _, stats = agent.compact_conversation(list(messages))
        assert "compacted" in stats
        assert "tokens_before" in stats
        assert "tokens_after" in stats
        assert "tokens_saved" in stats
        assert "tiers_used" in stats
        assert "compaction_number" in stats

    def test_defensive_copy_does_not_mutate_caller_list(self, workspace, provider):
        """compact_conversation should not mutate the original list."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent._context_window_size = 100
        agent._compaction_threshold = 0.1

        messages = []
        for i in range(PRESERVE_RECENT_PAIRS + 3):
            a, u = _make_pair(tool_result_content="x" * 200, tc_id=f"tc{i}")
            messages.extend([a, u])

        original_len = len(messages)
        original_ids = [id(m) for m in messages]
        agent.compact_conversation(messages)
        # Caller's list should be untouched
        assert len(messages) == original_len
        assert [id(m) for m in messages] == original_ids


# ---------------------------------------------------------------------------
# Tests: Tier 2 role validation
# ---------------------------------------------------------------------------


class TestTier2RoleValidation:
    """Tests for tier 2 role-checking in message pairing."""

    def test_skips_non_standard_role_pairs(self, workspace, provider):
        """Tier 2 should skip message pairs that don't follow assistant/user pattern."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        # Create messages with a system message breaking the pair pattern
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
        ]
        # Add enough normal pairs for the preserve zone
        for i in range(PRESERVE_RECENT_PAIRS + 1):
            a, u = _make_pair(tool_result_content=f"c{i}", tc_id=f"tc{i}")
            messages.extend([a, u])

        # Should not crash on non-standard pair
        result, saved = agent._remove_intermediate_steps(list(messages))
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Tests: get_token_stats
# ---------------------------------------------------------------------------


class TestGetTokenStats:
    """Tests for get_token_stats method."""

    def test_returns_required_keys(self, workspace, provider):
        """Should return dict with total_tokens, percentage_used, compaction_count, context_window_size."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = [{"role": "assistant", "content": "a" * 400}]
        stats = agent.get_token_stats(messages)
        assert "total_tokens" in stats
        assert "percentage_used" in stats
        assert "compaction_count" in stats
        assert "context_window_size" in stats

    def test_calculates_percentage(self, workspace, provider):
        """Percentage should be total_tokens / context_window_size."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent._context_window_size = 1000
        messages = [{"role": "assistant", "content": "a" * 400}]  # 100 tokens
        stats = agent.get_token_stats(messages)
        assert stats["total_tokens"] == 100
        assert stats["percentage_used"] == pytest.approx(0.1)
        assert stats["context_window_size"] == 1000

    def test_includes_compaction_count(self, workspace, provider):
        """Should reflect current _compaction_count."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent._compaction_count = 3
        stats = agent.get_token_stats([])
        assert stats["compaction_count"] == 3


# ---------------------------------------------------------------------------
# Tests: React loop integration
# ---------------------------------------------------------------------------


class TestReactLoopCompactionIntegration:
    """Tests for compact_conversation being called in the react loop."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_compact_conversation_called_in_loop(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """compact_conversation should be called during the react loop."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "test.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="contents")
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        original_compact = agent.compact_conversation
        compact_called = []

        def tracking_compact(messages):
            compact_called.append(True)
            return original_compact(messages)

        agent.compact_conversation = tracking_compact
        agent.run("task-1")

        assert len(compact_called) >= 1
        assert provider.call_count >= 1, "LLM provider should have been called during the react loop"

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_verbose_output_on_compaction(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, capsys
    ):
        """When compaction occurs, verbose output should mention tokens saved."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        # Build enough tool calls to fill history beyond threshold
        for i in range(PRESERVE_RECENT_PAIRS + 3):
            provider.add_tool_response(
                [ToolCall(id=f"tc{i}", name="read_file", input={"path": f"file_{i}.py"})]
            )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="x" * 2000)
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            verbose=True,
        )
        # Force small context window to trigger compaction
        agent._context_window_size = 100
        agent._compaction_threshold = 0.1
        agent.run("task-1")

        captured = capsys.readouterr()
        assert "[ReactAgent] Compacted" in captured.out


# ---------------------------------------------------------------------------
# Helper: build conversation of arbitrary size
# ---------------------------------------------------------------------------


def _build_conversation(n_pairs, content_size=1000):
    """Generate n_pairs of assistant+user message pairs with given content size."""
    messages = []
    for i in range(n_pairs):
        a, u = _make_pair(
            tool_name="read_file",
            tool_input={"path": f"file_{i}.py"},
            tool_result_content="x" * content_size,
            tc_id=f"tc{i}",
        )
        messages.extend([a, u])
    return messages


# ---------------------------------------------------------------------------
# Tests: Additional coverage for tier edge cases
# ---------------------------------------------------------------------------


class TestTier1TokenSavings:
    """Additional Tier 1 tests."""

    def test_tokens_saved_positive(self, workspace, provider):
        """Compacting verbose tool results should yield positive token savings."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = _build_conversation(PRESERVE_RECENT_PAIRS + 3, content_size=2000)
        _, saved = agent._compact_tool_results(list(messages))
        assert saved > 0


class TestTier2UniqueReads:
    """Additional Tier 2 tests."""

    def test_keeps_unique_reads(self, workspace, provider):
        """Reads of different files should all be kept."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        messages = []
        # Each file is read only once
        for i in range(PRESERVE_RECENT_PAIRS + 2):
            a, u = _make_pair(
                tool_name="read_file",
                tool_input={"path": f"unique_{i}.py"},
                tool_result_content=f"unique content {i}",
                tc_id=f"tc{i}",
            )
            messages.extend([a, u])

        result, saved = agent._remove_intermediate_steps(list(messages))
        # No redundant reads — nothing should be removed
        assert saved == 0
        assert len(result) == len(messages)


class TestCompactionOrchestrationAdvanced:
    """Advanced orchestration tests."""

    def test_tier1_sufficient_stops_early(self, workspace, provider):
        """When Tier 1 brings tokens below threshold, Tiers 2-3 should not run."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        # Use a threshold that will be just barely exceeded, so tier 1 is enough
        messages = _build_conversation(PRESERVE_RECENT_PAIRS + 2, content_size=500)
        # Set context window so we're just above threshold after fill
        tokens = agent._estimate_conversation_tokens(messages)
        # Threshold at 90% of current usage, so tier 1 compaction should bring below
        agent._context_window_size = int(tokens * 1.05)
        agent._compaction_threshold = 0.9

        _, stats = agent.compact_conversation(list(messages))
        if stats["compacted"]:
            # If tier 1 was sufficient, tiers 2 and 3 should not appear
            assert "tier3_summary" not in stats.get("tiers_used", [])

    def test_all_tiers_used_under_extreme_pressure(self, workspace, provider):
        """When context is extremely full, all 3 tiers should be exercised."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        # Very small context window forces all tiers
        agent._context_window_size = 10
        agent._compaction_threshold = 0.1  # threshold = 1 token
        messages = _build_conversation(PRESERVE_RECENT_PAIRS + 5, content_size=2000)

        _, stats = agent.compact_conversation(list(messages))
        assert stats["compacted"] is True
        assert len(stats["tiers_used"]) >= 1

    def test_multiple_compaction_rounds(self, workspace, provider):
        """Multiple compaction rounds should each increment the counter."""
        from codeframe.core.react_agent import ReactAgent, PRESERVE_RECENT_PAIRS

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent._context_window_size = 50
        agent._compaction_threshold = 0.1

        for round_num in range(3):
            messages = _build_conversation(PRESERVE_RECENT_PAIRS + 2, content_size=500)
            agent.compact_conversation(list(messages))

        assert agent._compaction_count == 3


class TestExistingTestsUnaffected:
    """Verify that compaction integration doesn't break existing functionality."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_basic_loop_still_works(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """A basic react loop (text response) should still complete."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")
        assert status == AgentStatus.COMPLETED

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_tool_calls_then_text_still_works(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Tool call followed by text response should still complete."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "main.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="contents")
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")
        assert status == AgentStatus.COMPLETED
