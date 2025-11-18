"""
Notification router for coordinating desktop and webhook notifications.

Implements tasks:
- T145-T147: NotificationRouter implementation
"""

import logging

from codeframe.notifications.desktop import DesktopNotificationService
from codeframe.notifications.webhook import WebhookNotificationService
from codeframe.core.models import BlockerType

logger = logging.getLogger(__name__)


class NotificationRouter:
    """
    Routes notifications to multiple channels (desktop + webhook).

    Features:
    - Multi-channel delivery (desktop + webhook)
    - Blocker type filtering (SYNC-only mode)
    - Graceful error handling (one failure doesn't block others)

    Implements: T145-T147
    """

    def __init__(
        self, desktop_enabled: bool = True, webhook_enabled: bool = False, sync_only: bool = True
    ):
        """
        Initialize notification router.

        Args:
            desktop_enabled: Enable desktop notifications
            webhook_enabled: Enable webhook notifications
            sync_only: Only send notifications for SYNC blockers (default: True)

        Implements: T145, T147
        """
        self.desktop_enabled = desktop_enabled
        self.webhook_enabled = webhook_enabled
        self.sync_only = sync_only

        # Initialize services
        self.desktop_service = DesktopNotificationService() if desktop_enabled else None
        self.webhook_service = WebhookNotificationService() if webhook_enabled else None

        logger.info(
            f"NotificationRouter initialized: "
            f"desktop={desktop_enabled}, webhook={webhook_enabled}, sync_only={sync_only}"
        )

    async def send(self, blocker_type: BlockerType, title: str, message: str) -> None:
        """
        Send notification through all enabled channels.

        Args:
            blocker_type: Type of blocker (SYNC or ASYNC)
            title: Notification title
            message: Notification message

        Implements: T146 (routing logic), T147 (SYNC-only filtering)
        """
        # T147: Filter by blocker type if sync_only is enabled
        if self.sync_only and blocker_type != BlockerType.SYNC:
            logger.debug(f"Skipping notification for {blocker_type} blocker (sync_only=True)")
            return

        # Send to all enabled channels (fire-and-forget for each)
        # T146: Route to desktop
        if self.desktop_enabled and self.desktop_service:
            try:
                if self.desktop_service.is_available():
                    self.desktop_service.send_notification(title, message)
                    logger.info(f"Desktop notification sent: {title}")
            except Exception as e:
                logger.error(f"Desktop notification failed: {e}")

        # T146: Route to webhook
        if self.webhook_enabled and self.webhook_service:
            try:
                await self.webhook_service.send_notification(
                    blocker_type=blocker_type, title=title, message=message
                )
                logger.info(f"Webhook notification sent: {title}")
            except Exception as e:
                logger.error(f"Webhook notification failed: {e}")
