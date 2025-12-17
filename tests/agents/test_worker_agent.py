"""
Tests for base WorkerAgent (execute_task implementation).

Test coverage for async task execution:
- Successful execution with LLM response
- API key validation
- Error handling (AuthenticationError, RateLimitError, etc.)
- Token usage tracking
- Prompt building

Following strict TDD methodology (RED-GREEN-REFACTOR).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os

from anthropic import AuthenticationError, RateLimitError, APIConnectionError

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import Task, TaskStatus, AgentMaturity


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id=1,
        project_id=1,
        task_number="1.0.1",
        title="Add logging to auth module",
        description="Add structured logging to the authentication module for better debugging.",
        status=TaskStatus.IN_PROGRESS,
        assigned_to="backend-001",
        priority=1,
    )


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    db.save_token_usage.return_value = 1
    return db


@pytest.fixture
def agent(mock_db):
    """Create a WorkerAgent for testing."""
    return WorkerAgent(
        agent_id="backend-001",
        agent_type="backend",
        provider="anthropic",
        maturity=AgentMaturity.D1,
        system_prompt="You are a backend developer.",
        db=mock_db,
    )


@pytest.fixture
def mock_anthropic_response():
    """Create a mock Anthropic API response."""
    response = MagicMock()
    response.content = [MagicMock(text="I've added structured logging to the auth module.")]
    response.usage.input_tokens = 150
    response.usage.output_tokens = 80
    return response


class TestExecuteTaskSuccess:
    """Test successful task execution scenarios."""

    @pytest.mark.asyncio
    async def test_execute_task_returns_completed_status(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test successful execution returns 'completed' status."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                result = await agent.execute_task(sample_task)

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_task_returns_output_content(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test successful execution returns LLM output."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                result = await agent.execute_task(sample_task)

        assert result["output"] == "I've added structured logging to the auth module."

    @pytest.mark.asyncio
    async def test_execute_task_returns_token_usage(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test successful execution returns token usage dict."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                result = await agent.execute_task(sample_task)

        assert "usage" in result
        assert result["usage"]["input_tokens"] == 150
        assert result["usage"]["output_tokens"] == 80

    @pytest.mark.asyncio
    async def test_execute_task_returns_model_name(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test successful execution returns model name."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                result = await agent.execute_task(sample_task)

        assert result["model"] == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_execute_task_with_custom_model(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test execution with a custom model name."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                result = await agent.execute_task(sample_task, model_name="claude-haiku-4")

        assert result["model"] == "claude-haiku-4"

    @pytest.mark.asyncio
    async def test_execute_task_sets_current_task(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that execute_task sets current_task for project context."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                await agent.execute_task(sample_task)

        assert agent.current_task == sample_task


class TestExecuteTaskApiKeyValidation:
    """Test API key validation."""

    @pytest.mark.asyncio
    async def test_execute_task_raises_without_api_key(self, agent, sample_task):
        """Test that missing API key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure ANTHROPIC_API_KEY is not set
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]

            with pytest.raises(ValueError) as exc_info:
                await agent.execute_task(sample_task)

        assert "ANTHROPIC_API_KEY" in str(exc_info.value)
        assert ".env.example" in str(exc_info.value)


