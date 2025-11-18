"""
Desktop notification service for native OS notifications.

Supports:
- macOS: pync (primary) and osascript (fallback)
- Linux: notify-send (primary) and dbus (fallback)
- Windows: win10toast (primary) and plyer (fallback)

Implements tasks:
- T135-T144: DesktopNotificationService implementation
"""

import platform
import subprocess
import logging

logger = logging.getLogger(__name__)

# Optional dependencies - imported at runtime
try:
    import pync
except ImportError:
    pync = None

try:
    from win10toast import ToastNotifier
except ImportError:
    ToastNotifier = None

try:
    from plyer import notification
except ImportError:
    notification = None


class DesktopNotificationService:
    """
    Service for sending native desktop notifications.

    Uses platform-specific methods with graceful degradation:
    - macOS: pync → osascript
    - Linux: notify-send → dbus
    - Windows: win10toast → plyer

    All notifications are fire-and-forget (do not block on errors).
    """

    # Title and message length limits
    MAX_TITLE_LENGTH = 50
    MAX_MESSAGE_LENGTH = 200

    def __init__(self):
        """Initialize desktop notification service with platform detection."""
        # T136: Implement platform detection
        self.platform = platform.system()
        logger.info(f"Desktop notification service initialized for platform: {self.platform}")

    def is_available(self) -> bool:
        """
        Check if desktop notifications are available on this platform.

        Returns:
            bool: True if notifications are supported, False otherwise

        Implements: T143
        """
        return self.platform in ["Darwin", "Linux", "Windows"]

    def send_notification(self, title: str, message: str) -> None:
        """
        Send a desktop notification.

        This is a fire-and-forget operation - errors are logged but not raised.

        Args:
            title: Notification title (truncated to MAX_TITLE_LENGTH)
            message: Notification message (truncated to MAX_MESSAGE_LENGTH)

        Implements: T132 (formatting), T144 (fire-and-forget)
        """
        try:
            # T132: Truncate title and message
            title = self._truncate(title, self.MAX_TITLE_LENGTH)
            message = self._truncate(message, self.MAX_MESSAGE_LENGTH)

            # Route to platform-specific implementation
            if self.platform == "Darwin":
                self._send_macos(title, message)
            elif self.platform == "Linux":
                self._send_linux(title, message)
            elif self.platform == "Windows":
                self._send_windows(title, message)
            else:
                logger.warning(f"Desktop notifications not supported on platform: {self.platform}")

        except Exception as e:
            # T144: Fire-and-forget - log error but don't raise
            logger.error(f"Failed to send desktop notification: {e}")

    def _send_macos(self, title: str, message: str) -> None:
        """
        Send notification on macOS.

        Uses pync if available, falls back to osascript.

        Implements: T137 (pync), T138 (osascript fallback)
        """
        # T137: Try pync first
        if pync is not None:
            try:
                pync.notify(message, title=title, sound=None)
                return
            except Exception as e:
                logger.warning(f"pync failed, trying osascript fallback: {e}")

        # T138: Fallback to osascript
        self._send_macos_fallback(title, message)

    def _send_macos_fallback(self, title: str, message: str) -> None:
        """
        Send notification using osascript on macOS.

        Implements: T138
        """
        try:
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=5)
        except Exception as e:
            logger.error(f"osascript notification failed: {e}")

    def _send_linux(self, title: str, message: str) -> None:
        """
        Send notification on Linux.

        Uses notify-send if available, falls back to dbus.

        Implements: T139 (notify-send), T140 (dbus fallback)
        """
        # T139: Try notify-send first
        try:
            result = subprocess.run(["notify-send", title, message], capture_output=True, timeout=5)
            if result.returncode == 0:
                return
        except Exception as e:
            logger.warning(f"notify-send failed, trying dbus fallback: {e}")

        # T140: Fallback to dbus
        self._send_linux_fallback(title, message)

    def _send_linux_fallback(self, title: str, message: str) -> None:
        """
        Send notification using dbus on Linux.

        Implements: T140
        """
        try:
            subprocess.run(
                [
                    "dbus-send",
                    "--session",
                    "--dest=org.freedesktop.Notifications",
                    "--type=method_call",
                    "/org/freedesktop/Notifications",
                    "org.freedesktop.Notifications.Notify",
                    "string:Codeframe",
                    "uint32:0",
                    "string:",
                    f"string:{title}",
                    f"string:{message}",
                    "array:string:",
                    "dict:string:string:",
                    "int32:5000",
                ],
                check=True,
                capture_output=True,
                timeout=5,
            )
        except Exception as e:
            logger.error(f"dbus notification failed: {e}")

    def _send_windows(self, title: str, message: str) -> None:
        """
        Send notification on Windows.

        Uses win10toast if available, falls back to plyer.

        Implements: T141 (win10toast), T142 (plyer fallback)
        """
        # T141: Try win10toast first
        if ToastNotifier is not None:
            try:
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=5, threaded=True)
                return
            except Exception as e:
                logger.warning(f"win10toast failed, trying plyer fallback: {e}")

        # T142: Fallback to plyer
        self._send_windows_fallback(title, message)

    def _send_windows_fallback(self, title: str, message: str) -> None:
        """
        Send notification using plyer on Windows.

        Implements: T142
        """
        if notification is None:
            logger.error("No notification library available on Windows")
            return

        try:
            notification.notify(title=title, message=message, app_name="Codeframe", timeout=5)
        except Exception as e:
            logger.error(f"plyer notification failed: {e}")

    def _truncate(self, text: str, max_length: int) -> str:
        """
        Truncate text to max length, adding ellipsis if truncated.

        Implements: T132
        """
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."
