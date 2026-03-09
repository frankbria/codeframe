"""Claude Code adapter for delegating task execution to the claude CLI."""

from __future__ import annotations

from pathlib import Path

from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter


class ClaudeCodeAdapter(SubprocessAdapter):
    """Adapter that delegates code execution to Claude Code CLI.

    Invokes ``claude`` with ``--print`` flag for non-interactive output.
    The prompt is piped via stdin.

    Requires the Claude Code CLI to be installed:
    https://docs.anthropic.com/en/docs/claude-code
    """

    def __init__(self, allowlist: list[str] | None = None) -> None:
        """Initialize the Claude Code adapter.

        Args:
            allowlist: Optional list of allowed tools/permissions.
                       If provided, uses ``--allowedTools`` flag for each tool.
                       When omitted, no permission flags are added (the caller
                       is responsible for configuring permissions externally).
        """
        cli_args = ["--print"]
        if allowlist:
            for tool in allowlist:
                cli_args.extend(["--allowedTools", tool])

        super().__init__(binary="claude", cli_args=cli_args)
        self._allowlist = allowlist

    @property
    def name(self) -> str:  # noqa: D102
        return "claude-code"

    def build_command(self, prompt: str, workspace_path: Path) -> list[str]:
        """Build claude CLI command.

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
            prompt: The task prompt to pipe into the claude process.

        Returns:
            The prompt string.
        """
        return prompt
