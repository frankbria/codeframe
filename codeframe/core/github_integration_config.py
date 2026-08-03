"""Per-workspace GitHub integration config (issue #563).

Stores only **non-secret** repo metadata for a connected GitHub repository under
``.codeframe/github_integration.json``. The PAT itself is stored in the
caller-scoped ``CredentialManager`` (``CredentialProvider.GIT_GITHUB``; issue
#790 — per-user when authenticated, machine-wide when auth is disabled) — never
in this file.

Headless — no FastAPI or HTTP imports (architecture rule #1). Mirrors the
shape of ``codeframe/core/notifications_config.py``.

Schema (``.codeframe/github_integration.json``):

    {
      "repo": "owner/repo",
      "owner_login": "owner",
      "owner_avatar_url": "https://avatars.githubusercontent.com/...",
      "connected_at": "2026-06-01T12:00:00+00:00"
    }
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypedDict

from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)

GITHUB_INTEGRATION_CONFIG_FILENAME = "github_integration.json"


class GitHubIntegrationConfig(TypedDict):
    repo: str
    owner_login: str
    owner_avatar_url: str
    connected_at: str


def _config_path(workspace: Workspace) -> Path:
    return workspace.state_dir / GITHUB_INTEGRATION_CONFIG_FILENAME


def load_github_integration_config(
    workspace: Workspace,
) -> Optional[GitHubIntegrationConfig]:
    """Read the integration config, returning ``None`` when absent or corrupt.

    Never raises — a broken config should read as "not connected" rather than
    breaking the status endpoint.
    """
    path = _config_path(workspace)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("repo"):
            raise ValueError("missing required 'repo' field")
        return {
            "repo": str(data["repo"]),
            "owner_login": str(data.get("owner_login") or ""),
            "owner_avatar_url": str(data.get("owner_avatar_url") or ""),
            "connected_at": str(data.get("connected_at") or ""),
        }
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "Invalid github_integration.json — treating as not connected: %s", e
        )
        return None


def save_github_integration_config(
    workspace: Workspace,
    config: dict,
) -> GitHubIntegrationConfig:
    """Atomically persist integration config to disk.

    ``connected_at`` is stamped here (UTC) if not supplied by the caller.
    Returns the normalized config that was written.
    """
    payload: GitHubIntegrationConfig = {
        "repo": str(config["repo"]),
        "owner_login": str(config.get("owner_login") or ""),
        "owner_avatar_url": str(config.get("owner_avatar_url") or ""),
        "connected_at": str(
            config.get("connected_at") or datetime.now(timezone.utc).isoformat()
        ),
    }
    path = _config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(payload, indent=2))
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return payload


def clear_github_integration_config(workspace: Workspace) -> None:
    """Remove the integration config. Idempotent — absence is a no-op."""
    path = _config_path(workspace)
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Failed to remove github_integration.json: %s", e)


class GitHubResolutionError(Exception):
    """No usable GitHub credential/repo for this caller and workspace.

    Carries a caller-facing ``message`` explaining which half is missing so the
    HTTP and CLI layers can render it without re-deriving the reason.
    """


def resolve_github_repo(
    workspace: Workspace,
    *,
    allow_env_fallback: bool = True,
) -> Optional[str]:
    """The repo GitHub operations should target for this workspace (issue #900).

    The workspace's own connection wins. ``GITHUB_REPO`` is a self-hosted
    convenience only: it is the operator's ambient setting, so it must never
    silently redirect a connected workspace's PRs at another repository.
    """
    config = load_github_integration_config(workspace)
    if config and config.get("repo"):
        return config["repo"]
    if allow_env_fallback:
        return os.getenv("GITHUB_REPO") or None
    return None


def resolve_github_credentials(
    workspace: Workspace,
    user_id: Optional[int] = None,
    *,
    allow_env_fallback: bool = True,
) -> tuple[str, str]:
    """Resolve ``(token, repo)`` for GitHub operations, scoped to the caller.

    The single resolution path shared by the v2 PR router and ``cf pr`` (issue
    #900), so the server and the CLI cannot drift.

    The token comes from the caller-scoped ``CredentialManager`` (#790). For an
    **authenticated principal** the store is consulted before the environment:
    the default env-first order would let the operator's ambient
    ``GITHUB_TOKEN`` beat the PAT that user connected in the UI, so every PR
    would be opened on the operator's behalf, unattributed — the defect this
    resolves. For ``user_id=None`` (CLI / auth disabled) the caller *is* the
    operator, so there is no one to protect the environment from and the
    original env-first order stands — which also keeps ``cf pr`` from doing an
    OS-keyring read on every invocation when ``GITHUB_TOKEN`` is set.

    The repo always comes from the workspace's own
    ``.codeframe/github_integration.json`` first.

    Args:
        workspace: Workspace whose GitHub connection to use.
        user_id: Authenticated principal, or ``None`` for the machine-wide store
            (auth disabled / CLI).
        allow_env_fallback: Permit ``GITHUB_TOKEN``/``GITHUB_REPO`` when the
            workspace/user has no connection of its own. Callers in hosted mode
            must pass ``False`` — there the environment is shared by every
            tenant, so falling back to it is precisely the cross-tenant leak.

    Raises:
        GitHubResolutionError: If either half cannot be resolved.
    """
    from codeframe.core.credentials import CredentialManager, CredentialProvider

    manager = CredentialManager(user_id=user_id, migrate=False)
    if not allow_env_fallback:
        token = manager.get_stored_credential(CredentialProvider.GIT_GITHUB)
    else:
        token = manager.get_credential(
            CredentialProvider.GIT_GITHUB,
            prefer_stored=user_id is not None,
        )

    repo = resolve_github_repo(workspace, allow_env_fallback=allow_env_fallback)

    if not token:
        raise GitHubResolutionError(
            "No GitHub credential for this account. Connect a repository in "
            "Settings → Integrations, or run 'cf auth setup --provider github'."
        )
    if not repo:
        raise GitHubResolutionError(
            "No GitHub repository connected for this workspace. Connect one in "
            "Settings → Integrations."
        )
    return token, repo
