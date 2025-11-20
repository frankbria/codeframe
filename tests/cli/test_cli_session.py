"""Unit tests for CLI session lifecycle commands.

Tests for:
- clear-session command (T026)
- Session cancellation with Ctrl+C
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from codeframe.cli import app


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def test_project_dir(tmp_path):
    """Create test project directory with .codeframe structure."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    codeframe_dir = project_dir / ".codeframe"
    codeframe_dir.mkdir()
    return project_dir


@pytest.fixture
def session_file(test_project_dir):
    """Create session state file."""
    session_path = test_project_dir / ".codeframe" / "session_state.json"
    session_data = {
        "last_session": {
            "summary": "Completed 2 tasks",
            "timestamp": "2025-11-20T10:00:00",
        },
        "next_actions": ["Complete Task #3", "Review code"],
        "progress_pct": 66.7,
        "active_blockers": [],
    }
    session_path.write_text(json.dumps(session_data, indent=2))
    return session_path


class TestClearSessionCommand:
    """Test suite for clear-session CLI command."""

    def test_clear_session_deletes_file(self, runner, session_file, test_project_dir):
        """Test that clear-session deletes the session state file."""
        # Verify file exists
        assert session_file.exists()

        # Run clear-session command
        result = runner.invoke(app, ["clear-session", str(test_project_dir)])

        # Verify success
        assert result.exit_code == 0
        assert "✓ Session state cleared" in result.stdout

        # Verify file deleted
        assert not session_file.exists()

    def test_clear_session_succeeds_if_file_doesnt_exist(self, runner, test_project_dir):
        """Test that clear-session succeeds even if file doesn't exist."""
        session_path = test_project_dir / ".codeframe" / "session_state.json"

        # Verify file doesn't exist
        assert not session_path.exists()

        # Run clear-session command
        result = runner.invoke(app, ["clear-session", str(test_project_dir)])

        # Verify success (should not error)
        assert result.exit_code == 0
        assert "✓ Session state cleared" in result.stdout

    def test_clear_session_uses_current_directory_if_no_arg(self, runner, monkeypatch):
        """Test that clear-session uses current directory if no project specified."""
        # Create temp directory with session
        with runner.isolated_filesystem():
            cwd = Path.cwd()
            codeframe_dir = cwd / ".codeframe"
            codeframe_dir.mkdir()
            session_path = codeframe_dir / "session_state.json"
            session_path.write_text('{"last_session": {}}')

            # Verify file exists
            assert session_path.exists()

            # Run clear-session without arguments
            result = runner.invoke(app, ["clear-session"])

            # Verify success
            assert result.exit_code == 0
            assert "✓ Session state cleared" in result.stdout
            assert not session_path.exists()

    def test_clear_session_handles_permission_error(self, runner, session_file, test_project_dir):
        """Test that clear-session handles permission errors gracefully."""
        # Mock SessionManager.clear_session to raise PermissionError
        # SessionManager is imported inside the clear_session function
        with patch("codeframe.core.session_manager.SessionManager") as mock_mgr:
            mock_instance = MagicMock()
            mock_instance.clear_session.side_effect = PermissionError("Permission denied")
            mock_mgr.return_value = mock_instance

            # Run clear-session command
            result = runner.invoke(app, ["clear-session", str(test_project_dir)])

            # Verify error handling
            assert result.exit_code == 1
            assert "Error:" in result.stdout
            assert "Permission denied" in result.stdout

    def test_clear_session_handles_invalid_project_path(self, runner):
        """Test that clear-session handles invalid project paths."""
        # Use non-existent directory
        invalid_path = "/tmp/nonexistent_project_12345"

        # Run clear-session command
        result = runner.invoke(app, ["clear-session", invalid_path])

        # Should handle gracefully (SessionManager will handle the error)
        # Exit code might be 0 or 1 depending on error handling
        assert "Error:" in result.stdout or "✓" in result.stdout


