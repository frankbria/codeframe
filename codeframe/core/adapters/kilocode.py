"""Kilocode adapter for delegating task execution to the kilo CLI."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from codeframe.core.adapters.agent_adapter import AgentResult
from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter

# Exit code used by kilo when the timeout is exceeded
_KILO_TIMEOUT_EXIT_CODE = 124


class KilocodeAdapter(SubprocessAdapter):
    """Adapter that delegates code execution to Kilocode CLI.

    Invokes ``kilo run <prompt> --auto --workspace <path>`` for headless
    non-interactive execution.  The prompt is passed as a positional argument
    (not via stdin), matching Kilocode's CLI interface.

    Exit codes:
        0   — success
        124 — timeout exceeded (mirrors the standard ``timeout(1)`` convention)
        *   — execution error

    Configuration via environment variables:
        KILOCODE_PATH   — path to kilo binary (default: "kilo", resolved from $PATH)
        KILOCODE_MODEL  — optional model override passed as ``--model``
        KILOCODE_FLAGS  — optional extra CLI flags (space-separated string)

    Requires Kilocode to be installed:
    https://kilocode.ai/
    """

    def __init__(
        self,
        *,
        timeout_s: int | None = None,
    ) -> None:
        binary = os.environ.get("KILOCODE_PATH") or "kilo"
        super().__init__(binary=binary, timeout_s=timeout_s)

    @property
    def name(self) -> str:  # noqa: D102
        return "kilocode"

    @classmethod
    def check_ready(cls) -> dict[str, bool]:
        """Check if the kilo binary is available on PATH."""
        binary = os.environ.get("KILOCODE_PATH") or "kilo"
        return {"kilo_binary": shutil.which(binary) is not None}

    def build_command(self, prompt: str, workspace_path: Path) -> list[str]:
        """Build the kilo CLI command.

        Kilocode takes the prompt as a positional argument, with ``--auto``
        for non-interactive execution and ``--workspace`` for the repo root.

        Args:
            prompt: The task prompt passed as a positional argument.
            workspace_path: Workspace root passed as ``--workspace``.

        Returns:
            Command list for subprocess.Popen.
        """
        cmd = [
            self._binary_path,
            "run",
            prompt,
            "--auto",
            "--workspace",
            str(workspace_path),
        ]

        model = os.environ.get("KILOCODE_MODEL")
        if model:
            cmd.extend(["--model", model])

        extra_flags_str = os.environ.get("KILOCODE_FLAGS", "").strip()
        if extra_flags_str:
            cmd.extend(extra_flags_str.split())

        return cmd

    def get_stdin(self, prompt: str) -> str | None:
        """Return None — prompt is passed as a positional CLI argument, not stdin."""
        return None

    def _map_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        workspace_path: Path,
    ) -> AgentResult:
        """Map kilo exit codes to AgentResult.

        Exit code 124 indicates a timeout (kilo's standard timeout sentinel),
        which is surfaced as a failed result with a descriptive message.
        All other non-zero codes use the base class logic for blocker detection.
        """
        if exit_code == _KILO_TIMEOUT_EXIT_CODE:
            return AgentResult(
                status="failed",
                output=stdout,
                error="Kilocode execution timed out (exit code 124)",
            )
        return super()._map_result(exit_code, stdout, stderr, workspace_path)
