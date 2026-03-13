"""Tests for Claude Code adapter."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.adapters.agent_adapter import AgentAdapter
from codeframe.core.adapters.claude_code import ClaudeCodeAdapter


class TestClaudeCodeAdapter:
    """Unit tests for ClaudeCodeAdapter."""

    @pytest.fixture(autouse=True)
    def _no_git(self):
        """Prevent _detect_modified_files from calling real git."""
        with patch.object(ClaudeCodeAdapter, "_detect_modified_files", return_value=[]):
            yield

    def test_name(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter()
            assert adapter.name == "claude-code"

    def test_conforms_to_protocol(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter()
            assert isinstance(adapter, AgentAdapter)

    def test_raises_if_claude_not_installed(self) -> None:
        with patch("shutil.which", return_value=None):
            with pytest.raises(EnvironmentError, match="not found on PATH"):
                ClaudeCodeAdapter()

    def test_build_command_includes_print_flag(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter()
            cmd = adapter.build_command("prompt", Path("/tmp"))
            assert cmd[0] == "/usr/bin/claude"
            assert "--print" in cmd

    def test_build_command_without_allowlist(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter()
            cmd = adapter.build_command("prompt", Path("/tmp"))
            assert "--allowedTools" not in cmd

    def test_build_command_with_allowlist(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter(allowlist=["Edit", "Write"])
            cmd = adapter.build_command("prompt", Path("/tmp"))
            assert "--allowedTools" in cmd
            # Verify both tools are present after their respective flags
            idx_edit = cmd.index("Edit")
            idx_write = cmd.index("Write")
            assert cmd[idx_edit - 1] == "--allowedTools"
            assert cmd[idx_write - 1] == "--allowedTools"

    def test_sends_prompt_via_stdin(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter()
            assert adapter.get_stdin("my prompt") == "my prompt"

    def test_successful_execution(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter()

        mock_process = MagicMock()
        mock_process.stdout = iter(
            ["Created file src/main.py\n", "All tests pass\n"]
        )
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""
        mock_process.stdin = MagicMock()
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "fix the bug", Path("/tmp/repo"))

        assert result.status == "completed"
        assert "All tests pass" in result.output

    def test_failed_execution(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter()

        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "Traceback: syntax error in config"
        mock_process.stdin = MagicMock()
        mock_process.returncode = 1
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "fix the bug", Path("/tmp/repo"))

        assert result.status == "failed"

    def test_event_callback_receives_output_lines(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter()

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

    def test_allowlist_stored(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter(allowlist=["Read", "Bash"])
            assert adapter._allowlist == ["Read", "Bash"]

    def test_no_allowlist_defaults_to_none(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/claude"):
            adapter = ClaudeCodeAdapter()
            assert adapter._allowlist is None
