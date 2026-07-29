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
        venv_bin = workspace_path / venv_dir / "bin"
        if venv_bin.is_dir():
            env["PATH"] = str(venv_bin) + os.pathsep + env.get("PATH", "")
            env["VIRTUAL_ENV"] = str(workspace_path / venv_dir)
            break

    return env
