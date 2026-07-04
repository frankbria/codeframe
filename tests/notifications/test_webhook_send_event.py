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


@pytest.fixture(autouse=True)
def _skip_ssrf_guard(monkeypatch):
    """These tests cover transport behavior with fake hosts (example.com) and
    a fully mocked ClientSession — opt out of the #746 dispatch-time host
    check so no real DNS resolution happens. The guard itself is covered in
    test_webhook_ssrf_guard.py."""
    monkeypatch.setenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", "1")


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
async def test_send_event_does_not_follow_redirects():
    """SSRF (#656): redirects must not be followed — a public target could
    302 → 169.254.169.254 / localhost and bypass the save-time host check."""
    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=5)
    session = _mock_post(200)
    with patch("aiohttp.ClientSession", return_value=session):
        await svc.send_event(format_test_payload())
    assert session.post.call_args.kwargs["allow_redirects"] is False


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


def test_send_event_background_outside_loop_runs_in_thread():
    """In sync context (no running loop), dispatch spawns a daemon thread
    and runs the send to completion. The caller must not block beyond the
    thread spawn cost.

    This is the CLI batch-run path — without this, webhooks from
    ``cf work batch run`` would silently never fire.
    """
    import threading

    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=5)
    threads_before = threading.active_count()

    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService._run_send_event_sync"
    ) as mock_runner:
        svc.send_event_background({"event": "test"})
        # Thread is spawned synchronously and starts immediately. Give it a
        # beat to run.
        import time

        for _ in range(50):
            if mock_runner.called:
                break
            time.sleep(0.01)

    assert mock_runner.called, "expected daemon thread to invoke the sync runner"
    # The thread spawns and dies — no leaked thread count. Give it up to a
    # second to clean up before asserting (the runner is mocked so this is
    # really just the thread overhead).
    for _ in range(50):
        leaked = threading.active_count() - threads_before
        if leaked <= 0:
            break
        time.sleep(0.02)
    assert threading.active_count() - threads_before <= 0, (
        "send_event_background leaked a thread"
    )


@pytest.mark.asyncio
async def test_send_event_background_schedules_task():
    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=5)
    with patch("aiohttp.ClientSession", return_value=_mock_post(200)):
        svc.send_event_background({"event": "test"})
        # Yield the loop so the task actually runs before the test exits.
        await asyncio.sleep(0)
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_send_event_background_task_has_done_callback():
    """Python 3.11+ logs ``Task exception was never retrieved`` when an
    async task ends with an unhandled exception and nobody awaits or calls
    .exception(). ``send_event`` swallows exceptions internally, but
    defence-in-depth: attach a done-callback so the result is always
    consumed and the log noise never appears in production.
    """
    svc = WebhookNotificationService(webhook_url="https://example.com/hook", timeout=5)

    captured_tasks = []
    loop = asyncio.get_running_loop()
    real_create_task = loop.create_task

    def capture(coro):
        t = real_create_task(coro)
        captured_tasks.append(t)
        return t

    with patch.object(loop, "create_task", side_effect=capture):
        with patch("aiohttp.ClientSession", return_value=_mock_post(200)):
            svc.send_event_background({"event": "test"})

    assert len(captured_tasks) == 1
    # The task's repr includes its registered callbacks. The send_event_background
    # lambda must appear there — without it, Python 3.11+ would warn on task
    # completion if send_event ever raised.
    assert "send_event_background.<locals>.<lambda>" in repr(captured_tasks[0])

    # Drain the task so the test exit is clean. After cancelling, await
    # the task so cancellation actually propagates — otherwise Python may
    # emit "Task was destroyed but it is pending" warnings on loop close.
    try:
        await asyncio.wait_for(captured_tasks[0], timeout=1.0)
    except asyncio.TimeoutError:
        captured_tasks[0].cancel()
        try:
            await captured_tasks[0]
        except (asyncio.CancelledError, Exception):
            pass


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
    p = format_pr_payload(pr_number=42, pr_url="https://github.com/o/r/pull/42")
    assert p["event"] == "pr.merged"
    assert p["pr_number"] == 42
    assert p["pr_url"] == "https://github.com/o/r/pull/42"
    assert "timestamp" in p


def test_format_pr_payload_url_is_optional():
    """When the GitHub integration can't construct a URL we send None,
    not an unparseable sentinel like 'pr#42' — consumers can branch on
    pr_number (always present) and use pr_url when available."""
    p = format_pr_payload(pr_number=99)
    assert p["event"] == "pr.merged"
    assert p["pr_number"] == 99
    assert p["pr_url"] is None


def test_format_batch_payload_includes_status():
    """Payload self-documents the terminal state — forward-compatible
    if PARTIAL/FAILED events get added later."""
    p = format_batch_payload(batch_id="b-1", task_count=3)
    assert p["status"] == "completed"


def test_format_test_payload():
    p = format_test_payload()
    assert p["event"] == "test"
    assert "timestamp" in p


def test_timestamp_uses_z_suffix_not_offset():
    """Slack/Discord/Zapier prefer the Z suffix over +00:00 offset format."""
    p = format_test_payload()
    assert p["timestamp"].endswith("Z"), (
        f"Expected ISO timestamp with Z suffix, got: {p['timestamp']!r}"
    )
    assert "+00:00" not in p["timestamp"]
