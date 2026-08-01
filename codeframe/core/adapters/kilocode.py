"""Kilocode adapter for delegating task execution to the kilo CLI."""

from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path

from codeframe.core.adapters.agent_adapter import AgentResult
from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter

# Exit code used by kilo when the timeout is exceeded
_KILO_TIMEOUT_EXIT_CODE = 124


class KilocodeAdapter(SubprocessAdapter):
    """Adapter that delegates code execution to Kilocode CLI.

    Invokes ``kilo <prompt> --auto --workspace <path>`` for headless
    non-interactive execution.  The prompt is the CLI's leading positional
    (not stdin, and **not** behind a subcommand).

    There is no ``run`` subcommand: verified against kilocode 0.22.0, whose
    usage is ``kilocode [options] [command] [prompt]`` with commands
    ``auth``/``config``/``debug``/``models`` only. The adapter used to prepend
    ``run``, which was then swallowed as the prompt — ``--auto`` never took
    effect, the interactive TUI opened, and the delegated run hung until the
    timeout having written nothing (#1012).

    Note on prompt length: the prompt is passed as a single positional argument.
    Linux supports up to ~2 MB per argument, but macOS caps individual arguments
    at 256 KB. Very large task contexts assembled by TaskContextPackager may fail
    on macOS. If Kilocode adds stdin support in a future release, prefer that path.

    Exit codes:
        0   — success
        124 — timeout exceeded (mirrors the standard ``timeout(1)`` convention)
        *   — execution error

    Configuration via environment variables:
        KILOCODE_PATH   — path to kilo binary (default: "kilo", resolved from $PATH)
        KILOCODE_MODEL  — optional model override passed as ``--model``
        KILOCODE_FLAGS  — optional extra CLI flags (shell-quoted, e.g. ``--flag "val"``)

    Requires Kilocode to be installed:
    https://kilocode.ai/
    """

    def __init__(
        self,
        *,
        timeout_s: int | None = None,
    ) -> None:
        super().__init__(
            binary=self._resolve_binary(),
            timeout_s=timeout_s,
            # A coding agent that exits 0 having written nothing is a false
            # completion: gates then run on an unchanged tree and the task can
            # be marked DONE with no code. The TUI path this adapter used to
            # take did exactly that. Same guard as claude-code (#739/#819) and
            # opencode (#913).
            require_file_changes=True,
        )

    @property
    def name(self) -> str:  # noqa: D102
        return "kilocode"

    @staticmethod
    def _resolve_binary() -> str:
        """Return the kilo binary path from env or default."""
        return os.environ.get("KILOCODE_PATH") or "kilo"

    @classmethod
    def requirements(cls) -> dict[str, str]:
        """Return environment variables recognised by ``cf engines check``."""
        return {
            "KILOCODE_PATH": "Path to kilo binary (optional — defaults to 'kilo' on $PATH)",
        }

    @classmethod
    def home_passthrough(cls) -> tuple[str, ...]:
        """`kilo` keeps its login here; a bare sandbox home logs it out (#996)."""
        return (".kilocode",)

    @classmethod
    def check_ready(cls) -> dict[str, bool]:
        """Check if the kilo binary is available on PATH."""
        return {"kilo_binary": shutil.which(cls._resolve_binary()) is not None}

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
            cmd.extend(shlex.split(extra_flags_str))

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
