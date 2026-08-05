"""A tool that isn't installed is SKIPPED, not FAILED (#955).

``_run_pytest`` gated only on ``shutil.which("pytest") or shutil.which("uv")``.
``uv`` being present proves nothing about the *target project* having pytest, so
``uv run pytest`` exits non-zero with "Failed to spawn" and the gate reported
FAILED — i.e. "CodeFRAME says my project is broken" when the honest answer is
"unverifiable". ``run_lint_on_file`` already made this distinction; the detection
is now shared.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.gates import GateStatus, _run_pytest, _tool_is_missing

pytestmark = pytest.mark.v2


class TestToolIsMissing:
    """One case per stderr shape `uv` and the shell actually produce."""

    @pytest.mark.parametrize(
        "stderr",
        [
            "error: Failed to spawn: `pytest`\n  Caused by: No such file or directory",
            "/bin/sh: 1: pytest: command not found",
            "No such file or directory: 'pytest'",
        ],
    )
    def test_missing_tool_shapes_are_detected(self, stderr):
        assert _tool_is_missing(2, stderr, {"pytest"}) is True

    def test_missing_target_file_is_not_a_missing_tool(self):
        """"No such file" without the tool's name is a missing *argument*, not a tool.

        Without this, any linter complaining about a path it was handed would be
        silently downgraded to SKIPPED and its findings dropped.
        """
        assert (
            _tool_is_missing(2, "No such file or directory: 'src/gone.py'", {"ruff"})
            is False
        )

    def test_success_is_never_a_missing_tool(self):
        assert _tool_is_missing(0, "Failed to spawn: `pytest`", {"pytest"}) is False

    def test_no_stderr_is_never_a_missing_tool(self):
        assert _tool_is_missing(1, None, {"pytest"}) is False
        assert _tool_is_missing(1, "", {"pytest"}) is False

    def test_detection_is_case_insensitive_on_the_tool_name(self):
        assert _tool_is_missing(2, "No such file or directory: 'PyTest'", {"pytest"})


class TestRunPytestSkipsWhenUnspawnable:
    @staticmethod
    def _result(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
        return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_project_without_pytest_skips(self, tmp_path):
        """The acceptance criterion: a project with no pytest is SKIPPED."""
        with patch("codeframe.core.gates.shutil.which", return_value="/usr/bin/uv"), patch(
            "codeframe.core.gates.subprocess.run",
            return_value=self._result(2, stderr="error: Failed to spawn: `pytest`"),
        ):
            check = _run_pytest(Path(tmp_path))

        assert check.status == GateStatus.SKIPPED
        assert "not found" in check.output

    def test_real_test_failures_still_fail(self, tmp_path):
        """The distinction has to cut both ways, or the gate stops gating."""
        with patch("codeframe.core.gates.shutil.which", return_value="/usr/bin/uv"), patch(
            "codeframe.core.gates.subprocess.run",
            return_value=self._result(1, stdout="1 failed, 2 passed"),
        ):
            check = _run_pytest(Path(tmp_path))

        assert check.status == GateStatus.FAILED

    def test_passing_suite_still_passes(self, tmp_path):
        with patch("codeframe.core.gates.shutil.which", return_value="/usr/bin/uv"), patch(
            "codeframe.core.gates.subprocess.run",
            return_value=self._result(0, stdout="3 passed"),
        ):
            check = _run_pytest(Path(tmp_path))

        assert check.status == GateStatus.PASSED
