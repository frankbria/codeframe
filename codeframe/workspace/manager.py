"""Workspace manager for creating and managing project workspaces."""

import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional
from codeframe.ui.models import SourceType

logger = logging.getLogger(__name__)


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
        source_branch: str = "main",
    ) -> Path:
        """Create workspace for a project.

        Args:
            project_id: Unique project identifier
            source_type: Type of source initialization
            source_location: Git URL, local path, or upload filename
            source_branch: Git branch to clone (for git_remote)

        Returns:
            Path to created workspace

        Raises:
            ValueError: If workspace already exists or invalid source
            RuntimeError: If workspace creation fails
        """
        workspace_path = self.workspace_root / str(project_id)

        if workspace_path.exists():
            raise ValueError(f"Workspace already exists: {workspace_path}")

        try:
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

        except Exception as e:
            # Cleanup on failure
            if workspace_path.exists():
                logger.error(f"Workspace creation failed, cleaning up: {workspace_path}")
                shutil.rmtree(workspace_path, ignore_errors=True)
            raise RuntimeError(f"Failed to create workspace: {e}") from e

    def _init_empty(self, workspace_path: Path) -> None:
        """Initialize empty workspace with git repo.

        Raises:
            RuntimeError: If git init fails
        """
        workspace_path.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["git", "init"],
                cwd=workspace_path,
                check=True,
                capture_output=True,
                timeout=30,
                text=True,
            )
            logger.info(f"Initialized empty git repository at {workspace_path}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Git init failed: {e.stderr}")
            raise RuntimeError(f"Failed to initialize git repository: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            logger.error("Git init timed out")
            raise RuntimeError("Git initialization timed out after 30 seconds") from e
        except FileNotFoundError as e:
            logger.error("Git command not found")
            raise RuntimeError("Git is not installed or not in PATH") from e

    def _init_from_git(self, workspace_path: Path, git_url: str, branch: str) -> None:
        """Clone from git repository.

        Args:
            workspace_path: Destination path for cloned repository
            git_url: Git repository URL to clone
            branch: Branch name to clone

        Raises:
            ValueError: If git_url is None or empty
            RuntimeError: If git clone fails
        """
        if not git_url:
            raise ValueError("Git URL is required for GIT_REMOTE source type")

        try:
            result = subprocess.run(
                ["git", "clone", "--branch", branch, "--depth", "1", git_url, str(workspace_path)],
                check=True,
                capture_output=True,
                timeout=300,  # 5 minute timeout for large repos
                text=True,
            )
            logger.info(f"Cloned {git_url} (branch: {branch}) to {workspace_path}")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.lower() if e.stderr else ""
            if "could not resolve host" in error_msg or "network" in error_msg:
                logger.error(f"Network error cloning {git_url}: {e.stderr}")
                raise RuntimeError(f"Network error: Could not reach {git_url}") from e
            elif "repository not found" in error_msg or "not found" in error_msg:
                logger.error(f"Repository not found: {git_url}")
                raise RuntimeError(f"Repository not found: {git_url}") from e
            elif "branch" in error_msg and "not found" in error_msg:
                logger.error(f"Branch '{branch}' not found in {git_url}")
                raise RuntimeError(f"Branch '{branch}' does not exist in repository") from e
            elif "authentication" in error_msg or "permission denied" in error_msg:
                logger.error(f"Authentication failed for {git_url}")
                raise RuntimeError(f"Authentication failed: Check credentials for {git_url}") from e
            else:
                logger.error(f"Git clone failed: {e.stderr}")
                raise RuntimeError(f"Failed to clone repository: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            logger.error(f"Git clone timed out for {git_url}")
            raise RuntimeError(f"Clone operation timed out after 5 minutes for {git_url}") from e
        except FileNotFoundError as e:
            logger.error("Git command not found")
            raise RuntimeError("Git is not installed or not in PATH") from e

    def _init_from_local(self, workspace_path: Path, local_path: str) -> None:
        """Copy from local filesystem path.

        Args:
            workspace_path: Destination path
            local_path: Source path to copy from

        Raises:
            ValueError: If local_path is invalid or inaccessible
            RuntimeError: If copy or git init fails
        """
        if not local_path:
            raise ValueError("Local path is required for LOCAL_PATH source type")

        source = Path(local_path).resolve()  # Resolve to absolute path

        # Security: Validate path is safe
        if not self._is_safe_path(source):
            raise ValueError(
                f"Access denied: Path '{source}' is outside allowed directories. "
                "Only paths under $HOME are allowed."
            )

        if not source.exists():
            raise ValueError(f"Source path does not exist: {local_path}")

        if not source.is_dir():
            raise ValueError(f"Source path is not a directory: {local_path}")

        if not os.access(source, os.R_OK):
            raise ValueError(f"Source path is not readable: {local_path}")

        try:
            shutil.copytree(source, workspace_path, symlinks=False)
            logger.info(f"Copied local path {source} to {workspace_path}")
        except shutil.Error as e:
            logger.error(f"Failed to copy directory: {e}")
            raise RuntimeError(f"Failed to copy directory: {e}") from e
        except PermissionError as e:
            logger.error(f"Permission denied copying {source}: {e}")
            raise RuntimeError(f"Permission denied: {e}") from e

        # Initialize git if not already a git repo
        if not (workspace_path / ".git").exists():
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=workspace_path,
                    check=True,
                    capture_output=True,
                    timeout=30,
                    text=True,
                )
                logger.info(f"Initialized git repository in {workspace_path}")
            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                FileNotFoundError,
            ) as e:
                logger.warning(f"Failed to initialize git repo: {e}")
                # Don't fail the whole operation if git init fails
                pass

    def _is_safe_path(self, path: Path) -> bool:
        """Check if path is safe to access.

        Security policy:
        - Must be under user's home directory
        - Must be a real path (resolve symlinks)
        - Cannot contain sensitive directories
        - No path traversal attempts

        Args:
            path: Path to validate (must be absolute)

        Returns:
            True if path is safe to access
        """
        try:
            # Resolve symlinks and normalize (strict=True requires path to exist)
            resolved_path = path.resolve(strict=True)
            home_dir = Path.home().resolve()

            # Check if path is under home directory
            resolved_path.relative_to(home_dir)

            # Blacklist sensitive directories
            sensitive_dirs = {".ssh", ".aws", ".gnupg", ".config"}
            for part in resolved_path.parts:
                if part in sensitive_dirs:
                    return False

            return True
        except (ValueError, RuntimeError, OSError):
            # Path is not under home directory, doesn't exist, or other error
            return False

    def _init_from_upload(self, workspace_path: Path, upload_filename: str) -> None:
        """Extract from uploaded archive."""
        # TODO: Implement in Phase 4 (upload endpoint)
        workspace_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=workspace_path, check=True, capture_output=True)
