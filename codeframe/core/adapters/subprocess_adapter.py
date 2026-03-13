"""Base subprocess adapter for external coding agents."""

from __future__ import annotations

import shutil
import subprocess
import threading
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

    # Default timeout: 30 minutes (coding agents can be long-running)
    DEFAULT_TIMEOUT_S = 1800

    def __init__(
        self,
        binary: str,
        cli_args: list[str] | None = None,
        timeout_s: int | None = None,
    ) -> None:
        """Initialize with the binary name and default CLI args.

        Args:
            binary: Name of the CLI binary (e.g., 'claude', 'opencode')
            cli_args: Default CLI arguments appended to every invocation
            timeout_s: Max execution time in seconds (default: 1800, None = no limit)

        Raises:
            EnvironmentError: If the binary is not found on PATH
        """
        self._binary = binary
        self._cli_args = cli_args or []
        self._timeout_s = timeout_s if timeout_s is not None else self.DEFAULT_TIMEOUT_S

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
        stderr_chunks: list[str] = []

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

            # Drain stderr in a background thread to prevent deadlock.
            # Without this, if the child fills the stderr pipe buffer (~64KB)
            # before finishing stdout, both processes block indefinitely.
            def _drain_stderr() -> None:
                if process.stderr:
                    stderr_chunks.append(process.stderr.read())

            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            # Stream stdout line-by-line
            if process.stdout:
                for line in process.stdout:
                    stripped = line.rstrip("\n")
                    stdout_lines.append(stripped)
                    if on_event:
                        on_event(AgentEvent(type="output", data={"line": stripped}))

            # Wait for stderr thread and process to finish
            stderr_thread.join(timeout=10)
            try:
                process.wait(timeout=self._timeout_s)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return AgentResult(
                    status="failed",
                    output="\n".join(stdout_lines),
                    error=f"Process timed out after {self._timeout_s}s",
                )

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

        stderr_output = "".join(stderr_chunks)

        modified_files = self._detect_modified_files(workspace_path)

        result = self._map_result(
            exit_code=process.returncode,
            stdout="\n".join(stdout_lines),
            stderr=stderr_output,
            workspace_path=workspace_path,
        )
        result.modified_files = modified_files
        return result

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

    def _detect_modified_files(self, workspace_path: Path) -> list[str]:
        """Detect files modified by the subprocess via git diff.

        Combines modified, staged, and untracked files. Returns an empty list
        if git is unavailable or the workspace is not a git repo.
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                # Also covers repos with no commits (HEAD does not exist)
                return []

            files = [f for f in result.stdout.strip().splitlines() if f]

            # Also pick up untracked files
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if untracked.returncode == 0:
                files.extend(
                    f for f in untracked.stdout.strip().splitlines() if f
                )

            # Deduplicate while preserving order
            return list(dict.fromkeys(files))
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return []

    def _extract_blocker_question(self, output: str) -> str:
        """Extract a meaningful blocker question from output."""
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if lines:
            return lines[-1]
        return "Agent encountered a blocker but no details were provided."
