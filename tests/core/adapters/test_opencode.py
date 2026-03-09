"""Tests for OpenCode adapter."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.adapters.agent_adapter import AgentAdapter
from codeframe.core.adapters.opencode import OpenCodeAdapter


class TestOpenCodeAdapter:
    """Unit tests for OpenCodeAdapter."""

    def test_name(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()
            assert adapter.name == "opencode"

    def test_conforms_to_protocol(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()
            assert isinstance(adapter, AgentAdapter)

    def test_raises_if_opencode_not_installed(self) -> None:
        with patch("shutil.which", return_value=None):
            with pytest.raises(EnvironmentError, match="not found on PATH"):
                OpenCodeAdapter()

    def test_build_command_includes_non_interactive(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()
            cmd = adapter.build_command("prompt", Path("/tmp"))
            assert cmd[0] == "/usr/bin/opencode"
            assert "--non-interactive" in cmd

    def test_sends_prompt_via_stdin(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()
            assert adapter.get_stdin("my prompt") == "my prompt"

    def test_successful_execution(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()

        mock_process = MagicMock()
        mock_process.stdout = iter(["Updated main.py\n"])
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""
        mock_process.stdin = MagicMock()
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "implement feature", Path("/tmp/repo"))

        assert result.status == "completed"
        assert "Updated main.py" in result.output

    def test_failed_execution(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()

        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "Fatal error"
        mock_process.stdin = MagicMock()
        mock_process.returncode = 1
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "implement feature", Path("/tmp/repo"))

        assert result.status == "failed"

    def test_event_callback_receives_output_lines(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()

        events: list = []
        mock_process = MagicMock()
        mock_process.stdout = iter(["line one\n", "line two\n"])
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""
        mock_process.stdin = MagicMock()
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            adapter.run(
                "task-1", "do work", Path("/tmp/repo"), on_event=events.append
            )

        assert len(events) == 2
        assert events[0].data["line"] == "line one"
        assert events[1].data["line"] == "line two"
