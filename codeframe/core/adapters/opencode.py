"""OpenCode adapter for delegating task execution to the opencode CLI."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter

#: opencode's `--auto` approves anything "not explicitly denied", so its native
#: permission config is a deny-list — the one mechanism that composes with the
#: flag rather than fighting it (https://opencode.ai/docs/permissions).
#:
#: These mirror the families in `core.dangerous_commands.DANGEROUS_PATTERNS`, but
#: they cannot be shared verbatim: ours are regexes, opencode's rules are globs.
#: The translation is lossy in the safe direction — a glob matches at least as
#: much as its regex counterpart's common shapes — and the regex list stays the
#: single source of truth for the engines that can use it (ReAct, claude-code's
#: hook, codex's approval guard).
_DENIED_BASH_GLOBS = (
    # Recursive delete of root or home
    "rm -rf /*", "rm -rf ~*", "rm -fr /*", "rm -fr ~*",
    "rm -r /*", "rm -r ~*", "rm -f /*", "rm -f ~*",
    "sudo rm *",
    "*--no-preserve-root*",
    # Filesystem destruction
    "mkfs*", "*mkfs *", "fdisk*", "*fdisk *",
    # dd against devices, either direction
    "dd if=/dev/*", "*of=/dev/*", "*dd if=/dev/*",
    # Fork bombs — the classic `:(){ :|:& };:` and its spaced variants
    ":()*", ": ()*", "*:|:&*", "*: | : &*",
    # chmod 777 on root
    "chmod 777 /*", "chmod -R 777 /*", "chmod -r 777 /*",
    # Redirects over devices and system directories
    "*> /dev/*", "*> /etc/*", "*> /bin/*", "*> /usr/*", "*> /lib/*", "*> /sbin/*",
    # Download piped to a shell
    "*curl *|*sh*", "*wget *|*sh*",
    # The operator's credential store
    "*.codeframe/credentials*",
)

#: Linux caps a *single* argv entry at MAX_ARG_STRLEN — 32 pages, 128 KiB —
#: independently of the much larger total ARG_MAX. CodeFrame's context packager
#: budgets 100K tokens (~400 KB of prompt), so a large task prompt passed as a
#: positional raises OSError(E2BIG) before opencode ever starts. Verified:
#: ``subprocess.run(["/bin/true", "x" * 200_000])`` → "Argument list too long".
_MAX_ARG_BYTES = 128 * 1024


class OpenCodeAdapter(SubprocessAdapter):
    """Adapter that delegates code execution to OpenCode CLI.

    Runs ``opencode run <message>`` — the CLI's headless entry point. The
    previous invocation was ``opencode --non-interactive`` with the prompt on
    stdin, and **no such flag exists**: verified against opencode 1.18.7,
    ``--non-interactive`` is absent from the option list and passing it simply
    starts the TUI, so the delegated run did no work at all (#913).

    Requires OpenCode to be installed: https://github.com/sst/opencode
    """

    def __init__(self, auto_approve: bool = False, timeout_s: int | None = None) -> None:
        """Initialize the OpenCode adapter.

        Args:
            timeout_s: Max execution time, forwarded to ``SubprocessAdapter``
                (same knob as ``KilocodeAdapter``). None keeps the 30-minute
                default; tests bound it far lower so an opencode hang fails in
                seconds rather than stalling the suite.
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
            timeout_s=timeout_s,
            # A coding agent that exits 0 having written nothing is a false
            # completion: gates then run on an unchanged tree and the task can be
            # marked DONE with no code. Same guard the claude-code adapter got
            # in #739/#819.
            require_file_changes=True,
        )
        self._auto_approve = auto_approve
        self._permission_config: Path | None = None

    @property
    def name(self) -> str:  # noqa: D102
        return "opencode"

    @staticmethod
    def _prompt_exceeds_argv(prompt: str) -> bool:
        """True when the prompt is too large to survive as a single argv entry."""
        return len(prompt.encode("utf-8")) >= _MAX_ARG_BYTES

    def build_command(self, prompt: str, workspace_path: Path) -> list[str]:
        """Build the opencode CLI command.

        ``opencode run`` declares ``message`` as a positional array, and that is
        the form verified end-to-end against the CLI. An oversized prompt cannot
        go that way (see ``_MAX_ARG_BYTES``), so it is omitted from argv and sent
        on stdin instead — ``opencode run`` with no positional reads the message
        from stdin, confirmed by its own ``prompt_submit`` log carrying the piped
        text verbatim.

        Args:
            prompt: The task prompt.
            workspace_path: Workspace root (cwd is set by the base class).

        Returns:
            Command list for subprocess.Popen.
        """
        cmd = [self._binary_path, *self._cli_args]
        if not self._prompt_exceeds_argv(prompt):
            cmd.append(prompt)
        return cmd

    def _permission_config_path(self) -> Path:
        """Write (once) the deny-list config `--auto` is checked against.

        Kept for the adapter's lifetime rather than per run: opencode reads it at
        startup, and regenerating it per task would be churn for a constant.
        """
        if self._permission_config is None:
            handle = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="codeframe-opencode-", delete=False
            )
            with handle:
                json.dump(
                    {"permission": {"bash": {glob: "deny" for glob in _DENIED_BASH_GLOBS}}},
                    handle,
                )
            self._permission_config = Path(handle.name)
        return self._permission_config

    def get_env(self, workspace_path: Path) -> dict[str, str] | None:
        """Point opencode at the deny-list config when auto-approval is on (#916).

        Only when ``auto_approve`` is set: without ``--auto`` the operator's own
        opencode permission config governs, and overriding it would be the
        adapter quietly changing their settings.

        **Known limitation**: ``OPENCODE_CONFIG`` loads *between* the global and
        project configs, so a repository's own ``opencode.json`` still takes
        precedence and can re-allow a denied command. That is the repo-supplied
        config trust problem #903/#905 address elsewhere; this raises the floor
        for the ordinary case, it is not a containment boundary.
        """
        if not self._auto_approve:
            return None
        return {"OPENCODE_CONFIG": str(self._permission_config_path())}

    def get_stdin(self, prompt: str) -> str | None:
        """The prompt, but only when it did not fit in argv.

        Returns:
            None for a normal prompt — it is already a positional argument, and
            sending it twice would duplicate the instruction. The prompt itself
            when it was too large for argv.
        """
        return prompt if self._prompt_exceeds_argv(prompt) else None
