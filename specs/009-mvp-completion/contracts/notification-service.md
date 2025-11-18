# Desktop Notification Service Contract

**Feature**: Desktop Notifications
**Sprint**: 009-mvp-completion
**Date**: 2025-11-15

## Overview

The Desktop Notification Service provides cross-platform desktop notifications for SYNC blockers. This improves local development UX by providing immediate, native feedback without requiring external webhook services.

---

## Service Interface

### DesktopNotificationService

**Location**: `codeframe/notifications/desktop.py`

```python
from typing import Optional, Literal
from dataclasses import dataclass

@dataclass
class NotificationConfig:
    """Desktop notification configuration."""
    enabled: bool = True
    sound: bool = True
    urgency: Literal['low', 'normal', 'critical'] = 'critical'
    duration: int = 10  # seconds (Windows/custom implementations)
    click_action: Optional[str] = None  # URL to open on click


class DesktopNotificationService:
    """Cross-platform desktop notification service."""

    def __init__(self, config: Optional[NotificationConfig] = None):
        """
        Initialize notification service.

        Args:
            config: Notification configuration (uses defaults if None)
        """
        self.config = config or NotificationConfig()
        self.platform = self._detect_platform()
        self._validate_availability()

    def send_notification(
        self,
        title: str,
        message: str,
        urgency: Optional[Literal['low', 'normal', 'critical']] = None,
        click_action: Optional[str] = None
    ) -> bool:
        """
        Send desktop notification.

        Args:
            title: Notification title (max 50 chars)
            message: Notification message (max 200 chars)
            urgency: Override default urgency level
            click_action: URL to open when notification clicked

        Returns:
            True if notification sent successfully, False otherwise

        Raises:
            NotificationError: If notification delivery fails critically
        """
        pass

    def is_available(self) -> bool:
        """
        Check if desktop notifications are available on this platform.

        Returns:
            True if notifications can be sent, False otherwise
        """
        pass

    def _detect_platform(self) -> str:
        """Detect current platform (darwin, linux, windows)."""
        pass

    def _send_macos(self, title: str, message: str, **kwargs) -> bool:
        """Send notification on macOS."""
        pass

    def _send_linux(self, title: str, message: str, **kwargs) -> bool:
        """Send notification on Linux."""
        pass

    def _send_windows(self, title: str, message: str, **kwargs) -> bool:
        """Send notification on Windows."""
        pass
```

---

## Platform Implementations

### macOS

**Primary Method**: `pync` library

```python
def _send_macos(self, title: str, message: str, **kwargs) -> bool:
    """Send notification on macOS using pync."""
    try:
        import pync

        pync.notify(
            message,
            title=title,
            sound='default' if self.config.sound else None,
            open=kwargs.get('click_action', self.config.click_action)
        )
        return True

    except ImportError:
        logger.warning("pync not installed, falling back to osascript")
        return self._send_macos_fallback(title, message, **kwargs)

    except Exception as e:
        logger.error(f"Failed to send macOS notification: {e}")
        return False


def _send_macos_fallback(self, title: str, message: str, **kwargs) -> bool:
    """Fallback to osascript (AppleScript) if pync unavailable."""
    import subprocess

    # Escape quotes in message
    message_escaped = message.replace('"', '\\"')
    title_escaped = title.replace('"', '\\"')

    sound_line = 'sound name "Glass"' if self.config.sound else ''

    script = f'''
    display notification "{message_escaped}"
    with title "{title_escaped}"
    {sound_line}
    '''

    try:
        subprocess.run(
            ['osascript', '-e', script],
            check=True,
            capture_output=True,
            timeout=5
        )
        return True
    except Exception as e:
        logger.error(f"osascript fallback failed: {e}")
        return False
```

### Linux

**Primary Method**: `notify-send` (libnotify)

```python
def _send_linux(self, title: str, message: str, **kwargs) -> bool:
    """Send notification on Linux using notify-send."""
    import subprocess

    urgency = kwargs.get('urgency', self.config.urgency)
    urgency_map = {
        'low': 'low',
        'normal': 'normal',
        'critical': 'critical'
    }

    cmd = [
        'notify-send',
        f'--urgency={urgency_map[urgency]}',
        '--icon=dialog-information',  # Can customize icon
        '--app-name=CodeFRAME',
        title,
        message
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=5
        )
        return True

    except FileNotFoundError:
        logger.warning("notify-send not found, trying dbus fallback")
        return self._send_linux_fallback(title, message, **kwargs)

    except Exception as e:
        logger.error(f"Failed to send Linux notification: {e}")
        return False


def _send_linux_fallback(self, title: str, message: str, **kwargs) -> bool:
    """Fallback to D-Bus if notify-send unavailable."""
    try:
        import dbus

        bus = dbus.SessionBus()
        notify_obj = bus.get_object(
            'org.freedesktop.Notifications',
            '/org/freedesktop/Notifications'
        )
        interface = dbus.Interface(notify_obj, 'org.freedesktop.Notifications')

        # Send notification
        interface.Notify(
            'CodeFRAME',       # app_name
            0,                 # replaces_id
            '',                # app_icon
            title,             # summary
            message,           # body
            [],                # actions
            {},                # hints
            5000               # timeout (ms)
        )
        return True

    except ImportError:
        logger.error("dbus-python not installed, cannot send notification")
        return False
    except Exception as e:
        logger.error(f"D-Bus fallback failed: {e}")
        return False
```

