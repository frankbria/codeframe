"""Tests for OpenCode adapter."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.adapters.agent_adapter import AgentAdapter
from codeframe.core.adapters.opencode import OpenCodeAdapter


class TestOpenCodeAdapter:
    """Unit tests for OpenCodeAdapter."""

    @pytest.fixture(autouse=True)
    def _no_git(self):
        """Prevent _detect_modified_files from calling real git.

        Returns a modified file, i.e. a run that actually did work. With
        ``require_file_changes=True`` (#913) an empty list means "wrote
        nothing", which is now a *failure* — so an empty default would make
        every test here exercise the false-completion guard rather than the
        behaviour it names. The no-work case has its own test below.
        """
        with patch.object(
            OpenCodeAdapter, "_detect_modified_files", return_value=["main.py"]
        ), patch.object(OpenCodeAdapter, "_git_head", return_value="abc123"):
            yield

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

    def test_build_command_uses_the_run_subcommand(self) -> None:
        """`--non-interactive` does not exist; it silently starts the TUI (#913)."""
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()
            cmd = adapter.build_command("prompt", Path("/tmp"))

        assert cmd == ["/usr/bin/opencode", "run", "prompt"]
        assert "--non-interactive" not in cmd

    def test_the_prompt_is_an_argument_not_stdin(self) -> None:
        """`opencode run` declares `message` as a positional; it reads no stdin.

        Returning the prompt here as well would send the instruction twice.
        """
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()

        assert adapter.get_stdin("my prompt") is None
        assert adapter.build_command("my prompt", Path("/tmp"))[-1] == "my prompt"

    def test_a_zero_work_run_is_not_reported_completed(self) -> None:
        """Exit 0 with nothing written is a false completion: gates would then
        run on an unchanged tree and the task could be marked DONE with no code
        (#739's class, which the claude-code adapter was already patched for)."""
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = OpenCodeAdapter()

        assert adapter._require_file_changes is True

    def test_auto_approve_is_off_by_default(self) -> None:
        """opencode documents --auto as "(dangerous!)" — it auto-approves
        anything not explicitly denied, for a prompt derived from repository
        content. Verified against 1.18.7 that plain `run` writes files, so the
        flag is not needed to make the engine work."""
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            default = OpenCodeAdapter()
            opted_in = OpenCodeAdapter(auto_approve=True)

        assert "--auto" not in default.build_command("p", Path("/tmp"))
        assert "--auto" in opted_in.build_command("p", Path("/tmp"))

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


class TestZeroWorkIsNotCompleted:
    """The false-completion guard, exercised through `run` (#913)."""

    @pytest.fixture(autouse=True)
    def _stable_head(self):
        """HEAD unchanged, so only the modified-file signal decides."""
        with patch.object(OpenCodeAdapter, "_git_head", return_value="abc123"):
            yield

    def _adapter(self) -> OpenCodeAdapter:
        with patch("shutil.which", return_value="/usr/bin/opencode"):
            return OpenCodeAdapter()

    def _exit_zero_process(self) -> MagicMock:
        proc = MagicMock()
        proc.stdout = iter(["I reviewed the code and everything looks fine.\n"])
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = ""
        proc.stdin = MagicMock()
        proc.returncode = 0
        proc.wait.return_value = None
        return proc

    def test_exit_zero_writing_nothing_is_not_completed(self) -> None:
        """The reported failure mode: the CLI exits 0 having done no work, gates
        then run on an unchanged tree, and the task can be marked DONE with no
        code written."""
        adapter = self._adapter()

        with patch.object(OpenCodeAdapter, "_detect_modified_files", return_value=[]):
            with patch("subprocess.Popen", return_value=self._exit_zero_process()):
                result = adapter.run("task-1", "implement feature", Path("/tmp/repo"))

        assert result.status != "completed", result.status

    def test_exit_zero_with_changes_is_completed(self) -> None:
        """The guard must not fail runs that genuinely did the work."""
        adapter = self._adapter()

        with patch.object(
            OpenCodeAdapter, "_detect_modified_files", return_value=["main.py"]
        ):
            with patch("subprocess.Popen", return_value=self._exit_zero_process()):
                result = adapter.run("task-1", "implement feature", Path("/tmp/repo"))

        assert result.status == "completed", result.status
