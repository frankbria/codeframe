"""Integration tests for dynamic config reload during batch execution.

Tests the full flow: ConfigFileWatcher detects file changes and the
conductor applies reloaded config to subsequent task dispatches.
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codeframe.core.agents_config import load_preferences
from codeframe.core.config_watcher import ConfigFileWatcher
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


def wait_until(predicate, timeout_s: float = 10.0, poll_s: float = 0.02) -> bool:
    """Block until ``predicate()`` is true, or ``timeout_s`` elapses.

    These tests drive a background poller and previously just slept for a fixed
    0.5s, assuming a 0.1s poll interval had fired by then. That holds on an idle
    machine and fails on a loaded one — the watcher thread simply may not be
    scheduled in time — which made this module flake under a full-suite run.

    Waiting on the condition instead of the clock is both reliable and faster:
    it returns as soon as the poller has done its work rather than always
    burning the whole budget. The generous timeout only bounds the failure case.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(poll_s)
    return predicate()


@pytest.fixture
def workspace(tmp_path: Path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return create_or_load_workspace(repo_path)


class TestConfigReloadLifecycle:
    """End-to-end: write config → detect change → reload → verify new prefs."""

    def test_full_reload_cycle(self, workspace):
        """Simulate a batch execution where config is modified mid-run."""
        # Step 1: Create initial config
        agents_path = workspace.repo_path / "AGENTS.md"
        agents_path.write_text(
            "# Always Do\n"
            "- Run tests after changes\n"
            "- Use type hints\n"
            "\n"
            "# Never Do\n"
            "- Delete production data\n"
        )

        # Step 2: Load initial preferences
        initial_prefs = load_preferences(workspace.repo_path)
        assert "Run tests after changes" in initial_prefs.always_do

        # Step 3: Start watcher
        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        state = watcher.start(initial_prefs)

        try:
            # Step 4: Verify initial state
            prefs = state.get_prefs()
            assert "Run tests after changes" in prefs.always_do
            assert state.last_reload_at is None

            # Step 5: Modify config (simulating operator change during batch)
            time.sleep(0.3)
            agents_path.write_text(
                "# Always Do\n"
                "- Run tests after changes\n"
                "- Use type hints\n"
                "- Log all API calls\n"
                "\n"
                "# Never Do\n"
                "- Delete production data\n"
                "- Modify database schema directly\n"
            )
            future_time = time.time() + 1
            os.utime(agents_path, (future_time, future_time))

            # Step 6: Wait for the watcher to notice the change.
            wait_until(lambda: state.last_reload_at is not None)

            # Step 7: Verify reload happened
            assert state.last_reload_at is not None
            new_prefs = state.get_prefs()
            assert "Log all API calls" in new_prefs.always_do
            assert "Modify database schema directly" in new_prefs.never_do
            assert len(state.reload_timestamps) == 1

        finally:
            watcher.stop()

    def test_multiple_reloads(self, workspace):
        """Config changed twice during execution → two reload events."""
        agents_path = workspace.repo_path / "AGENTS.md"
        agents_path.write_text("# Always Do\n- Original\n")

        initial_prefs = load_preferences(workspace.repo_path)
        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        state = watcher.start(initial_prefs)

        try:
            # First change
            time.sleep(0.3)
            agents_path.write_text("# Always Do\n- First update\n")
            os.utime(agents_path, (time.time() + 1, time.time() + 1))
            wait_until(lambda: len(state.reload_timestamps) >= 1)

            assert len(state.reload_timestamps) == 1
            assert "First update" in state.get_prefs().always_do

            # Second change
            agents_path.write_text("# Always Do\n- Second update\n")
            os.utime(agents_path, (time.time() + 2, time.time() + 2))
            wait_until(lambda: len(state.reload_timestamps) >= 2)

            assert len(state.reload_timestamps) == 2
            assert "Second update" in state.get_prefs().always_do

        finally:
            watcher.stop()

    def test_invalid_reload_preserves_last_good(self, workspace):
        """Invalid config change doesn't overwrite good config."""
        from unittest.mock import patch

        agents_path = workspace.repo_path / "AGENTS.md"
        agents_path.write_text("# Always Do\n- Original good config\n")

        initial_prefs = load_preferences(workspace.repo_path)
        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        state = watcher.start(initial_prefs)

        try:
            time.sleep(0.3)

            # Simulate a parse failure on reload
            with patch(
                "codeframe.core.config_watcher.load_preferences",
                side_effect=RuntimeError("Parse failed"),
            ):
                agents_path.write_text("corrupt")
                os.utime(agents_path, (time.time() + 1, time.time() + 1))
                # Wait for the failed reload attempt to be recorded — the patch
                # must still be active when the watcher thread runs, so this
                # cannot be moved outside the `with` block.
                wait_until(lambda: state.last_error is not None)

            # Original config preserved
            assert "Original good config" in state.get_prefs().always_do
            assert state.last_error is not None
            assert len(state.reload_timestamps) == 0  # No successful reloads

        finally:
            watcher.stop()

    def test_has_reloaded_since_tracks_correctly(self, workspace):
        """has_reloaded_since correctly reports reload relative to checkpoint."""
        agents_path = workspace.repo_path / "AGENTS.md"
        agents_path.write_text("# Always Do\n- Initial\n")

        initial_prefs = load_preferences(workspace.repo_path)
        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        state = watcher.start(initial_prefs)

        try:
            checkpoint = datetime.now(timezone.utc)
            assert not state.has_reloaded_since(checkpoint)

            time.sleep(0.3)
            agents_path.write_text("# Always Do\n- Changed\n")
            os.utime(agents_path, (time.time() + 1, time.time() + 1))
            wait_until(lambda: state.has_reloaded_since(checkpoint))

            assert state.has_reloaded_since(checkpoint)

            # New checkpoint after the reload
            new_checkpoint = datetime.now(timezone.utc)
            assert not state.has_reloaded_since(new_checkpoint)

        finally:
            watcher.stop()

    def test_watcher_stops_cleanly(self, workspace):
        """Watcher thread terminates within reasonable time on stop()."""
        agents_path = workspace.repo_path / "AGENTS.md"
        agents_path.write_text("# Always Do\n- Test\n")

        initial_prefs = load_preferences(workspace.repo_path)
        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        watcher.start(initial_prefs)

        import threading

        active_before = threading.active_count()
        watcher.stop()

        # Thread should have stopped (or at most still cleaning up)
        time.sleep(0.2)
        active_after = threading.active_count()
        assert active_after <= active_before
