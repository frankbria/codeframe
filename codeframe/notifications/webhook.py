"""Webhook notification service.

Originally built for SYNC blocker alerts (049-human-in-loop, Phase 7), now also
powers outbound event webhooks for batch completion / blocker creation / PR
merge (issue #560).

Delivery is fire-and-forget with a configurable timeout — failures are logged
but never break the triggering operation.
"""

import asyncio
import logging
import threading
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
    """ISO-8601 UTC timestamp for webhook payloads (``Z`` suffix).

    Slack/Discord/Zapier-style consumers expect ``Z``, not ``+00:00``.
    Drops sub-second precision for the same reason — consumers vary widely
    in fractional-second handling.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_batch_payload(batch_id: str, task_count: int) -> dict:
    # ``status`` is always "completed" today (the dispatcher gates on
    # BATCH_COMPLETED only) but is included so consumers can self-document
    # and so a future PARTIAL/FAILED extension is forward-compatible.
    return {
        "event": "batch.completed",
        "batch_id": batch_id,
        "task_count": task_count,
        "status": "completed",
        "timestamp": _utc_iso_now(),
    }


def format_blocker_payload(blocker_id: str, task_id: Optional[str]) -> dict:
    return {
        "event": "blocker.created",
        "blocker_id": blocker_id,
        "task_id": task_id,
        "timestamp": _utc_iso_now(),
    }


def format_pr_payload(pr_number: int, pr_url: Optional[str] = None) -> dict:
    # ``pr_number`` is always present so consumers can branch on it.
    # ``pr_url`` is the canonical github.com URL when GITHUB_REPO is set,
    # ``None`` otherwise (an unparseable sentinel like ``"pr#42"`` was
    # actively confusing for downstream handlers).
    return {
        "event": "pr.merged",
        "pr_number": pr_number,
        "pr_url": pr_url,
        "timestamp": _utc_iso_now(),
    }


def format_test_payload() -> dict:
    return {"event": "test", "timestamp": _utc_iso_now()}


class WebhookNotificationService:
    """Async outbound webhook service.

    Originally built for SYNC blocker alerts (``send_blocker_notification``);
    now also powers the issue #560 outbound event webhooks (batch / blocker /
    PR / test) via ``send_event``. Delivery is fire-and-forget with a
    configurable timeout — failures are logged but never break the triggering
    operation.
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

        Works in both contexts:

        * **Async** (FastAPI request handler): schedules the send on the
          current event loop via ``loop.create_task`` and returns
          immediately.
        * **Sync** (CLI batch run, sync test): spawns a daemon thread that
          runs the send in a fresh event loop. The thread is daemon so it
          never blocks process exit; ``timeout`` still applies inside the
          loop, so the thread lives at most ``self.timeout`` seconds.

        Either way, the triggering operation never blocks on webhook
        delivery and never sees an exception from this method.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — we're in sync context (CLI). Run the send
            # in a daemon thread so we don't block the caller and so the
            # process can exit cleanly even if the webhook hangs.
            thread = threading.Thread(
                target=self._run_send_event_sync,
                args=(payload, url),
                daemon=True,
                name="webhook-send-event",
            )
            thread.start()
            return
        task = loop.create_task(self.send_event(payload, url=url))
        # ``send_event`` already swallows all exceptions, but Python 3.11+
        # warns ``Task exception was never retrieved`` if a task ends with
        # an unhandled exception and nobody awaited / called .exception().
        # Add a no-op callback so the result is always consumed.
        task.add_done_callback(
            lambda t: t.exception() if not t.cancelled() else None
        )

    def _run_send_event_sync(self, payload: dict, url: Optional[str]) -> None:
        """Run ``send_event`` to completion in a fresh event loop.

        Used only by the sync branch of ``send_event_background`` — never
        raises into the calling thread (the daemon thread is meant to die
        quietly).
        """
        try:
            asyncio.run(self.send_event(payload, url=url))
        except Exception:
            logger.warning(
                "Sync webhook dispatch failed for event %s",
                payload.get("event"),
                exc_info=True,
            )

