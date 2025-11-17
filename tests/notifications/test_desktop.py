"""
Unit tests for desktop notification service.

Tests cover:
- T125: Platform detection (Darwin/Linux/Windows)
- T126: macOS notification (pync)
- T127: macOS fallback (osascript)
- T128: Linux notification (notify-send)
- T129: Linux fallback (dbus)
- T130: Windows notification (win10toast)
- T131: Windows fallback (plyer)
- T132: Notification formatting (title, message truncation)
"""

from unittest.mock import Mock, patch

from codeframe.notifications.desktop import DesktopNotificationService


class TestPlatformDetection:
    """T125: Unit test for platform detection"""

    @patch("platform.system")
    def test_detects_darwin(self, mock_system):
        """Should detect macOS (Darwin) platform"""
        mock_system.return_value = "Darwin"
        service = DesktopNotificationService()
        assert service.platform == "Darwin"

    @patch("platform.system")
    def test_detects_linux(self, mock_system):
        """Should detect Linux platform"""
        mock_system.return_value = "Linux"
        service = DesktopNotificationService()
        assert service.platform == "Linux"

    @patch("platform.system")
    def test_detects_windows(self, mock_system):
        """Should detect Windows platform"""
        mock_system.return_value = "Windows"
        service = DesktopNotificationService()
        assert service.platform == "Windows"


