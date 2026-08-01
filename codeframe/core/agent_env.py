"""The environment every agent-triggered subprocess runs with (#721, #905).

A **leaf module**: stdlib only, so both ``core/tools.py`` (ReAct engine) and
``core/executor.py`` (legacy plan engine) can converge on it without a cycle.

Two things it guarantees:

* **No secrets in the environment** (#721) — an allowlist, so a credential added
  to the operator's shell later is excluded by construction rather than by
  remembering to blocklist it.
* **No pointer to secrets** (#905) — ``HOME`` and the ``XDG_*`` paths resolve
  into a per-workspace scratch directory. The allowlist kept ``ANTHROPIC_API_KEY``
  out; ``HOME`` would have handed over the directory holding it.

This is not containment. The subprocess still runs as the operator with normal
filesystem access, so a command naming an absolute path still reaches whatever
that path holds. Only OS-level isolation (worktree/E2B/container) contains a
hostile command; this closes the paths a prompt-injected agent actually takes.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from collections.abc import Iterable
from pathlib import Path

#: The agent's shell inherits a *deny-by-default* environment. Without this it
#: would receive every secret in the operator's shell — ANTHROPIC_API_KEY,
#: OPENAI_API_KEY, AUTH_SECRET, etc. These are the non-secret vars needed to run
#: typical build/test/git commands; PATH and VIRTUAL_ENV are adjusted below for
#: venv activation.
SAFE_ENV_VARS = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "PWD", "TERM", "TZ",
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
    "TMPDIR", "TMP", "TEMP",
    "PYTHONPATH", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE", "VIRTUAL_ENV",
    "NODE_ENV", "NODE_PATH", "GOPATH", "GOCACHE", "CARGO_HOME", "RUSTUP_HOME",
    "JAVA_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
    "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC",  # Windows shell essentials
    # Proxy config + CI signal (infra, not secrets) so npm/pip/curl and
    # CI-aware test runners work; git identity for agent commits (#721 review).
    "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "ftp_proxy", "all_proxy", "no_proxy",
    "CI",
    "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
})

#: These default to ``$HOME/...`` when unset, so pinning ``HOME`` alone would
#: still let an XDG path resolve back to the operator's real home.
_XDG_VARS = ("XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME")

#: Opt out of the delegated-agent ``HOME`` sandbox (#996). For an operator whose
#: delegated CLI keeps state somewhere this module does not know to forward, and
#: who accepts that the agent can then read ``~/.codeframe``, ``~/.ssh``, ``~/.aws``.
#: Deliberately does *not* reopen the environment allowlist — two separate knobs.
INHERIT_HOME_ENV = "CODEFRAME_AGENT_INHERIT_HOME"

#: Where each delegated CLI gets its own home. Machine-wide rather than
#: per-workspace: a per-workspace home would force a fresh CLI login in every
#: repository, which is the failure the passthrough below exists to avoid.
_AGENT_HOMES = "agent-homes"

logger = logging.getLogger(__name__)


def build_agent_env(workspace_path: Path | str) -> dict[str, str]:
    """The environment for a subprocess an agent (or repo content) can steer.

    Args:
        workspace_path: The workspace the command runs in. The sandboxed ``HOME``
            lives under its ``.codeframe/`` state dir, so it is per-workspace and
            inspectable.
    """
    workspace_path = Path(workspace_path)
    env = {k: os.environ[k] for k in SAFE_ENV_VARS if k in os.environ}

    # A real directory rather than a nonexistent path, so tools that write
    # dotfiles (npm, pip, cargo, git) still work.
    sandbox_home = workspace_path / ".codeframe" / "agent-home"
    try:
        sandbox_home.mkdir(parents=True, exist_ok=True)
        # The sandbox fills with pip/npm/cargo cache files, and it lives inside
        # the workspace — so without this every one of them shows up as
        # untracked, marking the tree dirty and (worse) landing in the PROOF9
        # scope, which is built from `status.untracked_files`. Self-ignoring,
        # the way `uv venv` does it, needs no git-directory resolution and works
        # unchanged in the linked worktrees CodeFRAME creates.
        gitignore = sandbox_home / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n")
    except OSError:
        # Point at it anyway. Deleting HOME does NOT fail closed: with the
        # variable *unset*, `expanduser("~")` and everything built on it fall
        # back to getpwuid() and resolve the operator's real home — so the
        # child would quietly regain ~/.codeframe, ~/.npmrc, ~/.config/gh.
        # A set-but-missing directory keeps the pointer away from the operator
        # and makes tools that truly need to write there fail visibly.
        logger.warning(
            "Could not create the agent sandbox home %s; subprocesses will run "
            "with a non-existent HOME rather than the operator's.", sandbox_home
        )

    env["HOME"] = str(sandbox_home)
    for xdg in _XDG_VARS:
        env[xdg] = str(sandbox_home / xdg.lower())

    for venv_dir in (".venv", "venv"):
        # "Scripts" on Windows, "bin" everywhere else. Checking both rather than
        # os.name means a venv created on either platform is recognised (#908
        # review) — without this, a Windows target repo's pytest resolved from
        # CodeFRAME's PATH instead of the repo's own venv.
        for bin_dir in ("bin", "Scripts"):
            venv_bin = workspace_path / venv_dir / bin_dir
            if venv_bin.is_dir():
                env["PATH"] = str(venv_bin) + os.pathsep + env.get("PATH", "")
                env["VIRTUAL_ENV"] = str(workspace_path / venv_dir)
                return env

    return env


def build_delegated_agent_env(
    workspace_path: Path | str,
    *,
    adapter_name: str,
    credential_vars: Iterable[str] = (),
    home_passthrough: Iterable[str] = (),
) -> dict[str, str]:
    """The environment for a delegated coding CLI (claude, codex, opencode) — #996.

    ``build_agent_env`` above is not usable as-is here: it forwards *no*
    credentials, and these CLIs cannot do anything without their provider key.
    So this keeps its deny-by-default allowlist and adds back exactly what the
    chosen adapter declares — an OpenAI key never reaches Claude Code, and a
    key exported into the operator's shell tomorrow is excluded by construction
    rather than by remembering to blocklist it.

    ``HOME`` moves to ``~/.codeframe/agent-homes/<adapter>``, so the delegated
    agent no longer resolves ``~/.codeframe/credentials``, ``~/.ssh`` or
    ``~/.aws`` — while ``home_passthrough`` symlinks that CLI's *own* config
    directory back in, because a naive sandbox simply logs it out and breaks the
    engine for every subscription-auth operator.

    Same caveat as ``build_agent_env``: this is not containment. The child still
    runs as the operator, so an absolute path reaches whatever the operator can
    read. It closes the paths a prompt-injected agent actually takes.

    Args:
        workspace_path: The workspace the agent runs in (for the PATH/venv work
            ``build_agent_env`` does).
        adapter_name: Names the per-adapter home, so two CLIs do not fight over
            one config directory.
        credential_vars: Environment variables to forward from the operator's
            environment. Anything not listed is dropped.
        home_passthrough: Paths relative to the operator's real home to symlink
            into the sandbox home (e.g. ``.claude``, ``.config/opencode``).
            Missing entries are skipped.
    """
    env = build_agent_env(workspace_path)
    real_home = Path(os.path.expanduser("~"))

    for var in credential_vars:
        if var in os.environ:
            env[var] = os.environ[var]

    if _inherit_home():
        logger.warning(
            "%s is set: the delegated agent runs with the operator's real HOME "
            "and can read ~/.codeframe, ~/.ssh and ~/.aws.", INHERIT_HOME_ENV
        )
        for var in ("HOME", *_XDG_VARS):
            if var in os.environ:
                env[var] = os.environ[var]
            else:
                # Unset rather than left pointing at the built-in sandbox — the
                # opt-out means "behave as the operator's shell does".
                env.pop(var, None)
        return env

    agent_home = real_home / ".codeframe" / _AGENT_HOMES / _home_slug(adapter_name)
    try:
        agent_home.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Point at it anyway — see build_agent_env: an *unset* HOME falls back to
        # getpwuid() and silently regains the operator's real home.
        logger.warning(
            "Could not create the delegated agent home %s; the CLI will run with "
            "a non-existent HOME rather than the operator's.", agent_home
        )
    else:
        _link_home_passthrough(real_home, agent_home, home_passthrough)

    env["HOME"] = str(agent_home)
    # The conventional layout, not build_agent_env's flat one: a CLI that reads
    # $XDG_CONFIG_HOME/opencode and one that reads ~/.config/opencode must land
    # on the same directory, or the passthrough symlink below is never consulted.
    env["XDG_CONFIG_HOME"] = str(agent_home / ".config")
    env["XDG_DATA_HOME"] = str(agent_home / ".local" / "share")
    env["XDG_CACHE_HOME"] = str(agent_home / ".cache")
    return env


def _home_slug(adapter_name: str) -> str:
    """One path segment, whatever the adapter calls itself.

    ``adapter_name`` reaches this as ``SubprocessAdapter.name``, which the base
    class derives from the binary — so an absolute path would otherwise land
    ``Path / "/usr/bin/claude"`` straight back at the filesystem root, and a
    ``..`` would climb out of ``~/.codeframe``.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", adapter_name).strip(".-")
    return slug or "agent"


