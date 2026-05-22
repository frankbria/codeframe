"""Test outbound webhook dispatch on batch completion (issue #560).

We don't exercise the full conductor lifecycle here — the dispatch helper
is the contract under test, and the conductor calls it at each of the four
``BATCH_COMPLETED``-capable sites (verified by grep in the implementation).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core import events
from codeframe.core.conductor import _dispatch_batch_completed_webhook
from codeframe.core.notifications_config import save_notifications_config
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace():
    temp_dir = Path(tempfile.mkdtemp())
    ws_path = temp_dir / "ws"
    ws_path.mkdir(parents=True, exist_ok=True)
    ws = create_or_load_workspace(ws_path)
    try:
        yield ws
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _enable_webhook(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )


def test_does_not_fire_for_partial(workspace):
    _enable_webhook(workspace)
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        _dispatch_batch_completed_webhook(
            workspace, events.EventType.BATCH_PARTIAL, "b-1", 5
        )
    MockSvc.assert_not_called()


def test_does_not_fire_for_failed(workspace):
    _enable_webhook(workspace)
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        _dispatch_batch_completed_webhook(
            workspace, events.EventType.BATCH_FAILED, "b-1", 0
        )
    MockSvc.assert_not_called()


def test_does_not_fire_for_cancelled(workspace):
    _enable_webhook(workspace)
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        _dispatch_batch_completed_webhook(
            workspace, events.EventType.BATCH_CANCELLED, "b-1", 0
        )
    MockSvc.assert_not_called()


def test_fires_for_completed_when_enabled(workspace):
    _enable_webhook(workspace)
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        instance = MockSvc.return_value
        _dispatch_batch_completed_webhook(
            workspace, events.EventType.BATCH_COMPLETED, "b-42", 7
        )
    MockSvc.assert_called_once()
    instance.send_event_background.assert_called_once()
    payload = instance.send_event_background.call_args.args[0]
    assert payload["event"] == "batch.completed"
    assert payload["batch_id"] == "b-42"
    assert payload["task_count"] == 7


def test_does_not_fire_when_url_missing(workspace):
    # No save_notifications_config call → config is at defaults (disabled).
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        _dispatch_batch_completed_webhook(
            workspace, events.EventType.BATCH_COMPLETED, "b-1", 1
        )
    MockSvc.assert_not_called()


def test_does_not_fire_when_disabled(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": False},
    )
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        _dispatch_batch_completed_webhook(
            workspace, events.EventType.BATCH_COMPLETED, "b-1", 1
        )
    MockSvc.assert_not_called()


def test_failure_in_dispatch_is_swallowed(workspace):
    """A misconfigured webhook must never bubble up into the batch flow."""
    _enable_webhook(workspace)
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService",
        side_effect=RuntimeError("boom"),
    ):
        # Should not raise.
        _dispatch_batch_completed_webhook(
            workspace, events.EventType.BATCH_COMPLETED, "b-1", 1
        )