### Windows

**Primary Method**: `win10toast`

```python
def _send_windows(self, title: str, message: str, **kwargs) -> bool:
    """Send notification on Windows using win10toast."""
    try:
        from win10toast import ToastNotifier

        toaster = ToastNotifier()
        toaster.show_toast(
            title,
            message,
            duration=self.config.duration,
            threaded=True  # Non-blocking
        )
        return True

    except ImportError:
        logger.warning("win10toast not installed, trying plyer fallback")
        return self._send_windows_fallback(title, message, **kwargs)

    except Exception as e:
        logger.error(f"Failed to send Windows notification: {e}")
        return False


def _send_windows_fallback(self, title: str, message: str, **kwargs) -> bool:
    """Fallback to plyer (cross-platform abstraction)."""
    try:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            app_name='CodeFRAME',
            timeout=self.config.duration
        )
        return True

    except ImportError:
        logger.error("plyer not installed, cannot send notification")
        return False
    except Exception as e:
        logger.error(f"plyer fallback failed: {e}")
        return False
```

---

## Notification Router

Coordinates between desktop notifications and webhook notifications.

**Location**: `codeframe/notifications/router.py`

```python
from typing import Optional
from codeframe.notifications.desktop import DesktopNotificationService
from codeframe.notifications.webhook import WebhookNotificationService

class NotificationRouter:
    """Routes notifications to appropriate delivery channels."""

    def __init__(
        self,
        desktop_service: Optional[DesktopNotificationService] = None,
        webhook_service: Optional[WebhookNotificationService] = None
    ):
        self.desktop = desktop_service or DesktopNotificationService()
        self.webhook = webhook_service

    async def notify_blocker(
        self,
        blocker_id: int,
        project_id: int,
        question: str,
        blocker_type: str
    ) -> None:
        """
        Send notification for new blocker.

        Args:
            blocker_id: Blocker ID
            project_id: Project ID
            question: Blocker question (truncated for desktop)
            blocker_type: SYNC or ASYNC
        """
        # Desktop notification (local only, for SYNC blockers)
        if blocker_type == 'SYNC' and self.desktop.is_available():
            title = f"CodeFRAME: Agent Blocked"
            message = self._truncate_message(question, max_length=200)

            success = self.desktop.send_notification(
                title=title,
                message=message,
                urgency='critical',
                click_action=f'http://localhost:3000/projects/{project_id}#blocker-{blocker_id}'
            )

            if not success:
                logger.warning(f"Desktop notification failed for blocker {blocker_id}")

        # Webhook notification (remote, for both SYNC and ASYNC)
        if self.webhook:
            await self.webhook.send_blocker_notification(
                blocker_id=blocker_id,
                project_id=project_id,
                question=question,
                blocker_type=blocker_type
            )

    def _truncate_message(self, message: str, max_length: int = 200) -> str:
        """Truncate message to max length, adding ellipsis if needed."""
        if len(message) <= max_length:
            return message

        return message[:max_length - 3] + '...'
```

---

## Configuration

### Project Config (config.json)

```json
{
  "notifications": {
    "desktop": {
      "enabled": true,
      "sound": true,
      "urgency": "critical",
      "duration": 10,
      "sync_only": true  // Only send desktop notifications for SYNC blockers
    },
    "webhook": {
      "enabled": false,
      "url": null
    }
  }
}
```

### Environment Variables

```bash
# Disable desktop notifications globally
CODEFRAME_DESKTOP_NOTIFICATIONS=false

# Override urgency level
CODEFRAME_NOTIFICATION_URGENCY=normal  # low, normal, critical

# Enable sound
CODEFRAME_NOTIFICATION_SOUND=true
```

---

## Integration with Blockers

### Worker Agent Integration

```python
# In worker_agent.py or blocker creation logic

from codeframe.notifications.router import NotificationRouter

class WorkerAgent:
    def __init__(self, ...):
        self.notification_router = NotificationRouter()

    async def create_blocker(
        self,
        question: str,
        blocker_type: str,
        task_id: int
    ) -> int:
        """Create blocker and send notification."""

        # Create blocker in database
        blocker_id = self.db.create_blocker(
            project_id=self.project_id,
            type=blocker_type,
            question=question,
            task_id=task_id,
            blocking_agent_id=self.agent_id
        )

        # Send notification
        await self.notification_router.notify_blocker(
            blocker_id=blocker_id,
            project_id=self.project_id,
            question=question,
            blocker_type=blocker_type
        )

        return blocker_id
```

