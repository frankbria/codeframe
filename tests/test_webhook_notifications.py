"""Tests for webhook notification service (049-human-in-loop, Phase 7)."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from codeframe.core.models import BlockerType
from codeframe.notifications.webhook import WebhookNotificationService


@pytest.fixture
def webhook_service():
    """Create webhook service instance for testing."""
    return WebhookNotificationService(
        webhook_url="https://hooks.example.com/webhook/12345",
        timeout=5,
        dashboard_base_url="http://localhost:3000"
    )


@pytest.fixture
def webhook_service_no_url():
    """Create webhook service with no URL configured."""
    return WebhookNotificationService(
        webhook_url=None,
        timeout=5,
        dashboard_base_url="http://localhost:3000"
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

    def test_format_payload(self, webhook_service):
        """Test payload formatting includes all required fields."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)
        payload = webhook_service.format_payload(
            blocker_id=123,
            question="What API key should I use?",
            agent_id="backend-worker-abc123",
            task_id=456,
            blocker_type=BlockerType.SYNC,
            created_at=created_at
        )

        assert payload["blocker_id"] == 123
        assert payload["question"] == "What API key should I use?"
        assert payload["agent_id"] == "backend-worker-abc123"
        assert payload["task_id"] == 456
        assert payload["type"] == "SYNC"
        assert payload["created_at"] == "2025-11-08T14:30:00"
        assert payload["dashboard_url"] == "http://localhost:3000/#blocker-123"

    def test_format_payload_async_type(self, webhook_service):
        """Test payload formatting with ASYNC blocker type."""
        created_at = datetime(2025, 11, 8, 15, 0, 0)
        payload = webhook_service.format_payload(
            blocker_id=789,
            question="Should we use light or dark theme?",
            agent_id="frontend-worker-xyz789",
            task_id=101,
            blocker_type=BlockerType.ASYNC,
            created_at=created_at
        )

        assert payload["type"] == "ASYNC"

    @pytest.mark.asyncio
    async def test_send_blocker_notification_sync_success(self, webhook_service):
        """Test successful webhook notification for SYNC blocker."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        # Mock aiohttp response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()

        # Create proper async context manager mock
        mock_post_context = AsyncMock()
        mock_post_context.__aenter__.return_value = mock_response
        mock_post_context.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.post.return_value = mock_post_context
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await webhook_service.send_blocker_notification(
                blocker_id=123,
                question="Critical blocker",
                agent_id="backend-worker-1",
                task_id=456,
                blocker_type=BlockerType.SYNC,
                created_at=created_at
            )

        assert result is True
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_blocker_notification_async_skipped(self, webhook_service):
        """Test webhook notification skipped for ASYNC blocker."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        result = await webhook_service.send_blocker_notification(
            blocker_id=123,
            question="Non-critical question",
            agent_id="backend-worker-1",
            task_id=456,
            blocker_type=BlockerType.ASYNC,
            created_at=created_at
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_blocker_notification_disabled(self, webhook_service_no_url):
        """Test webhook notification skipped when webhooks disabled."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        result = await webhook_service_no_url.send_blocker_notification(
            blocker_id=123,
            question="Critical blocker",
            agent_id="backend-worker-1",
            task_id=456,
            blocker_type=BlockerType.SYNC,
            created_at=created_at
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_blocker_notification_timeout(self, webhook_service):
        """Test webhook notification handles timeout gracefully."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        mock_session = AsyncMock()
        mock_session.post.side_effect = asyncio.TimeoutError()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await webhook_service.send_blocker_notification(
                blocker_id=123,
                question="Critical blocker",
                agent_id="backend-worker-1",
                task_id=456,
                blocker_type=BlockerType.SYNC,
                created_at=created_at
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_blocker_notification_client_error(self, webhook_service):
        """Test webhook notification handles HTTP client errors."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        mock_response = AsyncMock()
        mock_response.raise_for_status.side_effect = aiohttp.ClientError("Connection failed")

        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await webhook_service.send_blocker_notification(
                blocker_id=123,
                question="Critical blocker",
                agent_id="backend-worker-1",
                task_id=456,
                blocker_type=BlockerType.SYNC,
                created_at=created_at
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_blocker_notification_unexpected_error(self, webhook_service):
        """Test webhook notification handles unexpected exceptions."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        mock_session = AsyncMock()
        mock_session.post.side_effect = RuntimeError("Unexpected error")

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await webhook_service.send_blocker_notification(
                blocker_id=123,
                question="Critical blocker",
                agent_id="backend-worker-1",
                task_id=456,
                blocker_type=BlockerType.SYNC,
                created_at=created_at
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_blocker_notification_http_error_status(self, webhook_service):
        """Test webhook notification handles HTTP error status codes."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.raise_for_status.side_effect = aiohttp.ClientError("500 Internal Server Error")

        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await webhook_service.send_blocker_notification(
                blocker_id=123,
                question="Critical blocker",
                agent_id="backend-worker-1",
                task_id=456,
                blocker_type=BlockerType.SYNC,
                created_at=created_at
            )

        assert result is False

    def test_send_blocker_notification_background(self, webhook_service):
        """Test fire-and-forget background notification."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        with patch("asyncio.create_task") as mock_create_task:
            webhook_service.send_blocker_notification_background(
                blocker_id=123,
                question="Critical blocker",
                agent_id="backend-worker-1",
                task_id=456,
                blocker_type=BlockerType.SYNC,
                created_at=created_at
            )

            # Verify background task was created
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_blocker_notification_correct_payload(self, webhook_service):
        """Test webhook notification sends correct JSON payload."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()

        # Create proper async context manager mock
        mock_post_context = AsyncMock()
        mock_post_context.__aenter__.return_value = mock_response
        mock_post_context.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.post.return_value = mock_post_context
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await webhook_service.send_blocker_notification(
                blocker_id=123,
                question="What API key?",
                agent_id="backend-worker-1",
                task_id=456,
                blocker_type=BlockerType.SYNC,
                created_at=created_at
            )

        # Verify POST was called with correct arguments
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "https://hooks.example.com/webhook/12345"
        assert call_args[1]["json"]["blocker_id"] == 123
        assert call_args[1]["json"]["question"] == "What API key?"
        assert call_args[1]["json"]["agent_id"] == "backend-worker-1"
        assert call_args[1]["json"]["task_id"] == 456
        assert call_args[1]["json"]["type"] == "SYNC"
        assert call_args[1]["json"]["dashboard_url"] == "http://localhost:3000/#blocker-123"

    @pytest.mark.asyncio
    async def test_send_blocker_notification_timeout_configured(self, webhook_service):
        """Test webhook notification uses configured timeout."""
        created_at = datetime(2025, 11, 8, 14, 30, 0)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()

        # Create proper async context manager mock
        mock_post_context = AsyncMock()
        mock_post_context.__aenter__.return_value = mock_response
        mock_post_context.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.post.return_value = mock_post_context
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await webhook_service.send_blocker_notification(
                blocker_id=123,
                question="Critical blocker",
                agent_id="backend-worker-1",
                task_id=456,
                blocker_type=BlockerType.SYNC,
                created_at=created_at
            )

        # Verify timeout was passed
        call_args = mock_session.post.call_args
        assert call_args[1]["timeout"].total == 5
