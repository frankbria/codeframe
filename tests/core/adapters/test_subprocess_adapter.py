"""Tests for SubprocessAdapter base class."""

import subprocess

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter
from codeframe.core.adapters.agent_adapter import AgentAdapter, AgentEvent


class TestSubprocessAdapterInit:
    """Tests for adapter initialization and binary detection."""

    def test_init_with_available_binary(self):
        with patch("shutil.which", return_value="/usr/bin/test-agent"):
            adapter = SubprocessAdapter("test-agent")
            assert adapter.name == "test-agent"

    def test_init_raises_on_missing_binary(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(EnvironmentError, match="not found on PATH"):
                SubprocessAdapter("nonexistent-agent")

    def test_init_stores_cli_args(self):
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent", cli_args=["--auto", "--quiet"])
            assert adapter._cli_args == ["--auto", "--quiet"]

    def test_init_defaults_cli_args_to_empty(self):
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent")
            assert adapter._cli_args == []

    def test_init_stores_resolved_path(self):
        with patch("shutil.which", return_value="/opt/bin/my-agent"):
            adapter = SubprocessAdapter("my-agent")
            assert adapter._binary_path == "/opt/bin/my-agent"


class TestSubprocessAdapterRun:
    """Tests for subprocess execution."""

    @pytest.fixture
    def adapter(self):
        with patch("shutil.which", return_value="/usr/bin/test-agent"):
            return SubprocessAdapter("test-agent", cli_args=["--print"])

    def _make_mock_process(
        self, stdout_lines=None, stderr_text="", returncode=0
    ):
        mock = MagicMock()
        mock.stdout = iter(stdout_lines or [])
        mock.stderr = MagicMock()
        mock.stderr.read.return_value = stderr_text
        mock.stdin = MagicMock()
        mock.returncode = returncode
        mock.wait.return_value = None
        return mock

    def test_successful_execution(self, adapter):
        mock_process = self._make_mock_process(
            stdout_lines=["line 1\n", "line 2\n"], returncode=0
        )
        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "fix the bug", Path("/tmp/repo"))

        assert result.status == "completed"
        assert "line 1" in result.output
        assert "line 2" in result.output

    def test_failed_execution(self, adapter):
        mock_process = self._make_mock_process(
            stderr_text="Error: tests failed", returncode=1
        )
        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "fix the bug", Path("/tmp/repo"))

        assert result.status == "failed"
        assert result.error == "Error: tests failed"

    def test_failed_with_empty_stderr_uses_exit_code(self, adapter):
        mock_process = self._make_mock_process(returncode=42)
        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "fix", Path("/tmp"))

        assert result.status == "failed"
        assert "42" in result.error

    def test_blocked_on_permission_denied(self, adapter):
        mock_process = self._make_mock_process(
            stdout_lines=["permission denied: cannot access repo\n"], returncode=1
        )
        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "fix the bug", Path("/tmp/repo"))

        assert result.status == "blocked"
        assert result.blocker_question is not None

    def test_blocked_on_credentials_required(self, adapter):
        mock_process = self._make_mock_process(
            stdout_lines=["credentials required to access the service\n"],
            returncode=1,
        )
        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "deploy", Path("/tmp/repo"))

        assert result.status == "blocked"

    def test_blocked_on_api_key_missing(self, adapter):
        mock_process = self._make_mock_process(
            stderr_text="Error: API key not configured", returncode=1
        )
        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "call api", Path("/tmp"))

        assert result.status == "blocked"

    def test_streams_events(self, adapter):
        events: list[AgentEvent] = []
        mock_process = self._make_mock_process(
            stdout_lines=["hello\n", "world\n"], returncode=0
        )
        with patch("subprocess.Popen", return_value=mock_process):
            adapter.run("task-1", "fix", Path("/tmp"), on_event=events.append)

        assert len(events) == 2
        assert events[0].type == "output"
        assert events[0].data["line"] == "hello"
        assert events[1].data["line"] == "world"

    def test_no_events_when_callback_is_none(self, adapter):
        mock_process = self._make_mock_process(
            stdout_lines=["hello\n"], returncode=0
        )
        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "fix", Path("/tmp"), on_event=None)

        assert result.status == "completed"

    def test_passes_cwd_to_popen(self, adapter):
        mock_process = self._make_mock_process(returncode=0)
        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            adapter.run("task-1", "fix", Path("/my/repo"))
            mock_popen.assert_called_once()
            assert mock_popen.call_args.kwargs["cwd"] == "/my/repo"

    def test_sends_prompt_via_stdin(self, adapter):
        mock_process = self._make_mock_process(returncode=0)
        with patch("subprocess.Popen", return_value=mock_process):
            adapter.run("task-1", "my prompt text", Path("/tmp"))
            mock_process.stdin.write.assert_called_once_with("my prompt text")
            mock_process.stdin.close.assert_called_once()

    def test_handles_oserror(self, adapter):
        with patch("subprocess.Popen", side_effect=OSError("spawn failed")):
            result = adapter.run("task-1", "fix", Path("/tmp"))
        assert result.status == "failed"
        assert "spawn failed" in result.error

    def test_handles_file_not_found_error(self, adapter):
        with patch("subprocess.Popen", side_effect=FileNotFoundError()):
            result = adapter.run("task-1", "fix", Path("/tmp"))
        assert result.status == "failed"
        assert "not found during execution" in result.error

    def test_conforms_to_agent_adapter_protocol(self, adapter):
        assert isinstance(adapter, AgentAdapter)

    def test_timeout_kills_process(self):
        """Process should be killed when timeout expires."""
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent", timeout_s=1)

        mock_process = MagicMock()
        mock_process.stdout = iter(["working...\n"])
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""
        mock_process.stdin = MagicMock()
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="agent", timeout=1),
            None,
        ]
        mock_process.returncode = -9

        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "fix", Path("/tmp"))

        assert result.status == "failed"
        assert "timed out" in result.error
        mock_process.kill.assert_called_once()


class TestSubprocessAdapterBuildCommand:
    """Tests for command building."""

    def test_default_build_command(self):
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent", cli_args=["--auto"])
            cmd = adapter.build_command("prompt", Path("/tmp"))
            assert cmd == ["/usr/bin/agent", "--auto"]

    def test_build_command_without_args(self):
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent")
            cmd = adapter.build_command("prompt", Path("/tmp"))
            assert cmd == ["/usr/bin/agent"]


class TestSubprocessAdapterGetStdin:
    """Tests for stdin content generation."""

    def test_default_returns_prompt(self):
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent")
            assert adapter.get_stdin("hello world") == "hello world"

    def test_default_returns_empty_prompt(self):
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent")
            assert adapter.get_stdin("") == ""


class TestSubprocessAdapterBlockerExtraction:
    """Tests for blocker question extraction."""

    def test_extracts_last_line(self):
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent")
            question = adapter._extract_blocker_question(
                "Starting...\nChecking...\nPermission denied for /secret/file"
            )
            assert question == "Permission denied for /secret/file"

    def test_handles_empty_output(self):
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent")
            question = adapter._extract_blocker_question("")
            assert "no details" in question.lower()

    def test_handles_blank_lines_only(self):
        with patch("shutil.which", return_value="/usr/bin/agent"):
            adapter = SubprocessAdapter("agent")
            question = adapter._extract_blocker_question("\n\n  \n")
            assert "no details" in question.lower()
