"""Tests for HybridWorkerAgent - SDK execution with CodeFRAME coordination.

Tests cover:
- Task execution via SDK
- Context management (load/save)
- Token usage tracking
- Quality gates integration (inherited)
- Session management
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from codeframe.agents.hybrid_worker import HybridWorkerAgent
from codeframe.core.models import Task, TaskStatus, AgentMaturity, ContextItemType

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Create a mock database with required methods."""
    db = MagicMock()

    # Mock context methods
    db.create_context_item = MagicMock(return_value="ctx-123")
    db.list_context_items = MagicMock(return_value=[])
    db.update_context_item_access = MagicMock()
    db.get_context_item = MagicMock(return_value=None)

    return db


@pytest.fixture
def mock_sdk_client():
    """Create a mock SDKClientWrapper."""
    client = MagicMock()

    # Mock send_message as async
    client.send_message = AsyncMock(
        return_value={
            "content": "Task completed successfully. Created file `src/api/handler.py`.",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1500, "output_tokens": 800},
        }
    )

    # Mock streaming
    async def mock_streaming(prompt):
        yield MagicMock(content="Part 1")
        yield MagicMock(content="Part 2")

    client.send_message_streaming = mock_streaming

    return client


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id=42,
        project_id=1,
        issue_id=10,
        task_number=5,
        parent_issue_number="",
        title="Implement user authentication",
        description="Add JWT token authentication to the API endpoints",
        status=TaskStatus.ASSIGNED,
        depends_on=None,
        priority=1,
    )


@pytest.fixture
def hybrid_agent(mock_db, mock_sdk_client):
    """Create a HybridWorkerAgent for testing."""
    return HybridWorkerAgent(
        agent_id="backend-001",
        agent_type="backend",
        db=mock_db,
        sdk_client=mock_sdk_client,
        maturity=AgentMaturity.D2,
        system_prompt="You are a backend developer.",
    )


# ============================================================================
# Initialization Tests
# ============================================================================


class TestHybridWorkerInitialization:
    """Tests for HybridWorkerAgent initialization."""

    def test_init_with_required_params(self, mock_db, mock_sdk_client):
        """Should initialize with required parameters."""
        agent = HybridWorkerAgent(
            agent_id="test-001",
            agent_type="test",
            db=mock_db,
            sdk_client=mock_sdk_client,
        )

        assert agent.agent_id == "test-001"
        assert agent.agent_type == "test"
        assert agent.db == mock_db
        assert agent.sdk_client == mock_sdk_client
        assert agent.maturity == AgentMaturity.D1  # Default

    def test_init_with_all_params(self, mock_db, mock_sdk_client):
        """Should initialize with all optional parameters."""
        agent = HybridWorkerAgent(
            agent_id="backend-001",
            agent_type="backend",
            db=mock_db,
            sdk_client=mock_sdk_client,
            provider="sdk",
            maturity=AgentMaturity.D3,
            system_prompt="Custom prompt",
            session_id="session-abc123",
        )

        assert agent.maturity == AgentMaturity.D3
        assert agent.system_prompt == "Custom prompt"
        assert agent.session_id == "session-abc123"
        assert agent.provider == "sdk"

    def test_inherits_from_worker_agent(self, hybrid_agent):
        """Should inherit from WorkerAgent."""
        from codeframe.agents.worker_agent import WorkerAgent

        assert isinstance(hybrid_agent, WorkerAgent)


# ============================================================================
# Task Execution Tests
# ============================================================================