def _inherit_home() -> bool:
    return os.getenv(INHERIT_HOME_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _link_home_passthrough(
    real_home: Path, agent_home: Path, entries: Iterable[str]
) -> None:
    """Link the delegated CLI's own config back into its sandbox home.

    Only the named entries — linking ``~/.claude`` must not drag ``~/.codeframe``
    or ``~/.ssh`` along with it. The agent can write *through* a link into that
    CLI's own config, which it could already do today; the point is that
    everything else in the operator's home stops being reachable via ``~``.
    """
    for entry in entries:
        source = real_home / entry
        if not source.exists():
            continue  # operator has never run this CLI
        target = agent_home / entry
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                if target.readlink() == source:
                    continue
                target.unlink()
            elif target.exists():
                # A config dir the CLI made for itself on a run that happened
                # *before* the operator logged in. Leaving it in place would keep
                # the delegated agent logged out forever even after they do log
                # in — the real home is the authority once it exists. Moved
                # aside rather than deleted: it may hold a login made from
                # inside the sandbox.
                stale = target.with_name(target.name + ".superseded")
                if stale.is_symlink() or not stale.is_dir():
                    stale.unlink(missing_ok=True)
                elif stale.is_dir():
                    shutil.rmtree(stale)
                target.rename(stale)
            target.symlink_to(source, target_is_directory=source.is_dir())
        except OSError as e:
            # Batch execution runs several workers against the *same* adapter
            # home, so two of them can reach symlink_to() together and one loses
            # with FileExistsError. The loser's work is already done.
            if target.is_symlink() and target.readlink() == source:
                continue
            logger.warning(
                "Could not link %s into the delegated agent home: %s. That CLI "
                "may need to be re-authenticated.", entry, e
            )
