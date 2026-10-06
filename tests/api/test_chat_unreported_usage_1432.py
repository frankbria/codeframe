"""A finished chat call whose endpoint reports no usage is still billed (#1432).

`OpenAIProvider.async_stream` asks for usage with `include_usage`, but some
OpenAI-compatible servers (local ollama/vllm, some proxies) never send it. The
counters started at 0, so the finished call's `message_stop` said (0, 0) and
was billed as nothing: less than the same call cut off mid-stream, which gets
the #1345 estimate, and invisible to the daily spend limit.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

import pytest

from codeframe.adapters.llm.openai import OpenAIProvider
from tests.api.test_session_chat_spend_1345 import _rows, chat_ws  # noqa: F401

pytestmark = pytest.mark.v2

REPLY = "x" * 600


def _openai(with_usage: bool):
    async def chunks():
        yield NS(usage=None, choices=[NS(finish_reason=None, delta=NS(content=REPLY, tool_calls=None))])
        yield NS(usage=None, choices=[NS(finish_reason="stop", delta=NS(content=None, tool_calls=None))])
        if with_usage:
            yield NS(usage=NS(prompt_tokens=123, completion_tokens=45), choices=[])

    async def create(**kw):
        return chunks()

    p = OpenAIProvider(api_key="sk-test")
    p._async_client = NS(chat=NS(completions=NS(create=create)))
    return p


def _drive(chat_ws, monkeypatch, with_usage):  # noqa: F811
    from codeframe.ui.routers import session_chat_ws as mod

    monkeypatch.setattr("codeframe.core.llm_resolution.create_provider", lambda *a, **k: _openai(with_usage))
    monkeypatch.setattr(mod.StreamingChatAdapter, "_load_history", lambda self: [])
    monkeypatch.setattr(mod.StreamingChatAdapter, "_persist_turn", lambda self, *a: asyncio.sleep(0))

    async def go():
        await mod._run_streaming_adapter(
            "s1", "Hi", asyncio.Queue(), asyncio.Event(), None, chat_ws.repo_path,
            usage_workspace=chat_ws,
        )
        return _rows(chat_ws)

    return asyncio.run(go())


def test_a_finished_call_with_no_usage_reported_is_billed_an_estimate(chat_ws, monkeypatch):  # noqa: F811
    rows = _drive(chat_ws, monkeypatch, with_usage=False)
    assert len(rows) == 1, rows
    assert rows[0][0] > 0 and rows[0][1] >= len(REPLY) // 4, rows


def test_reported_usage_is_still_billed_exactly(chat_ws, monkeypatch):  # noqa: F811
    assert _drive(chat_ws, monkeypatch, with_usage=True) == [(123, 45, "session_chat")]
