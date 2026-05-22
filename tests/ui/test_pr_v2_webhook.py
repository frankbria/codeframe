"""Test outbound webhook dispatch on PR merge (issue #560)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core.notifications_config import save_notifications_config
from codeframe.core.workspace import create_or_load_workspace
from codeframe.ui.routers.pr_v2 import _dispatch_pr_merged_webhook

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


def test_no_dispatch_when_disabled(workspace):
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        _dispatch_pr_merged_webhook(workspace, pr_number=42)
    MockSvc.assert_not_called()


def test_dispatches_when_enabled_with_pr_url(workspace, monkeypatch):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    # Provide GitHub env so GitHubIntegration() succeeds and the URL has the
    # owner/repo segment.
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("GITHUB_REPO", "frankbria/codeframe")

    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        instance = MockSvc.return_value
        _dispatch_pr_merged_webhook(workspace, pr_number=42)
    MockSvc.assert_called_once()
    instance.send_event_background.assert_called_once()
    payload = instance.send_event_background.call_args.args[0]
    assert payload["event"] == "pr.merged"
    assert payload["pr_number"] == 42
    assert payload["pr_url"] == "https://github.com/frankbria/codeframe/pull/42"


def test_dispatches_with_null_url_when_github_unconfigured(workspace, monkeypatch):
    """If GitHubIntegration() can't be constructed, we still emit the event
    but pr_url is None — consumers branch on pr_number (always present)
    rather than parsing an unparseable sentinel."""
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)

    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        instance = MockSvc.return_value
        _dispatch_pr_merged_webhook(workspace, pr_number=99)

    MockSvc.assert_called_once()
    payload = instance.send_event_background.call_args.args[0]
    assert payload["event"] == "pr.merged"
    assert payload["pr_number"] == 99
    assert payload["pr_url"] is None


def test_dispatch_failure_does_not_raise(workspace, monkeypatch):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("GITHUB_REPO", "frankbria/codeframe")
    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService",
        side_effect=RuntimeError("boom"),
    ):
        # Should not raise.
        _dispatch_pr_merged_webhook(workspace, pr_number=1)
