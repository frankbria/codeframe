"""Artifact management for CodeFRAME v2.

Handles patch export and git commit operations.

This module is headless - no FastAPI or HTTP dependencies.
"""

import subprocess
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from codeframe.core.workspace import Workspace
from codeframe.core import events


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@dataclass
class PatchInfo:
    """Information about an exported patch.

    Attributes:
        path: Path to the patch file
        size_bytes: Size of the patch file
        files_changed: Number of files in the patch
        insertions: Lines added
        deletions: Lines removed
        created_at: When the patch was created
    """

    path: Path
    size_bytes: int
    files_changed: int
    insertions: int
    deletions: int
    created_at: datetime


@dataclass
class CommitInfo:
    """Information about a created commit.

    Attributes:
        hash: Commit hash (short)
        full_hash: Full commit hash
        message: Commit message
        files_changed: Number of files changed
        insertions: Lines added
        deletions: Lines removed
        created_at: When the commit was created
    """

    hash: str
    full_hash: str
    message: str
    files_changed: int
    insertions: int
    deletions: int
    created_at: datetime


def export_patch(
    workspace: Workspace,
    out_path: Optional[Path] = None,
    staged_only: bool = False,
) -> PatchInfo:
    """Export changes as a patch file.

    Args:
        workspace: Target workspace
        out_path: Output path (auto-generated if None)
        staged_only: Only include staged changes

    Returns:
        PatchInfo with patch details

    Raises:
        ValueError: If no changes to export or git not available
    """
    repo_path = workspace.repo_path

    # Check git is available
    if not shutil.which("git"):
        raise ValueError("git not found in PATH")

    # Check we're in a git repo
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"Not a git repository: {repo_path}")

    # Generate patch content
    # Track which diff was actually used for stats calculation
    actual_staged_used = staged_only

    if staged_only:
        diff_cmd = ["git", "diff", "--cached"]
    else:
        diff_cmd = ["git", "diff", "HEAD"]

    result = subprocess.run(
        diff_cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    patch_content = result.stdout

    if not patch_content.strip():
        # Try just unstaged changes
        result = subprocess.run(
            ["git", "diff"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        patch_content = result.stdout
        # We fell back to unstaged diff, so update the tracking flag
        actual_staged_used = False

    if not patch_content.strip():
        raise ValueError("No changes to export")

    # Generate output path if not provided
    if out_path is None:
        timestamp = _utc_now().strftime("%Y%m%d-%H%M%S")
        out_path = repo_path / f".codeframe/patches/patch-{timestamp}.patch"

    # Ensure parent directory exists
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write patch
    out_path.write_text(patch_content)

    # Get stats using the actual diff type that was used
    stats = _get_diff_stats(repo_path, actual_staged_used)

    patch_info = PatchInfo(
        path=out_path,
        size_bytes=out_path.stat().st_size,
        files_changed=stats["files"],
        insertions=stats["insertions"],
        deletions=stats["deletions"],
        created_at=_utc_now(),
    )

    # Emit event
    events.emit_for_workspace(
        workspace,
        events.EventType.PATCH_EXPORTED,
        {
            "path": str(out_path),
            "size": patch_info.size_bytes,
            "files": patch_info.files_changed,
        },
        print_event=True,
    )

    return patch_info


def create_commit(
    workspace: Workspace,
    message: str,
    add_all: bool = False,
) -> CommitInfo:
    """Create a git commit.

    Args:
        workspace: Target workspace
        message: Commit message
        add_all: Stage all changes before committing

    Returns:
        CommitInfo with commit details

    Raises:
        ValueError: If commit fails or nothing to commit
    """
    repo_path = workspace.repo_path

    # Check git is available
    if not shutil.which("git"):
        raise ValueError("git not found in PATH")

    # Optionally stage all changes
    if add_all:
        result = subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ValueError(f"git add failed: {result.stderr}")

    # Check there are staged changes
    result = subprocess.run(
        ["git", "diff", "--cached", "--stat"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        raise ValueError("No staged changes to commit")

    # Get stats before commit
    stats = _get_diff_stats(repo_path, staged_only=True)

    # Create commit
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise ValueError(f"git commit failed: {result.stderr}")

    # Get commit hash
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    full_hash = result.stdout.strip()
    short_hash = full_hash[:7]

    commit_info = CommitInfo(
        hash=short_hash,
        full_hash=full_hash,
        message=message,
        files_changed=stats["files"],
        insertions=stats["insertions"],
        deletions=stats["deletions"],
        created_at=_utc_now(),
    )

    # Emit event
    events.emit_for_workspace(
        workspace,
        events.EventType.COMMIT_CREATED,
        {
            "hash": short_hash,
            "message": message[:100],
            "files": commit_info.files_changed,
        },
        print_event=True,
    )

    return commit_info


def get_status(repo_path: Path) -> dict:
    """Get git status summary.

    Args:
        repo_path: Repository path

    Returns:
        Dict with status info
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    lines = [line for line in result.stdout.strip().split("\n") if line]

    staged = []
    unstaged = []
    untracked = []

    for line in lines:
        if len(line) < 3:
            continue
        index_status = line[0]
        worktree_status = line[1]
        filename = line[3:]

        if index_status == "?":
            untracked.append(filename)
        elif index_status != " ":
            staged.append(filename)
        if worktree_status != " " and worktree_status != "?":
            unstaged.append(filename)

    return {
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "clean": len(lines) == 0,
    }


def list_patches(workspace: Workspace) -> list[PatchInfo]:
    """List exported patches.

    Args:
        workspace: Target workspace

    Returns:
        List of PatchInfo, newest first
    """
    patches_dir = workspace.state_dir / "patches"
    if not patches_dir.exists():
        return []

    patches = []
    for patch_file in sorted(patches_dir.glob("*.patch"), reverse=True):
        stats = _parse_patch_stats(patch_file)
        patches.append(
            PatchInfo(
                path=patch_file,
                size_bytes=patch_file.stat().st_size,
                files_changed=stats.get("files", 0),
                insertions=stats.get("insertions", 0),
                deletions=stats.get("deletions", 0),
                created_at=datetime.fromtimestamp(
                    patch_file.stat().st_mtime, tz=timezone.utc
                ),
            )
        )

    return patches


def _get_diff_stats(repo_path: Path, staged_only: bool = False) -> dict:
    """Get diff statistics."""
    if staged_only:
        cmd = ["git", "diff", "--cached", "--stat"]
    else:
        cmd = ["git", "diff", "HEAD", "--stat"]

    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    # Parse the last line which has summary
    lines = result.stdout.strip().split("\n")
    if not lines or not lines[-1]:
        return {"files": 0, "insertions": 0, "deletions": 0}

    summary = lines[-1]

    # Parse "X files changed, Y insertions(+), Z deletions(-)"
    files = 0
    insertions = 0
    deletions = 0

    import re

    files_match = re.search(r"(\d+) files? changed", summary)
    if files_match:
        files = int(files_match.group(1))

    ins_match = re.search(r"(\d+) insertions?\(\+\)", summary)
    if ins_match:
        insertions = int(ins_match.group(1))

    del_match = re.search(r"(\d+) deletions?\(-\)", summary)
    if del_match:
        deletions = int(del_match.group(1))

    return {"files": files, "insertions": insertions, "deletions": deletions}


def _parse_patch_stats(patch_file: Path) -> dict:
    """Parse stats from a patch file."""
    content = patch_file.read_text()

    files = set()
    insertions = 0
    deletions = 0

    for line in content.split("\n"):
        if line.startswith("diff --git"):
            # Extract filename
            parts = line.split()
            if len(parts) >= 4:
                files.add(parts[3])
        elif line.startswith("+") and not line.startswith("+++"):
            insertions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    return {
        "files": len(files),
        "insertions": insertions,
        "deletions": deletions,
    }
