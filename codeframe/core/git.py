"""Git operations for CodeFRAME v2.

This module provides v2-compatible git operations that work with
the Workspace model. It uses GitPython directly without requiring
the v1 database.

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import git

from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class GitStatus:
    """Git working tree status."""

    current_branch: str
    is_dirty: bool
    modified_files: list[str]
    untracked_files: list[str]
    staged_files: list[str]


@dataclass
class CommitInfo:
    """Git commit information."""

    hash: str
    short_hash: str
    message: str
    author: str
    timestamp: str


@dataclass
class CommitResult:
    """Result of a commit operation."""

    commit_hash: str
    commit_message: str
    files_changed: int


# ============================================================================
# Git Operations
# ============================================================================


def _get_repo(workspace: Workspace) -> git.Repo:
    """Get git repo for a workspace.

    Args:
        workspace: Target workspace

    Returns:
        GitPython Repo object

    Raises:
        ValueError: If workspace is not a git repository
    """
    try:
        return git.Repo(workspace.repo_path)
    except git.InvalidGitRepositoryError:
        raise ValueError(f"Not a git repository: {workspace.repo_path}")
    except git.NoSuchPathError:
        raise ValueError(f"Path does not exist: {workspace.repo_path}")


def get_status(workspace: Workspace) -> GitStatus:
    """Get git working tree status for a workspace.

    Args:
        workspace: Target workspace

    Returns:
        GitStatus with branch and file states
    """
    repo = _get_repo(workspace)

    # Get current branch
    try:
        current_branch = repo.active_branch.name
    except TypeError:
        # Detached HEAD state
        current_branch = f"(detached HEAD at {repo.head.commit.hexsha[:7]})"

    # Check if dirty
    is_dirty = repo.is_dirty(untracked_files=True)

    # Get modified files (tracked, unstaged changes)
    modified_files = [item.a_path for item in repo.index.diff(None)]

    # Get untracked files
    untracked_files = list(repo.untracked_files)

    # Get staged files (handle repos with no commits/HEAD)
    staged_files: list[str] = []
    try:
        if repo.head.is_valid():
            staged_files = [item.a_path for item in repo.index.diff("HEAD")]
        else:
            # No HEAD yet - all indexed files are staged
            staged_files = [path for path, _stage in repo.index.entries.keys()]
    except git.BadName:
        # HEAD reference doesn't exist (empty repo)
        pass

    return GitStatus(
        current_branch=current_branch,
        is_dirty=is_dirty,
        modified_files=modified_files,
        untracked_files=untracked_files,
        staged_files=staged_files,
    )


def list_commits(
    workspace: Workspace,
    branch: Optional[str] = None,
    limit: int = 50,
) -> list[CommitInfo]:
    """List git commits for a workspace.

    Args:
        workspace: Target workspace
        branch: Optional branch name (default: current branch)
        limit: Maximum number of commits to return

    Returns:
        List of CommitInfo objects
    """
    repo = _get_repo(workspace)

    commits: list[CommitInfo] = []
    try:
        if branch:
            commits_iter = repo.iter_commits(branch, max_count=limit)
        else:
            commits_iter = repo.iter_commits(max_count=limit)

        for commit in commits_iter:
            commits.append(
                CommitInfo(
                    hash=commit.hexsha,
                    short_hash=commit.hexsha[:7],
                    message=commit.message.strip().split("\n")[0],
                    author=str(commit.author),
                    timestamp=commit.committed_datetime.isoformat(),
                )
            )
    except git.GitCommandError as e:
        logger.warning(f"Failed to list commits: {e}")
    except git.BadName as e:
        logger.warning(f"Invalid branch reference: {e}")

    return commits


def create_commit(
    workspace: Workspace,
    files: list[str],
    message: str,
) -> CommitResult:
    """Create a git commit with specified files.

    Args:
        workspace: Target workspace
        files: List of file paths to commit (relative to repo root)
        message: Commit message

    Returns:
        CommitResult with commit details

    Raises:
        ValueError: If no files provided or commit fails
    """
    if not files:
        raise ValueError("No files to commit")

    if not message or not message.strip():
        raise ValueError("Commit message cannot be empty")

    repo = _get_repo(workspace)

    # Validate file paths exist
    repo_root = Path(repo.working_tree_dir)
    valid_files: list[str] = []
    for file_path in files:
        full_path = repo_root / file_path
        if full_path.exists():
            valid_files.append(file_path)
        else:
            logger.warning(f"File not found, skipping: {file_path}")

    if not valid_files:
        raise ValueError("None of the specified files exist")

    # Stage files
    repo.index.add(valid_files)

    # Create commit
    commit = repo.index.commit(message.strip())

    logger.info(f"Created commit {commit.hexsha[:7]}: {message.strip()[:50]}")

    return CommitResult(
        commit_hash=commit.hexsha,
        commit_message=message.strip(),
        files_changed=len(valid_files),
    )


def get_diff(
    workspace: Workspace,
    staged: bool = False,
) -> str:
    """Get git diff for a workspace.

    Args:
        workspace: Target workspace
        staged: If True, show staged changes; if False, show unstaged changes

    Returns:
        Diff as string
    """
    repo = _get_repo(workspace)

    try:
        if staged:
            # Staged changes (compared to HEAD)
            if repo.head.is_valid():
                return repo.git.diff("--cached")
            return ""
        else:
            # Unstaged changes (working tree vs index)
            return repo.git.diff()
    except git.GitCommandError as e:
        logger.warning(f"Failed to get diff: {e}")
        return ""


def get_current_branch(workspace: Workspace) -> str:
    """Get current branch name for a workspace.

    Args:
        workspace: Target workspace

    Returns:
        Branch name or detached HEAD indicator
    """
    repo = _get_repo(workspace)

    try:
        return repo.active_branch.name
    except TypeError:
        return f"(detached HEAD at {repo.head.commit.hexsha[:7]})"


def is_clean(workspace: Workspace) -> bool:
    """Check if workspace has no uncommitted changes.

    Args:
        workspace: Target workspace

    Returns:
        True if working tree is clean
    """
    repo = _get_repo(workspace)
    return not repo.is_dirty(untracked_files=True)