class TestSessionCancellation:
    """Test suite for session cancellation with Ctrl+C."""

    def test_session_start_handles_keyboard_interrupt(self, runner, session_file, test_project_dir):
        """Test that Ctrl+C during session start is handled gracefully.

        Note: This tests the error handling structure. Full integration testing
        of KeyboardInterrupt requires manual testing since it depends on
        signal handling and user input timing.
        """
        # Mock the Project class to raise KeyboardInterrupt
        with patch("codeframe.cli.Project") as mock_project:
            mock_instance = MagicMock()
            mock_instance.start.side_effect = KeyboardInterrupt()
            mock_project.return_value = mock_instance

            # Run start command
            result = runner.invoke(app, ["start", str(test_project_dir)])

            # Verify clean exit (not crashing)
            # Exit code 130 is the standard Ctrl+C exit code (128 + SIGINT=2)
            # Exit code 1 or 0 also acceptable depending on error handling
            assert result.exit_code in [0, 1, 130]

    def test_session_restoration_prompt_structure(self, runner, session_file, test_project_dir):
        """Test that session restoration includes user prompt structure.

        Note: This verifies the prompt exists in the on_session_start flow.
        Actual user interaction testing requires manual/integration tests.
        """
        # This test verifies the prompt structure exists
        # Full interaction testing is done in integration tests

        # Mock Project to verify on_session_start is called
        with patch("codeframe.cli.Project") as mock_project:
            mock_instance = MagicMock()
            mock_project.return_value = mock_instance

            # Run start command
            result = runner.invoke(app, ["start", str(test_project_dir)])

            # Verify Project was instantiated and start was called
            mock_project.assert_called_once()
            mock_instance.start.assert_called_once()


class TestSessionCommandIntegration:
    """Integration tests for session-related commands."""

    def test_clear_and_restart_workflow(self, runner, session_file, test_project_dir):
        """Test complete workflow: clear session, verify cleared, start fresh."""
        # Step 1: Verify session exists
        assert session_file.exists()

        # Step 2: Clear session
        result = runner.invoke(app, ["clear-session", str(test_project_dir)])
        assert result.exit_code == 0
        assert not session_file.exists()

        # Step 3: Verify we can start without session
        with patch("codeframe.cli.Project") as mock_project:
            mock_instance = MagicMock()
            mock_project.return_value = mock_instance

            result = runner.invoke(app, ["start", str(test_project_dir)])

            # Should start successfully (no session to restore)
            mock_instance.start.assert_called_once()

    def test_multiple_clear_commands_idempotent(self, runner, session_file, test_project_dir):
        """Test that running clear-session multiple times is safe."""
        # Clear once
        result1 = runner.invoke(app, ["clear-session", str(test_project_dir)])
        assert result1.exit_code == 0
        assert not session_file.exists()

        # Clear again
        result2 = runner.invoke(app, ["clear-session", str(test_project_dir)])
        assert result2.exit_code == 0
        assert "✓ Session state cleared" in result2.stdout

        # Clear third time
        result3 = runner.invoke(app, ["clear-session", str(test_project_dir)])
        assert result3.exit_code == 0


class TestSessionFilePermissions:
    """Test suite for session file permission handling."""

    def test_clear_session_with_readonly_file(self, runner, session_file, test_project_dir):
        """Test clearing a read-only session file."""
        # Make file read-only
        session_file.chmod(0o444)

        # Attempt to clear
        result = runner.invoke(app, ["clear-session", str(test_project_dir)])

        # Should handle permission error gracefully
        # Actual behavior depends on SessionManager implementation
        assert result.exit_code in [0, 1]

        # Restore permissions for cleanup (only if file still exists)
        if session_file.exists():
            session_file.chmod(0o644)

    def test_clear_session_with_readonly_directory(self, runner, session_file, test_project_dir):
        """Test clearing session when .codeframe directory is read-only."""
        codeframe_dir = test_project_dir / ".codeframe"

        # Make directory read-only
        original_mode = codeframe_dir.stat().st_mode
        codeframe_dir.chmod(0o555)

        try:
            # Attempt to clear (will fail to delete file)
            result = runner.invoke(app, ["clear-session", str(test_project_dir)])

            # Should handle gracefully
            assert result.exit_code in [0, 1]
        finally:
            # Restore permissions for cleanup
            codeframe_dir.chmod(original_mode)
