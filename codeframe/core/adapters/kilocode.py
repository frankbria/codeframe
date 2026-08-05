"""Kilocode adapter for delegating task execution to the kilo CLI."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from codeframe.core.adapters.agent_adapter import AgentResult
from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter

logger = logging.getLogger(__name__)

# Exit code used by kilo when the timeout is exceeded
_KILO_TIMEOUT_EXIT_CODE = 124


#: The two incompatible CLIs that both answer to ``kilo``.
_MODERN = "modern"  # 7.x: `kilo run <message> --dir <path>`
_LEGACY = "legacy"  # 0.22.0: `kilo <prompt> --auto --workspace <path>`

#: Substring that appears in ``kilo --help`` only once ``run`` exists. Detection
#: reads the CLI's own help rather than parsing ``--version``: #1015 requires
#: that the invocation never be guessed from a version string, and this repo has
#: been bitten three times by adapters that assumed a CLI surface (#913/#914/
#: #1012). Help text is what the binary actually offers.
_RUN_SUBCOMMAND_MARKER = "kilo run"

#: Detection runs a subprocess, so it is cached per binary path for the process.
_SURFACE_CACHE: dict[str, str] = {}


def _detect_surface(binary_path: str) -> str:
    """Which kilo CLI is installed, according to its own ``--help``.

    ``@kilocode/cli`` was rewritten between 0.22.0 (2026-01-15) and 7.x
    (2026-07-29) — 213 releases apart. The invocations share nothing:

    ==============  ============================  ==========================
    \\               0.22.0                        7.4.17
    ==============  ============================  ==========================
    usage           ``kilocode [options] [prompt]``  ``kilo run [message..]``
    workspace       ``--workspace <path>``        ``--dir <path>``
    ``--auto``      non-interactive               **auto-approve ALL perms**
    ==============  ============================  ==========================

    That last row is why this cannot be a blind rename: on 7.x ``--auto`` is the
    old ``--yolo``, the permission bypass #916 established must stay off.

    An unreadable or failing ``--help`` falls back to modern — the version any
    new install gets, and the one whose ``run`` subcommand fails loudly rather
    than opening a TUI that hangs until the timeout (#1012).
    """
    if binary_path in _SURFACE_CACHE:
        return _SURFACE_CACHE[binary_path]

    try:
        # Bytes, decoded permissively. `text=True` decodes with the locale
        # encoding and no error handler, so under a non-UTF-8 locale
        # (LC_ALL=C with UTF-8 coercion disabled — verified: encoding becomes
        # ANSI_X3.4-1968) kilo 7.x's box-drawing banner raises
        # UnicodeDecodeError. That is a ValueError, so it sailed straight past
        # the handler below and crashed build_command. (#1015 review)
        proc = subprocess.run(
            [binary_path, "--help"], capture_output=True, timeout=90
        )
        help_text = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError, ValueError):
        logger.warning(
            "Could not read `%s --help`; assuming the modern kilo surface.",
            binary_path,
        )
        help_text = ""

    surface = _MODERN if (not help_text or _RUN_SUBCOMMAND_MARKER in help_text) else _LEGACY
    _SURFACE_CACHE[binary_path] = surface
    return surface


class KilocodeAdapter(SubprocessAdapter):
    """Adapter that delegates code execution to Kilocode CLI.

    **Supported version floor: ``@kilocode/cli`` 7.x**, the surface any new
    install gets. 0.22.0 is still driven correctly when that is what is
    installed, because #1012 verified it end-to-end and an unupgraded machine
    should not silently break — but it is not the target, and support for it
    can be dropped once nobody is on it.

    Which invocation to use is **detected from the CLI's own ``--help``**, never
    inferred from a version string (#1015). ``_detect_surface`` has the table:

    * 7.x — ``kilo run --dir <path> <message>``. No ``--auto``: on this CLI that
      flag means "auto-approve all permissions", i.e. the old ``--yolo`` the
      adapter has always withheld (#916). ``run`` is non-interactive on its own,
      exactly like ``opencode run``.
    * 0.22.0 — ``kilo <prompt> --auto --workspace <path>``, where ``--auto`` is
      merely "non-interactive". There is no ``run`` subcommand; prepending one
      got it swallowed as the prompt, opening the TUI to hang until the timeout
      having written nothing (#1012).

    Prompt delivery: on 7.x the prompt always goes over **stdin**, never argv
    (#955). argv is world-readable — the whole prompt, including whatever task
    context it carries, shows up in ``ps`` for every user on the box — and Linux
    caps a single argv entry at 128 KiB (macOS 256 KB), under CodeFrame's ~100K
    token budget, so a large task raised ``OSError(E2BIG)`` before kilo started.
    ``kilo run`` with no positional reads the message from stdin (verified
    against 7.4.17: ``echo "say ok" | kilo run --dir /tmp`` reaches the model
    call). 0.22.0 has no stdin path at all, so there the prompt stays positional
    and an oversized one fails loudly rather than silently doing nothing.

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

    def _surface(self) -> str:
        """Which kilo CLI this adapter is talking to."""
        return _detect_surface(self._binary_path)

    def build_command(self, prompt: str, workspace_path: Path) -> list[str]:
        """Build the kilo CLI command for whichever CLI is actually installed.

        The two eras take completely different invocations (see
        ``_detect_surface``). Modern is the documented target; legacy is kept
        because it is what #1012 verified end-to-end and what an unupgraded
        install still speaks.

        Args:
            prompt: The task prompt.
            workspace_path: Workspace root.

        Returns:
            Command list for subprocess.Popen.
        """
        if self._surface() == _MODERN:
            # `run` is non-interactive by itself, exactly like `opencode run`.
            # --auto is deliberately NOT passed: in 7.x it means "auto-approve
            # all permissions", the 0.22 `--yolo` that #916 established must
            # stay off. Renaming --workspace to --dir while keeping --auto
            # would have silently upgraded the adapter into a permission bypass.
            # No positional: the prompt goes over stdin (see get_stdin), keeping
            # it out of `ps` and off the 128 KiB argv-entry ceiling (#955).
            cmd = [self._binary_path, "run", "--dir", str(workspace_path)]
        else:
            # 0.22.0: bare positional prompt, --auto is merely non-interactive
            # and --yolo (never passed) is the bypass. Verified in #1012/#916.
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
        """The prompt on modern kilo; None on legacy, which has no stdin path.

        ``kilo run`` with no positional reads the message from stdin: verified
        against 7.4.17, where `echo "say ok" | kilo run --dir /tmp` gets past
        message validation to the model call.

        This used to apply only to prompts over 128 KiB, the Linux cap on a
        single argv entry. Size was never the whole problem: argv is readable by
        every user on the machine via ``ps``, so a normal-sized prompt — task
        description, file excerpts, whatever context was assembled — was on
        display for the duration of the run (#955). Sending it over stdin fixes
        both, and it is the same code path the oversized case already used.

        0.22.0 takes the prompt positionally and has no stdin path, so there an
        oversized prompt still fails loudly rather than silently doing nothing.
        """
        return prompt if self._surface() == _MODERN else None

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
