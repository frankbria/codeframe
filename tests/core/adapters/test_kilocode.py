"""Tests for Kilocode adapter."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.adapters.agent_adapter import AgentAdapter
from codeframe.core.adapters.kilocode import KilocodeAdapter

pytestmark = pytest.mark.v2

_WHICH = "codeframe.core.adapters.subprocess_adapter.shutil.which"
_WHICH_KILOCODE = "codeframe.core.adapters.kilocode.shutil.which"


class TestKilocodeAdapter:
    """Unit tests for KilocodeAdapter."""

    @pytest.fixture(autouse=True)
    def _no_git(self):
        """Prevent _detect_modified_files from calling real git."""
        with patch.object(KilocodeAdapter, "_detect_modified_files", return_value=[]):
            yield

    def test_name(self) -> None:
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()
            assert adapter.name == "kilocode"

    def test_conforms_to_protocol(self) -> None:
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()
            assert isinstance(adapter, AgentAdapter)

    def test_raises_if_kilo_not_installed(self) -> None:
        with patch(_WHICH, return_value=None):
            with pytest.raises(EnvironmentError, match="not found on PATH"):
                KilocodeAdapter()

    def test_build_command_includes_prompt_and_auto_flag(self) -> None:
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()
        cmd = adapter.build_command("do the thing", Path("/tmp/repo"))
        assert cmd[0] == "/usr/bin/kilo"
        assert cmd[1] == "run"
        assert "do the thing" in cmd
        assert "--auto" in cmd
        assert "--workspace" in cmd
        assert "/tmp/repo" in cmd

    def test_prompt_is_not_sent_via_stdin(self) -> None:
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()
        assert adapter.get_stdin("my prompt") is None

    def test_build_command_includes_model_when_env_set(self, monkeypatch) -> None:
        monkeypatch.setenv("KILOCODE_MODEL", "claude-3-5-sonnet")
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()
        cmd = adapter.build_command("prompt", Path("/tmp/repo"))
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-3-5-sonnet"

    def test_build_command_extra_flags_uses_shlex(self, monkeypatch) -> None:
        """KILOCODE_FLAGS must be split with shlex to handle quoted values."""
        monkeypatch.setenv("KILOCODE_FLAGS", '--verbose --log-level "debug mode"')
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()
        cmd = adapter.build_command("prompt", Path("/tmp/repo"))
        assert "--verbose" in cmd
        assert "--log-level" in cmd
        # shlex preserves quoted string as a single token
        assert "debug mode" in cmd

    def test_build_command_extra_flags_simple(self, monkeypatch) -> None:
        monkeypatch.setenv("KILOCODE_FLAGS", "--verbose --log-level debug")
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()
        cmd = adapter.build_command("prompt", Path("/tmp/repo"))
        assert "--verbose" in cmd
        assert "--log-level" in cmd
        assert "debug" in cmd

    def test_custom_binary_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("KILOCODE_PATH", "/opt/kilo/bin/kilo")
        with patch(_WHICH, return_value="/opt/kilo/bin/kilo"):
            adapter = KilocodeAdapter()
        assert adapter._binary_path == "/opt/kilo/bin/kilo"

    def test_resolve_binary_uses_env_var(self, monkeypatch) -> None:
        monkeypatch.setenv("KILOCODE_PATH", "/custom/kilo")
        assert KilocodeAdapter._resolve_binary() == "/custom/kilo"

    def test_resolve_binary_defaults_to_kilo(self, monkeypatch) -> None:
        monkeypatch.delenv("KILOCODE_PATH", raising=False)
        assert KilocodeAdapter._resolve_binary() == "kilo"

    def test_check_ready_when_binary_present(self) -> None:
        with patch(_WHICH_KILOCODE, return_value="/usr/bin/kilo"):
            result = KilocodeAdapter.check_ready()
        assert result["kilo_binary"] is True

    def test_check_ready_when_binary_missing(self) -> None:
        with patch(_WHICH_KILOCODE, return_value=None):
            result = KilocodeAdapter.check_ready()
        assert result["kilo_binary"] is False

    def test_requirements_returns_kilocode_path_key(self) -> None:
        reqs = KilocodeAdapter.requirements()
        assert "KILOCODE_PATH" in reqs

    def test_successful_execution(self) -> None:
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()

        mock_process = MagicMock()
        mock_process.stdout = iter(["Wrote src/foo.py\n"])
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""
        mock_process.stdin = None
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "implement foo", Path("/tmp/repo"))

        assert result.status == "completed"
        assert "Wrote src/foo.py" in result.output

    def test_failed_execution_nonzero_exit(self) -> None:
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()

        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "kilo: fatal error"
        mock_process.stdin = None
        mock_process.returncode = 1
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "implement foo", Path("/tmp/repo"))

        assert result.status == "failed"

    def test_timeout_exit_code_124_maps_to_failed(self) -> None:
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()

        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""
        mock_process.stdin = None
        mock_process.returncode = 124
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "implement foo", Path("/tmp/repo"))

        assert result.status == "failed"
        assert "timed out" in (result.error or "").lower()

    def test_event_callback_receives_output_lines(self) -> None:
        with patch(_WHICH, return_value="/usr/bin/kilo"):
            adapter = KilocodeAdapter()

        events: list = []
        mock_process = MagicMock()
        mock_process.stdout = iter(["step 1\n", "step 2\n"])
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""
        mock_process.stdin = None
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            adapter.run("task-1", "do work", Path("/tmp/repo"), on_event=events.append)

        assert len(events) == 2
        assert events[0].data["line"] == "step 1"
        assert events[1].data["line"] == "step 2"
