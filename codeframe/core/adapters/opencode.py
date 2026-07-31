"""OpenCode adapter for delegating task execution to the opencode CLI."""

from __future__ import annotations

from pathlib import Path

from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter


class OpenCodeAdapter(SubprocessAdapter):
    """Adapter that delegates code execution to OpenCode CLI.

    Runs ``opencode run <message>`` — the CLI's headless entry point. The
    previous invocation was ``opencode --non-interactive`` with the prompt on
    stdin, and **no such flag exists**: verified against opencode 1.18.7,
    ``--non-interactive`` is absent from the option list and passing it simply
    starts the TUI, so the delegated run did no work at all (#913).

    Requires OpenCode to be installed: https://github.com/sst/opencode
    """

    def __init__(self, auto_approve: bool = False) -> None:
        """Initialize the OpenCode adapter.

        Args:
            auto_approve: Pass ``--auto``, which opencode documents as
                "auto-approve permissions that are not explicitly denied
                (dangerous!)". **Off by default.** Verified against opencode
                1.18.7 that a plain ``opencode run <message>`` writes files
                headlessly under the default permission config, so the flag is
                not needed to make the engine work — and turning it on would
                auto-approve arbitrary actions for a prompt derived from
                repository content, the exposure #905–#907 exist to close.

                Where an operator's opencode config *does* deny writes, the run
                produces no file changes and ``require_file_changes`` below turns
                that into a loud failure rather than a silent false completion.
        """
        cli_args = ["run"]
        if auto_approve:
            cli_args.append("--auto")

        super().__init__(
            binary="opencode",
            cli_args=cli_args,
            # A coding agent that exits 0 having written nothing is a false
            # completion: gates then run on an unchanged tree and the task can be
            # marked DONE with no code. Same guard the claude-code adapter got
            # in #739/#819.
            require_file_changes=True,
        )
        self._auto_approve = auto_approve

    @property
    def name(self) -> str:  # noqa: D102
        return "opencode"

    def build_command(self, prompt: str, workspace_path: Path) -> list[str]:
        """Build the opencode CLI command.

        Args:
            prompt: The task prompt — a positional argument to ``run``, not
                stdin. ``opencode run`` declares ``message`` as a positional
                array; it does not read the prompt from stdin.
            workspace_path: Workspace root (cwd is set by the base class).

        Returns:
            Command list for subprocess.Popen.
        """
        return [self._binary_path, *self._cli_args, prompt]

    def get_stdin(self, prompt: str) -> str | None:
        """No stdin: the prompt travels as an argument to ``run``.

        Returns:
            None — sending it twice would duplicate the instruction.
        """
        return None
