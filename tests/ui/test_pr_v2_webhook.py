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
    # Provide GITHUB_REPO so the URL has the owner/repo segment.
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
    """If GITHUB_REPO is unset, we still emit the event but pr_url is None —
    consumers branch on pr_number (always present) rather than parsing an
    unparseable sentinel."""
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


def test_no_github_client_constructed(workspace, monkeypatch):
    """Regression guard for #779: the dispatch only needs the repo slug —
    constructing GitHubIntegration would eagerly open (and leak) an
    httpx.AsyncClient, so it must never be reintroduced on this path."""
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("GITHUB_REPO", "frankbria/codeframe")

    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ), patch("codeframe.ui.routers.pr_v2.GitHubIntegration") as MockGH:
        _dispatch_pr_merged_webhook(workspace, pr_number=42)
    MockGH.assert_not_called()


def test_pr_url_built_without_token(workspace, monkeypatch):
    """A canonical github.com URL needs no auth — GITHUB_REPO alone suffices."""
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPO", "frankbria/codeframe")

    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        instance = MockSvc.return_value
        _dispatch_pr_merged_webhook(workspace, pr_number=7)
    payload = instance.send_event_background.call_args.args[0]
    assert payload["pr_url"] == "https://github.com/frankbria/codeframe/pull/7"


@pytest.mark.parametrize("bad_repo", ["no-slash", "owner/", "/repo", " / "])
def test_pr_url_none_for_malformed_repo(workspace, monkeypatch, bad_repo):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    monkeypatch.setenv("GITHUB_REPO", bad_repo)

    with patch(
        "codeframe.notifications.webhook.WebhookNotificationService"
    ) as MockSvc:
        instance = MockSvc.return_value
        _dispatch_pr_merged_webhook(workspace, pr_number=3)
    payload = instance.send_event_background.call_args.args[0]
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
