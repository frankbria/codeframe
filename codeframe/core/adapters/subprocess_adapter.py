"""Base subprocess adapter for external coding agents."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from codeframe.core.adapters.agent_adapter import AgentEvent, AgentResult
from codeframe.core.blocker_detection import classify_error_for_blocker


class SubprocessAdapter:
    """Base adapter for coding agents invoked as subprocesses.

    Provides shared infrastructure: binary availability check, subprocess
    execution with stdout streaming, and exit code to AgentResult mapping.

    Subclasses override build_command() to customize CLI invocation.
    """

    def __init__(self, binary: str, cli_args: list[str] | None = None) -> None:
        """Initialize with the binary name and default CLI args.

        Args:
            binary: Name of the CLI binary (e.g., 'claude', 'opencode')
            cli_args: Default CLI arguments appended to every invocation

        Raises:
            EnvironmentError: If the binary is not found on PATH
        """
        self._binary = binary
        self._cli_args = cli_args or []

        resolved = shutil.which(binary)
        if resolved is None:
            raise EnvironmentError(
                f"'{binary}' not found on PATH. "
                f"Install it or ensure it is available in your environment."
            )
        self._binary_path = resolved

    @property
    def name(self) -> str:
        """Engine name derived from the binary."""
        return self._binary

    def build_command(self, prompt: str, workspace_path: Path) -> list[str]:
        """Build the subprocess command list.

        Override in subclasses for custom CLI invocation.
        Default: [binary, *cli_args] with prompt on stdin.

        Args:
            prompt: The task prompt to send to the agent
            workspace_path: Path to the workspace root

        Returns:
            Command list for subprocess.Popen
        """
        return [self._binary_path, *self._cli_args]

    def get_stdin(self, prompt: str) -> str | None:
        """Return stdin content for the subprocess, or None to not pipe stdin.

        Override in subclasses if the agent reads prompt from a file instead.
        Default: returns the prompt string (piped via stdin).
        """
        return prompt

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Execute the agent subprocess and return the result."""
        cmd = self.build_command(prompt, workspace_path)
        stdin_content = self.get_stdin(prompt)

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if stdin_content else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(workspace_path),
                text=True,
            )

            # Write stdin and close
            if stdin_content and process.stdin:
                process.stdin.write(stdin_content)
                process.stdin.close()

            # Stream stdout line-by-line
            if process.stdout:
                for line in process.stdout:
                    stripped = line.rstrip("\n")
                    stdout_lines.append(stripped)
                    if on_event:
                        on_event(AgentEvent(type="output", data={"line": stripped}))

            # Collect stderr
            if process.stderr:
                stderr_lines = process.stderr.read().splitlines()

            process.wait()

        except FileNotFoundError:
            return AgentResult(
                status="failed",
                error=f"Binary '{self._binary}' not found during execution",
            )
        except OSError as e:
            return AgentResult(
                status="failed",
                error=f"Failed to start '{self._binary}': {e}",
            )

        return self._map_result(
            exit_code=process.returncode,
            stdout="\n".join(stdout_lines),
            stderr="\n".join(stderr_lines),
            workspace_path=workspace_path,
        )

    def _map_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        workspace_path: Path,
    ) -> AgentResult:
        """Map subprocess exit code and output to AgentResult.

        Override in subclasses for custom exit code interpretation.
        Default: 0 = completed, non-zero = failed.
        Uses blocker_detection.classify_error_for_blocker for blocker detection.
        """
        if exit_code == 0:
            return AgentResult(
                status="completed",
                output=stdout,
            )

        # Check if the error looks like a blocker using the shared classifier
        combined_output = f"{stdout}\n{stderr}".strip()
        category = classify_error_for_blocker(combined_output)
        if category is not None:
            return AgentResult(
                status="blocked",
                output=stdout,
                error=stderr or None,
                blocker_question=self._extract_blocker_question(combined_output),
            )

        return AgentResult(
            status="failed",
            output=stdout,
            error=stderr or f"Process exited with code {exit_code}",
        )

    def _extract_blocker_question(self, output: str) -> str:
        """Extract a meaningful blocker question from output."""
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if lines:
            return lines[-1]
        return "Agent encountered a blocker but no details were provided."