---

## Error Handling

### Notification Unavailable

**Scenario**: Platform doesn't support desktop notifications (e.g., headless server)

**Behavior**:
- `is_available()` returns False
- Skip desktop notification silently
- Fall back to webhook if configured
- Log info: "Desktop notifications not available on this platform"

### Notification Timeout

**Scenario**: Notification library hangs or takes too long

**Behavior**:
- Timeout after 5 seconds
- Log warning: "Notification timeout"
- Don't block blocker creation
- Continue execution

### Multiple Notification Failures

**Scenario**: 3+ consecutive notification failures

**Behavior**:
- Disable desktop notifications for session
- Log error: "Desktop notifications disabled due to repeated failures"
- Create ASYNC blocker: "Notification system failure"
- User can re-enable via config

---

## Testing

### Unit Tests (10 tests)

1. `test_detect_platform_macos()` - Platform detection on macOS
2. `test_detect_platform_linux()` - Platform detection on Linux
3. `test_detect_platform_windows()` - Platform detection on Windows
4. `test_send_notification_macos()` - macOS notification delivery
5. `test_send_notification_linux()` - Linux notification delivery
6. `test_send_notification_windows()` - Windows notification delivery
7. `test_fallback_to_osascript()` - macOS fallback when pync unavailable
8. `test_fallback_to_dbus()` - Linux fallback when notify-send unavailable
9. `test_notification_router()` - Router sends to desktop + webhook
10. `test_notification_truncation()` - Long messages truncated correctly

### Integration Tests (2 tests)

1. `test_blocker_notification_sync()` - SYNC blocker triggers desktop notification
2. `test_blocker_notification_async()` - ASYNC blocker skips desktop, sends webhook

### Manual Testing Checklist

- [ ] macOS: Notification appears in Notification Center
- [ ] macOS: Sound plays (if enabled)
- [ ] macOS: Click opens dashboard URL
- [ ] Linux (GNOME): Notification appears in top-right
- [ ] Linux (KDE): Notification appears in system tray
- [ ] Linux: Urgency level affects appearance
- [ ] Windows: Toast notification appears in bottom-right
- [ ] Windows: Notification duration respected
- [ ] All platforms: Truncation works for long messages
- [ ] All platforms: Graceful degradation when library unavailable

---

## Performance

**Expected Metrics**:
- Notification delivery: <500ms (local only)
- Platform detection: <10ms (cached)
- Fallback attempts: <2 seconds (with timeout)

**Optimization**:
- Cache platform detection result
- Fire-and-forget delivery (don't block blocker creation)
- Timeout aggressive (5 seconds max)

---

## Security Considerations

1. **Message Sanitization**: Escape special characters for shell commands
2. **Click Action Validation**: Validate URL is localhost or trusted domain
3. **No Sensitive Data**: Don't include secrets/tokens in notifications
4. **User Consent**: Respect system notification preferences

---

## Platform-Specific Notes

### macOS

- **Requirements**: macOS 10.8+ (Mountain Lion)
- **Permissions**: Notification access granted by system (user prompt)
- **Icon**: Uses default application icon (can customize with pync)
- **Sound**: System sounds available: "Glass", "Hero", "Ping", etc.

### Linux

- **Requirements**: D-Bus session bus, notification daemon
- **Desktop Environments**: GNOME, KDE, XFCE, Cinnamon, etc.
- **Icon**: Can use custom icon path or standard icon names
- **Urgency**: Affects visual appearance and persistence

### Windows

- **Requirements**: Windows 10+ (for toast notifications)
- **Permissions**: App registration required for persistent notifications
- **Duration**: Windows controls actual duration (may override)
- **Action Center**: Notifications persist in Action Center

---

## Dependencies

### Required (for full functionality)

**macOS**:
```bash
pip install pync  # Python Notification Center
```

**Windows**:
```bash
pip install win10toast  # Windows 10 toast notifications
```

### Optional (fallbacks)

**Linux**:
```bash
sudo apt-get install libnotify-bin  # notify-send command
pip install dbus-python  # D-Bus fallback
```

**Cross-platform**:
```bash
pip install plyer  # Cross-platform notification abstraction
```

### Installation in setup.py

```python
extras_require = {
    'notifications': [
        'pync>=2.0.3; sys_platform == "darwin"',
        'win10toast>=0.9; sys_platform == "win32"',
        'dbus-python>=1.2.18; sys_platform == "linux"'
    ]
}
```

---

## Future Enhancements (v2)

1. **Rich Notifications**: Images, buttons, progress bars
2. **Notification History**: Store sent notifications in database
3. **Custom Icons**: Per-blocker-type icons
4. **Sound Customization**: Custom sound files
5. **Notification Actions**: "Resolve", "Snooze", "View Details" buttons
6. **Mobile Notifications**: Push notifications to mobile devices
7. **Email Notifications**: Fallback to email if desktop unavailable
