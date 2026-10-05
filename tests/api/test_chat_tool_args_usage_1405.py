"""An interrupted chat call is charged for the tool arguments it streamed (#1405).

A call cut short before message_stop reports no usage, so #1345 charges an
estimate from the prompt plus the *streamed text*. Neither provider passed
tool-argument output through: Anthropic dropped ``input_json_delta`` and the
OpenAI adapter only accumulated argument fragments. A call interrupted while
writing a large tool input was charged about one output token for it.

Driven through the real providers (fake SDK streams) and the real producer.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

import pytest

from codeframe.adapters.llm.anthropic import AnthropicProvider
from codeframe.adapters.llm.openai import OpenAIProvider
from tests.api.test_session_chat_spend_1345 import _rows, chat_ws  # noqa: F401

pytestmark = pytest.mark.v2

ARGS = '{"path": "' + "a" * 3000 + '"}'  # ~3000 chars of tool input
CHUNK = 100


class _AnthropicStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._events()

    async def _events(self):
        yield NS(type="message_start")
        yield NS(type="content_block_start",
                 content_block=NS(type="tool_use", id="t1", name="read_file", input={}))
        for i in range(0, len(ARGS), CHUNK):
            yield NS(type="content_block_delta",
                     delta=NS(type="input_json_delta", partial_json=ARGS[i:i + CHUNK]))
        await asyncio.Event().wait()  # cut off before message_stop


def _anthropic():
    p = AnthropicProvider(api_key="sk-test")
    p._async_client = NS(messages=NS(stream=lambda **kw: _AnthropicStream()),
                         beta=NS(messages=NS(stream=lambda **kw: _AnthropicStream())))
    return p


def _openai():
    async def chunks():
        for i in range(0, len(ARGS), CHUNK):
            tc = NS(index=0, id="c1" if i == 0 else None,
                    function=NS(name="read_file" if i == 0 else None, arguments=ARGS[i:i + CHUNK]))
            yield NS(usage=None, choices=[NS(finish_reason=None, delta=NS(content=None, tool_calls=[tc]))])
        await asyncio.Event().wait()

    async def create(**kw):
        return chunks()

    p = OpenAIProvider(api_key="sk-test")
    p._async_client = NS(chat=NS(completions=NS(create=create)))
    return p


@pytest.mark.parametrize("make", [_anthropic, _openai], ids=["anthropic", "openai"])
def test_a_call_cut_off_mid_tool_arguments_is_charged_for_them(chat_ws, monkeypatch, make):  # noqa: F811
    from codeframe.ui.routers import session_chat_ws as mod

    monkeypatch.setattr("codeframe.core.llm_resolution.create_provider", lambda *a, **k: make())
    monkeypatch.setattr(mod.StreamingChatAdapter, "_load_history", lambda self: [])
    monkeypatch.setattr(mod.StreamingChatAdapter, "_persist_turn", lambda self, *a: asyncio.sleep(0))

    async def go():
        task = asyncio.create_task(mod._run_streaming_adapter(
            "s1", "Hi", asyncio.Queue(), asyncio.Event(), None, chat_ws.repo_path,
            usage_workspace=chat_ws,
        ))
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return _rows(chat_ws)

    rows = asyncio.run(go())
    assert len(rows) == 1, rows
    # At least the argument tokens produced, at any sane chars/token ratio.
    assert rows[0][1] >= len(ARGS) // 4, rows
