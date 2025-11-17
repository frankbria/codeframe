"""
Unit tests for notification router.

Tests cover:
- T133: NotificationRouter (desktop + webhook)
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from codeframe.notifications.router import NotificationRouter
from codeframe.core.models import BlockerType


class TestNotificationRouter:
    """T133: Unit test for NotificationRouter"""

    @pytest.mark.asyncio
    async def test_routes_to_desktop_and_webhook(self):
        """Should route notifications to both desktop and webhook services"""
        # Mock both services
        with (
            patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop,
            patch("codeframe.notifications.router.WebhookNotificationService") as mock_webhook,
        ):

            mock_desktop_instance = Mock()
            mock_desktop_instance.is_available.return_value = True
            mock_desktop.return_value = mock_desktop_instance

            mock_webhook_instance = AsyncMock()
            mock_webhook.return_value = mock_webhook_instance

            router = NotificationRouter(desktop_enabled=True, webhook_enabled=True)

            await router.send(
                blocker_type=BlockerType.SYNC,
                title="Test Blocker",
                message="This is a test blocker",
            )

            # Both services should be called
            mock_desktop_instance.send_notification.assert_called_once_with(
                "Test Blocker", "This is a test blocker"
            )
            mock_webhook_instance.send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_desktop_when_disabled(self):
        """Should skip desktop notification when disabled"""
        with (
            patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop,
            patch("codeframe.notifications.router.WebhookNotificationService") as mock_webhook,
        ):

            mock_desktop_instance = Mock()
            mock_desktop.return_value = mock_desktop_instance

            mock_webhook_instance = AsyncMock()
            mock_webhook.return_value = mock_webhook_instance

            router = NotificationRouter(desktop_enabled=False, webhook_enabled=True)

            await router.send(
                blocker_type=BlockerType.SYNC,
                title="Test Blocker",
                message="This is a test blocker",
            )

            # Desktop should not be called
            mock_desktop_instance.send_notification.assert_not_called()
            # Webhook should still be called
            mock_webhook_instance.send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_webhook_when_disabled(self):
        """Should skip webhook notification when disabled"""
        with (
            patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop,
            patch("codeframe.notifications.router.WebhookNotificationService") as mock_webhook,
        ):

            mock_desktop_instance = Mock()
            mock_desktop_instance.is_available.return_value = True
            mock_desktop.return_value = mock_desktop_instance

            mock_webhook_instance = AsyncMock()
            mock_webhook.return_value = mock_webhook_instance

            router = NotificationRouter(desktop_enabled=True, webhook_enabled=False)

            await router.send(
                blocker_type=BlockerType.SYNC,
                title="Test Blocker",
                message="This is a test blocker",
            )

            # Desktop should be called
            mock_desktop_instance.send_notification.assert_called_once()
            # Webhook should not be called
            mock_webhook_instance.send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_filters_sync_only_when_configured(self):
        """Should only send notifications for SYNC blockers when sync_only=True"""
        with (
            patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop,
            patch("codeframe.notifications.router.WebhookNotificationService") as mock_webhook,
        ):

            mock_desktop_instance = Mock()
            mock_desktop_instance.is_available.return_value = True
            mock_desktop.return_value = mock_desktop_instance

            mock_webhook_instance = AsyncMock()
            mock_webhook.return_value = mock_webhook_instance

            router = NotificationRouter(desktop_enabled=True, sync_only=True)

            # Send ASYNC blocker
            await router.send(
                blocker_type=BlockerType.ASYNC,
                title="Async Blocker",
                message="This is an async blocker",
            )

            # Should not send notification
            mock_desktop_instance.send_notification.assert_not_called()

            # Send SYNC blocker
            await router.send(
                blocker_type=BlockerType.SYNC,
                title="Sync Blocker",
                message="This is a sync blocker",
            )

            # Should send notification
            mock_desktop_instance.send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_all_blockers_when_sync_only_false(self):
        """Should send notifications for all blocker types when sync_only=False"""
        with (
            patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop,
            patch("codeframe.notifications.router.WebhookNotificationService") as mock_webhook,
        ):

            mock_desktop_instance = Mock()
            mock_desktop_instance.is_available.return_value = True
            mock_desktop.return_value = mock_desktop_instance

            mock_webhook_instance = AsyncMock()
            mock_webhook.return_value = mock_webhook_instance

            router = NotificationRouter(desktop_enabled=True, sync_only=False)

            # Send ASYNC blocker
            await router.send(
                blocker_type=BlockerType.ASYNC,
                title="Async Blocker",
                message="This is an async blocker",
            )

            # Should send notification for ASYNC
            assert mock_desktop_instance.send_notification.call_count == 1

            # Send SYNC blocker
            await router.send(
                blocker_type=BlockerType.SYNC,
                title="Sync Blocker",
                message="This is a sync blocker",
            )

            # Should send notification for SYNC too
            assert mock_desktop_instance.send_notification.call_count == 2

    @pytest.mark.asyncio
    async def test_continues_on_desktop_failure(self):
        """Should continue to webhook even if desktop notification fails"""
        with (
            patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop,
            patch("codeframe.notifications.router.WebhookNotificationService") as mock_webhook,
        ):

            mock_desktop_instance = Mock()
            mock_desktop_instance.is_available.return_value = True
            mock_desktop_instance.send_notification.side_effect = Exception("Desktop failed")
            mock_desktop.return_value = mock_desktop_instance

            mock_webhook_instance = AsyncMock()
            mock_webhook.return_value = mock_webhook_instance

            router = NotificationRouter(desktop_enabled=True, webhook_enabled=True)

            # Should not raise exception
            await router.send(
                blocker_type=BlockerType.SYNC,
                title="Test Blocker",
                message="This is a test blocker",
            )

            # Webhook should still be called
            mock_webhook_instance.send_notification.assert_called_once()