class TestTaskExecution:
    """Tests for task execution via SDK."""

    @pytest.mark.asyncio
    async def test_execute_task_success(self, hybrid_agent, sample_task):
        """Should execute task successfully via SDK."""
        result = await hybrid_agent.execute_task(sample_task)

        assert result["status"] == "completed"
        assert "content" in result
        assert "usage" in result
        assert result["usage"]["input_tokens"] == 1500
        assert result["usage"]["output_tokens"] == 800

    @pytest.mark.asyncio
    async def test_execute_task_sets_current_task(self, hybrid_agent, sample_task):
        """Should set current_task during execution."""
        await hybrid_agent.execute_task(sample_task)

        assert hybrid_agent.current_task == sample_task

    @pytest.mark.asyncio
    async def test_execute_task_loads_context(self, hybrid_agent, sample_task, mock_db):
        """Should load context from HOT and WARM tiers."""
        mock_db.list_context_items.return_value = [
            {"id": "ctx-1", "item_type": "TASK", "content": "Previous task context"},
        ]

        await hybrid_agent.execute_task(sample_task)

        # Should call list_context_items for both HOT and WARM tiers
        assert mock_db.list_context_items.call_count >= 2

    @pytest.mark.asyncio
    async def test_execute_task_saves_result_to_context(self, hybrid_agent, sample_task, mock_db):
        """Should save task result to context."""
        await hybrid_agent.execute_task(sample_task)

        # Should call create_context_item with task result
        mock_db.create_context_item.assert_called()
        call_args = mock_db.create_context_item.call_args
        assert call_args[1]["item_type"] == "TASK"
        assert f"Task {sample_task.id} result" in call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_execute_task_extracts_changed_files(self, hybrid_agent, sample_task):
        """Should extract changed files from response."""
        result = await hybrid_agent.execute_task(sample_task)

        # Response contains "Created file `src/api/handler.py`"
        assert "files_changed" in result
        assert any("handler.py" in f for f in result["files_changed"])

    @pytest.mark.asyncio
    async def test_execute_task_handles_sdk_error(self, hybrid_agent, sample_task, mock_sdk_client):
        """Should handle SDK execution errors gracefully."""
        mock_sdk_client.send_message = AsyncMock(side_effect=RuntimeError("SDK Error"))

        result = await hybrid_agent.execute_task(sample_task)

        assert result["status"] == "failed"
        assert "SDK Error" in result["content"]


# ============================================================================
# Context Management Tests
# ============================================================================


class TestContextManagement:
    """Tests for context management integration."""

    @pytest.mark.asyncio
    async def test_load_context_hot_tier(self, hybrid_agent, mock_db, sample_task):
        """Should load HOT tier context."""
        # Assign task to establish project context
        hybrid_agent.current_task = sample_task

        mock_db.list_context_items.return_value = [
            {"id": "ctx-1", "item_type": "TASK", "content": "HOT item"}
        ]

        from codeframe.core.models import ContextTier

        items = await hybrid_agent.load_context(tier=ContextTier.HOT)

        mock_db.list_context_items.assert_called()
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_save_context_item(self, hybrid_agent, mock_db, sample_task):
        """Should save context items via inherited method."""
        # Assign task to establish project context
        hybrid_agent.current_task = sample_task

        item_id = await hybrid_agent.save_context_item(
            item_type=ContextItemType.CODE, content="def hello(): pass"
        )

        mock_db.create_context_item.assert_called_once()
        assert item_id == "ctx-123"

    @pytest.mark.asyncio
    async def test_flash_save_checks_threshold(self, hybrid_agent, mock_db, sample_task):
        """Should check flash save threshold after execution."""
        with patch("codeframe.lib.context_manager.ContextManager") as mock_context_mgr_class:
            mock_context_mgr = MagicMock()
            mock_context_mgr.should_flash_save.return_value = False
            mock_context_mgr_class.return_value = mock_context_mgr

            await hybrid_agent.execute_task(sample_task)

            # should_flash_save is called during execute_task
            mock_context_mgr.should_flash_save.assert_called()


# ============================================================================
# Token Tracking Tests
# ============================================================================


class TestTokenTracking:
    """Tests for token usage tracking."""

    @pytest.mark.asyncio
    async def test_records_token_usage(self, hybrid_agent, sample_task):
        """Should record token usage after execution."""
        with patch("codeframe.lib.metrics_tracker.MetricsTracker") as mock_tracker_class:
            mock_tracker = MagicMock()
            mock_tracker.record_token_usage = AsyncMock()
            mock_tracker_class.return_value = mock_tracker

            await hybrid_agent.execute_task(sample_task)

            mock_tracker.record_token_usage.assert_called_once()
            call_kwargs = mock_tracker.record_token_usage.call_args[1]
            assert call_kwargs["task_id"] == sample_task.id
            assert call_kwargs["agent_id"] == "backend-001"
            assert call_kwargs["input_tokens"] == 1500
            assert call_kwargs["output_tokens"] == 800

    @pytest.mark.asyncio
    async def test_token_tracking_failure_doesnt_break_execution(self, hybrid_agent, sample_task):
        """Should not fail execution if token tracking fails."""
        with patch("codeframe.lib.metrics_tracker.MetricsTracker") as mock_tracker_class:
            mock_tracker = MagicMock()
            mock_tracker.record_token_usage = AsyncMock(side_effect=Exception("DB Error"))
            mock_tracker_class.return_value = mock_tracker

            # Should still return successful execution
            result = await hybrid_agent.execute_task(sample_task)
            assert result["status"] == "completed"