class TestExecuteTaskErrorHandling:
    """Test error handling for various API failures."""

    @pytest.mark.asyncio
    async def test_execute_task_handles_authentication_error(self, agent, sample_task):
        """Test handling of AuthenticationError."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "invalid-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    side_effect=AuthenticationError(
                        message="Invalid API key",
                        response=MagicMock(),
                        body=None,
                    )
                )

                result = await agent.execute_task(sample_task)

        assert result["status"] == "failed"
        assert "authentication" in result["output"].lower()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_task_handles_rate_limit_error(self, agent, sample_task):
        """Test handling of RateLimitError."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    side_effect=RateLimitError(
                        message="Rate limit exceeded",
                        response=MagicMock(),
                        body=None,
                    )
                )

                result = await agent.execute_task(sample_task)

        assert result["status"] == "failed"
        assert "rate limit" in result["output"].lower()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_task_handles_connection_error(self, agent, sample_task):
        """Test handling of APIConnectionError."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    side_effect=APIConnectionError(request=MagicMock())
                )

                result = await agent.execute_task(sample_task)

        assert result["status"] == "failed"
        assert "network" in result["output"].lower() or "connection" in result["output"].lower()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_task_handles_timeout_error(self, agent, sample_task):
        """Test handling of TimeoutError."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    side_effect=TimeoutError("Request timed out")
                )

                result = await agent.execute_task(sample_task)

        assert result["status"] == "failed"
        assert "timed out" in result["output"].lower()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_task_handles_generic_exception(self, agent, sample_task):
        """Test handling of unexpected exceptions."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    side_effect=RuntimeError("Unexpected internal error")
                )

                result = await agent.execute_task(sample_task)

        assert result["status"] == "failed"
        assert "RuntimeError" in result["output"]
        assert "error" in result


class TestExecuteTaskTokenTracking:
    """Test token usage tracking."""

    @pytest.mark.asyncio
    async def test_execute_task_records_token_usage(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that token usage is recorded after successful execution."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                with patch(
                    "codeframe.lib.metrics_tracker.MetricsTracker.record_token_usage",
                    new_callable=AsyncMock,
                ) as mock_tracker:
                    mock_tracker.return_value = 1

                    result = await agent.execute_task(sample_task)

                    # Verify token tracking was called
                    mock_tracker.assert_called_once()
                    call_kwargs = mock_tracker.call_args.kwargs
                    assert call_kwargs["task_id"] == sample_task.id
                    assert call_kwargs["agent_id"] == "backend-001"
                    assert call_kwargs["project_id"] == 1
                    assert call_kwargs["model_name"] == "claude-sonnet-4-5"
                    assert call_kwargs["input_tokens"] == 150
                    assert call_kwargs["output_tokens"] == 80

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_task_continues_on_tracking_failure(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that task execution succeeds even if token tracking fails."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                with patch(
                    "codeframe.lib.metrics_tracker.MetricsTracker.record_token_usage",
                    new_callable=AsyncMock,
                ) as mock_tracker:
                    mock_tracker.side_effect = Exception("Database error")

                    result = await agent.execute_task(sample_task)

        # Task should still complete successfully
        assert result["status"] == "completed"
        assert result["output"] == "I've added structured logging to the auth module."

    @pytest.mark.asyncio
    async def test_execute_task_skips_tracking_without_db(
        self, sample_task, mock_anthropic_response
    ):
        """Test that token tracking is skipped when db is None."""
        agent_no_db = WorkerAgent(
            agent_id="backend-002",
            agent_type="backend",
            provider="anthropic",
            db=None,  # No database
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                # Should not raise error, just skip tracking
                result = await agent_no_db.execute_task(sample_task)

        assert result["status"] == "completed"


class TestBuildTaskPrompt:
    """Test prompt building from task."""

    def test_build_task_prompt_includes_title(self, agent, sample_task):
        """Test that prompt includes task title."""
        prompt = agent._build_task_prompt(sample_task)

        assert sample_task.title in prompt

    def test_build_task_prompt_includes_description(self, agent, sample_task):
        """Test that prompt includes task description."""
        prompt = agent._build_task_prompt(sample_task)

        assert sample_task.description in prompt

    def test_build_task_prompt_includes_task_number(self, agent, sample_task):
        """Test that prompt includes task number."""
        prompt = agent._build_task_prompt(sample_task)

        assert sample_task.task_number in prompt

    def test_build_task_prompt_handles_empty_description(self, agent):
        """Test prompt building with empty description."""
        task = Task(
            id=1,
            project_id=1,
            task_number="1.0.1",
            title="Test Task",
            description="",
            status=TaskStatus.PENDING,
        )

        prompt = agent._build_task_prompt(task)

        assert "No description provided" in prompt

    def test_build_task_prompt_handles_none_description(self, agent):
        """Test prompt building with None description."""
        task = Task(
            id=1,
            project_id=1,
            task_number="1.0.1",
            title="Test Task",
            description=None,
            status=TaskStatus.PENDING,
        )

        prompt = agent._build_task_prompt(task)

        assert "No description provided" in prompt


class TestExecuteTaskApiCallParameters:
    """Test that correct parameters are passed to the API."""

    @pytest.mark.asyncio
    async def test_execute_task_uses_system_prompt(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that system prompt is passed to the API."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_create = AsyncMock(return_value=mock_anthropic_response)
                mock_client.return_value.messages.create = mock_create

                await agent.execute_task(sample_task)

                # Verify system prompt was passed
                call_kwargs = mock_create.call_args.kwargs
                assert call_kwargs["system"] == "You are a backend developer."

    @pytest.mark.asyncio
    async def test_execute_task_uses_default_system_prompt_when_none(
        self, sample_task, mock_anthropic_response
    ):
        """Test that default system prompt is used when none is set."""
        agent_no_prompt = WorkerAgent(
            agent_id="backend-003",
            agent_type="backend",
            provider="anthropic",
            system_prompt=None,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_create = AsyncMock(return_value=mock_anthropic_response)
                mock_client.return_value.messages.create = mock_create

                await agent_no_prompt.execute_task(sample_task)

                # Verify default system prompt was used
                call_kwargs = mock_create.call_args.kwargs
                assert "software development" in call_kwargs["system"].lower()

    @pytest.mark.asyncio
    async def test_execute_task_passes_correct_model(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that correct model is passed to the API."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_create = AsyncMock(return_value=mock_anthropic_response)
                mock_client.return_value.messages.create = mock_create

                await agent.execute_task(sample_task, model_name="claude-opus-4")

                # Verify model was passed
                call_kwargs = mock_create.call_args.kwargs
                assert call_kwargs["model"] == "claude-opus-4"

    @pytest.mark.asyncio
    async def test_execute_task_sets_max_tokens(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that max_tokens is set correctly."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_create = AsyncMock(return_value=mock_anthropic_response)
                mock_client.return_value.messages.create = mock_create

                await agent.execute_task(sample_task)

                # Verify max_tokens was set
                call_kwargs = mock_create.call_args.kwargs
                assert call_kwargs["max_tokens"] == 4096


class TestExecuteTaskEmptyResponse:
    """Test handling of empty or unusual API responses."""

    @pytest.mark.asyncio
    async def test_execute_task_handles_empty_content(self, agent, sample_task):
        """Test handling of empty content array."""
        empty_response = MagicMock()
        empty_response.content = []
        empty_response.usage.input_tokens = 50
        empty_response.usage.output_tokens = 0

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=empty_response
                )

                result = await agent.execute_task(sample_task)

        assert result["status"] == "completed"
        assert result["output"] == ""


class TestModelValidation:
    """Test model name validation."""

    @pytest.mark.asyncio
    async def test_execute_task_raises_for_unsupported_model(self, agent, sample_task):
        """Test that unsupported model names raise ValueError."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with pytest.raises(ValueError) as exc_info:
                await agent.execute_task(sample_task, model_name="gpt-4-turbo")

        assert "Unsupported model" in str(exc_info.value)
        assert "gpt-4-turbo" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_task_accepts_all_supported_models(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that all supported models are accepted."""
        from codeframe.agents.worker_agent import SUPPORTED_MODELS

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                for model in SUPPORTED_MODELS:
                    result = await agent.execute_task(sample_task, model_name=model)
                    assert result["status"] == "completed"
                    assert result["model"] == model


class TestMaxTokensParameter:
    """Test max_tokens parameter handling."""

    @pytest.mark.asyncio
    async def test_execute_task_uses_custom_max_tokens(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that custom max_tokens is passed to API."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_create = AsyncMock(return_value=mock_anthropic_response)
                mock_client.return_value.messages.create = mock_create

                await agent.execute_task(sample_task, max_tokens=8192)

                call_kwargs = mock_create.call_args.kwargs
                assert call_kwargs["max_tokens"] == 8192

    @pytest.mark.asyncio
    async def test_execute_task_uses_default_max_tokens(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that default max_tokens is 4096."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_create = AsyncMock(return_value=mock_anthropic_response)
                mock_client.return_value.messages.create = mock_create

                await agent.execute_task(sample_task)

                call_kwargs = mock_create.call_args.kwargs
                assert call_kwargs["max_tokens"] == 4096


class TestTokenTrackingFailedFlag:
    """Test token_tracking_failed result field."""

    @pytest.mark.asyncio
    async def test_token_tracking_failed_is_false_on_success(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that token_tracking_failed is False when tracking succeeds."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                with patch(
                    "codeframe.lib.metrics_tracker.MetricsTracker.record_token_usage",
                    new_callable=AsyncMock,
                ) as mock_tracker:
                    mock_tracker.return_value = 1

                    result = await agent.execute_task(sample_task)

        assert result["token_tracking_failed"] is False

    @pytest.mark.asyncio
    async def test_token_tracking_failed_is_true_on_failure(
        self, agent, sample_task, mock_anthropic_response
    ):
        """Test that token_tracking_failed is True when tracking fails."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                with patch(
                    "codeframe.lib.metrics_tracker.MetricsTracker.record_token_usage",
                    new_callable=AsyncMock,
                ) as mock_tracker:
                    mock_tracker.side_effect = Exception("Database error")

                    result = await agent.execute_task(sample_task)

        assert result["status"] == "completed"
        assert result["token_tracking_failed"] is True

    @pytest.mark.asyncio
    async def test_token_tracking_failed_is_false_when_no_db(
        self, sample_task, mock_anthropic_response
    ):
        """Test that token_tracking_failed is False when db is None (skipped)."""
        agent_no_db = WorkerAgent(
            agent_id="backend-004",
            agent_type="backend",
            provider="anthropic",
            db=None,
        )

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("codeframe.agents.worker_agent.AsyncAnthropic") as mock_client:
                mock_client.return_value.messages.create = AsyncMock(
                    return_value=mock_anthropic_response
                )

                result = await agent_no_db.execute_task(sample_task)

        assert result["token_tracking_failed"] is False
