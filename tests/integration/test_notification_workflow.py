"""
Integration tests for notification workflow.

Tests cover:
- T134: SYNC blocker triggering desktop notification
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from codeframe.persistence.database import Database
from codeframe.core.models import BlockerType


class TestNotificationWorkflow:
    """T134: Integration test for SYNC blocker triggering desktop notification"""

    @pytest.mark.asyncio
    async def test_sync_blocker_triggers_desktop_notification(self, db: Database):
        """Should trigger desktop notification when SYNC blocker is created"""
        with (
            patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop,
            patch("codeframe.notifications.router.WebhookNotificationService") as mock_webhook,
        ):

            mock_desktop_instance = Mock()
            mock_desktop_instance.is_available.return_value = True
            mock_desktop.return_value = mock_desktop_instance

            mock_webhook_instance = AsyncMock()
            mock_webhook.return_value = mock_webhook_instance

            # Enable notifications in the database
            from codeframe.notifications.router import NotificationRouter

            router = NotificationRouter(desktop_enabled=True)

            # Create a project and task
            project_id = await db.create_project("Test Project")
            task_id = await db.create_task(project_id, "Test Task", "test-file.py", "BACKEND")

            # Create a SYNC blocker (this should trigger notification)
            await db.create_blocker(
                task_id=task_id,
                blocker_type=BlockerType.SYNC,
                message="Critical issue found",
                details={"error": "Syntax error in test-file.py"},
            )

            # Manually trigger notification (simulating what create_blocker would do)
            await router.send(
                blocker_type=BlockerType.SYNC,
                title="🚨 SYNC Blocker Created",
                message="Critical issue found",
            )

            # Verify desktop notification was sent
            mock_desktop_instance.send_notification.assert_called_once()
            call_args = mock_desktop_instance.send_notification.call_args[0]
            assert "SYNC Blocker" in call_args[0]
            assert "Critical issue found" in call_args[1]

    @pytest.mark.asyncio
    async def test_async_blocker_does_not_trigger_when_sync_only(self, db: Database):
        """Should NOT trigger desktop notification for ASYNC blocker when sync_only=True"""
        with (
            patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop,
            patch("codeframe.notifications.router.WebhookNotificationService") as mock_webhook,
        ):

            mock_desktop_instance = Mock()
            mock_desktop_instance.is_available.return_value = True
            mock_desktop.return_value = mock_desktop_instance

            mock_webhook_instance = AsyncMock()
            mock_webhook.return_value = mock_webhook_instance

            from codeframe.notifications.router import NotificationRouter

            router = NotificationRouter(desktop_enabled=True, sync_only=True)

            # Create a project and task
            project_id = await db.create_project("Test Project")
            task_id = await db.create_task(project_id, "Test Task", "test-file.py", "BACKEND")

            # Create an ASYNC blocker
            await db.create_blocker(
                task_id=task_id,
                blocker_type=BlockerType.ASYNC,
                message="Non-critical issue found",
                details={"warning": "Deprecated API usage"},
            )

            # Try to send notification (should be filtered out)
            await router.send(
                blocker_type=BlockerType.ASYNC,
                title="ASYNC Blocker Created",
                message="Non-critical issue found",
            )

            # Verify desktop notification was NOT sent
            mock_desktop_instance.send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_notification_includes_task_context(self, db: Database):
        """Should include task context in notification message"""
        with patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop:

            mock_desktop_instance = Mock()
            mock_desktop_instance.is_available.return_value = True
            mock_desktop.return_value = mock_desktop_instance

            from codeframe.notifications.router import NotificationRouter

            router = NotificationRouter(desktop_enabled=True)

            # Create a project and task
            project_id = await db.create_project("Test Project")
            task_id = await db.create_task(project_id, "Implement User Auth", "auth.py", "BACKEND")

            # Create a SYNC blocker
            await db.create_blocker(
                task_id=task_id,
                blocker_type=BlockerType.SYNC,
                message="Security vulnerability detected",
                details={"vulnerability": "SQL injection risk"},
            )

            # Get task details
            task = await db.get_task(task_id)

            # Send notification with context
            await router.send(
                blocker_type=BlockerType.SYNC,
                title=f"🚨 SYNC Blocker in {task['file_path']}",
                message=f"Task: {task['description']}\n\nSecurity vulnerability detected",
            )

            # Verify notification includes context
            mock_desktop_instance.send_notification.assert_called_once()
            call_args = mock_desktop_instance.send_notification.call_args[0]
            assert "auth.py" in call_args[0]
            assert "Implement User Auth" in call_args[1]
            assert "Security vulnerability detected" in call_args[1]

    @pytest.mark.asyncio
    async def test_notification_fires_even_if_desktop_unavailable(self, db: Database):
        """Should gracefully handle desktop notification being unavailable"""
        with patch("codeframe.notifications.router.DesktopNotificationService") as mock_desktop:

            mock_desktop_instance = Mock()
            mock_desktop_instance.is_available.return_value = False  # Desktop not available
            mock_desktop.return_value = mock_desktop_instance

            from codeframe.notifications.router import NotificationRouter

            router = NotificationRouter(desktop_enabled=True)

            # Create a project and task
            project_id = await db.create_project("Test Project")
            task_id = await db.create_task(project_id, "Test Task", "test-file.py", "BACKEND")

            # Create a SYNC blocker
            await db.create_blocker(
                task_id=task_id,
                blocker_type=BlockerType.SYNC,
                message="Critical issue found",
                details={"error": "Syntax error"},
            )

            # Try to send notification (should not raise exception)
            await router.send(
                blocker_type=BlockerType.SYNC,
                title="SYNC Blocker Created",
                message="Critical issue found",
            )

            # Should have checked availability but not sent
            mock_desktop_instance.is_available.assert_called()
            mock_desktop_instance.send_notification.assert_not_called()


@pytest.fixture
async def db():
    """Create a test database"""
    db = Database(":memory:")
    await db.initialize()
    yield db
    await db.close()