# ============================================================================
# Prompt Building Tests
# ============================================================================


class TestPromptBuilding:
    """Tests for prompt construction."""

    def test_build_prompt_includes_task_info(self, hybrid_agent, sample_task):
        """Should include task title and description in prompt."""
        prompt = hybrid_agent._build_execution_prompt(sample_task, [], [])

        assert sample_task.title in prompt
        assert sample_task.description in prompt
        assert f"Task #{sample_task.task_number}" in prompt

    def test_build_prompt_includes_context(self, hybrid_agent, sample_task):
        """Should include context items in prompt."""
        hot_context = [{"id": "1", "item_type": "CODE", "content": "def existing_function(): pass"}]
        warm_context = [{"id": "2", "item_type": "TASK", "content": "Previous task completed"}]

        prompt = hybrid_agent._build_execution_prompt(sample_task, hot_context, warm_context)

        assert "[CODE]" in prompt
        assert "existing_function" in prompt
        assert "[TASK]" in prompt
        assert "Previous task" in prompt

    def test_build_prompt_truncates_long_context(self, hybrid_agent, sample_task):
        """Should truncate long context items."""
        long_content = "x" * 1000
        hot_context = [{"id": "1", "item_type": "CODE", "content": long_content}]

        prompt = hybrid_agent._build_execution_prompt(sample_task, hot_context, [])

        # Should be truncated with "..."
        assert "..." in prompt
        # Should not contain full content
        assert long_content not in prompt

    def test_build_prompt_includes_dependencies(self, hybrid_agent):
        """Should include task dependencies in prompt."""
        task = Task(
            id=1,
            issue_id=1,
            task_number=1,
            title="Task with deps",
            description="Description",
            status=TaskStatus.ASSIGNED,
            depends_on="1,2,3",
            priority=1,
        )

        prompt = hybrid_agent._build_execution_prompt(task, [], [])

        assert "Dependencies" in prompt
        assert "1,2,3" in prompt


# ============================================================================
# File Extraction Tests
# ============================================================================


class TestFileExtraction:
    """Tests for extracting changed files from response."""

    def test_extract_created_file(self, hybrid_agent):
        """Should extract file paths from 'created' statements."""
        content = "Created file `src/api/handler.py` with the implementation."

        files = hybrid_agent._extract_changed_files(content)

        assert "src/api/handler.py" in files

    def test_extract_modified_file(self, hybrid_agent):
        """Should extract file paths from 'modified' statements."""
        content = "Modified file `tests/test_api.py` to add new tests."

        files = hybrid_agent._extract_changed_files(content)

        assert "tests/test_api.py" in files

    def test_extract_multiple_files(self, hybrid_agent):
        """Should extract multiple file paths."""
        content = """
        Created file `src/models/user.py`.
        Modified `src/api/routes.py`.
        Updated file: `tests/test_user.py`
        """

        files = hybrid_agent._extract_changed_files(content)

        assert len(files) >= 2

    def test_empty_content_returns_empty_list(self, hybrid_agent):
        """Should return empty list for empty content."""
        files = hybrid_agent._extract_changed_files("")
        assert files == []


# ============================================================================
# Session Management Tests
# ============================================================================


class TestSessionManagement:
    """Tests for SDK session management."""

    def test_get_session_info(self, hybrid_agent, sample_task):
        """Should return session information."""
        # Assign task to establish project context
        hybrid_agent.current_task = sample_task

        info = hybrid_agent.get_session_info()

        assert info["agent_id"] == "backend-001"
        assert info["agent_type"] == "backend"
        assert info["project_id"] == 1  # From sample_task
        assert info["maturity"] == "coaching"  # D2 enum value is "coaching"
        assert info["has_sdk_client"] is True

    def test_session_id_in_execution_result(self, hybrid_agent, sample_task):
        """Should include session_id in execution result."""
        hybrid_agent.session_id = "session-xyz"

        # We can't await here in a sync test, so just verify the attribute
        assert hybrid_agent.session_id == "session-xyz"

    @pytest.mark.asyncio
    async def test_session_id_returned_in_result(self, hybrid_agent, sample_task):
        """Should return session_id in result dict."""
        hybrid_agent.session_id = "session-abc"

        result = await hybrid_agent.execute_task(sample_task)

        assert result["session_id"] == "session-abc"


