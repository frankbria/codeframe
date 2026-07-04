"""Tests for SubprocessAdapter base class."""

import subprocess
import sys
import time

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

    @pytest.fixture(autouse=True)
    def _no_git(self):
        """Prevent _detect_modified_files from calling real git."""
        with patch.object(SubprocessAdapter, "_detect_modified_files", return_value=[]):
            yield

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

    def test_real_child_stalling_with_stdout_open_is_killed_at_timeout(self, tmp_path):
        """A real child that keeps stdout open past the timeout must be killed (#736).

        Regression: previously stdout was read inline, so a child that wrote a
        line then blocked with stdout open hung the run forever — the
        process.wait(timeout=...) was never reached.
        """
        # Print one line, then block far longer than the timeout with stdout open.
        script = "import sys, time; print('working', flush=True); time.sleep(60)"

        class _PyAdapter(SubprocessAdapter):
            def build_command(self, prompt, workspace_path):
                return [sys.executable, "-c", script]

            def get_stdin(self, prompt):
                return None

        with patch("shutil.which", return_value=sys.executable):
            adapter = _PyAdapter("python", timeout_s=1)

        with patch.object(SubprocessAdapter, "_detect_modified_files", return_value=[]):
            start = time.monotonic()
            result = adapter.run("task-1", "go", tmp_path)
            elapsed = time.monotonic() - start

        assert result.status == "failed"
        assert "timed out" in result.error
        assert "working" in result.output  # streamed output before the stall
        assert elapsed < 30  # bounded by the timeout, not the 60s sleep

    def test_large_stdin_with_early_child_output_does_not_deadlock(self, tmp_path):
        """A >64KB prompt must not deadlock against a child that writes before

        reading stdin (#737).

        Regression: stdin was written+closed inline BEFORE the drain threads
        started. If the child emitted output larger than the pipe buffer before
        consuming stdin, both sides blocked forever on full pipes — and the write
        blocked before process.wait(timeout=...) was ever reached, so the #736
        timeout could not fire either.
        """
        # Child fills its stdout pipe (>64KB) BEFORE reading any stdin, then
        # echoes how many bytes of stdin it received.
        script = (
            "import sys\n"
            "sys.stdout.write('x' * (128 * 1024) + '\\n'); sys.stdout.flush()\n"
            "data = sys.stdin.read()\n"
            "print('RECEIVED', len(data))\n"
        )
        big_prompt = "y" * (128 * 1024)

        class _PyAdapter(SubprocessAdapter):
            def build_command(self, prompt, workspace_path):
                return [sys.executable, "-c", script]

        with patch("shutil.which", return_value=sys.executable):
            # Bound the run so a regression fails (times out) instead of hanging CI.
            adapter = _PyAdapter("python", timeout_s=30)

        with patch.object(SubprocessAdapter, "_detect_modified_files", return_value=[]):
            start = time.monotonic()
            result = adapter.run("task-1", big_prompt, tmp_path)
            elapsed = time.monotonic() - start

        assert result.status == "completed"
        assert f"RECEIVED {len(big_prompt)}" in result.output
        assert elapsed < 30  # completed promptly, not bounded by the timeout

    def test_child_exiting_before_reading_stdin_is_handled(self, tmp_path):
        """A child that exits before draining a large stdin must not crash run().

        Writing a >64KB payload to a pipe whose read end the child already closed
        raises BrokenPipeError in the stdin thread; run() must swallow it and
        still return a result based on the exit code. (#737)
        """
        # Exit immediately without reading stdin, so the write end breaks.
        script = "import sys; sys.exit(0)"
        big_prompt = "z" * (128 * 1024)

        class _PyAdapter(SubprocessAdapter):
            def build_command(self, prompt, workspace_path):
                return [sys.executable, "-c", script]

        with patch("shutil.which", return_value=sys.executable):
            adapter = _PyAdapter("python", timeout_s=30)

        with patch.object(SubprocessAdapter, "_detect_modified_files", return_value=[]):
            result = adapter.run("task-1", big_prompt, tmp_path)

        assert result.status == "completed"  # exit 0, BrokenPipeError swallowed


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


class TestSubprocessAdapterModifiedFiles:
    """Tests for git diff file detection after execution."""

    @pytest.fixture
    def adapter(self):
        with patch("shutil.which", return_value="/usr/bin/test-agent"):
            return SubprocessAdapter("test-agent")

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

    def test_populates_modified_files_on_success(self, adapter, tmp_path):
        """After successful execution, modified_files should list changed files."""
        mock_process = self._make_mock_process(
            stdout_lines=["done\n"], returncode=0
        )
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(returncode=0, stdout="src/main.py\ntests/test_main.py\n"),
                    MagicMock(returncode=0, stdout=""),  # no untracked files
                ],
            ),
        ):
            result = adapter.run("task-1", "fix", tmp_path)

        assert result.status == "completed"
        assert result.modified_files == ["src/main.py", "tests/test_main.py"]

    def test_empty_modified_files_when_no_changes(self, adapter, tmp_path):
        mock_process = self._make_mock_process(
            stdout_lines=["done\n"], returncode=0
        )
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(returncode=0, stdout=""),
                    MagicMock(returncode=0, stdout=""),
                ],
            ),
        ):
            result = adapter.run("task-1", "fix", tmp_path)

        assert result.modified_files == []

    def test_detects_files_even_on_failure(self, adapter, tmp_path):
        """Failed execution should still detect modified files."""
        mock_process = self._make_mock_process(
            stderr_text="error", returncode=1
        )
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(returncode=0, stdout="src/broken.py\n"),
                    MagicMock(returncode=0, stdout=""),
                ],
            ),
        ):
            result = adapter.run("task-1", "fix", tmp_path)

        assert result.status == "failed"
        assert "src/broken.py" in result.modified_files

    def test_graceful_when_not_git_repo(self, adapter, tmp_path):
        """Should return empty modified_files if git is unavailable."""
        mock_process = self._make_mock_process(
            stdout_lines=["done\n"], returncode=0
        )
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch(
                "subprocess.run",
                side_effect=FileNotFoundError("git not found"),
            ),
        ):
            result = adapter.run("task-1", "fix", tmp_path)

        assert result.status == "completed"
        assert result.modified_files == []

    def test_graceful_when_git_fails(self, adapter, tmp_path):
        """Should return empty modified_files if git diff fails."""
        mock_process = self._make_mock_process(
            stdout_lines=["done\n"], returncode=0
        )
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=128, stdout=""),
            ),
        ):
            result = adapter.run("task-1", "fix", tmp_path)

        assert result.status == "completed"
        assert result.modified_files == []


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
