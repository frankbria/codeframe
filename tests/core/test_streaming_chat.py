"""Unit tests for StreamingChatAdapter.

Uses MockProvider with async_stream() to drive streaming scenarios without
real API calls.  All streaming events are exercised: TEXT_DELTA, THINKING,
TOOL_USE_START, TOOL_RESULT, COST_UPDATE, DONE, ERROR.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codeframe.adapters.llm.base import StreamChunk
from codeframe.adapters.llm.mock import MockProvider
from codeframe.core.adapters.streaming_chat import (
    ChatEventType,
    StreamingChatAdapter,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_db_repo(messages: list[dict] | None = None):
    """Create a mock DB repo with pre-loaded messages."""
    repo = MagicMock()
    repo.get_messages.return_value = messages or []
    repo.add_message.return_value = {"id": str(uuid.uuid4())}
    return repo


def _stop_chunk(
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 20,
    tool_inputs_by_id: dict | None = None,
) -> StreamChunk:
    return StreamChunk(
        type="message_stop",
        stop_reason=stop_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_inputs_by_id=tool_inputs_by_id or {},
    )


def _make_adapter(
    session_id: str = "s1",
    db_repo=None,
    workspace_path: Path | None = None,
    provider: MockProvider | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> StreamingChatAdapter:
    return StreamingChatAdapter(
        session_id=session_id,
        db_repo=db_repo or _make_db_repo(),
        workspace_path=workspace_path or Path("/tmp"),
        model=model,
        provider=provider or MockProvider(),
    )


# ---------------------------------------------------------------------------
# Adapter construction
# ---------------------------------------------------------------------------


class TestStreamingChatAdapterInit:
    def test_raises_if_no_api_key(self, monkeypatch):
        """When no provider is supplied, the default AnthropicProvider raises."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            StreamingChatAdapter(
                session_id="s1",
                db_repo=_make_db_repo(),
                workspace_path=Path("/tmp"),
            )

    def test_accepts_explicit_provider(self):
        adapter = _make_adapter()
        assert adapter._session_id == "s1"
        assert isinstance(adapter._provider, MockProvider)

    def test_default_model(self):
        adapter = _make_adapter()
        assert adapter._model == "claude-sonnet-4-20250514"

    def test_custom_model(self):
        adapter = _make_adapter(model="claude-opus-4-20250514")
        assert adapter._model == "claude-opus-4-20250514"

    def test_accepts_api_key_from_env(self, monkeypatch):
        """Legacy path: no provider given but ANTHROPIC_API_KEY set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        adapter = StreamingChatAdapter(
            session_id="s1",
            db_repo=_make_db_repo(),
            workspace_path=Path("/tmp"),
        )
        assert adapter._session_id == "s1"


# ---------------------------------------------------------------------------
# History loading
# ---------------------------------------------------------------------------


class TestLoadHistory:
    def test_empty_history(self):
        repo = _make_db_repo([])
        adapter = _make_adapter(db_repo=repo)
        history = adapter._load_history()
        assert history == []

    def test_converts_messages(self):
        stored = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        repo = _make_db_repo(stored)
        adapter = _make_adapter(db_repo=repo)
        history = adapter._load_history()
        assert history == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]


# ---------------------------------------------------------------------------
# History truncation
# ---------------------------------------------------------------------------


class TestTruncateHistory:
    def test_result_starts_with_user_message(self):
        adapter = _make_adapter()
        msgs = [
            {"role": "user", "content": "a" * 100},
            {"role": "assistant", "content": "b" * 100},
            {"role": "user", "content": "c"},
        ]
        result = adapter._truncate_history(msgs)
        assert result[0]["role"] == "user"

    def test_empty_list_unchanged(self):
        adapter = _make_adapter()
        assert adapter._truncate_history([]) == []

    def test_no_truncation_when_within_budget(self):
        adapter = _make_adapter()
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = adapter._truncate_history(msgs)
        assert result == msgs


# ---------------------------------------------------------------------------
# send_message — text-only turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSendMessageTextOnly:
    async def test_yields_text_delta_events(self, tmp_path):
        provider = MockProvider()
        provider.add_stream_chunks([
            StreamChunk(type="text_delta", text="Hello"),
            StreamChunk(type="text_delta", text=" world"),
            _stop_chunk(),
        ])
        adapter = _make_adapter(workspace_path=tmp_path, provider=provider)

        collected = [e async for e in adapter.send_message("hi", [])]
        types = [e.type for e in collected]
        assert ChatEventType.TEXT_DELTA in types
        assert ChatEventType.COST_UPDATE in types
        assert ChatEventType.DONE in types

    async def test_text_delta_content(self, tmp_path):
        provider = MockProvider()
        provider.add_stream_chunks([
            StreamChunk(type="text_delta", text="Hello"),
            StreamChunk(type="text_delta", text=" world"),
            _stop_chunk(),
        ])
        adapter = _make_adapter(workspace_path=tmp_path, provider=provider)

        deltas = [
            e.content
            async for e in adapter.send_message("hi", [])
            if e.type == ChatEventType.TEXT_DELTA
        ]
        assert deltas == ["Hello", " world"]

    async def test_cost_update_has_token_counts(self, tmp_path):
        provider = MockProvider()
        provider.add_stream_chunks([
            StreamChunk(type="text_delta", text="ok"),
            _stop_chunk(input_tokens=10, output_tokens=20),
        ])
        adapter = _make_adapter(workspace_path=tmp_path, provider=provider)

        cost_events = [
            e
            async for e in adapter.send_message("hi", [])
            if e.type == ChatEventType.COST_UPDATE
        ]
        assert len(cost_events) == 1
        assert cost_events[0].input_tokens == 10
        assert cost_events[0].output_tokens == 20

    async def test_done_is_last_event(self, tmp_path):
        provider = MockProvider()
        provider.add_stream_chunks([
            StreamChunk(type="text_delta", text="hi"),
            _stop_chunk(),
        ])
        adapter = _make_adapter(workspace_path=tmp_path, provider=provider)
        collected = [e async for e in adapter.send_message("hi", [])]
        assert collected[-1].type == ChatEventType.DONE


# ---------------------------------------------------------------------------
# send_message — thinking events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestThinkingEvents:
    async def test_yields_thinking_events(self, tmp_path):
        provider = MockProvider()
        provider.add_stream_chunks([
            StreamChunk(type="thinking_delta", text="Let me think..."),
            StreamChunk(type="text_delta", text="Answer"),
            _stop_chunk(),
        ])
        adapter = _make_adapter(workspace_path=tmp_path, provider=provider)

        thinking_events = [
            e
            async for e in adapter.send_message("hi", [])
            if e.type == ChatEventType.THINKING
        ]
        assert len(thinking_events) == 1
        assert thinking_events[0].content == "Let me think..."

    async def test_non_anthropic_provider_no_thinking(self, tmp_path):
        """Providers that don't emit thinking_delta produce no THINKING events."""
        provider = MockProvider()
        provider.add_stream_chunks([
            StreamChunk(type="text_delta", text="Answer"),
            _stop_chunk(),
        ])
        adapter = _make_adapter(workspace_path=tmp_path, provider=provider)

        thinking_events = [
            e
            async for e in adapter.send_message("hi", [])
            if e.type == ChatEventType.THINKING
        ]
        assert thinking_events == []


