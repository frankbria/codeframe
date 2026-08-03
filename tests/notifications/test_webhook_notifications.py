"""Tests for webhook notification service (049-human-in-loop, Phase 7)."""


import pytest

from codeframe.notifications.webhook import WebhookNotificationService


@pytest.fixture
def webhook_service():
    """Create webhook service instance for testing."""
    return WebhookNotificationService(
        webhook_url="https://hooks.example.com/webhook/12345",
        timeout=5,
        dashboard_base_url="http://localhost:3000",
    )


@pytest.fixture
def webhook_service_no_url():
    """Create webhook service with no URL configured."""
    return WebhookNotificationService(
        webhook_url=None, timeout=5, dashboard_base_url="http://localhost:3000"
    )


class TestWebhookNotificationService:
    """Test suite for WebhookNotificationService."""

    def test_is_enabled_with_url(self, webhook_service):
        """Test is_enabled returns True when webhook_url is configured."""
        assert webhook_service.is_enabled() is True

    def test_is_enabled_without_url(self, webhook_service_no_url):
        """Test is_enabled returns False when webhook_url is None."""
        assert webhook_service_no_url.is_enabled() is False

    def test_is_enabled_with_empty_url(self):
        """Test is_enabled returns False when webhook_url is empty string."""
        service = WebhookNotificationService(webhook_url="", timeout=5)
        assert service.is_enabled() is False

    def test_is_enabled_with_whitespace_url(self):
        """Test is_enabled returns False when webhook_url is whitespace."""
        service = WebhookNotificationService(webhook_url="   ", timeout=5)
        assert service.is_enabled() is False

    # The format_payload / send_blocker_notification tests were removed with the
    # methods they covered (#941). Those methods had no production callers and
    # POSTed with a plain aiohttp session — no host vetting, no pinned resolver,
    # redirects enabled — bypassing the SSRF guards send_event implements.
    # Deleting the tests alongside the code is deliberate: keeping them would
    # have required keeping the unsafe path alive to test.











