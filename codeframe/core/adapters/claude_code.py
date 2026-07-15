"""Claude Code adapter for delegating task execution to the claude CLI."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter

_GUARD_MODULE = "codeframe.core.claude_code_guard"

# Tools known to be incapable of changing the workspace. Everything *not* listed
# here — Edit/Write/Bash, an MCP write tool, Task (whose subagent can write), a
# tool that does not exist yet — is assumed write-capable.
#
# The polarity matters. Reading a write tool as read-only would silently switch
# off the zero-file guard and re-open the #739 false completion; reading a
# read-only tool as a write tool merely fails an analysis run loudly. So the
# unknown case must land on "write". Keeping an allowlist of the safe names, not
# a blocklist of the dangerous ones, is what makes that the default. (#819 review)
_READ_ONLY_TOOLS = frozenset(
    {"read", "grep", "glob", "ls", "notebookread", "webfetch", "websearch"}
)


def _grants_write_access(allowlist: list[str]) -> bool:
    """True unless every allowlist entry is a known read-only tool.

    Entries may be bare tool names ("Edit") or rule-shaped ("Bash(git *)"), so
    match on the tool name preceding any rule parentheses.
    """
    return not all(
        entry.split("(", 1)[0].strip().lower() in _READ_ONLY_TOOLS
        for entry in allowlist
    )


def _guard_settings() -> str:
    """Build the --settings payload registering the dangerous-command guard.

    The hook runs under the interpreter already running CodeFrame, so the guard
    module is importable regardless of what is on the delegated CLI's PATH.
    """
    hook_command = f"{shlex.quote(sys.executable)} -m {_GUARD_MODULE}"
    return json.dumps(
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": hook_command}],
                    }
                ]
            }
        }
    )


class ClaudeCodeAdapter(SubprocessAdapter):
    """Adapter that delegates code execution to Claude Code CLI.

    Invokes ``claude`` with ``--print`` flag for non-interactive output.
    The prompt is piped via stdin.

    Requires the Claude Code CLI to be installed:
    https://docs.anthropic.com/en/docs/claude-code
    """

    def __init__(
        self,
        allowlist: list[str] | None = None,
        require_file_changes: bool | None = None,
    ) -> None:
        """Initialize the Claude Code adapter.

        Args:
            allowlist: Optional list of allowed tools/permissions.
                       If provided, uses ``--allowedTools`` flag for each tool.
                       When omitted, the adapter runs with
                       ``--permission-mode bypassPermissions`` so Edit/Write/Bash
                       are auto-approved in non-interactive ``--print`` mode.
                       Without this, ``--print`` silently denies those tools and
                       the delegated agent can analyze but never modify files. (#739)
                       Either way a PreToolUse hook vets Bash commands against
                       CodeFrame's dangerous-command patterns — the permission
                       mode skips approval prompts, not hooks. (#819)
            require_file_changes: If True, a run that exits 0 but touches no files
                       is downgraded to ``failed`` — a coding task that writes
                       nothing is a false completion. Defaults to whether the
                       adapter actually grants write access: on for the
                       bypassPermissions default, and for an allowlist carrying a
                       write tool; off for a read-only allowlist, whose whole
                       point is a run that writes nothing. (#819)
        """
        cli_args = ["--print"]
        if allowlist:
            for tool in allowlist:
                cli_args.extend(["--allowedTools", tool])
        else:
            cli_args.extend(["--permission-mode", "bypassPermissions"])

        # Attached on both paths: an allowlist granting Bash has the same blast
        # radius as bypass mode, and a read-only one loses nothing by carrying it.
        cli_args.extend(["--settings", _guard_settings()])

        if require_file_changes is None:
            require_file_changes = (
                _grants_write_access(allowlist) if allowlist else True
            )

        super().__init__(
            binary="claude",
            cli_args=cli_args,
            require_file_changes=require_file_changes,
        )
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
