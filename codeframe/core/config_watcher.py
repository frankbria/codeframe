"""Dynamic configuration reload for batch execution.

Watches CODEFRAME.md, AGENTS.md, and CLAUDE.md for changes during
long-running batch executions and hot-reloads configuration without
restarting. Inspired by Symphony's dynamic WORKFLOW.md reload pattern.

Components:
- ConfigReloadState: Thread-safe shared state holding current config
- ConfigFileWatcher: Daemon thread polling file mtimes for changes

What reloads dynamically:
- Agent prompt / system prompt supplement (always_do, ask_first, never_do, raw_content)
- Tool preferences (tooling, commands)
- Code style preferences (code_style)

What requires restart (not reloaded):
- Engine selection (react/plan)
- Workspace path
- Tech stack

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from codeframe.core.agents_config import AgentPreferences, load_preferences

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Config files to watch, in priority order
_CONFIG_FILES = ("CODEFRAME.md", "AGENTS.md", "CLAUDE.md")


class ConfigReloadState:
    """Thread-safe shared state for dynamic config reload.

    Holds the last-known-good configuration and tracks reload history.
    Accessed by the watcher thread (writes) and the conductor (reads).
    """

    def __init__(self, initial_prefs: AgentPreferences) -> None:
        self._prefs = initial_prefs
        self._lock = threading.Lock()
        self.last_reload_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.reload_timestamps: list[str] = []

    def get_prefs(self) -> AgentPreferences:
        with self._lock:
            return self._prefs

    def apply_reload(self, new_prefs: AgentPreferences, timestamp: datetime) -> None:
        with self._lock:
            self._prefs = new_prefs
            self.last_reload_at = timestamp
            self.last_error = None
            self.reload_timestamps.append(timestamp.isoformat())

    def record_error(self, msg: str) -> None:
        with self._lock:
            self.last_error = msg

    def has_reloaded_since(self, since: datetime) -> bool:
        with self._lock:
            return self.last_reload_at is not None and self.last_reload_at > since


class ConfigFileWatcher:
    """Polling-based file watcher for config hot-reload.

    Monitors CODEFRAME.md, AGENTS.md, and CLAUDE.md for mtime changes.
    On change, re-parses and validates the config, updating shared state.

    Follows the same daemon-thread pattern as StallMonitor.

    Usage::

        watcher = ConfigFileWatcher(workspace_path, poll_interval_s=2.0)
        state = watcher.start(initial_prefs)
        try:
            # ... batch execution ...
            # Check state.get_prefs() between tasks
        finally:
            watcher.stop()
    """

    def __init__(
        self,
        workspace_path: Path,
        poll_interval_s: float = 2.0,
    ) -> None:
        self._workspace_path = workspace_path
        self._poll_interval_s = poll_interval_s
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state: Optional[ConfigReloadState] = None
        self._watched_mtimes: dict[Path, float] = {}

    def start(self, initial_prefs: AgentPreferences) -> ConfigReloadState:
        """Begin watching config files.

        Args:
            initial_prefs: The current agent preferences to use as baseline.

        Returns:
            Shared ConfigReloadState that the conductor can query.
        """
        self.stop()

        self._state = ConfigReloadState(initial_prefs)
        self._stop_event.clear()

        # Snapshot current mtimes
        self._watched_mtimes = {}
        for name in _CONFIG_FILES:
            path = self._workspace_path / name
            if path.is_file():
                self._watched_mtimes[path] = path.stat().st_mtime

        self._thread = threading.Thread(
            target=self._poll_loop,
            name="config-file-watcher",
            daemon=True,
        )
        self._thread.start()
        return self._state

    def stop(self) -> None:
        """Stop the watcher thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _poll_loop(self) -> None:
        """Daemon thread: check file mtimes at regular intervals."""
        while not self._stop_event.wait(timeout=self._poll_interval_s):
            self._check_for_changes()

    def _check_for_changes(self) -> None:
        """Compare current mtimes against snapshots."""
        changed = False

        for name in _CONFIG_FILES:
            path = self._workspace_path / name
            if not path.is_file():
                # File might have been created since start
                if path not in self._watched_mtimes:
                    continue
                # File was deleted — skip
                continue

            try:
                current_mtime = path.stat().st_mtime
            except OSError:
                continue

            prev_mtime = self._watched_mtimes.get(path, 0.0)
            if current_mtime > prev_mtime:
                self._watched_mtimes[path] = current_mtime
                changed = True

        # Also detect newly created config files
        for name in _CONFIG_FILES:
            path = self._workspace_path / name
            if path.is_file() and path not in self._watched_mtimes:
                self._watched_mtimes[path] = path.stat().st_mtime
                changed = True

        if changed:
            self._reload()

    def _reload(self) -> None:
        """Re-parse config files and update shared state."""
        try:
            new_prefs = load_preferences(self._workspace_path)

            if not new_prefs.has_preferences() and not new_prefs.raw_content:
                msg = "Reloaded config is empty — retaining previous config"
                logger.warning(msg)
                if self._state:
                    self._state.record_error(msg)
                self._emit_reload_failed(msg)
                return

            now = _utc_now()
            if self._state:
                old_prefs = self._state.get_prefs()
                self._state.apply_reload(new_prefs, now)
                diff = self._build_diff_summary(old_prefs, new_prefs)
                logger.info("Config reloaded: %s", diff)
                self._emit_reload_success(diff)

        except Exception as e:
            msg = f"Config reload failed: {e}"
            logger.warning(msg)
            if self._state:
                self._state.record_error(msg)
            self._emit_reload_failed(msg)

    def _build_diff_summary(
        self, old: AgentPreferences, new: AgentPreferences
    ) -> str:
        """Build a human-readable summary of what changed."""
        changes = []
        if old.always_do != new.always_do:
            changes.append(f"always_do: {len(old.always_do)} -> {len(new.always_do)} items")
        if old.never_do != new.never_do:
            changes.append(f"never_do: {len(old.never_do)} -> {len(new.never_do)} items")
        if old.ask_first != new.ask_first:
            changes.append(f"ask_first: {len(old.ask_first)} -> {len(new.ask_first)} items")
        if old.tooling != new.tooling:
            changes.append("tooling changed")
        if old.commands != new.commands:
            changes.append("commands changed")
        if old.code_style != new.code_style:
            changes.append("code_style changed")
        return "; ".join(changes) if changes else "content changed"

    def _emit_reload_success(self, diff_summary: str) -> None:
        """Emit CONFIG_RELOADED event (best-effort)."""
        try:
            from codeframe.core import events
            from codeframe.core.workspace import get_workspace

            workspace = get_workspace(self._workspace_path)
            events.emit_for_workspace(
                workspace,
                events.EventType.CONFIG_RELOADED,
                {"diff_summary": diff_summary},
                print_event=True,
            )
        except Exception:
            logger.debug("Failed to emit CONFIG_RELOADED event", exc_info=True)

    def _emit_reload_failed(self, error_msg: str) -> None:
        """Emit CONFIG_RELOAD_FAILED event (best-effort)."""
        try:
            from codeframe.core import events
            from codeframe.core.workspace import get_workspace

            workspace = get_workspace(self._workspace_path)
            events.emit_for_workspace(
                workspace,
                events.EventType.CONFIG_RELOAD_FAILED,
                {"error": error_msg},
                print_event=True,
            )
        except Exception:
            logger.debug("Failed to emit CONFIG_RELOAD_FAILED event", exc_info=True)