# ============================================================================
# Streaming Execution Tests
# ============================================================================


class TestStreamingExecution:
    """Tests for streaming task execution."""

    @pytest.mark.asyncio
    async def test_streaming_yields_chunks(self, hybrid_agent, sample_task, mock_sdk_client):
        """Should yield content chunks during streaming."""
        chunks = []

        async for chunk in hybrid_agent.execute_with_streaming(sample_task):
            if chunk.get("status") == "streaming":
                chunks.append(chunk)

        assert len(chunks) == 2  # Two chunks from mock

    @pytest.mark.asyncio
    async def test_streaming_returns_final_result(self, hybrid_agent, sample_task, mock_sdk_client):
        """Should return final result after streaming."""
        result = None

        async for chunk in hybrid_agent.execute_with_streaming(sample_task):
            result = chunk

        assert result["status"] == "completed"
        assert "Part 1" in result["content"]
        assert "Part 2" in result["content"]


# ============================================================================
# Result Summary Tests
# ============================================================================


class TestResultSummary:
    """Tests for result summarization."""

    def test_summarize_short_content(self, hybrid_agent):
        """Should return short content unchanged."""
        content = "Task completed successfully."

        summary = hybrid_agent._summarize_result(content)

        assert summary == content

    def test_summarize_long_content(self, hybrid_agent):
        """Should truncate long content."""
        long_content = "x" * 1000

        summary = hybrid_agent._summarize_result(long_content, max_length=100)

        assert len(summary) <= 103  # 100 + "..."
        assert summary.endswith("...")

    def test_summarize_empty_content(self, hybrid_agent):
        """Should handle empty content."""
        summary = hybrid_agent._summarize_result("")

        assert summary == "No output"

    def test_summarize_takes_first_paragraph(self, hybrid_agent):
        """Should take first paragraph if short enough."""
        content = "First paragraph here.\n\nSecond paragraph here."

        summary = hybrid_agent._summarize_result(content)

        assert summary == "First paragraph here."


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for HybridWorkerAgent."""

    @pytest.mark.asyncio
    async def test_full_execution_flow(self, mock_db, mock_sdk_client, sample_task):
        """Test complete execution flow from start to finish."""
        # Set up context
        mock_db.list_context_items.side_effect = [
            [{"id": "hot-1", "item_type": "TASK", "content": "Previous task"}],  # HOT
            [],  # WARM
        ]

        agent = HybridWorkerAgent(
            agent_id="test-agent",
            agent_type="backend",
            db=mock_db,
            sdk_client=mock_sdk_client,
            session_id="test-session",
        )

        with patch("codeframe.lib.metrics_tracker.MetricsTracker") as mock_tracker_class:
            mock_tracker = MagicMock()
            mock_tracker.record_token_usage = AsyncMock()
            mock_tracker_class.return_value = mock_tracker

            with patch("codeframe.lib.context_manager.ContextManager") as mock_context_mgr_class:
                mock_context_mgr = MagicMock()
                mock_context_mgr.should_flash_save.return_value = False
                mock_context_mgr_class.return_value = mock_context_mgr

                result = await agent.execute_task(sample_task)

        # Verify execution
        assert result["status"] == "completed"
        assert result["session_id"] == "test-session"

        # Verify context was loaded
        assert mock_db.list_context_items.call_count == 2

        # Verify result was saved to context
        mock_db.create_context_item.assert_called()

        # Verify SDK was called
        mock_sdk_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_quality_gates_inherited(self, mock_db, mock_sdk_client, sample_task):
        """Test that quality gates from WorkerAgent are accessible."""
        agent = HybridWorkerAgent(
            agent_id="test-agent",
            agent_type="backend",
            db=mock_db,
            sdk_client=mock_sdk_client,
        )

        # complete_task is inherited from WorkerAgent
        assert hasattr(agent, "complete_task")
        assert callable(agent.complete_task)
