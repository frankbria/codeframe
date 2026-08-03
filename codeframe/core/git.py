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
    #: Requested paths that were not committed — outside the repo, or neither
    #: present nor deleted. Returned so a 201 cannot silently drop a path (#942).
    skipped: list[str] = field(default_factory=list)


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
    to_add: list[str] = []
    to_remove: list[str] = []
    skipped: list[str] = []
    for file_path in files:
        candidate = (repo_root / file_path).resolve()
        # Security: Ensure path stays within repo root
        try:
            rel = str(candidate.relative_to(repo_root))
        except ValueError:
            logger.warning(f"File outside repo, skipping: {file_path}")
            skipped.append(str(file_path))
            continue
        if candidate.exists():
            to_add.append(rel)
        elif _is_tracked(repo, rel):
            # A DELETION. The old code skipped anything that did not exist, so a
            # deletion that get_status offered as committable was silently
            # dropped from a 201 response, and a deletions-only request failed
            # with "None of the specified files exist" (#942).
            to_remove.append(rel)
        else:
            logger.warning(f"File not found and not tracked, skipping: {file_path}")
            skipped.append(str(file_path))

    if not to_add and not to_remove:
        raise ValueError("None of the specified files exist")

    if to_add:
        repo.index.add(to_add)
    if to_remove:
        # Only stage the removal for paths still IN the index. `git rm` already
        # removed the entry for an already-staged deletion, and index.remove on
        # a path that is not there fails with "pathspec did not match any
        # files" — rejecting a deletion the user had correctly staged.
        still_indexed = [p for p in to_remove if _in_index(repo, p)]
        if still_indexed:
            repo.index.remove(still_indexed, working_tree=False, r=True)

    # Commit ONLY the requested paths (#942). repo.index.commit() writes the
    # WHOLE index, so any unrelated change already staged — an agent run's
    # leftovers, say — was swept into the user's commit while files_changed
    # reported only the count they asked for.
    committed = sorted(set(to_add) | set(to_remove))
    repo.git.commit("-m", message.strip(), "--", *committed)
    commit = repo.head.commit

    logger.info(f"Created commit {commit.hexsha[:7]}: {message.strip()[:50]}")

    return CommitResult(
        commit_hash=commit.hexsha,
        commit_message=message.strip(),
        files_changed=len(committed),
        skipped=skipped,
    )


def _in_index(repo, rel_path: str) -> bool:
    """Whether the path currently has an index entry."""
    try:
        return bool(repo.git.ls_files("--error-unmatch", "--", rel_path))
    except Exception:
        return False


def _is_tracked(repo, rel_path: str) -> bool:
    """Whether git knows this path, in the INDEX or in HEAD.

    Checking only ``ls-files`` (the index) misread an already-staged deletion:
    ``git rm`` removes the entry from the index, so a path the user had already
    staged for deletion looked untracked and was rejected. Consulting HEAD too
    means both "deleted in the working tree" and "already staged for deletion"
    count as committable.
    """
    if _in_index(repo, rel_path):
        return True
    try:
        return bool(repo.git.ls_tree("HEAD", "--", rel_path).strip())
    except Exception:
        return False


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

    # Index the diff body ONCE, keyed by new path (#942). The old code ran a
    # fresh re.search over the whole diff for every changed file — O(files x
    # diff size) on exactly the large diffs where it hurts.
    sections = _index_diff_sections(diff_text)

    for line in stat_output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            ins_str, del_str = parts[0], parts[1]
            # numstat renders a rename as "old => new" in ONE field (and
            # "dir/{a => b}/f" for a directory move). Take the NEW path:
            # reporting the old one made a rename look like an edit to a file
            # that no longer exists.
            file_path = _numstat_new_path(parts[2])
            ins = int(ins_str) if ins_str != "-" else 0
            dels = int(del_str) if del_str != "-" else 0
            total_insertions += ins
            total_deletions += dels

            file_section = sections.get(file_path, "")

            change_type = "modified"
            if "new file mode" in file_section:
                change_type = "added"
            elif "deleted file mode" in file_section:
                change_type = "deleted"
            elif re.search(r"^rename (from|to) ", file_section, re.MULTILINE):
                # Was always "modified": the rename marker lives in the diff
                # header, and the old per-file regex keyed on the numstat path
                # frequently missed the section entirely (#942).
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


def _numstat_new_path(raw: str) -> str:
    """The post-rename path from a numstat path field.

    git renders a rename as ``old => new``, or ``dir/{old => new}/file`` when
    only a path component changed. Both used to be reported verbatim, so the
    "path" of a renamed file was a arrow-joined pair that matched nothing (#942).
    """
    raw = raw.strip()
    brace = re.match(r"^(.*)\{(.*) => (.*)\}(.*)$", raw)
    if brace:
        prefix, _old, new, suffix = brace.groups()
        return f"{prefix}{new}{suffix}".replace("//", "/")
    if " => " in raw:
        return raw.split(" => ", 1)[1].strip()
    return raw


def _index_diff_sections(diff_text: str) -> dict[str, str]:
    """Split a unified diff into per-file sections keyed by the NEW path.

    Built once per call instead of re-scanning the whole diff for each changed
    file (#942). Renames are indexed under both paths so a lookup by either
    finds the section.
    """
    sections: dict[str, str] = {}
    if not diff_text:
        return sections

    for chunk in re.split(r"(?=^diff --git )", diff_text, flags=re.MULTILINE):
        if not chunk.startswith("diff --git "):
            continue
        header = re.match(r"diff --git a/(.*?) b/(\S+)", chunk)
        if not header:
            continue
        old_path, new_path = header.group(1), header.group(2)
        sections[new_path] = chunk
        # A rename's numstat path may be reported either way round.
        sections.setdefault(old_path, chunk)
        rename_to = re.search(r"^rename to (.+)$", chunk, re.MULTILINE)
        if rename_to:
            sections[rename_to.group(1).strip()] = chunk
    return sections


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
