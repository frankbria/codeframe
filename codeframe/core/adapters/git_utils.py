"""Shared git utilities for adapter file detection."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_modified_files(workspace_path: Path) -> list[str]:
    """Detect files modified in a workspace via git diff.

    Combines modified, staged, and untracked files. Returns an empty list
    if git is unavailable or the workspace is not a git repo.

    Errors are logged rather than swallowed silently: an empty list means
    "failed" for ``require_file_changes`` adapters, so a transient git error
    (lock contention, missing binary, timeout) would otherwise be
    indistinguishable from "the agent changed nothing". (#819)
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                "git diff failed in %s (exit %d): %s — reporting no modified "
                "files, which callers may read as 'agent did nothing'.",
                workspace_path,
                result.returncode,
                (result.stderr or "").strip() or "<no stderr>",
            )
            return []

        files = [f for f in result.stdout.strip().splitlines() if f]

        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if untracked.returncode == 0:
            files.extend(f for f in untracked.stdout.strip().splitlines() if f)
        else:
            logger.warning(
                "git ls-files failed in %s (exit %d): %s — untracked files are "
                "missing from the result.",
                workspace_path,
                untracked.returncode,
                (untracked.stderr or "").strip() or "<no stderr>",
            )

        return list(dict.fromkeys(files))
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as e:
        logger.warning("git could not run in %s: %s", workspace_path, e)
        return []


def git_head(workspace_path: Path) -> str | None:
    """Return the current HEAD commit sha, or None if HEAD is unresolvable.

    None means "not a git repo, git unavailable, or an unborn HEAD" — i.e.
    a state where modified-file detection can't judge whether work happened.
    Errors are logged: since empty now means failed for require_file_changes
    adapters, a git hiccup would otherwise be indistinguishable from "the
    agent changed nothing" in the logs. (#819)
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                "git rev-parse HEAD failed in %s (exit %d): %s",
                workspace_path,
                result.returncode,
                (result.stderr or "").strip() or "<no stderr>",
            )
            return None
        return result.stdout.strip() or None
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as e:
        logger.warning("git rev-parse HEAD could not run in %s: %s", workspace_path, e)
        return None
