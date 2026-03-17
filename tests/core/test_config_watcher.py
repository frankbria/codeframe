"""Tests for dynamic configuration reload during batch execution.

Tests cover:
- ConfigReloadState thread-safe shared state
- ConfigFileWatcher mtime-based file watching
- Validation of reloaded config (valid vs invalid)
- Event emission on reload
"""

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codeframe.core.agents_config import AgentPreferences
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return create_or_load_workspace(repo_path)


@pytest.fixture
def agents_md_path(workspace):
    """Create an AGENTS.md file in the workspace."""
    path = workspace.repo_path / "AGENTS.md"
    path.write_text(
        "# Always Do\n"
        "- Run tests after changes\n"
        "\n"
        "# Never Do\n"
        "- Delete production data\n"
    )
    return path


@pytest.fixture
def initial_prefs():
    return AgentPreferences(
        always_do=["Run tests after changes"],
        never_do=["Delete production data"],
        raw_content="initial config",
    )


# =============================================================================
# ConfigReloadState tests
# =============================================================================


class TestConfigReloadState:
    """Tests for thread-safe shared configuration state."""

    def test_initial_state(self, initial_prefs):
        from codeframe.core.config_watcher import ConfigReloadState

        state = ConfigReloadState(initial_prefs)
        prefs = state.get_prefs()
        assert prefs.always_do == ["Run tests after changes"]
        assert state.last_reload_at is None
        assert state.last_error is None

    def test_apply_reload_updates_prefs(self, initial_prefs):
        from codeframe.core.config_watcher import ConfigReloadState

        state = ConfigReloadState(initial_prefs)
        new_prefs = AgentPreferences(
            always_do=["Updated action"],
            raw_content="updated config",
        )
        now = datetime.now(timezone.utc)
        state.apply_reload(new_prefs, now)

        assert state.get_prefs().always_do == ["Updated action"]
        assert state.last_reload_at == now
        assert state.last_error is None

    def test_record_error_preserves_last_good(self, initial_prefs):
        from codeframe.core.config_watcher import ConfigReloadState

        state = ConfigReloadState(initial_prefs)
        state.record_error("Parse failed: invalid YAML")

        assert state.get_prefs().always_do == ["Run tests after changes"]
        assert state.last_error == "Parse failed: invalid YAML"

    def test_thread_safe_access(self, initial_prefs):
        from codeframe.core.config_watcher import ConfigReloadState

        state = ConfigReloadState(initial_prefs)
        errors = []

        def reader():
            for _ in range(100):
                prefs = state.get_prefs()
                if prefs is None:
                    errors.append("got None")

        def writer():
            for i in range(100):
                new_prefs = AgentPreferences(
                    always_do=[f"action-{i}"],
                    raw_content=f"config-{i}",
                )
                state.apply_reload(new_prefs, datetime.now(timezone.utc))

        threads = [threading.Thread(target=reader) for _ in range(3)]
        threads.append(threading.Thread(target=writer))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert state.get_prefs() is not None

    def test_has_reloaded_since(self, initial_prefs):
        from codeframe.core.config_watcher import ConfigReloadState

        state = ConfigReloadState(initial_prefs)
        before = datetime.now(timezone.utc)

        assert not state.has_reloaded_since(before)

        new_prefs = AgentPreferences(raw_content="new")
        state.apply_reload(new_prefs, datetime.now(timezone.utc))

        assert state.has_reloaded_since(before)


# =============================================================================
# ConfigFileWatcher tests
# =============================================================================


class TestConfigFileWatcher:
    """Tests for file-watching daemon thread."""

    def test_start_and_stop(self, workspace, agents_md_path, initial_prefs):
        from codeframe.core.config_watcher import ConfigFileWatcher

        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        state = watcher.start(initial_prefs)
        assert state is not None
        assert state.get_prefs().always_do == ["Run tests after changes"]
        watcher.stop()

    def test_detects_file_change(self, workspace, agents_md_path, initial_prefs):
        from codeframe.core.config_watcher import ConfigFileWatcher

        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        state = watcher.start(initial_prefs)

        try:
            # Modify the file
            time.sleep(0.3)
            agents_md_path.write_text(
                "# Always Do\n"
                "- Updated action item\n"
                "\n"
                "# Never Do\n"
                "- Updated forbidden action\n"
            )
            # Bump mtime to ensure detection
            future_time = time.time() + 1
            os.utime(agents_md_path, (future_time, future_time))

            # Wait for detection
            time.sleep(0.5)

            assert state.last_reload_at is not None
            prefs = state.get_prefs()
            assert "Updated action item" in prefs.always_do
        finally:
            watcher.stop()

    def test_invalid_config_retains_previous(self, workspace, agents_md_path, initial_prefs):
        from unittest.mock import patch

        from codeframe.core.config_watcher import ConfigFileWatcher

        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        state = watcher.start(initial_prefs)

        try:
            time.sleep(0.3)
            # Make load_preferences raise to simulate parse failure
            with patch(
                "codeframe.core.config_watcher.load_preferences",
                side_effect=ValueError("Corrupt config file"),
            ):
                # Touch the file to trigger mtime change
                agents_md_path.write_text("corrupt data")
                future_time = time.time() + 1
                os.utime(agents_md_path, (future_time, future_time))

                time.sleep(0.5)

            # Previous config should be retained
            prefs = state.get_prefs()
            assert prefs.always_do == ["Run tests after changes"]
            assert state.last_error is not None
            assert "Corrupt config" in state.last_error
        finally:
            watcher.stop()

    def test_watches_multiple_files(self, workspace, initial_prefs):
        from codeframe.core.config_watcher import ConfigFileWatcher

        # Create both AGENTS.md and CODEFRAME.md
        agents_path = workspace.repo_path / "AGENTS.md"
        agents_path.write_text("# Always Do\n- Original\n")

        codeframe_path = workspace.repo_path / "CODEFRAME.md"
        codeframe_path.write_text("---\nengine: react\n---\n# Always Do\n- From codeframe\n")

        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        state = watcher.start(initial_prefs)

        try:
            time.sleep(0.3)
            # Modify CODEFRAME.md
            codeframe_path.write_text(
                "---\nengine: react\n---\n# Always Do\n- Updated from codeframe\n"
            )
            future_time = time.time() + 1
            os.utime(codeframe_path, (future_time, future_time))

            time.sleep(0.5)

            assert state.last_reload_at is not None
        finally:
            watcher.stop()

    def test_stop_is_idempotent(self, workspace, agents_md_path, initial_prefs):
        from codeframe.core.config_watcher import ConfigFileWatcher

        watcher = ConfigFileWatcher(workspace.repo_path, poll_interval_s=0.1)
        watcher.start(initial_prefs)
        watcher.stop()
        watcher.stop()  # Should not raise
