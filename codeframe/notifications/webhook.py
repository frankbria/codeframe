"""Webhook notification service for blocker alerts.

This module provides async webhook notification capabilities for SYNC blockers,
enabling external integrations like Zapier, Slack, email, etc.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import aiohttp

from codeframe.core.models import BlockerType

logger = logging.getLogger(__name__)


class WebhookNotificationService:
    """Async webhook notification service for blocker alerts.

    Sends HTTP POST notifications for SYNC blockers to configured webhook endpoints.
    Uses fire-and-forget delivery with timeout to prevent blocking agent execution.
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        timeout: int = 5,
        dashboard_base_url: str = "http://localhost:3000",
    ):
        """Initialize webhook notification service.

        Args:
            webhook_url: Target webhook endpoint URL (e.g., Zapier, webhook.site)
            timeout: HTTP request timeout in seconds (default: 5)
            dashboard_base_url: Base URL for dashboard links (default: http://localhost:3000)
        """
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.dashboard_base_url = dashboard_base_url

    def is_enabled(self) -> bool:
        """Check if webhook notifications are enabled.

        Returns:
            True if webhook_url is configured, False otherwise
        """
        return self.webhook_url is not None and self.webhook_url.strip() != ""

    def format_payload(
        self,
        blocker_id: int,
        question: str,
        agent_id: str,
        task_id: int,
        blocker_type: BlockerType,
        created_at: datetime,
    ) -> dict:
        """Format webhook payload with blocker details.

        Args:
            blocker_id: Blocker database ID
            question: Blocker question text
            agent_id: Agent that created the blocker
            task_id: Associated task ID
            blocker_type: SYNC or ASYNC
            created_at: Blocker creation timestamp

        Returns:
            Dictionary payload ready for JSON serialization
        """
        dashboard_url = f"{self.dashboard_base_url}/#blocker-{blocker_id}"

        return {
            "blocker_id": blocker_id,
            "question": question,
            "agent_id": agent_id,
            "task_id": task_id,
            "type": blocker_type.value,
            "created_at": created_at.isoformat(),
            "dashboard_url": dashboard_url,
        }

    async def send_blocker_notification(
        self,
        blocker_id: int,
        question: str,
        agent_id: str,
        task_id: int,
        blocker_type: BlockerType,
        created_at: datetime,
    ) -> bool:
        """Send async webhook notification for a blocker.

        Fire-and-forget delivery with timeout. Logs errors but doesn't block execution.
        Only sends notifications for SYNC blockers.

        Args:
            blocker_id: Blocker database ID
            question: Blocker question text
            agent_id: Agent that created the blocker
            task_id: Associated task ID
            blocker_type: SYNC or ASYNC
            created_at: Blocker creation timestamp

        Returns:
            True if notification sent successfully, False on failure
        """
        # Only send notifications for SYNC blockers
        if blocker_type != BlockerType.SYNC:
            logger.debug(f"Skipping webhook notification for ASYNC blocker {blocker_id}")
            return False

        # Check if webhooks are enabled
        if not self.is_enabled():
            logger.debug(f"Webhook notifications disabled, skipping blocker {blocker_id}")
            return False

        # Format payload
        payload = self.format_payload(
            blocker_id=blocker_id,
            question=question,
            agent_id=agent_id,
            task_id=task_id,
            blocker_type=blocker_type,
            created_at=created_at,
        )

        try:
            # Send HTTP POST with timeout
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    response.raise_for_status()

                    logger.info(
                        f"Webhook notification sent for blocker {blocker_id} "
                        f"(status: {response.status})"
                    )
                    return True

        except asyncio.TimeoutError:
            logger.error(
                f"Webhook notification timeout for blocker {blocker_id} "
                f"(exceeded {self.timeout}s)"
            )
            return False

        except aiohttp.ClientError as e:
            logger.error(f"Webhook notification failed for blocker {blocker_id}: {e}")
            return False

        except Exception as e:
            logger.error(
                f"Unexpected error sending webhook for blocker {blocker_id}: {e}", exc_info=True
            )
            return False

    def send_blocker_notification_background(
        self,
        blocker_id: int,
        question: str,
        agent_id: str,
        task_id: int,
        blocker_type: BlockerType,
        created_at: datetime,
    ) -> None:
        """Fire-and-forget wrapper for send_blocker_notification.

        Launches notification task in background without awaiting result.
        Use this method to avoid blocking blocker creation.

        Args:
            blocker_id: Blocker database ID
            question: Blocker question text
            agent_id: Agent that created the blocker
            task_id: Associated task ID
            blocker_type: SYNC or ASYNC
            created_at: Blocker creation timestamp
        """
        # Create background task
        asyncio.create_task(
            self.send_blocker_notification(
                blocker_id=blocker_id,
                question=question,
                agent_id=agent_id,
                task_id=task_id,
                blocker_type=blocker_type,
                created_at=created_at,
            )
        )
