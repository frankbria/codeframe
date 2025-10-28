"""Workspace manager for creating and managing project workspaces."""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from codeframe.ui.models import SourceType


class WorkspaceManager:
    """Manages project workspaces (sandboxed directories)."""

    def __init__(self, workspace_root: Path):
        """Initialize workspace manager.

        Args:
            workspace_root: Root directory for all project workspaces
        """
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def create_workspace(
        self,
        project_id: int,
        source_type: SourceType,
        source_location: Optional[str] = None,
        source_branch: str = "main"
    ) -> Path:
        """Create workspace for a project.

        Args:
            project_id: Unique project identifier
            source_type: Type of source initialization
            source_location: Git URL, local path, or upload filename
            source_branch: Git branch to clone (for git_remote)

        Returns:
            Path to created workspace
        """
        workspace_path = self.workspace_root / str(project_id)

        if workspace_path.exists():
            raise ValueError(f"Workspace already exists: {workspace_path}")

        # Initialize based on source type
        if source_type == SourceType.GIT_REMOTE:
            self._init_from_git(workspace_path, source_location, source_branch)
        elif source_type == SourceType.LOCAL_PATH:
            self._init_from_local(workspace_path, source_location)
        elif source_type == SourceType.UPLOAD:
            self._init_from_upload(workspace_path, source_location)
        else:  # EMPTY
            self._init_empty(workspace_path)

        return workspace_path

    def _init_empty(self, workspace_path: Path) -> None:
        """Initialize empty workspace with git repo."""
        workspace_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=workspace_path,
            check=True,
            capture_output=True
        )

    def _init_from_git(self, workspace_path: Path, git_url: str, branch: str) -> None:
        """Clone from git repository."""
        subprocess.run(
            ["git", "clone", "--branch", branch, git_url, str(workspace_path)],
            check=True,
            capture_output=True
        )

    def _init_from_local(self, workspace_path: Path, local_path: str) -> None:
        """Copy from local filesystem path."""
        source = Path(local_path)
        if not source.exists():
            raise ValueError(f"Source path does not exist: {local_path}")

        shutil.copytree(source, workspace_path)

        # Initialize git if not already a git repo
        if not (workspace_path / ".git").exists():
            subprocess.run(
                ["git", "init"],
                cwd=workspace_path,
                check=True,
                capture_output=True
            )

    def _init_from_upload(self, workspace_path: Path, upload_filename: str) -> None:
        """Extract from uploaded archive."""
        # TODO: Implement in Phase 4 (upload endpoint)
        workspace_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=workspace_path,
            check=True,
            capture_output=True
        )
