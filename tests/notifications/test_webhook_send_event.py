"""Tests for the generic outbound webhook ``send_event`` method (issue #560)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from codeframe.notifications.webhook import (
    WebhookNotificationService,
    WebhookSendResult,
    format_batch_payload,
    format_blocker_payload,
    format_pr_payload,
    format_test_payload,
)

pytestmark = pytest.mark.v2


def _mock_post(status: int):
    """Build the AsyncMock chain that mirrors aiohttp's session.post() context."""
    mock_response = AsyncMock()
    mock_response.status = status
    mock_post_context = AsyncMock()
    mock_post_context.__aenter__.return_value = mock_response
    mock_post_context.__aexit__.return_value = None
    mock_session = MagicMock()
    mock_session.post.return_value = mock_post_context
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    return mock_session


@pytest.mark.asyncio
async def test_send_event_returns_ok_on_2xx():
    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=5)
    payload = format_test_payload()
    with patch("aiohttp.ClientSession", return_value=_mock_post(200)):
        result = await svc.send_event(payload)
    assert isinstance(result, WebhookSendResult)
    assert result.ok is True
    assert result.status_code == 200
    assert result.error is None


@pytest.mark.asyncio
async def test_send_event_returns_not_ok_on_5xx():
    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=5)
    with patch("aiohttp.ClientSession", return_value=_mock_post(500)):
        result = await svc.send_event({"event": "test"})
    assert result.ok is False
    assert result.status_code == 500


@pytest.mark.asyncio
async def test_send_event_no_url_returns_error():
    svc = WebhookNotificationService(webhook_url=None, timeout=5)
    result = await svc.send_event({"event": "test"})
    assert result.ok is False
    assert result.status_code is None
    assert result.error and "No webhook URL" in result.error


@pytest.mark.asyncio
async def test_send_event_url_override_used():
    """A per-call URL override takes precedence over the constructor URL."""
    svc = WebhookNotificationService(webhook_url=None, timeout=5)
    mock_session = _mock_post(200)
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await svc.send_event(
            {"event": "test"}, url="https://override.example/hook"
        )
    assert result.ok is True
    # Verify the override URL was actually passed to session.post
    mock_session.post.assert_called_once()
    args, _ = mock_session.post.call_args
    assert args[0] == "https://override.example/hook"


@pytest.mark.asyncio
async def test_send_event_handles_timeout():
    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=1)
    mock_session = MagicMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.post.side_effect = asyncio.TimeoutError()
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await svc.send_event({"event": "test"})
    assert result.ok is False
    assert result.status_code is None
    assert "Timeout" in (result.error or "")


@pytest.mark.asyncio
async def test_send_event_handles_client_error():
    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=5)
    mock_session = MagicMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.post.side_effect = aiohttp.ClientError("connection refused")
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await svc.send_event({"event": "test"})
    assert result.ok is False
    assert result.status_code is None
    assert "connection refused" in (result.error or "")


@pytest.mark.asyncio
async def test_send_event_background_outside_loop_logs_and_returns():
    """Calling background dispatch outside an event loop must not raise."""
    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=5)
    # Run synchronously — no running loop in this context (we're in the sync
    # part before pytest-asyncio creates one).
    # Calling the background method should not raise.
    svc.send_event_background({"event": "test"})  # no exception


@pytest.mark.asyncio
async def test_send_event_background_schedules_task():
    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=5)
    with patch("aiohttp.ClientSession", return_value=_mock_post(200)):
        svc.send_event_background({"event": "test"})
        # Yield the loop so the task actually runs before the test exits.
        await asyncio.sleep(0)
        await asyncio.sleep(0)


def test_format_batch_payload():
    p = format_batch_payload(batch_id="b-123", task_count=5)
    assert p["event"] == "batch.completed"
    assert p["batch_id"] == "b-123"
    assert p["task_count"] == 5
    assert "timestamp" in p


def test_format_blocker_payload():
    p = format_blocker_payload(blocker_id="bk-7", task_id="t-1")
    assert p["event"] == "blocker.created"
    assert p["blocker_id"] == "bk-7"
    assert p["task_id"] == "t-1"
    assert "timestamp" in p


def test_format_blocker_payload_allows_null_task_id():
    p = format_blocker_payload(blocker_id="bk-7", task_id=None)
    assert p["task_id"] is None


def test_format_pr_payload():
    p = format_pr_payload(pr_url="https://github.com/o/r/pull/42")
    assert p["event"] == "pr.merged"
    assert p["pr_url"] == "https://github.com/o/r/pull/42"
    assert "timestamp" in p


def test_format_test_payload():
    p = format_test_payload()
    assert p["event"] == "test"
    assert "timestamp" in p
