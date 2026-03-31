"""Unit tests for StreamingChatAdapter.

Uses mocked AsyncAnthropic client to avoid real API calls.
All streaming events are exercised: TEXT_DELTA, THINKING, TOOL_USE_START,
TOOL_RESULT, COST_UPDATE, DONE, ERROR.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from codeframe.core.adapters.streaming_chat import (
    ChatEvent,
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


def _make_stream_events(events: list[dict]) -> AsyncIterator:
    """Async iterator of mock SDK events for use in stream context manager."""

    class _MockStreamCM:
        def __init__(self, evts):
            self._events = evts
            self._final_message = MagicMock()
            self._final_message.usage.input_tokens = 10
            self._final_message.usage.output_tokens = 20
            self._final_message.stop_reason = "end_turn"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def __aiter__(self):
            return self._iter()

        async def _iter(self):
            for evt in self._events:
                yield evt

        def get_final_message(self):
            return self._final_message

    return _MockStreamCM(events)


def _text_event(text: str):
    evt = MagicMock()
    evt.type = "content_block_delta"
    evt.delta = MagicMock()
    evt.delta.type = "text_delta"
    evt.delta.text = text
    return evt


def _thinking_event(text: str):
    evt = MagicMock()
    evt.type = "content_block_delta"
    evt.delta = MagicMock()
    evt.delta.type = "thinking_delta"
    evt.delta.thinking = text
    return evt


def _tool_start_event(tool_name: str, tool_id: str, tool_input: dict):
    evt = MagicMock()
    evt.type = "content_block_start"
    evt.content_block = MagicMock()
    evt.content_block.type = "tool_use"
    evt.content_block.name = tool_name
    evt.content_block.id = tool_id
    evt.content_block.input = tool_input
    return evt


def _tool_stop_event(tool_id: str):
    evt = MagicMock()
    evt.type = "content_block_stop"
    evt.index = 0
    # Signal that this stop corresponds to a tool_use block
    evt._tool_id = tool_id
    return evt


def _message_stop_event():
    evt = MagicMock()
    evt.type = "message_stop"
    return evt


# ---------------------------------------------------------------------------
# Adapter construction
# ---------------------------------------------------------------------------


class TestStreamingChatAdapterInit:
    def test_raises_if_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            StreamingChatAdapter(
                session_id="s1",
                db_repo=_make_db_repo(),
                workspace_path=Path("/tmp"),
            )

    def test_accepts_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        adapter = StreamingChatAdapter(
            session_id="s1",
            db_repo=_make_db_repo(),
            workspace_path=Path("/tmp"),
        )
        assert adapter._session_id == "s1"

    def test_default_model(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        adapter = StreamingChatAdapter(
            session_id="s1",
            db_repo=_make_db_repo(),
            workspace_path=Path("/tmp"),
        )
        assert adapter._model == "claude-sonnet-4-20250514"

    def test_custom_model(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        adapter = StreamingChatAdapter(
            session_id="s1",
            db_repo=_make_db_repo(),
            workspace_path=Path("/tmp"),
            model="claude-opus-4-20250514",
        )
        assert adapter._model == "claude-opus-4-20250514"


# ---------------------------------------------------------------------------
# History loading
# ---------------------------------------------------------------------------


class TestLoadHistory:
    def test_empty_history(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo([])
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=Path("/tmp")
        )
        history = adapter._load_history()
        assert history == []

    def test_converts_messages_to_anthropic_format(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        stored = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        repo = _make_db_repo(stored)
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=Path("/tmp")
        )
        history = adapter._load_history()
        assert history == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]


# ---------------------------------------------------------------------------
# send_message — text-only turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSendMessageTextOnly:
    async def test_yields_text_delta_events(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo()
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=tmp_path
        )

        sdk_events = [
            _text_event("Hello"),
            _text_event(" world"),
            _message_stop_event(),
        ]

        with patch.object(adapter, "_async_client") as mock_client:
            mock_client.messages.stream.return_value = _make_stream_events(sdk_events)

            collected = []
            async for event in adapter.send_message("hi", []):
                collected.append(event)

        types = [e.type for e in collected]
        assert ChatEventType.TEXT_DELTA in types
        assert ChatEventType.COST_UPDATE in types
        assert ChatEventType.DONE in types

    async def test_text_delta_content(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo()
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=tmp_path
        )

        sdk_events = [
            _text_event("Hello"),
            _text_event(" world"),
            _message_stop_event(),
        ]

        with patch.object(adapter, "_async_client") as mock_client:
            mock_client.messages.stream.return_value = _make_stream_events(sdk_events)

            deltas = [
                e.content
                async for e in adapter.send_message("hi", [])
                if e.type == ChatEventType.TEXT_DELTA
            ]

        assert deltas == ["Hello", " world"]

    async def test_cost_update_has_token_counts(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo()
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=tmp_path
        )

        sdk_events = [_text_event("ok"), _message_stop_event()]

        with patch.object(adapter, "_async_client") as mock_client:
            mock_client.messages.stream.return_value = _make_stream_events(sdk_events)

            cost_events = [
                e
                async for e in adapter.send_message("hi", [])
                if e.type == ChatEventType.COST_UPDATE
            ]

        assert len(cost_events) == 1
        assert cost_events[0].input_tokens == 10
        assert cost_events[0].output_tokens == 20

    async def test_done_is_last_event(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo()
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=tmp_path
        )

        sdk_events = [_text_event("hi"), _message_stop_event()]

        with patch.object(adapter, "_async_client") as mock_client:
            mock_client.messages.stream.return_value = _make_stream_events(sdk_events)

            collected = [e async for e in adapter.send_message("hi", [])]

        assert collected[-1].type == ChatEventType.DONE


# ---------------------------------------------------------------------------
# send_message — thinking events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestThinkingEvents:
    async def test_yields_thinking_events(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo()
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=tmp_path
        )

        sdk_events = [
            _thinking_event("Let me think..."),
            _text_event("Answer"),
            _message_stop_event(),
        ]

        with patch.object(adapter, "_async_client") as mock_client:
            mock_client.messages.stream.return_value = _make_stream_events(sdk_events)

            thinking_events = [
                e
                async for e in adapter.send_message("hi", [])
                if e.type == ChatEventType.THINKING
            ]

        assert len(thinking_events) == 1
        assert thinking_events[0].content == "Let me think..."


# ---------------------------------------------------------------------------
# send_message — tool calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestToolCallEvents:
    async def test_yields_tool_use_start_and_result(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo()
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=tmp_path
        )

        tool_id = "tool_abc"
        tool_input = {"path": "README.md"}

        # First turn: tool_use stop_reason, second turn: end_turn
        first_stream = _make_stream_events([
            _tool_start_event("read_file", tool_id, tool_input),
            _message_stop_event(),
        ])
        # Override stop_reason on first stream's final message
        first_stream._final_message.stop_reason = "tool_use"

        second_stream = _make_stream_events([
            _text_event("Here is the file content."),
            _message_stop_event(),
        ])

        call_count = 0

        def _fake_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            return first_stream if call_count == 1 else second_stream

        with patch.object(adapter, "_async_client") as mock_client:
            mock_client.messages.stream.side_effect = _fake_stream

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
    async def test_interrupt_event_stops_stream(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo()
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=tmp_path
        )

        interrupt = asyncio.Event()

        class _SlowStream:
            def __init__(self):
                self._final_message = MagicMock()
                self._final_message.usage.input_tokens = 0
                self._final_message.usage.output_tokens = 0
                self._final_message.stop_reason = "end_turn"

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                for i in range(100):
                    if interrupt.is_set():
                        return
                    evt = MagicMock()
                    evt.type = "content_block_delta"
                    evt.delta = MagicMock()
                    evt.delta.type = "text_delta"
                    evt.delta.text = f"chunk{i}"
                    yield evt
                    # Set interrupt mid-stream
                    if i == 2:
                        interrupt.set()

            def get_final_message(self):
                return self._final_message

        with patch.object(adapter, "_async_client") as mock_client:
            mock_client.messages.stream.return_value = _SlowStream()

            collected = [e async for e in adapter.send_message("hi", [], interrupt)]

        # Should stop well before 100 chunks
        text_deltas = [e for e in collected if e.type == ChatEventType.TEXT_DELTA]
        assert len(text_deltas) < 20


# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPersistence:
    async def test_messages_persisted_after_turn(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo()
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=tmp_path
        )

        sdk_events = [_text_event("response text"), _message_stop_event()]

        with patch.object(adapter, "_async_client") as mock_client:
            mock_client.messages.stream.return_value = _make_stream_events(sdk_events)

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
    async def test_yields_error_event_on_api_failure(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        repo = _make_db_repo()
        adapter = StreamingChatAdapter(
            session_id="s1", db_repo=repo, workspace_path=tmp_path
        )

        class _ErrorStream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                raise RuntimeError("API failure")
                yield  # make it a generator

        with patch.object(adapter, "_async_client") as mock_client:
            mock_client.messages.stream.return_value = _ErrorStream()

            collected = [e async for e in adapter.send_message("hi", [])]

        error_events = [e for e in collected if e.type == ChatEventType.ERROR]
        assert len(error_events) == 1
        assert "API failure" in error_events[0].content
