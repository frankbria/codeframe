"""Git operations for CodeFRAME v2.

This module provides v2-compatible git operations that work with
the Workspace model. It uses GitPython directly without requiring
the v1 database.

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
import re
from dataclasses import dataclass, field
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


@dataclass
class FileChange:
    """Per-file change statistics from a diff."""

    path: str
    change_type: str  # "modified", "added", "deleted", "renamed"
    insertions: int = 0
    deletions: int = 0


@dataclass
class DiffStats:
    """Parsed diff statistics."""

    diff: str
    files_changed: int
    insertions: int
    deletions: int
    changed_files: list[FileChange] = field(default_factory=list)


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
        # Detached HEAD or empty repo
        if not repo.head.is_valid():
            current_branch = "(no commits)"
        else:
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

    # Validate file paths exist and are within repo
    repo_root = Path(repo.working_tree_dir).resolve()
    valid_files: list[str] = []
    for file_path in files:
        candidate = (repo_root / file_path).resolve()
        # Security: Ensure path stays within repo root
        try:
            candidate.relative_to(repo_root)
        except ValueError:
            logger.warning(f"File outside repo, skipping: {file_path}")
            continue
        if candidate.exists():
            valid_files.append(str(candidate.relative_to(repo_root)))
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
        # Detached HEAD or empty repo
        if not repo.head.is_valid():
            return "(no commits)"
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


def get_diff_stats(workspace: Workspace, staged: bool = False) -> DiffStats:
    """Get diff with parsed statistics.

    Args:
        workspace: Target workspace
        staged: If True, show staged changes; if False, show unstaged

    Returns:
        DiffStats with parsed per-file statistics
    """
    repo = _get_repo(workspace)
    diff_text = get_diff(workspace, staged=staged)

    if not diff_text.strip():
        return DiffStats(diff=diff_text, files_changed=0, insertions=0, deletions=0)

    # Use git diff --stat for accurate statistics
    try:
        if staged:
            stat_output = repo.git.diff("--cached", "--numstat") if repo.head.is_valid() else ""
        else:
            stat_output = repo.git.diff("--numstat")
    except git.GitCommandError:
        stat_output = ""

    changed_files: list[FileChange] = []
    total_insertions = 0
    total_deletions = 0

    for line in stat_output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            ins_str, del_str, file_path = parts[0], parts[1], parts[2]
            ins = int(ins_str) if ins_str != "-" else 0
            dels = int(del_str) if del_str != "-" else 0
            total_insertions += ins
            total_deletions += dels

            # Extract per-file section from diff for accurate change type detection
            file_section_match = re.search(
                rf"diff --git a/.*? b/{re.escape(file_path)}\n(.*?)(?=diff --git|\Z)",
                diff_text,
                re.DOTALL,
            )
            file_section = file_section_match.group(0) if file_section_match else ""

            change_type = "modified"
            if "new file mode" in file_section:
                change_type = "added"
            elif "deleted file mode" in file_section:
                change_type = "deleted"
            elif "rename from" in file_section:
                change_type = "renamed"

            changed_files.append(FileChange(
                path=file_path,
                change_type=change_type,
                insertions=ins,
                deletions=dels,
            ))

    return DiffStats(
        diff=diff_text,
        files_changed=len(changed_files),
        insertions=total_insertions,
        deletions=total_deletions,
        changed_files=changed_files,
    )


def get_patch(workspace: Workspace, staged: bool = False) -> str:
    """Get patch-formatted diff for export.

    Args:
        workspace: Target workspace
        staged: If True, show staged changes; if False, show unstaged

    Returns:
        Patch content as string (with full headers for git apply)
    """
    repo = _get_repo(workspace)

    try:
        if staged:
            if repo.head.is_valid():
                return repo.git.diff("--cached", "--patch", "--full-index")
            return ""
        else:
            return repo.git.diff("--patch", "--full-index")
    except git.GitCommandError as e:
        logger.warning(f"Failed to get patch: {e}")
        return ""


def generate_commit_message(workspace: Workspace, staged: bool = False) -> str:
    """Generate a commit message from the current diff.

    Uses heuristic analysis of changed files and diff content to suggest
    a conventional commit message. Does not require LLM.

    Args:
        workspace: Target workspace
        staged: If True, analyze staged changes; if False, unstaged

    Returns:
        Suggested commit message string
    """
    stats = get_diff_stats(workspace, staged=staged)

    if not stats.changed_files:
        return ""

    files = stats.changed_files
    file_count = len(files)

    # Determine primary action from change types
    added = [f for f in files if f.change_type == "added"]
    deleted = [f for f in files if f.change_type == "deleted"]
    modified = [f for f in files if f.change_type == "modified"]

    # Pick prefix based on dominant change type
    if len(added) > len(modified) and len(added) > len(deleted):
        prefix = "feat"
        action = "add"
    elif len(deleted) > len(modified):
        prefix = "refactor"
        action = "remove"
    else:
        prefix = "feat"
        action = "update"

    # Detect common patterns
    test_files = [f for f in files if "test" in f.path.lower()]
    if test_files and len(test_files) == file_count:
        prefix = "test"
        action = "add" if added else "update"

    config_files = [f for f in files if f.path.endswith((".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"))]
    if config_files and len(config_files) == file_count:
        prefix = "chore"
        action = "update"

    # Build description
    if file_count == 1:
        file_path = files[0].path
        name = Path(file_path).stem
        description = f"{action} {name}"
    else:
        # Find common directory
        dirs = set(str(Path(f.path).parent) for f in files)
        if len(dirs) == 1 and list(dirs)[0] != ".":
            description = f"{action} {list(dirs)[0]} ({file_count} files)"
        else:
            description = f"{action} {file_count} files"

    return f"{prefix}: {description}"
