"""Webhook notification service.

Originally built for SYNC blocker alerts (049-human-in-loop, Phase 7), now also
powers outbound event webhooks for batch completion / blocker creation / PR
merge (issue #560).

Delivery is fire-and-forget with a configurable timeout — failures are logged
but never break the triggering operation.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from codeframe.core.models import BlockerType

logger = logging.getLogger(__name__)


@dataclass
class WebhookSendResult:
    """Result of a single ``send_event`` call.

    ``ok`` mirrors HTTP 2xx semantics. ``status_code`` is ``None`` when the
    request never completed (timeout, DNS failure, connection refused, …) —
    the ``error`` field carries a short human-readable reason in that case.
    """

    ok: bool
    status_code: Optional[int]
    error: Optional[str] = None


def _utc_iso_now() -> str:
    """ISO-8601 UTC timestamp for webhook payloads."""
    return datetime.now(timezone.utc).isoformat()


def format_batch_payload(batch_id: str, task_count: int) -> dict:
    return {
        "event": "batch.completed",
        "batch_id": batch_id,
        "task_count": task_count,
        "timestamp": _utc_iso_now(),
    }


def format_blocker_payload(blocker_id: str, task_id: Optional[str]) -> dict:
    return {
        "event": "blocker.created",
        "blocker_id": blocker_id,
        "task_id": task_id,
        "timestamp": _utc_iso_now(),
    }


def format_pr_payload(pr_url: str) -> dict:
    return {
        "event": "pr.merged",
        "pr_url": pr_url,
        "timestamp": _utc_iso_now(),
    }


def format_test_payload() -> dict:
    return {"event": "test", "timestamp": _utc_iso_now()}


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

    async def send_event(
        self, payload: dict, url: Optional[str] = None
    ) -> WebhookSendResult:
        """Generic webhook POST for outbound event notifications (issue #560).

        Unlike ``send_blocker_notification``, this method:

        * Accepts an arbitrary JSON payload (the caller composes the event).
        * Returns rich status information so the Settings ``Test`` endpoint
          can surface the HTTP status code or error to the user.
        * Accepts an optional ``url`` override so the same service instance
          can dispatch to a freshly-configured URL without rebuilding state.

        Failures (timeout, network, non-2xx) are logged but never raised —
        the caller can react via the returned ``WebhookSendResult``.
        """
        target_url = url or self.webhook_url
        if not target_url or not target_url.strip():
            return WebhookSendResult(
                ok=False, status_code=None, error="No webhook URL configured"
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    target_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    ok = 200 <= response.status < 300
                    if not ok:
                        logger.warning(
                            "Webhook returned non-2xx status %s for event %s",
                            response.status,
                            payload.get("event"),
                        )
                    return WebhookSendResult(ok=ok, status_code=response.status)
        except asyncio.TimeoutError:
            logger.error(
                "Webhook timeout for event %s (exceeded %ss)",
                payload.get("event"),
                self.timeout,
            )
            return WebhookSendResult(
                ok=False, status_code=None, error=f"Timeout after {self.timeout}s"
            )
        except aiohttp.ClientError as e:
            logger.error("Webhook ClientError for event %s: %s", payload.get("event"), e)
            return WebhookSendResult(ok=False, status_code=None, error=str(e))
        except Exception as e:
            logger.error(
                "Unexpected webhook error for event %s: %s",
                payload.get("event"),
                e,
                exc_info=True,
            )
            return WebhookSendResult(ok=False, status_code=None, error=str(e))

    def send_event_background(self, payload: dict, url: Optional[str] = None) -> None:
        """Fire-and-forget wrapper for ``send_event``.

        Schedules the send on the current event loop and returns immediately.
        If no event loop is running (e.g., called from sync code outside of
        async context), the call is silently dropped after logging — the
        triggering operation must never block on webhook delivery.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "send_event_background called outside of a running event loop; "
                "skipping webhook for event %s",
                payload.get("event"),
            )
            return
        loop.create_task(self.send_event(payload, url=url))

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