# ---------------------------------------------------------------------------
# send_message — tool calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestToolCallEvents:
    async def test_yields_tool_use_start_and_result(self, tmp_path):
        tool_id = "tool_abc"
        tool_input = {"path": "README.md"}

        provider = MockProvider()
        # First turn: tool_use with stop_reason="tool_use"
        provider.add_stream_chunks([
            StreamChunk(
                type="tool_use_start",
                tool_id=tool_id,
                tool_name="read_file",
                tool_input=tool_input,
            ),
            StreamChunk(type="tool_use_stop"),
            _stop_chunk(
                stop_reason="tool_use",
                tool_inputs_by_id={tool_id: tool_input},
            ),
        ])
        # Second turn: text response
        provider.add_stream_chunks([
            StreamChunk(type="text_delta", text="Here is the file content."),
            _stop_chunk(),
        ])

        adapter = _make_adapter(workspace_path=tmp_path, provider=provider)

        with patch.object(adapter, "_execute_tool", new_callable=AsyncMock) as mock_tool:
            mock_tool.return_value = "file contents here"
            collected = [e async for e in adapter.send_message("read README", [])]

        types = [e.type for e in collected]
        assert ChatEventType.TOOL_USE_START in types
        assert ChatEventType.TOOL_RESULT in types

        start = next(e for e in collected if e.type == ChatEventType.TOOL_USE_START)
        assert start.tool_name == "read_file"
        assert start.tool_input == tool_input

        result = next(e for e in collected if e.type == ChatEventType.TOOL_RESULT)
        assert result.content == "file contents here"


# ---------------------------------------------------------------------------
# Interrupt support
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInterrupt:
    async def test_interrupt_event_stops_stream(self, tmp_path):
        interrupt = asyncio.Event()

        # Build a lot of chunks so interrupt has time to fire
        chunks = [StreamChunk(type="text_delta", text=f"chunk{i}") for i in range(100)]
        # Inject message_stop at the end
        chunks.append(_stop_chunk())

        provider = MockProvider()

        async def _slow_stream(*args, **kwargs):
            for i, chunk in enumerate(chunks):
                if interrupt.is_set():
                    return
                yield chunk
                if i == 2:
                    interrupt.set()

        provider.async_stream = _slow_stream

        adapter = _make_adapter(workspace_path=tmp_path, provider=provider)
        collected = [e async for e in adapter.send_message("hi", [], interrupt)]

        text_deltas = [e for e in collected if e.type == ChatEventType.TEXT_DELTA]
        assert len(text_deltas) < 20


# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPersistence:
    async def test_messages_persisted_after_turn(self, tmp_path):
        repo = _make_db_repo()
        provider = MockProvider()
        provider.add_stream_chunks([
            StreamChunk(type="text_delta", text="response text"),
            _stop_chunk(),
        ])
        adapter = _make_adapter(db_repo=repo, workspace_path=tmp_path, provider=provider)
        _ = [e async for e in adapter.send_message("user input", [])]

        # Two calls: one for user message, one for assistant message
        assert repo.add_message.call_count == 2
        calls = repo.add_message.call_args_list
        roles = [c.kwargs.get("role") or c.args[1] for c in calls]
        assert "user" in roles
        assert "assistant" in roles


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestErrorHandling:
    async def test_yields_error_event_on_api_failure(self, tmp_path):
        provider = MockProvider()

        async def _error_stream(*args, **kwargs):
            raise RuntimeError("API failure")
            if False:
                yield  # make it an async generator

        provider.async_stream = _error_stream

        adapter = _make_adapter(workspace_path=tmp_path, provider=provider)
        collected = [e async for e in adapter.send_message("hi", [])]

        error_events = [e for e in collected if e.type == ChatEventType.ERROR]
        assert len(error_events) == 1
        assert "API failure" in error_events[0].content
