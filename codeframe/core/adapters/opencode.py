"""OpenCode adapter for delegating task execution to the opencode CLI."""

from __future__ import annotations

import atexit
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

#: The deny-list is a constant, so one file per *process* — not per adapter.
#: Adapters are constructed per task, so an instance-scoped temp file would leak
#: one /tmp entry per task once --auto is wired in. (#916 review)
_PERMISSION_CONFIG: Path | None = None


def _permission_config_path() -> Path:
    """Path to the deny-list config `--auto` is checked against, written once."""
    global _PERMISSION_CONFIG

    if _PERMISSION_CONFIG is not None and _PERMISSION_CONFIG.exists():
        return _PERMISSION_CONFIG

    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="codeframe-opencode-", delete=False
    )
    with handle:
        json.dump(
            {"permission": {"bash": {glob: "deny" for glob in _DENIED_BASH_GLOBS}}},
            handle,
        )
    _PERMISSION_CONFIG = Path(handle.name)
    atexit.register(_PERMISSION_CONFIG.unlink, missing_ok=True)
    return _PERMISSION_CONFIG



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

    @property
    def name(self) -> str:  # noqa: D102
        return "opencode"

    @classmethod
    def requirements(cls) -> dict[str, str]:
        """Environment variables ``cf engines check`` reports on."""
        return {
            "ANTHROPIC_API_KEY": "Anthropic API key (or `opencode auth login`)",
            "OPENAI_API_KEY": "OpenAI API key (or `opencode auth login`)",
        }

    @classmethod
    def credential_env_vars(cls) -> tuple[str, ...]:
        """opencode is genuinely multi-provider, so both keys are in scope (#996)."""
        return ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL")

    @classmethod
    def home_passthrough(cls) -> tuple[str, ...]:
        """`opencode auth login` writes to both — config and stored credentials."""
        return (".config/opencode", ".local/share/opencode")

    def build_command(self, prompt: str, workspace_path: Path) -> list[str]:
        """Build the opencode CLI command.

        The prompt is never in argv: ``ps`` shows argv to every user on the
        machine, so the task description and assembled context were on display
        for the whole run (#1306, as #955 fixed for kilocode). It goes on stdin
        — ``opencode run`` with no positional reads the message from there,
        confirmed by its own ``prompt_submit`` log carrying the piped text
        verbatim. That also sidesteps Linux's 128 KiB cap on one argv entry,
        which a large prompt used to hit with E2BIG.

        ``--dir`` is **required**, not belt-and-braces: opencode resolves its
        project directory from the *parent* process and ignores the ``cwd=``
        every other adapter relies on, so without it a delegated task edits
        whatever directory CodeFrame itself was launched from — under
        ``codeframe serve``, the server's own checkout (#1007). ``require_file_
        changes`` does not save us: it inspects the workspace, finds nothing and
        fails the run, correctly reporting failure while the edits have already
        landed somewhere else.

        Args:
            prompt: The task prompt.
            workspace_path: Workspace root. Also passed as ``cwd`` by the base
                class, which opencode does not honour — hence ``--dir``.

        Returns:
            Command list for subprocess.Popen.
        """
        return [self._binary_path, *self._cli_args, "--dir", str(workspace_path)]

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
        return {"OPENCODE_CONFIG": str(_permission_config_path())}

    def get_stdin(self, prompt: str) -> str | None:
        """The prompt — always on stdin, never in argv (see ``build_command``)."""
        return prompt
