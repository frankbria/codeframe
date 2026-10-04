"""Interactive session chat is inside the daily spend limit (#1345).

Chat spent tokens the limit never saw: its cost went only to the session row,
not to the workspace token_usage the limit sums, and nothing checked the
limit before a message was sent to the model.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from codeframe.auth.stream_tickets import mint_ticket
from codeframe.core.models import TokenUsage
from codeframe.core.workspace import create_or_load_workspace
from codeframe.platform_store.repositories.token_repository import TokenRepository
from tests.api.test_session_chat_ws import _create_session, _ws_url

pytestmark = pytest.mark.v2

LIMIT_ENV = "CODEFRAME_USER_DAILY_COST_LIMIT_USD"


@pytest.fixture
def chat_ws():
    path = os.path.join(os.environ.get("WORKSPACE_ROOT", "/tmp"), "ws-spend-1345")
    os.makedirs(path, exist_ok=True)
    return create_or_load_workspace(__import__("pathlib").Path(path))


def _turn(api_client: TestClient, session_id: str, events):
    calls = []

    async def fake_adapter(session_id, user_message, token_queue, *a, **k):
        calls.append(user_message)
        for e in events:
            await token_queue.put(e)
        await token_queue.put({"type": "done"})

    received = []
    with patch("codeframe.ui.routers.session_chat_ws._run_streaming_adapter", side_effect=fake_adapter):
        with api_client.websocket_connect(_ws_url(session_id, mint_ticket(user_id=1))) as ws:
            ws.send_json({"type": "message", "content": "Hi"})
            while True:
                msg = ws.receive_json()
                received.append(msg)
                if msg["type"] in ("done", "error"):
                    break
    return calls, received


def test_the_socket_hands_the_producer_its_ledger(api_client: TestClient, chat_ws):
    """The producer records (test below); the socket must give it the ledger."""
    seen = {}

    async def fake_adapter(session_id, user_message, token_queue, *a, **k):
        seen.update(k)
        await token_queue.put({"type": "done"})

    session_id = _create_session(api_client, str(chat_ws.repo_path))
    with patch("codeframe.ui.routers.session_chat_ws._run_streaming_adapter", side_effect=fake_adapter):
        with api_client.websocket_connect(_ws_url(session_id, mint_ticket(user_id=1))) as ws:
            ws.send_json({"type": "message", "content": "Hi"})
            assert ws.receive_json()["type"] == "done"
    assert seen["usage_workspace"].repo_path == chat_ws.repo_path


def test_a_message_over_the_limit_is_refused_before_the_model_is_called(
    api_client: TestClient, chat_ws, monkeypatch
):
    monkeypatch.setenv(LIMIT_ENV, "1")
    conn = sqlite3.connect(str(chat_ws.db_path))
    try:
        TokenRepository(sync_conn=conn).save_token_usage(TokenUsage(
            task_id="x", agent_id="react", project_id=0, model_name="claude-sonnet-4-5",
            input_tokens=1, output_tokens=1, estimated_cost_usd=5.0,
            timestamp=datetime.now(timezone.utc),
        ))
    finally:
        conn.close()
    session_id = _create_session(api_client, str(chat_ws.repo_path))
    # A signed-in user: the auth-off operator (user_id None) is never limited,
    # here as on the REST routes.
    db = api_client.app.state.db
    db.conn.execute("UPDATE interactive_sessions SET user_id = 1 WHERE id = ?", (session_id,))
    db.conn.commit()

    from unittest.mock import AsyncMock

    with patch(
        "codeframe.ui.routers.session_chat_ws._authenticate_websocket",
        new=AsyncMock(return_value=(True, 1)),
    ):
        calls, received = _turn(api_client, session_id, [])

    assert calls == []
    assert received[-1]["type"] == "error"
    assert received[-1]["code"] == "SPEND_LIMIT_EXCEEDED"


def test_chat_without_a_ledger_is_refused_while_a_limit_is_on(api_client: TestClient, monkeypatch):
    """A session in a directory that is not an initialised workspace has no
    ledger, so its spend can be neither counted nor recorded. That failed
    open: an over-budget user chatted on unlimited (both reviews)."""
    monkeypatch.setenv(LIMIT_ENV, "1")
    path = os.path.join(os.environ.get("WORKSPACE_ROOT", "/tmp"), "not-a-workspace-1345")
    os.makedirs(path, exist_ok=True)
    session_id = _create_session(api_client, path)
    db = api_client.app.state.db
    db.conn.execute("UPDATE interactive_sessions SET user_id = 1 WHERE id = ?", (session_id,))
    db.conn.commit()

    from unittest.mock import AsyncMock

    with patch(
        "codeframe.ui.routers.session_chat_ws._authenticate_websocket",
        new=AsyncMock(return_value=(True, 1)),
    ):
        calls, received = _turn(api_client, session_id, [])

    assert calls == []
    assert received[-1]["code"] == "SPEND_LIMIT_EXCEEDED"


def test_a_chat_turn_releases_its_hold_when_it_ends(api_client: TestClient, chat_ws, monkeypatch):
    """Each turn reserves a budget; a hold left behind would shrink every
    later turn's share until midnight."""
    import time

    from codeframe.core import spend_limit

    monkeypatch.setenv(LIMIT_ENV, "50")
    session_id = _create_session(api_client, str(chat_ws.repo_path))
    db = api_client.app.state.db
    db.conn.execute("UPDATE interactive_sessions SET user_id = 1 WHERE id = ?", (session_id,))
    db.conn.commit()

    from unittest.mock import AsyncMock

    with patch(
        "codeframe.ui.routers.session_chat_ws._authenticate_websocket",
        new=AsyncMock(return_value=(True, 1)),
    ):
        calls, _ = _turn(api_client, session_id, [])
    assert calls == ["Hi"]
    for _ in range(50):  # the done-callback runs as the task finishes
        if not spend_limit._held:
            break
        time.sleep(0.05)
    assert not spend_limit._held


class _Provider:
    """Streams one text chunk, then finishes, stops (interrupt) or hangs."""

    def __init__(self, end):
        self.end = end

    def supports(self, _feature):
        return False

    async def async_stream(self, **kw):
        import asyncio

        from codeframe.adapters.llm.base import StreamChunk

        yield StreamChunk(type="text_delta", text="x" * 300)
        if self.end == "finish":
            yield StreamChunk(type="message_stop", stop_reason="end_turn", input_tokens=1000, output_tokens=200)
        elif self.end == "hang":
            await asyncio.Event().wait()
        # "stop": return early, as AnthropicProvider does when interrupted


def _rows(ws):
    conn = sqlite3.connect(str(ws.db_path))
    try:
        return conn.execute("SELECT input_tokens, output_tokens, call_type FROM token_usage").fetchall()
    finally:
        conn.close()


def _drive(chat_ws, monkeypatch, end, cancel=False):
    """Run the real producer + StreamingChatAdapter; nothing reads the queue."""
    import asyncio

    from codeframe.ui.routers import session_chat_ws as mod

    monkeypatch.setattr("codeframe.core.llm_resolution.create_provider", lambda *a, **k: _Provider(end))
    monkeypatch.setattr(mod.StreamingChatAdapter, "_load_history", lambda self: [])
    monkeypatch.setattr(mod.StreamingChatAdapter, "_persist_turn", lambda self, *a: asyncio.sleep(0))

    async def go():
        task = asyncio.create_task(mod._run_streaming_adapter(
            "s1", "Hi", asyncio.Queue(), asyncio.Event(), None, chat_ws.repo_path,
            usage_workspace=chat_ws,
        ))
        if cancel:
            await asyncio.sleep(0.2)
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # Read here, as the task ends (when its hold is released): after
        # asyncio.run, shutdown would have finalized any abandoned generator.
        return _rows(chat_ws)

    return asyncio.run(go())


def test_chat_usage_is_recorded_by_the_producer_not_the_socket(chat_ws, monkeypatch):
    """The turn's hold is released when the adapter task ends. Recording in
    the relay let that happen before the rows were written, and a disconnect
    dropped them entirely (codex P1)."""
    assert _drive(chat_ws, monkeypatch, "finish") == [(1000, 200, "session_chat")]


@pytest.mark.parametrize("end,cancel", [("stop", False), ("hang", True)], ids=["interrupted", "cancelled"])
def test_a_call_cut_short_is_still_counted(chat_ws, monkeypatch, end, cancel):
    """An interrupted or cancelled call reports no usage, so it went
    uncounted and repeated interrupts spent past the limit (codex P1)."""
    rows = _drive(chat_ws, monkeypatch, end, cancel)
    assert len(rows) == 1 and rows[0][2] == "session_chat", rows
    assert rows[0][0] > 0 and rows[0][1] >= 100, rows  # 300 streamed chars


def test_a_new_message_replaces_a_turn_that_holds_the_whole_budget(api_client: TestClient, chat_ws, monkeypatch):
    """An active turn holds all that is left, so reserving before cancelling it
    refused every replacement message (codex P2)."""
    import asyncio
    from unittest.mock import AsyncMock

    monkeypatch.setenv(LIMIT_ENV, "50")
    session_id = _create_session(api_client, str(chat_ws.repo_path))
    db = api_client.app.state.db
    db.conn.execute("UPDATE interactive_sessions SET user_id = 1 WHERE id = ?", (session_id,))
    db.conn.commit()
    calls = []

    async def fake_adapter(session_id, user_message, token_queue, *a, **k):
        calls.append(user_message)
        if user_message == "first":
            await asyncio.Event().wait()  # in flight until cancelled
        await token_queue.put({"type": "done"})

    with patch("codeframe.ui.routers.session_chat_ws._authenticate_websocket",
               new=AsyncMock(return_value=(True, 1))), \
         patch("codeframe.ui.routers.session_chat_ws._run_streaming_adapter", side_effect=fake_adapter):
        with api_client.websocket_connect(_ws_url(session_id, mint_ticket(user_id=1))) as ws:
            ws.send_json({"type": "message", "content": "first"})
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"  # the first turn is running
            ws.send_json({"type": "message", "content": "second"})
            msg = ws.receive_json()

    assert msg["type"] == "done", msg
    assert calls == ["first", "second"]
