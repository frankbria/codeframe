"""Repository for Checkpoint Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import logging


from codeframe.persistence.repositories.base import BaseRepository

if TYPE_CHECKING:
    from codeframe.core.models import Checkpoint, CheckpointMetadata

logger = logging.getLogger(__name__)


class CheckpointRepository(BaseRepository):
    """Repository for checkpoint repository operations."""


    def create_checkpoint(
        self,
        agent_id: str,
        checkpoint_data: str,
        items_count: int,
        items_archived: int,
        hot_items_retained: int,
        token_count: int,
    ) -> int:
        """Create a flash save checkpoint.

        Args:
            agent_id: Agent ID creating the checkpoint
            checkpoint_data: JSON serialized context state
            items_count: Total items before flash save
            items_archived: Number of COLD items archived
            hot_items_retained: Number of HOT items kept
            token_count: Total tokens before flash save

        Returns:
            Created checkpoint ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO context_checkpoints (
                agent_id, checkpoint_data, items_count, items_archived,
                hot_items_retained, token_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                checkpoint_data,
                items_count,
                items_archived,
                hot_items_retained,
                token_count,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid



    def list_checkpoints(self, agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """List checkpoints for an agent, most recent first.

        Args:
            agent_id: Agent ID to filter by
            limit: Maximum number of checkpoints to return

        Returns:
            List of checkpoint dictionaries ordered by created_at DESC
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM context_checkpoints
            WHERE agent_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (agent_id, limit),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]



    def get_checkpoint(self, checkpoint_id: int) -> Optional[Dict[str, Any]]:
        """Get a checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Checkpoint dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM context_checkpoints WHERE id = ?", (checkpoint_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    # Sprint 9: MVP Completion Database Methods



    def save_checkpoint(
        self,
        project_id: int,
        name: str,
        description: Optional[str],
        trigger: str,
        git_commit: str,
        database_backup_path: str,
        context_snapshot_path: str,
        metadata: "CheckpointMetadata",
    ) -> int:
        """Save a checkpoint to database.

        Args:
            project_id: Project ID
            name: Checkpoint name (max 100 chars)
            description: Optional description (max 500 chars)
            trigger: Trigger type (manual, auto, phase_transition, pause)
            git_commit: Git commit SHA
            database_backup_path: Path to database backup file
            context_snapshot_path: Path to context snapshot JSON
            metadata: CheckpointMetadata object

        Returns:
            Created checkpoint ID
        """

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO checkpoints (
                project_id, name, description, trigger, git_commit,
                database_backup_path, context_snapshot_path, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                name,
                description,
                trigger,
                git_commit,
                database_backup_path,
                context_snapshot_path,
                json.dumps(metadata.model_dump()),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_checkpoints(self, project_id: int) -> List["Checkpoint"]:
        """Get all checkpoints for a project, sorted by created_at DESC.

        Args:
            project_id: Project ID

        Returns:
            List of Checkpoint objects, most recent first
        """
        from codeframe.core.models import Checkpoint, CheckpointMetadata

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                id, project_id, name, description, trigger, git_commit,
                database_backup_path, context_snapshot_path, metadata, created_at
            FROM checkpoints
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,),
        )

        checkpoints = []
        for row in cursor.fetchall():
            # Parse metadata JSON
            metadata_dict = json.loads(row["metadata"]) if row["metadata"] else {}
            metadata = CheckpointMetadata(**metadata_dict)

            checkpoint = Checkpoint(
                id=row["id"],
                project_id=row["project_id"],
                name=row["name"],
                description=row["description"],
                trigger=row["trigger"],
                git_commit=row["git_commit"],
                database_backup_path=row["database_backup_path"],
                context_snapshot_path=row["context_snapshot_path"],
                metadata=metadata,
                created_at=(
                    datetime.fromisoformat(row["created_at"])
                    if row["created_at"]
                    else datetime.now(timezone.utc)
                ),
            )
            checkpoints.append(checkpoint)

        return checkpoints



    def get_checkpoint_by_id(self, checkpoint_id: int) -> Optional["Checkpoint"]:
        """Get a checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Checkpoint object or None if not found
        """
        from codeframe.core.models import Checkpoint, CheckpointMetadata

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                id, project_id, name, description, trigger, git_commit,
                database_backup_path, context_snapshot_path, metadata, created_at
            FROM checkpoints
            WHERE id = ?
            """,
            (checkpoint_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        # Parse metadata JSON
        metadata_dict = json.loads(row["metadata"]) if row["metadata"] else {}
        metadata = CheckpointMetadata(**metadata_dict)

        return Checkpoint(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            description=row["description"],
            trigger=row["trigger"],
            git_commit=row["git_commit"],
            database_backup_path=row["database_backup_path"],
            context_snapshot_path=row["context_snapshot_path"],
            metadata=metadata,
            created_at=(
                datetime.fromisoformat(row["created_at"])
                if row["created_at"]
                else datetime.now(timezone.utc)
            ),
        )



    def delete_checkpoint(self, checkpoint_id: int) -> None:
        """Delete a checkpoint from the database.

        Args:
            checkpoint_id: Checkpoint ID to delete
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,))
        self.conn.commit()

    # ============================================================================
    # Token Usage and Metrics Methods (Sprint 10 Phase 5)
    # ============================================================================

