"""Checkpoint and recovery system for CodeFrame projects (Sprint 10 Phase 4).

Provides checkpoint creation, listing, and restoration capabilities to save and
restore complete project state including git commits, database backups, and
context snapshots.
"""

import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from codeframe.core.models import Checkpoint, CheckpointMetadata
from codeframe.persistence.database import Database

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages project checkpoints for state preservation and recovery.

    Checkpoints capture complete project state:
    - Git commit (code state)
    - Database backup (tasks, context, metrics)
    - Context snapshot (agent context items as JSON)
    - Metadata (progress, costs, active agents)

    Usage:
        >>> mgr = CheckpointManager(db=db, project_root=Path("."), project_id=1)
        >>> checkpoint = mgr.create_checkpoint("Before refactor", "Safety checkpoint")
        >>> # ... make changes ...
        >>> mgr.restore_checkpoint(checkpoint.id, confirm=True)
    """

    def __init__(self, db: Database, project_root: Path, project_id: int):
        """Initialize checkpoint manager.

        Args:
            db: Database instance for state persistence
            project_root: Path to project root (must be git repository)
            project_id: Project ID in database
        """
        self.db = db
        self.project_root = Path(project_root)
        self.project_id = project_id
        self.checkpoints_dir = self.project_root / ".codeframe" / "checkpoints"

        # Ensure checkpoints directory exists
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def create_checkpoint(
        self, name: str, description: Optional[str] = None, trigger: str = "manual"
    ) -> Checkpoint:
        """Create checkpoint with git commit, DB backup, and context snapshot.

        Steps:
        1. Create git commit with message "Checkpoint: {name}"
        2. Backup SQLite database to .codeframe/checkpoints/checkpoint-{id}-db.sqlite
        3. Save context items to .codeframe/checkpoints/checkpoint-{id}-context.json
        4. Generate metadata (tasks_completed, agents_active, etc.)
        5. Save checkpoint to database

        Args:
            name: Human-readable checkpoint name (max 100 chars)
            description: Optional detailed description (max 500 chars)
            trigger: Trigger type (manual, auto, phase_transition, pause)

        Returns:
            Created Checkpoint instance with all paths populated

        Raises:
            RuntimeError: If git operations fail
            IOError: If file operations fail
            ValueError: If invalid trigger type provided
        """
        # Validate trigger type
        valid_triggers = {"manual", "auto", "phase_transition", "pause"}
        if trigger not in valid_triggers:
            raise ValueError(
                f"Invalid trigger type '{trigger}'. "
                f"Valid triggers: {', '.join(sorted(valid_triggers))}"
            )

        logger.info(f"Creating checkpoint: {name}")

        # Step 1: Create git commit
        git_commit = self._create_git_commit(name)
        logger.debug(f"Created git commit: {git_commit}")

        # Generate metadata first (needed for database insert)
        metadata = self._generate_metadata()

        # Save checkpoint to database to get ID
        checkpoint_id = self.db.save_checkpoint(
            project_id=self.project_id,
            name=name,
            description=description,
            trigger=trigger,
            git_commit=git_commit,
            database_backup_path="",  # Will update after creating files
            context_snapshot_path="",
            metadata=metadata,
        )

        # Step 2: Backup database
        db_backup_path = self._snapshot_database(checkpoint_id)
        logger.debug(f"Created database backup: {db_backup_path}")

        # Step 3: Save context snapshot
        context_snapshot_path = self._snapshot_context(checkpoint_id)
        logger.debug(f"Created context snapshot: {context_snapshot_path}")

        # Update checkpoint with file paths
        cursor = self.db.conn.cursor()  # type: ignore[union-attr]
        cursor.execute(
            """
            UPDATE checkpoints
            SET database_backup_path = ?, context_snapshot_path = ?
            WHERE id = ?
            """,
            (str(db_backup_path), str(context_snapshot_path), checkpoint_id),
        )
        self.db.conn.commit()  # type: ignore[union-attr]

        # Create and return Checkpoint object
        checkpoint = Checkpoint(
            id=checkpoint_id,
            project_id=self.project_id,
            name=name,
            description=description,
            trigger=trigger,
            git_commit=git_commit,
            database_backup_path=str(db_backup_path),
            context_snapshot_path=str(context_snapshot_path),
            metadata=metadata,
            created_at=datetime.now(timezone.utc),
        )

        logger.info(f"Checkpoint created successfully: ID={checkpoint_id}, commit={git_commit[:7]}")
        return checkpoint

    def list_checkpoints(self) -> List[Checkpoint]:
        """List all checkpoints for project, sorted by created_at DESC.

        Returns:
            List of Checkpoint instances, most recent first
        """
        checkpoints = self.db.get_checkpoints(self.project_id)
        logger.debug(f"Listed {len(checkpoints)} checkpoints for project {self.project_id}")
        return checkpoints

    def restore_checkpoint(self, checkpoint_id: int, confirm: bool = False) -> Dict[str, Any]:
        """Restore project to checkpoint state.

        Steps:
        1. Validate checkpoint exists and files are intact
        2. Show git diff if confirm=False
        3. Checkout git commit
        4. Restore database from backup
        5. Restore context items
        6. Verify restoration succeeded

        Args:
            checkpoint_id: ID of checkpoint to restore
            confirm: If False, only show diff. If True, perform restore.

        Returns:
            Dictionary with restore results:
            - success: bool (only if confirm=True)
            - checkpoint_name: str
            - diff: str (only if confirm=False)
            - files_restored: List[str] (only if confirm=True)

        Raises:
            ValueError: If checkpoint not found
            FileNotFoundError: If backup files are missing
            RuntimeError: If restoration fails
        """
        # Get checkpoint from database
        checkpoint = self.db.get_checkpoint_by_id(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        logger.info(f"Restoring checkpoint: {checkpoint.name} (ID={checkpoint_id})")

        # Validate checkpoint files exist
        if not self._validate_checkpoint(checkpoint):
            raise FileNotFoundError(
                f"Checkpoint files missing: "
                f"DB={checkpoint.database_backup_path}, "
                f"Context={checkpoint.context_snapshot_path}"
            )

        # If not confirmed, just show diff
        if not confirm:
            diff = self._show_diff(checkpoint.git_commit)
            return {"checkpoint_name": checkpoint.name, "diff": diff}

        # Perform restoration
        try:
            # Step 1: Restore database FIRST (before git checkout)
            # This ensures .codeframe files exist when git reverts the working directory
            self._restore_database(checkpoint.database_backup_path)
            logger.debug("Restored database from backup")

            # Step 2: Restore context items
            restored_items = self._restore_context(checkpoint.context_snapshot_path)
            logger.debug(f"Restored {restored_items} context items")

            # Step 3: Checkout git commit LAST (after restoring database/context)
            # This prevents git from deleting the .codeframe directory
            self._restore_git_commit(checkpoint.git_commit)
            logger.debug(f"Restored git commit: {checkpoint.git_commit}")

            logger.info(f"Checkpoint restored successfully: {checkpoint.name}")

            return {
                "success": True,
                "checkpoint_name": checkpoint.name,
                "git_commit": checkpoint.git_commit,
                "items_restored": restored_items,
            }

        except Exception as e:
            logger.error(f"Failed to restore checkpoint: {e}")
            raise RuntimeError(f"Checkpoint restoration failed: {e}") from e

    def _create_git_commit(self, checkpoint_name: str) -> str:
        """Create git commit for checkpoint.

        Args:
            checkpoint_name: Name for commit message

        Returns:
            Git commit SHA (full 40 characters)

        Raises:
            RuntimeError: If git operations fail
        """
        try:
            # Stage all changes (including untracked files)
            subprocess.run(
                ["git", "add", "-A"], cwd=self.project_root, check=True, capture_output=True
            )

            # Create commit
            commit_message = f"Checkpoint: {checkpoint_name}"
            subprocess.run(
                ["git", "commit", "-m", commit_message, "--allow-empty"],
                cwd=self.project_root,
                check=True,
                capture_output=True,
            )

            # Get commit SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_root,
                check=True,
                capture_output=True,
                text=True,
            )

            commit_sha = result.stdout.strip()
            return commit_sha

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git commit failed: {e.stderr}") from e

    def _snapshot_database(self, checkpoint_id: int) -> Path:
        """Copy state.db to checkpoint-{id}-db.sqlite.

        Args:
            checkpoint_id: Checkpoint ID for filename

        Returns:
            Path to database backup file

        Raises:
            IOError: If file copy fails
        """
        backup_filename = f"checkpoint-{checkpoint_id:03d}-db.sqlite"
        backup_path = self.checkpoints_dir / backup_filename

        # Close any open transactions before copying
        self.db.conn.commit()  # type: ignore[union-attr]

        # Copy database file
        shutil.copy2(self.db.db_path, backup_path)

        return backup_path

    def _snapshot_context(self, checkpoint_id: int) -> Path:
        """Export context items to JSON.

        Args:
            checkpoint_id: Checkpoint ID for filename

        Returns:
            Path to context snapshot JSON file

        Raises:
            IOError: If file write fails
        """
        snapshot_filename = f"checkpoint-{checkpoint_id:03d}-context.json"
        snapshot_path = self.checkpoints_dir / snapshot_filename

        # Get all context items for this project
        cursor = self.db.conn.cursor()  # type: ignore[union-attr]
        cursor.execute(
            """
            SELECT
                id, agent_id, project_id, item_type, content,
                importance_score, current_tier, access_count, created_at, last_accessed
            FROM context_items
            WHERE project_id = ?
            ORDER BY importance_score DESC
            """,
            (self.project_id,),
        )

        context_items = []
        for row in cursor.fetchall():
            context_items.append(
                {
                    "id": row["id"],
                    "agent_id": row["agent_id"],
                    "project_id": row["project_id"],
                    "item_type": row["item_type"],
                    "content": row["content"],
                    "importance_score": row["importance_score"],
                    "tier": row["current_tier"],
                    "access_count": row["access_count"],
                    "created_at": row["created_at"],
                    "last_accessed": row["last_accessed"],
                }
            )

        # Create snapshot structure
        snapshot_data = {
            "checkpoint_id": checkpoint_id,
            "project_id": self.project_id,
            "export_date": datetime.now(timezone.utc).isoformat(),
            "context_items": context_items,
        }

        # Write to file
        with open(snapshot_path, "w") as f:
            json.dump(snapshot_data, f, indent=2)

        return snapshot_path

    def _generate_metadata(self) -> CheckpointMetadata:
        """Generate checkpoint metadata for quick inspection.

        Returns:
            CheckpointMetadata with current project state
        """
        cursor = self.db.conn.cursor()  # type: ignore[union-attr]

        # Get project phase
        cursor.execute("SELECT phase FROM projects WHERE id = ?", (self.project_id,))
        row = cursor.fetchone()
        phase = row["phase"] if row else "unknown"

        # Count tasks
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ?", (self.project_id,))
        tasks_total = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM tasks
            WHERE project_id = ? AND status = 'completed'
            """,
            (self.project_id,),
        )
        tasks_completed = cursor.fetchone()[0]

        # Get last completed task
        cursor.execute(
            """
            SELECT title FROM tasks
            WHERE project_id = ? AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            (self.project_id,),
        )
        row = cursor.fetchone()
        last_task_completed = row["title"] if row else None

        # Get active agents
        cursor.execute(
            """
            SELECT DISTINCT agent_id FROM context_items
            WHERE project_id = ?
            """,
            (self.project_id,),
        )
        agents_active = [row["agent_id"] for row in cursor.fetchall()]

        # Count context items
        cursor.execute(
            "SELECT COUNT(*) FROM context_items WHERE project_id = ?", (self.project_id,)
        )
        context_items_count = cursor.fetchone()[0]

        # Calculate total cost (if token_usage table exists)
        try:
            cursor.execute(
                """
                SELECT SUM(estimated_cost_usd) FROM token_usage
                WHERE project_id = ?
                """,
                (self.project_id,),
            )
            row = cursor.fetchone()
            total_cost_usd = row[0] if row and row[0] else 0.0
        except Exception:
            total_cost_usd = 0.0

        return CheckpointMetadata(
            project_id=self.project_id,
            phase=phase,
            tasks_completed=tasks_completed,
            tasks_total=tasks_total,
            agents_active=agents_active,
            last_task_completed=last_task_completed,
            context_items_count=context_items_count,
            total_cost_usd=total_cost_usd,
        )

    def _validate_path_safety(self, file_path: Path) -> bool:
        """Validate that a path is within the checkpoints directory.

        Prevents path traversal attacks by ensuring file paths resolve
        to locations within the expected checkpoints directory.

        Args:
            file_path: Path to validate

        Returns:
            True if path is safe (within checkpoints_dir), False otherwise
        """
        try:
            # Resolve both paths to absolute, canonical forms
            resolved_path = file_path.resolve()
            checkpoints_base = self.checkpoints_dir.resolve()

            # Check if resolved path is relative to checkpoints directory
            return resolved_path.is_relative_to(checkpoints_base)
        except (ValueError, RuntimeError):
            # is_relative_to() raises ValueError if paths are on different drives
            return False

    def _validate_checkpoint(self, checkpoint: Checkpoint) -> bool:
        """Check if all checkpoint files exist and paths are safe.

        Args:
            checkpoint: Checkpoint to validate

        Returns:
            True if all files exist and paths are safe, False otherwise

        Raises:
            ValueError: If paths are outside checkpoints directory (path traversal)
        """
        db_path = Path(checkpoint.database_backup_path)
        context_path = Path(checkpoint.context_snapshot_path)

        # Validate paths are within checkpoints directory (prevent traversal)
        if not self._validate_path_safety(db_path):
            raise ValueError(f"Database backup path outside checkpoints directory: {db_path}")
        if not self._validate_path_safety(context_path):
            raise ValueError(f"Context snapshot path outside checkpoints directory: {context_path}")

        db_exists = db_path.exists()
        context_exists = context_path.exists()

        if not db_exists:
            logger.warning(f"Database backup not found: {db_path}")
        if not context_exists:
            logger.warning(f"Context snapshot not found: {context_path}")

        return db_exists and context_exists

    def _show_diff(self, git_commit: str) -> str:
        """Return git diff between HEAD and checkpoint commit.

        Args:
            git_commit: Git commit SHA to compare against

        Returns:
            Git diff output as string
        """
        try:
            result = subprocess.run(
                ["git", "diff", git_commit, "HEAD"],
                cwd=self.project_root,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to generate diff: {e.stderr}")
            return f"Error generating diff: {e.stderr}"

    def _restore_git_commit(self, git_commit: str) -> None:
        """Checkout git commit (hard reset).

        Args:
            git_commit: Git commit SHA to checkout

        Raises:
            RuntimeError: If git checkout fails
        """
        try:
            # Use git checkout instead of reset to avoid deleting untracked files
            # This preserves .codeframe/ directory which isn't tracked by git
            subprocess.run(
                ["git", "checkout", git_commit, "--force"],
                cwd=self.project_root,
                check=True,
                capture_output=True,
            )

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git checkout failed: {e.stderr}") from e

    def _restore_database(self, backup_path: str) -> None:
        """Restore database from backup file.

        Args:
            backup_path: Path to database backup

        Raises:
            FileNotFoundError: If backup file doesn't exist
            IOError: If file copy fails
        """
        backup = Path(backup_path)
        if not backup.exists():
            raise FileNotFoundError(f"Database backup not found: {backup_path}")

        # Close current database connection
        self.db.conn.close()  # type: ignore[union-attr]

        # Replace database file with backup
        shutil.copy2(backup, self.db.db_path)

        # Reconnect to restored database
        self.db.conn = None
        self.db.initialize()

    def _restore_context(self, snapshot_path: str) -> int:
        """Restore context items from JSON snapshot.

        Args:
            snapshot_path: Path to context snapshot JSON

        Returns:
            Number of context items restored

        Raises:
            FileNotFoundError: If snapshot file doesn't exist
            IOError: If file read fails
        """
        snapshot = Path(snapshot_path)
        if not snapshot.exists():
            raise FileNotFoundError(f"Context snapshot not found: {snapshot_path}")

        # Load snapshot data
        with open(snapshot) as f:
            snapshot_data = json.load(f)

        # Delete existing context items for this project
        cursor = self.db.conn.cursor()  # type: ignore[union-attr]
        cursor.execute("DELETE FROM context_items WHERE project_id = ?", (self.project_id,))

        # Restore context items from snapshot with original IDs
        context_items = snapshot_data.get("context_items", [])
        max_id = 0
        for item in context_items:
            item_id = item.get("id")
            if item_id and item_id > max_id:
                max_id = item_id

            cursor.execute(
                """
                INSERT INTO context_items
                (id, agent_id, project_id, item_type, content, importance_score,
                 current_tier, access_count, created_at, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    item["agent_id"],
                    item["project_id"],
                    item["item_type"],
                    item["content"],
                    item["importance_score"],
                    item["tier"],
                    item.get("access_count", 0),
                    item["created_at"],
                    item["last_accessed"],
                ),
            )

        # Update SQLite sequence to prevent future PK collisions
        if max_id > 0:
            cursor.execute(
                "UPDATE sqlite_sequence SET seq = ? WHERE name = 'context_items'", (max_id,)
            )
            # If no row exists for context_items in sqlite_sequence, insert it
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO sqlite_sequence (name, seq) VALUES ('context_items', ?)", (max_id,)
                )

        self.db.conn.commit()  # type: ignore[union-attr]

        return len(context_items)
