"""Shared git utilities for adapter file detection."""

from __future__ import annotations

import subprocess
from pathlib import Path


def detect_modified_files(workspace_path: Path) -> list[str]:
    """Detect files modified in a workspace via git diff.

    Combines modified, staged, and untracked files. Returns an empty list
    if git is unavailable or the workspace is not a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []

        files = [f for f in result.stdout.strip().splitlines() if f]

        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if untracked.returncode == 0:
            files.extend(f for f in untracked.stdout.strip().splitlines() if f)

        return list(dict.fromkeys(files))
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []
