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


def test_duplicate_open_blocker_is_deduped(workspace):
    """One escalation → exactly one OPEN blocker and one webhook (issue #735).

    Adapter + runtime each call create() with the same (task_id, question); the
    second must return the existing OPEN blocker without a new row or webhook.
    """
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        instance = MockSvc.return_value
        first = blockers.create(
            workspace, question="Gates failing?", task_id="t-1", created_by="agent"
        )
        second = blockers.create(
            workspace, question="Gates failing?", task_id="t-1"
        )

    assert second.id == first.id  # same blocker, not a duplicate
    assert second.created_by == first.created_by  # first writer (agent) wins
    assert len(blockers.list_open(workspace)) == 1
    instance.send_event_background.assert_called_once()  # only one webhook


def test_dedupe_does_not_collapse_distinct_questions(workspace):
    """Different questions on the same task remain separate blockers."""
    a = blockers.create(workspace, question="Q1?", task_id="t-1")
    b = blockers.create(workspace, question="Q2?", task_id="t-1")
    assert a.id != b.id
    assert len(blockers.list_open(workspace)) == 2


def test_dedupe_scoped_to_open_status(workspace):
    """An answered blocker does not suppress a new one with the same question."""
    first = blockers.create(workspace, question="Same?", task_id="t-1")
    blockers.answer(workspace, first.id, "resolved")
    second = blockers.create(workspace, question="Same?", task_id="t-1")
    assert second.id != first.id
    assert len(blockers.list_open(workspace)) == 1


def test_dedupe_handles_null_task_id(workspace):
    """Workspace-level (task_id=None) duplicates are deduped too."""
    first = blockers.create(workspace, question="Global?")
    second = blockers.create(workspace, question="Global?")
    assert second.id == first.id
    assert len(blockers.list_open(workspace)) == 1