class TestMacOSNotification:
    """T126: Unit test for macOS notification (pync)"""

    @patch("platform.system", return_value="Darwin")
    @patch("codeframe.notifications.desktop.pync")
    def test_sends_notification_with_pync(self, mock_pync, mock_system):
        """Should send notification using pync on macOS"""
        service = DesktopNotificationService()
        service.send_notification("Test Title", "Test Message")

        mock_pync.notify.assert_called_once_with("Test Message", title="Test Title", sound=None)

    @patch("platform.system", return_value="Darwin")
    @patch("codeframe.notifications.desktop.pync", None)  # pync not available
    def test_uses_fallback_when_pync_unavailable(self, mock_system):
        """Should use osascript fallback when pync is not available"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            service = DesktopNotificationService()
            service.send_notification("Test Title", "Test Message")

            # Should have called osascript
            assert mock_run.called


class TestMacOSFallback:
    """T127: Unit test for macOS fallback (osascript)"""

    @patch("platform.system", return_value="Darwin")
    @patch("codeframe.notifications.desktop.pync", None)
    @patch("subprocess.run")
    def test_sends_notification_with_osascript(self, mock_run, mock_system):
        """Should send notification using osascript fallback"""
        mock_run.return_value = Mock(returncode=0)
        service = DesktopNotificationService()
        service.send_notification("Test Title", "Test Message")

        # Verify osascript was called
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "osascript" in call_args
        assert "display notification" in " ".join(call_args)


class TestLinuxNotification:
    """T128: Unit test for Linux notification (notify-send)"""

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.run")
    def test_sends_notification_with_notify_send(self, mock_run, mock_system):
        """Should send notification using notify-send on Linux"""
        mock_run.return_value = Mock(returncode=0)
        service = DesktopNotificationService()
        service.send_notification("Test Title", "Test Message")

        # Verify notify-send was called
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "notify-send" in call_args
        assert "Test Title" in call_args
        assert "Test Message" in call_args


class TestLinuxFallback:
    """T129: Unit test for Linux fallback (dbus)"""

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.run")
    def test_uses_dbus_when_notify_send_fails(self, mock_run, mock_system):
        """Should use dbus fallback when notify-send fails"""
        # First call (notify-send) fails, second (dbus) succeeds
        mock_run.side_effect = [
            Mock(returncode=1),  # notify-send fails
            Mock(returncode=0),  # dbus succeeds
        ]

        service = DesktopNotificationService()
        service.send_notification("Test Title", "Test Message")

        # Should have been called twice (notify-send + dbus)
        assert mock_run.call_count == 2


class TestWindowsNotification:
    """T130: Unit test for Windows notification (win10toast)"""

    @patch("platform.system", return_value="Windows")
    @patch("codeframe.notifications.desktop.ToastNotifier")
    def test_sends_notification_with_win10toast(self, mock_toast, mock_system):
        """Should send notification using win10toast on Windows"""
        mock_notifier = Mock()
        mock_toast.return_value = mock_notifier

        service = DesktopNotificationService()
        service.send_notification("Test Title", "Test Message")

        mock_notifier.show_toast.assert_called_once_with(
            "Test Title", "Test Message", duration=5, threaded=True
        )


class TestWindowsFallback:
    """T131: Unit test for Windows fallback (plyer)"""

    @patch("platform.system", return_value="Windows")
    @patch("codeframe.notifications.desktop.ToastNotifier", None)  # win10toast not available
    @patch("codeframe.notifications.desktop.notification")
    def test_uses_plyer_when_win10toast_unavailable(self, mock_notification, mock_system):
        """Should use plyer fallback when win10toast is not available"""
        service = DesktopNotificationService()
        service.send_notification("Test Title", "Test Message")

        mock_notification.notify.assert_called_once_with(
            title="Test Title", message="Test Message", app_name="Codeframe", timeout=5
        )


class TestNotificationFormatting:
    """T132: Unit test for notification formatting"""

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.run")
    def test_truncates_long_title(self, mock_run, mock_system):
        """Should truncate title to 50 characters"""
        mock_run.return_value = Mock(returncode=0)
        service = DesktopNotificationService()

        long_title = "A" * 100
        service.send_notification(long_title, "Test Message")

        call_args = mock_run.call_args[0][0]
        # Title should be truncated
        truncated_title = "A" * 47 + "..."
        assert truncated_title in call_args

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.run")
    def test_truncates_long_message(self, mock_run, mock_system):
        """Should truncate message to 200 characters"""
        mock_run.return_value = Mock(returncode=0)
        service = DesktopNotificationService()

        long_message = "B" * 300
        service.send_notification("Test Title", long_message)

        call_args = mock_run.call_args[0][0]
        # Message should be truncated
        truncated_message = "B" * 197 + "..."
        assert truncated_message in call_args

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.run")
    def test_handles_empty_strings(self, mock_run, mock_system):
        """Should handle empty title and message gracefully"""
        mock_run.return_value = Mock(returncode=0)
        service = DesktopNotificationService()

        service.send_notification("", "")

        # Should still call notify-send with empty strings
        assert mock_run.called


class TestIsAvailable:
    """T125: Test platform availability check"""

    @patch("platform.system", return_value="Darwin")
    def test_is_available_on_macos(self, mock_system):
        """Should be available on macOS"""
        service = DesktopNotificationService()
        assert service.is_available() is True

    @patch("platform.system", return_value="Linux")
    def test_is_available_on_linux(self, mock_system):
        """Should be available on Linux"""
        service = DesktopNotificationService()
        assert service.is_available() is True

    @patch("platform.system", return_value="Windows")
    def test_is_available_on_windows(self, mock_system):
        """Should be available on Windows"""
        service = DesktopNotificationService()
        assert service.is_available() is True

    @patch("platform.system", return_value="FreeBSD")
    def test_not_available_on_unsupported_platform(self, mock_system):
        """Should not be available on unsupported platforms"""
        service = DesktopNotificationService()
        assert service.is_available() is False


class TestFireAndForget:
    """T144: Test fire-and-forget delivery"""

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.run")
    def test_does_not_block_on_error(self, mock_run, mock_system):
        """Should not raise exception even if notification fails"""
        mock_run.side_effect = Exception("Notification failed")

        service = DesktopNotificationService()
        # Should not raise exception
        service.send_notification("Test Title", "Test Message")

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.run")
    def test_logs_error_on_failure(self, mock_run, mock_system):
        """Should log error when notification fails"""
        mock_run.side_effect = Exception("Notification failed")

        service = DesktopNotificationService()
        with patch("codeframe.notifications.desktop.logger") as mock_logger:
            service.send_notification("Test Title", "Test Message")

            # Should have logged the error
            mock_logger.error.assert_called()
