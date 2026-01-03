"""Checkpoints router for CodeFRAME FastAPI server.

Handles checkpoint management endpoints including creating checkpoints, listing
checkpoints, restoring from checkpoints, and getting checkpoint diffs.

Sprint 10 - Phase 4: Checkpoint API endpoints (T092-T097):
- GET /api/projects/{project_id}/checkpoints - List all checkpoints
- POST /api/projects/{project_id}/checkpoints - Create a new checkpoint
- GET /api/projects/{project_id}/checkpoints/{checkpoint_id} - Get checkpoint details
- DELETE /api/projects/{project_id}/checkpoints/{checkpoint_id} - Delete checkpoint
- POST /api/projects/{project_id}/checkpoints/{checkpoint_id}/restore - Restore checkpoint
- GET /api/projects/{project_id}/checkpoints/{checkpoint_id}/diff - Get checkpoint diff
"""

from fastapi import APIRouter, HTTPException, Depends, Response, Body
from fastapi.responses import JSONResponse
from pathlib import Path
from datetime import datetime, UTC
import hashlib
import logging
import re
import subprocess

from codeframe.ui.models import (
    CheckpointCreateRequest,
    CheckpointResponse,
    CheckpointDiffResponse,
    RestoreCheckpointRequest,
)
from codeframe.ui.dependencies import get_db
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User
from codeframe.ui.shared import manager
from codeframe.persistence.database import Database
from codeframe.lib.checkpoint_manager import CheckpointManager

# Module logger
logger = logging.getLogger(__name__)

# Create router with prefix for all checkpoint endpoints
router = APIRouter(prefix="/api/projects/{project_id}/checkpoints", tags=["checkpoints"])


