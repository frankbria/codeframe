"""Test outbound webhook dispatch on blocker creation (issue #560)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core import blockers
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


def test_no_webhook_dispatch_when_disabled(workspace):
    """No URL configured → no WebhookNotificationService instantiated."""
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        blockers.create(workspace, question="any?")
    MockSvc.assert_not_called()


def test_no_webhook_dispatch_when_url_set_but_flag_off(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": False},
    )
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        blockers.create(workspace, question="any?")
    MockSvc.assert_not_called()


def test_dispatches_webhook_when_enabled(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        instance = MockSvc.return_value
        blockers.create(workspace, question="why?", task_id="t-1")
    MockSvc.assert_called_once()
    # The payload should be a blocker.created event for the newly created blocker.
    instance.send_event_background.assert_called_once()
    payload = instance.send_event_background.call_args.args[0]
    assert payload["event"] == "blocker.created"
    assert payload["task_id"] == "t-1"
    assert "blocker_id" in payload


def test_webhook_failure_does_not_break_blocker_create(workspace):
    """Even if the webhook plumbing explodes, blocker creation succeeds."""
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService",
        side_effect=RuntimeError("boom"),
    ):
        blocker = blockers.create(workspace, question="why?")
    assert blocker.id  # still got created
