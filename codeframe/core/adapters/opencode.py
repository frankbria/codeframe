"""OpenCode adapter for delegating task execution to the opencode CLI."""

from __future__ import annotations

from pathlib import Path

from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter


class OpenCodeAdapter(SubprocessAdapter):
    """Adapter that delegates code execution to OpenCode CLI.

    Invokes ``opencode`` with ``--non-interactive`` flag for headless execution.
    The prompt is piped via stdin.

    Requires OpenCode to be installed:
    https://github.com/opencode-ai/opencode
    """

    def __init__(self) -> None:
        super().__init__(binary="opencode", cli_args=["--non-interactive"])

    @property
    def name(self) -> str:  # noqa: D102
        return "opencode"

    def build_command(self, prompt: str, workspace_path: Path) -> list[str]:
        """Build opencode CLI command.

        Args:
            prompt: The task prompt (sent via stdin, not in the command).
            workspace_path: Workspace root (cwd is set by the base class).

        Returns:
            Command list for subprocess.Popen.
        """
        return [self._binary_path, *self._cli_args]

    def get_stdin(self, prompt: str) -> str | None:
        """Send prompt via stdin.

        Args:
            prompt: The task prompt to pipe into the opencode process.

        Returns:
            The prompt string.
        """
        return prompt
