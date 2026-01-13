"""Git operations router for CodeFRAME (#270).

This module provides REST API endpoints for git operations:
- Branch creation and management
- Commit creation and listing
- Git status retrieval

Endpoints follow the pattern: /api/projects/{project_id}/git/*
"""

import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
import git

from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User
from codeframe.git.workflow_manager import GitWorkflowManager
from codeframe.ui.shared import manager
from codeframe.ui.websocket_broadcasts import (
    broadcast_branch_created,
    broadcast_commit_created,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["git"])


# ============================================================================
# Request/Response Models
# ============================================================================


class BranchCreateRequest(BaseModel):
    """Request model for branch creation."""

    issue_number: str = Field(..., min_length=1, description="Issue number (e.g., '1.1')")
    issue_title: str = Field(..., min_length=1, description="Issue title for branch name")

    @field_validator("issue_number", "issue_title")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip whitespace and validate non-empty."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field cannot be empty or whitespace only")
        return stripped


class BranchResponse(BaseModel):
    """Response model for branch details."""

    id: int
    branch_name: str
    issue_id: int
    status: str
    created_at: str
    merged_at: Optional[str] = None
    merge_commit: Optional[str] = None


class BranchCreateResponse(BaseModel):
    """Response model for branch creation."""

    branch_name: str
    issue_number: str
    status: str
    created_at: str


class BranchListResponse(BaseModel):
    """Response model for branch listing."""

    branches: List[BranchResponse]


class CommitRequest(BaseModel):
    """Request model for commit creation."""

    task_id: int = Field(..., description="Task ID this commit is for")
    files_modified: List[str] = Field(..., min_length=1, description="List of modified files")
    agent_id: str = Field(..., min_length=1, description="Agent ID making the commit")

    @field_validator("files_modified")
    @classmethod
    def validate_files(cls, v: List[str]) -> List[str]:
        """Validate files list is not empty."""
        if not v:
            raise ValueError("files_modified cannot be empty")
        return v


class CommitResponse(BaseModel):
    """Response model for commit creation."""

    commit_hash: str
    commit_message: str
    files_changed: int
    timestamp: str


class CommitListItem(BaseModel):
    """Individual commit in list response."""

    hash: str
    short_hash: str
    message: str
    author: str
    timestamp: str
    files_changed: Optional[int] = None


class CommitListResponse(BaseModel):
    """Response model for commit listing."""

    commits: List[CommitListItem]


class GitStatusResponse(BaseModel):
    """Response model for git status."""

    current_branch: str
    is_dirty: bool
    modified_files: List[str]
    untracked_files: List[str]
    staged_files: List[str]


# ============================================================================
# Helper Functions
# ============================================================================