@router.get("")
async def list_checkpoints(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all checkpoints for a project (T092).

    Sprint 10 - Phase 4: Checkpoint API

    Returns all checkpoints for the specified project, sorted by creation time
    (most recent first). Includes checkpoint metadata for quick inspection.

    Args:
        project_id: Project ID to list checkpoints for
        db: Database connection (injected)

    Returns:
        200 OK: List of checkpoints
        {
            "checkpoints": [
                {
                    "id": int,
                    "project_id": int,
                    "name": str,
                    "description": str | null,
                    "trigger": str,
                    "git_commit": str,
                    "database_backup_path": str,
                    "context_snapshot_path": str,
                    "metadata": {
                        "project_id": int,
                        "phase": str,
                        "tasks_completed": int,
                        "tasks_total": int,
                        "agents_active": list[str],
                        "last_task_completed": str | null,
                        "context_items_count": int,
                        "total_cost_usd": float
                    },
                    "created_at": str  # ISO 8601
                },
                ...
            ]
        }

        404 Not Found: Project not found

    Example:
        GET /api/projects/123/checkpoints
    """

    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get checkpoints from database
    checkpoints = db.get_checkpoints(project_id)

    # Convert to response models
    checkpoint_responses = []
    for checkpoint in checkpoints:
        checkpoint_responses.append(
            CheckpointResponse(
                id=checkpoint.id,
                project_id=checkpoint.project_id,
                name=checkpoint.name,
                description=checkpoint.description,
                trigger=checkpoint.trigger,
                git_commit=checkpoint.git_commit,
                database_backup_path=checkpoint.database_backup_path,
                context_snapshot_path=checkpoint.context_snapshot_path,
                metadata=checkpoint.metadata.model_dump(),
                created_at=checkpoint.created_at.isoformat(),
            )
        )

    return {"checkpoints": checkpoint_responses}


@router.post("", status_code=201)
async def create_checkpoint(
    project_id: int,
    request: CheckpointCreateRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new checkpoint for a project (T093).

    Sprint 10 - Phase 4: Checkpoint API

    Creates a complete project checkpoint including:
    - Git commit (code state)
    - Database backup (tasks, context, metrics)
    - Context snapshot (agent context items as JSON)
    - Metadata (progress, costs, active agents)

    Args:
        project_id: Project ID to create checkpoint for
        request: CheckpointCreateRequest with name, description, trigger
        db: Database connection (injected)

    Returns:
        201 Created: Checkpoint created successfully
        {
            "id": int,
            "project_id": int,
            "name": str,
            "description": str | null,
            "trigger": str,
            "git_commit": str,
            "database_backup_path": str,
            "context_snapshot_path": str,
            "metadata": {
                "project_id": int,
                "phase": str,
                "tasks_completed": int,
                "tasks_total": int,
                "agents_active": list[str],
                "last_task_completed": str | null,
                "context_items_count": int,
                "total_cost_usd": float
            },
            "created_at": str  # ISO 8601
        }

        404 Not Found: Project not found
        500 Internal Server Error: Checkpoint creation failed

    Example:
        POST /api/projects/123/checkpoints
        Body: {
            "name": "Before refactor",
            "description": "Safety checkpoint before major refactoring",
            "trigger": "manual"
        }
    """

    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get project workspace path
    workspace_path = project.get("workspace_path")
    if not workspace_path:
        raise HTTPException(
            status_code=500,
            detail=f"Project {project_id} has no workspace path configured",
        )

    try:
        # Create checkpoint manager
        checkpoint_mgr = CheckpointManager(
            db=db,
            project_root=Path(workspace_path),
            project_id=project_id,
        )

        # Create checkpoint
        checkpoint = checkpoint_mgr.create_checkpoint(
            name=request.name,
            description=request.description,
            trigger=request.trigger,
        )

        logger.info(
            f"Created checkpoint {checkpoint.id} for project {project_id}: {checkpoint.name}"
        )

        # Broadcast checkpoint created event
        try:
            await manager.broadcast(
                {
                    "type": "checkpoint_created",
                    "project_id": project_id,
                    "checkpoint_id": checkpoint.id,
                    "checkpoint_name": checkpoint.name,
                    "trigger": checkpoint.trigger,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast checkpoint_created event: {e}")

        # Return checkpoint response
        return CheckpointResponse(
            id=checkpoint.id,
            project_id=checkpoint.project_id,
            name=checkpoint.name,
            description=checkpoint.description,
            trigger=checkpoint.trigger,
            git_commit=checkpoint.git_commit,
            database_backup_path=checkpoint.database_backup_path,
            context_snapshot_path=checkpoint.context_snapshot_path,
            metadata=checkpoint.metadata.model_dump(),
            created_at=checkpoint.created_at.isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to create checkpoint for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Internal server error while creating checkpoint"
        )


@router.get("/{checkpoint_id}")
async def get_checkpoint(
    project_id: int,
    checkpoint_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get details of a specific checkpoint (T094).

    Sprint 10 - Phase 4: Checkpoint API

    Returns full details of a checkpoint including all metadata.

    Args:
        project_id: Project ID (for path consistency)
        checkpoint_id: Checkpoint ID to retrieve
        db: Database connection (injected)

    Returns:
        200 OK: Checkpoint details
        {
            "id": int,
            "project_id": int,
            "name": str,
            "description": str | null,
            "trigger": str,
            "git_commit": str,
            "database_backup_path": str,
            "context_snapshot_path": str,
            "metadata": {
                "project_id": int,
                "phase": str,
                "tasks_completed": int,
                "tasks_total": int,
                "agents_active": list[str],
                "last_task_completed": str | null,
                "context_items_count": int,
                "total_cost_usd": float
            },
            "created_at": str  # ISO 8601
        }

        404 Not Found: Project or checkpoint not found

    Example:
        GET /api/projects/123/checkpoints/42
    """

    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get checkpoint from database
    checkpoint = db.get_checkpoint_by_id(checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")

    # Verify checkpoint belongs to this project
    if checkpoint.project_id != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {checkpoint_id} does not belong to project {project_id}",
        )

    # Return checkpoint response
    return CheckpointResponse(
        id=checkpoint.id,
        project_id=checkpoint.project_id,
        name=checkpoint.name,
        description=checkpoint.description,
        trigger=checkpoint.trigger,
        git_commit=checkpoint.git_commit,
        database_backup_path=checkpoint.database_backup_path,
        context_snapshot_path=checkpoint.context_snapshot_path,
        metadata=checkpoint.metadata.model_dump(),
        created_at=checkpoint.created_at.isoformat(),
    )


@router.delete("/{checkpoint_id}", status_code=204)
async def delete_checkpoint(
    project_id: int,
    checkpoint_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a checkpoint and its files (T095).

    Sprint 10 - Phase 4: Checkpoint API

    Deletes a checkpoint from the database and removes its backup files
    (database backup and context snapshot).

    Args:
        project_id: Project ID (for path consistency)
        checkpoint_id: Checkpoint ID to delete
        db: Database connection (injected)

    Returns:
        204 No Content: Checkpoint deleted successfully

        404 Not Found: Project or checkpoint not found
        500 Internal Server Error: File deletion failed

    Example:
        DELETE /api/projects/123/checkpoints/42
    """

    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get checkpoint from database
    checkpoint = db.get_checkpoint_by_id(checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")

    # Verify checkpoint belongs to this project
    if checkpoint.project_id != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {checkpoint_id} does not belong to project {project_id}",
        )

    try:
        # Delete backup files
        db_backup_path = Path(checkpoint.database_backup_path)
        context_snapshot_path = Path(checkpoint.context_snapshot_path)

        if db_backup_path.exists():
            db_backup_path.unlink()
            logger.debug(f"Deleted database backup: {db_backup_path}")

        if context_snapshot_path.exists():
            context_snapshot_path.unlink()
            logger.debug(f"Deleted context snapshot: {context_snapshot_path}")

        # Delete checkpoint from database
        db.delete_checkpoint(checkpoint_id)

        logger.info(f"Deleted checkpoint {checkpoint_id} for project {project_id}")

        # Broadcast checkpoint deleted event
        try:
            await manager.broadcast(
                {
                    "type": "checkpoint_deleted",
                    "project_id": project_id,
                    "checkpoint_id": checkpoint_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast checkpoint_deleted event: {e}")

        # Return 204 No Content
        return Response(status_code=204)

    except Exception as e:
        logger.error(f"Failed to delete checkpoint {checkpoint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Checkpoint deletion failed")


@router.post("/{checkpoint_id}/restore", status_code=202)
async def restore_checkpoint(
    project_id: int,
    checkpoint_id: int,
    request: RestoreCheckpointRequest = Body(default_factory=RestoreCheckpointRequest),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore project to checkpoint state (T096, T097).

    Sprint 10 - Phase 4: Checkpoint API

    Restores project to a previous checkpoint state. If confirm_restore=False,
    shows git diff without making changes. If confirm_restore=True, performs
    the restoration including:
    - Checking out git commit
    - Restoring database from backup
    - Restoring context items

    Args:
        project_id: Project ID
        checkpoint_id: Checkpoint ID to restore
        request: RestoreCheckpointRequest with confirm_restore flag
        db: Database connection (injected)

    Returns:
        200 OK (if confirm_restore=False): Diff preview
        {
            "checkpoint_name": str,
            "diff": str  # Git diff output
        }

        202 Accepted (if confirm_restore=True): Restore started
        {
            "success": bool,
            "checkpoint_name": str,
            "git_commit": str,
            "items_restored": int
        }

        404 Not Found: Project or checkpoint not found
        500 Internal Server Error: Restore failed

    Example:
        POST /api/projects/123/checkpoints/42/restore
        Body: {
            "confirm_restore": false  # Show diff first
        }

        POST /api/projects/123/checkpoints/42/restore
        Body: {
            "confirm_restore": true  # Actually restore
        }
    """

    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get project workspace path
    workspace_path = project.get("workspace_path")
    if not workspace_path:
        raise HTTPException(
            status_code=500,
            detail=f"Project {project_id} has no workspace path configured",
        )

    # Verify checkpoint exists
    checkpoint = db.get_checkpoint_by_id(checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")

    # Verify checkpoint belongs to this project
    if checkpoint.project_id != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {checkpoint_id} does not belong to project {project_id}",
        )

    try:
        # Create checkpoint manager
        checkpoint_mgr = CheckpointManager(
            db=db,
            project_root=Path(workspace_path),
            project_id=project_id,
        )

        # Restore checkpoint (or show diff if not confirmed)
        result = checkpoint_mgr.restore_checkpoint(
            checkpoint_id=checkpoint_id,
            confirm=request.confirm_restore,
        )

        if request.confirm_restore:
            logger.info(f"Restored checkpoint {checkpoint_id} for project {project_id}")

            # Broadcast checkpoint restored event
            try:
                await manager.broadcast(
                    {
                        "type": "checkpoint_restored",
                        "project_id": project_id,
                        "checkpoint_id": checkpoint_id,
                        "checkpoint_name": checkpoint.name,
                        "git_commit": result.get("git_commit"),
                        "files_changed": result.get("files_changed", 0),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast checkpoint_restored event: {e}")

            # Return 202 Accepted for successful restore
            return result
        else:
            # Return 200 OK for diff preview
            return result

    except ValueError as e:
        # Checkpoint not found or validation error
        logger.error(f"Checkpoint validation error: {e}", exc_info=True)
        raise HTTPException(status_code=404, detail="Checkpoint not found or invalid")
    except FileNotFoundError as e:
        # Backup files missing
        logger.error(f"Checkpoint backup files missing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Checkpoint backup files not found")
    except Exception as e:
        logger.error(f"Failed to restore checkpoint {checkpoint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Checkpoint restore failed")


@router.get("/{checkpoint_id}/diff")
async def get_checkpoint_diff(
    project_id: int,
    checkpoint_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CheckpointDiffResponse:
    """Get git diff for a checkpoint (Sprint 10 Phase 4).

    Returns the git diff between the checkpoint commit and current HEAD,
    including statistics about files changed, insertions, and deletions.

    Args:
        project_id: Project ID
        checkpoint_id: Checkpoint ID to get diff for
        db: Database connection (injected)

    Returns:
        200 OK: Checkpoint diff with statistics
        {
            "files_changed": int,
            "insertions": int,
            "deletions": int,
            "diff": str
        }
        404 Not Found: Project or checkpoint not found
        500 Internal Server Error: Git operation failed
    """

    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get project workspace path
    workspace_path = project.get("workspace_path")
    if not workspace_path:
        raise HTTPException(
            status_code=500,
            detail=f"Project {project_id} has no workspace path configured",
        )

    # Verify checkpoint exists
    checkpoint = db.get_checkpoint_by_id(checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")

    # Verify checkpoint belongs to this project
    if checkpoint.project_id != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {checkpoint_id} does not belong to project {project_id}",
        )

    # SECURITY: Validate git commit SHA format to prevent command injection
    git_sha_pattern = re.compile(r"^[a-f0-9]{7,40}$")
    if not git_sha_pattern.match(checkpoint.git_commit):
        logger.error(f"Invalid git commit SHA format: {checkpoint.git_commit}")
        raise HTTPException(
            status_code=500,
            detail=f"Invalid git commit format in checkpoint {checkpoint_id}",
        )

    try:
        # Verify git commit exists before attempting diff
        try:
            subprocess.run(
                ["git", "cat-file", "-e", checkpoint.git_commit],
                cwd=Path(workspace_path),
                check=True,
                capture_output=True,
                timeout=5,
            )
        except subprocess.CalledProcessError:
            logger.error(f"Git commit {checkpoint.git_commit} not found in repository")
            raise HTTPException(
                status_code=404,
                detail=f"Checkpoint commit {checkpoint.git_commit[:7]} not found in repository",
            )
        except subprocess.TimeoutExpired:
            logger.error(f"Git verification timed out for commit {checkpoint.git_commit}")
            raise HTTPException(status_code=500, detail="Git operation timed out")

        # Create checkpoint manager
        checkpoint_mgr = CheckpointManager(
            db=db,
            project_root=Path(workspace_path),
            project_id=project_id,
        )

        # Get diff output with size limit (10MB)
        diff_output = checkpoint_mgr._show_diff(checkpoint.git_commit)
        MAX_DIFF_SIZE = 10 * 1024 * 1024  # 10MB
        if len(diff_output) > MAX_DIFF_SIZE:
            diff_output = (
                diff_output[:MAX_DIFF_SIZE] + "\n\n... [diff truncated - exceeded 10MB limit]"
            )
            logger.warning(f"Diff for checkpoint {checkpoint_id} truncated due to size limit")

        # Parse diff statistics using git diff --numstat
        try:
            stats_result = subprocess.run(
                ["git", "diff", "--numstat", checkpoint.git_commit, "HEAD"],
                cwd=Path(workspace_path),
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Parse numstat output
            # Format: <insertions>\t<deletions>\t<filename>
            files_changed = 0
            total_insertions = 0
            total_deletions = 0
            binary_files = 0

            for line in stats_result.stdout.strip().split("\n"):
                if not line:
                    continue
                files_changed += 1
                parts = line.split("\t")
                if len(parts) >= 2:
                    # Handle binary files (marked as '-')
                    if parts[0] == "-" or parts[1] == "-":
                        binary_files += 1
                    else:
                        insertions = int(parts[0])
                        deletions = int(parts[1])
                        total_insertions += insertions
                        total_deletions += deletions

            # Get current HEAD commit for ETag computation
            head_commit_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(workspace_path),
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            head_commit = head_commit_result.stdout.strip()

            # Compute ETag from checkpoint and HEAD commits
            etag_value = hashlib.sha256(
                f"{checkpoint.git_commit}:{head_commit}".encode()
            ).hexdigest()[:16]

            response = CheckpointDiffResponse(
                files_changed=files_changed,
                insertions=total_insertions,
                deletions=total_deletions,
                diff=diff_output,
            )

            # Add cache headers with revalidation strategy
            return JSONResponse(
                content=response.model_dump(),
                headers={
                    "Cache-Control": "no-cache, must-revalidate",
                    "ETag": f'"{etag_value}"',
                    "X-Binary-Files": str(binary_files),
                },
            )

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get diff stats: {e.stderr}", exc_info=True)
            # Return error response when parsing fails (not misleading zeros)
            raise HTTPException(status_code=500, detail="Internal error parsing diff statistics")
        except subprocess.TimeoutExpired:
            logger.error(f"Git diff timed out for checkpoint {checkpoint_id}")
            raise HTTPException(status_code=500, detail="Diff operation timed out")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get checkpoint diff {checkpoint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get checkpoint diff")
