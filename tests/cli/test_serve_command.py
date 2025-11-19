"""Tests for the serve CLI command."""

import subprocess
from unittest.mock import Mock, patch

from typer.testing import CliRunner


# Tests for serve command following TDD approach
runner = CliRunner()


class TestServeBasicFunctionality:
    """Test basic serve command functionality (User Story 1)."""

    @patch("codeframe.cli.subprocess.run")
    @patch("codeframe.cli.check_port_availability")
    def test_serve_default_port(self, mock_port_check, mock_run):
        """Test that serve command uses default port 8080."""
        from codeframe.cli import app

        # Mock port as available
        mock_port_check.return_value = (True, "")
        # Mock subprocess to avoid actually starting server
        mock_run.return_value = Mock(returncode=0)

        # Run command
        runner.invoke(app, ["serve", "--no-browser"])

        # Verify uvicorn was called with port 8080
        assert mock_run.called
        call_args = mock_run.call_args[0][0]  # Get the command list
        assert "uvicorn" in call_args
        assert "--port" in call_args
        port_index = call_args.index("--port") + 1
        assert call_args[port_index] == "8080"

    @patch("codeframe.cli.subprocess.run")
    @patch("codeframe.cli.check_port_availability")
    def test_serve_keyboard_interrupt(self, mock_port_check, mock_run):
        """Test graceful shutdown on Ctrl+C."""
        from codeframe.cli import app

        # Mock port as available
        mock_port_check.return_value = (True, "")
        # Mock subprocess to raise KeyboardInterrupt (simulating Ctrl+C)
        mock_run.side_effect = KeyboardInterrupt()

        # Run command - should handle KeyboardInterrupt gracefully
        result = runner.invoke(app, ["serve", "--no-browser"])

        # Should have attempted to start server
        assert mock_run.called
        # Should show shutdown message
        assert "Server stopped" in result.stdout


class TestServeCustomPort:
    """Test custom port configuration (User Story 2)."""

    @patch("codeframe.cli.subprocess.run")
    @patch("codeframe.cli.check_port_availability")
    def test_serve_custom_port(self, mock_port_check, mock_run):
        """Test that --port flag sets custom port."""
        from codeframe.cli import app

        # Mock port as available
        mock_port_check.return_value = (True, "")
        mock_run.return_value = Mock(returncode=0)

        # Run command with custom port
        runner.invoke(app, ["serve", "--port", "3000", "--no-browser"])

        # Verify uvicorn was called with port 3000
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "--port" in call_args
        port_index = call_args.index("--port") + 1
        assert call_args[port_index] == "3000"

    def test_serve_port_validation(self):
        """Test that port <1024 is rejected with helpful error."""
        from codeframe.cli import app

        # Attempt to use privileged port should fail
        result = runner.invoke(app, ["serve", "--port", "80"])
        assert result.exit_code != 0
        assert "elevated privileges" in result.stdout

    @patch("codeframe.cli.subprocess.run")
    @patch("codeframe.cli.check_port_availability")
    def test_serve_port_in_use(self, mock_port_check, mock_run):
        """Test helpful error when port is already in use."""
        from codeframe.cli import app

        # Simulate port already in use
        mock_port_check.return_value = (False, "Port 8080 is already in use")

        # Run command
        result = runner.invoke(app, ["serve"])

        # Should exit with error
        assert result.exit_code != 0
        # Should not attempt to start server
        assert not mock_run.called

    @patch("codeframe.cli.subprocess.run")
    @patch("codeframe.cli.check_port_availability")
    def test_serve_race_condition_port_conflict(self, mock_port_check, mock_run):
        """Test error handling when port becomes unavailable after check (race condition)."""
        from codeframe.cli import app

        # Port check passes
        mock_port_check.return_value = (True, "")

        # But uvicorn fails due to race condition
        mock_error = Mock()
        mock_error.stderr = "Error: [Errno 48] Address already in use"
        mock_error.returncode = 1
        mock_run.side_effect = subprocess.CalledProcessError(1, "uvicorn", stderr=mock_error.stderr)

        # Run command
        result = runner.invoke(app, ["serve", "--no-browser"])

        # Should exit with error
        assert result.exit_code != 0
        # Should show race condition message
        assert "race condition" in result.stdout.lower()
        assert "became unavailable" in result.stdout.lower()


class TestServeBrowserOpening:
    """Test browser auto-open functionality (User Story 3)."""

    @patch("codeframe.cli.threading.Thread")
    @patch("codeframe.cli.subprocess.run")
    @patch("codeframe.cli.check_port_availability")
    def test_serve_browser_opens(self, mock_port_check, mock_run, mock_thread):
        """Test that browser opens automatically by default."""
        from codeframe.cli import app

        # Mock port as available
        mock_port_check.return_value = (True, "")
        mock_run.return_value = Mock(returncode=0)
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        # Run command with default (browser enabled)
        runner.invoke(app, ["serve"])

        # Verify background thread was created for browser opening
        assert mock_thread.called
        # Verify thread was started
        assert mock_thread_instance.start.called

    @patch("codeframe.cli.threading.Thread")
    @patch("codeframe.cli.subprocess.run")
    @patch("codeframe.cli.check_port_availability")
    def test_serve_no_browser(self, mock_port_check, mock_run, mock_thread):
        """Test that --no-browser flag prevents browser opening."""
        from codeframe.cli import app

        # Mock port as available
        mock_port_check.return_value = (True, "")
        mock_run.return_value = Mock(returncode=0)

        # Run command with --no-browser
        runner.invoke(app, ["serve", "--no-browser"])

        # Browser thread should NOT be created
        assert not mock_thread.called


class TestServeReloadFlag:
    """Test development reload functionality (User Story 4)."""

    @patch("codeframe.cli.subprocess.run")
    @patch("codeframe.cli.check_port_availability")
    def test_serve_reload_flag(self, mock_port_check, mock_run):
        """Test that --reload flag is passed to uvicorn."""
        from codeframe.cli import app

        # Mock port as available
        mock_port_check.return_value = (True, "")
        mock_run.return_value = Mock(returncode=0)

        # Run command with --reload
        runner.invoke(app, ["serve", "--reload", "--no-browser"])

        # Verify --reload was passed to uvicorn
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "--reload" in call_args