def get_project_or_404(db: Database, project_id: int) -> dict:
    """Get project or raise 404.

    Args:
        db: Database instance
        project_id: Project ID

    Returns:
        Project dictionary

    Raises:
        HTTPException: 404 if project not found
    """
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def check_project_access(db: Database, user: User, project_id: int) -> None:
    """Check user has project access or raise 403.

    Args:
        db: Database instance
        user: Current user
        project_id: Project ID

    Raises:
        HTTPException: 403 if user lacks access
    """
    if not db.user_has_project_access(user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")


def get_git_workflow_manager(project: dict, db: Database) -> GitWorkflowManager:
    """Get GitWorkflowManager for a project.

    Args:
        project: Project dictionary
        db: Database instance

    Returns:
        GitWorkflowManager instance

    Raises:
        HTTPException: 400 if project has no workspace
        HTTPException: 500 if not a git repository
    """
    workspace_path = project.get("workspace_path")
    if not workspace_path:
        raise HTTPException(status_code=400, detail="Project has no workspace")

    try:
        return GitWorkflowManager(Path(workspace_path), db)
    except git.InvalidGitRepositoryError:
        raise HTTPException(
            status_code=500, detail="Project workspace is not a git repository"
        )
    except git.NoSuchPathError:
        raise HTTPException(status_code=500, detail="Project workspace path does not exist")


# ============================================================================
# Branch Endpoints
# ============================================================================


@router.post("/{project_id}/git/branches", status_code=201, response_model=BranchCreateResponse)
async def create_branch(
    project_id: int,
    request: BranchCreateRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a feature branch for an issue.

    Args:
        project_id: Project ID
        request: Branch creation request
        db: Database instance
        current_user: Authenticated user

    Returns:
        Created branch details

    Raises:
        HTTPException:
            - 400: Branch already exists or invalid parameters
            - 403: Access denied
            - 404: Project not found
            - 500: Git operation failed
    """
    # Get project and check access
    project = get_project_or_404(db, project_id)
    check_project_access(db, current_user, project_id)

    # Get workflow manager
    workflow_manager = get_git_workflow_manager(project, db)

    # Find the issue to get its ID
    issues = db.get_project_issues(project_id)
    matching_issue = next(
        (i for i in issues if i.issue_number == request.issue_number),
        None
    )
    issue_id = matching_issue.id if matching_issue else None

    try:
        # Create the branch
        branch_name = workflow_manager.create_feature_branch(
            request.issue_number,
            request.issue_title
        )

        # Broadcast event
        await broadcast_branch_created(
            manager,
            project_id,
            branch_name,
            request.issue_number,
            issue_id,
        )

        logger.info(f"Created branch {branch_name} for project {project_id}")

        return BranchCreateResponse(
            branch_name=branch_name,
            issue_number=request.issue_number,
            status="active",
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    except ValueError as e:
        # Branch already exists or validation error
        raise HTTPException(status_code=400, detail=str(e))
    except git.GitCommandError as e:
        logger.error(f"Git error creating branch: {e}")
        raise HTTPException(status_code=500, detail=f"Git operation failed: {e}")


@router.get("/{project_id}/git/branches", response_model=BranchListResponse)
async def list_branches(
    project_id: int,
    status: Optional[str] = Query(default="active", description="Filter by status"),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List branches for a project.

    Args:
        project_id: Project ID
        status: Optional status filter (active, merged, abandoned)
        db: Database instance
        current_user: Authenticated user

    Returns:
        List of branches

    Raises:
        HTTPException:
            - 403: Access denied
            - 404: Project not found
    """
    # Get project and check access
    get_project_or_404(db, project_id)
    check_project_access(db, current_user, project_id)

    # Get project issues to filter branches
    project_issues = db.get_project_issues(project_id)
    project_issue_ids = {i.id for i in project_issues}

    # Get branches by status
    all_branches = db.get_branches_by_status(status) if status else []

    # Filter to only branches for this project's issues
    project_branches = [
        b for b in all_branches
        if b.get("issue_id") in project_issue_ids
    ]

    # Convert to response format
    branches = [
        BranchResponse(
            id=b["id"],
            branch_name=b["branch_name"],
            issue_id=b["issue_id"],
            status=b["status"],
            created_at=b.get("created_at", ""),
            merged_at=b.get("merged_at"),
            merge_commit=b.get("merge_commit"),
        )
        for b in project_branches
    ]

    return BranchListResponse(branches=branches)


@router.get("/{project_id}/git/branches/{branch_name}", response_model=BranchResponse)
async def get_branch(
    project_id: int,
    branch_name: str,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get branch details.

    Args:
        project_id: Project ID
        branch_name: Branch name
        db: Database instance
        current_user: Authenticated user

    Returns:
        Branch details

    Raises:
        HTTPException:
            - 403: Access denied
            - 404: Project or branch not found
    """
    # Get project and check access
    get_project_or_404(db, project_id)
    check_project_access(db, current_user, project_id)

    # Get project issues to verify branch belongs to project
    project_issues = db.get_project_issues(project_id)
    project_issue_ids = {i.id for i in project_issues}

    # Search for branch in all statuses
    for status_value in ["active", "merged", "abandoned"]:
        branches = db.get_branches_by_status(status_value)
        for b in branches:
            if b["branch_name"] == branch_name and b.get("issue_id") in project_issue_ids:
                return BranchResponse(
                    id=b["id"],
                    branch_name=b["branch_name"],
                    issue_id=b["issue_id"],
                    status=b["status"],
                    created_at=b.get("created_at", ""),
                    merged_at=b.get("merged_at"),
                    merge_commit=b.get("merge_commit"),
                )

    raise HTTPException(status_code=404, detail=f"Branch '{branch_name}' not found")


# ============================================================================
# Commit Endpoints
# ============================================================================


@router.post("/{project_id}/git/commit", status_code=201, response_model=CommitResponse)
async def create_commit(
    project_id: int,
    request: CommitRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a git commit for task changes.

    Args:
        project_id: Project ID
        request: Commit request
        db: Database instance
        current_user: Authenticated user

    Returns:
        Commit details

    Raises:
        HTTPException:
            - 400: No files to commit or validation error
            - 403: Access denied
            - 404: Project or task not found
            - 500: Git operation failed
    """
    # Get project and check access
    project = get_project_or_404(db, project_id)
    check_project_access(db, current_user, project_id)

    # Validate files_modified is not empty
    if not request.files_modified:
        raise HTTPException(status_code=400, detail="No files to commit")

    # Get task and verify it belongs to this project
    task = db.get_task(request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {request.task_id} not found")
    if task.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Task {request.task_id} not found in project")

    # Get workflow manager
    workflow_manager = get_git_workflow_manager(project, db)

    try:
        # Create task dict for commit_task_changes
        task_dict = {
            "id": task.id,
            "project_id": task.project_id,
            "task_number": task.task_number,
            "title": task.title,
            "description": task.description,
        }

        # Create commit
        commit_hash = workflow_manager.commit_task_changes(
            task_dict,
            request.files_modified,
            request.agent_id
        )

        # Get commit message from the repository
        commit = workflow_manager.repo.head.commit
        commit_message = commit.message.strip()

        # Broadcast event
        await broadcast_commit_created(
            manager,
            project_id,
            task.id,
            commit_hash,
            commit_message,
            len(request.files_modified),
        )

        logger.info(f"Created commit {commit_hash[:7]} for task {task.task_number}")

        return CommitResponse(
            commit_hash=commit_hash,
            commit_message=commit_message,
            files_changed=len(request.files_modified),
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Invalid task data: {e}")
    except git.GitCommandError as e:
        logger.error(f"Git error creating commit: {e}")
        raise HTTPException(status_code=500, detail=f"Git operation failed: {e}")


@router.get("/{project_id}/git/commits", response_model=CommitListResponse)
async def list_commits(
    project_id: int,
    branch: Optional[str] = Query(default=None, description="Branch name (default: current)"),
    limit: int = Query(default=50, ge=1, le=100, description="Max commits to return"),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List git commits for a project.

    Args:
        project_id: Project ID
        branch: Optional branch name (default: current branch)
        limit: Maximum number of commits to return (1-100)
        db: Database instance
        current_user: Authenticated user

    Returns:
        List of commits

    Raises:
        HTTPException:
            - 403: Access denied
            - 404: Project not found
            - 500: Git operation failed
    """
    # Get project and check access
    project = get_project_or_404(db, project_id)
    check_project_access(db, current_user, project_id)

    # Get workflow manager
    workflow_manager = get_git_workflow_manager(project, db)

    try:
        # Get commit iterator
        if branch:
            commits_iter = workflow_manager.repo.iter_commits(branch, max_count=limit)
        else:
            commits_iter = workflow_manager.repo.iter_commits(max_count=limit)

        # Build commit list
        commits = []
        for commit in commits_iter:
            # Count files changed (if available)
            try:
                files_changed = commit.stats.total.get("files", 0) if commit.stats else None
            except Exception:
                files_changed = None

            commits.append(
                CommitListItem(
                    hash=commit.hexsha,
                    short_hash=commit.hexsha[:7],
                    message=commit.message.strip().split("\n")[0],  # First line only
                    author=str(commit.author),
                    timestamp=commit.committed_datetime.isoformat().replace("+00:00", "Z"),
                    files_changed=files_changed,
                )
            )

        return CommitListResponse(commits=commits)

    except git.GitCommandError as e:
        logger.error(f"Git error listing commits: {e}")
        raise HTTPException(status_code=500, detail=f"Git operation failed: {e}")
    except Exception as e:
        logger.error(f"Error listing commits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Status Endpoint
# ============================================================================


@router.get("/{project_id}/git/status", response_model=GitStatusResponse)
async def get_git_status(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get git working tree status.

    Args:
        project_id: Project ID
        db: Database instance
        current_user: Authenticated user

    Returns:
        Git status including current branch and file states

    Raises:
        HTTPException:
            - 403: Access denied
            - 404: Project not found
            - 500: Git operation failed
    """
    # Get project and check access
    project = get_project_or_404(db, project_id)
    check_project_access(db, current_user, project_id)

    # Get workflow manager
    workflow_manager = get_git_workflow_manager(project, db)

    try:
        repo = workflow_manager.repo

        # Get current branch
        current_branch = workflow_manager.get_current_branch()

        # Check if dirty
        is_dirty = repo.is_dirty(untracked_files=True)

        # Get modified files (tracked, unstaged changes)
        modified_files = [item.a_path for item in repo.index.diff(None)]

        # Get untracked files
        untracked_files = repo.untracked_files

        # Get staged files
        staged_files = [item.a_path for item in repo.index.diff("HEAD")]

        return GitStatusResponse(
            current_branch=current_branch,
            is_dirty=is_dirty,
            modified_files=modified_files,
            untracked_files=list(untracked_files),
            staged_files=staged_files,
        )

    except git.GitCommandError as e:
        logger.error(f"Git error getting status: {e}")
        raise HTTPException(status_code=500, detail=f"Git operation failed: {e}")
    except Exception as e:
        logger.error(f"Error getting git status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
