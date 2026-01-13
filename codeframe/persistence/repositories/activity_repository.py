"""Repository for Activity Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

from typing import List, Optional, Dict, Any
import logging


from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ActivityRepository(BaseRepository):
    """Repository for activity repository operations."""


    def get_recent_activity(self, project_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent activity/changelog entries for a project.

        Args:
            project_id: Project ID to filter activity
            limit: Maximum number of activity items to return

        Returns:
            List of activity dictionaries formatted for frontend
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                timestamp,
                agent_id,
                action,
                task_id,
                details
            FROM changelog
            WHERE project_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (project_id, limit),
        )

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        # Format for frontend
        activity_items = []
        for row in rows:
            activity_dict = dict(zip(columns, row))

            # Map database fields to frontend expected format
            activity_items.append(
                {
                    "timestamp": activity_dict["timestamp"],
                    "type": activity_dict["action"],
                    "agent": activity_dict["agent_id"] or "system",
                    "message": activity_dict.get("details") or activity_dict["action"],
                }
            )

        return activity_items

    # Context Management Methods (007-context-management)


    def get_prd(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Get PRD for a project.

        Args:
            project_id: Project ID

        Returns:
            Dictionary with prd_content, generated_at, updated_at or None if not found
        """

        cursor = self.conn.cursor()

        # Get PRD content
        cursor.execute(
            """
            SELECT value, created_at, updated_at
            FROM memory
            WHERE project_id = ? AND category = 'prd' AND key = 'content'
            """,
            (project_id,),
        )
        prd_row = cursor.fetchone()

        if not prd_row:
            return None

        # Get generated_at timestamp
        cursor.execute(
            """
            SELECT value
            FROM memory
            WHERE project_id = ? AND category = 'prd' AND key = 'generated_at'
            """,
            (project_id,),
        )
        generated_row = cursor.fetchone()

        # Determine generated_at
        generated_at = (
            generated_row["value"] if generated_row else self._ensure_rfc3339(prd_row["created_at"])
        )

        # Determine updated_at - use generated_at if updated_at is same as created_at
        updated_at = self._ensure_rfc3339(
            prd_row["updated_at"] if prd_row["updated_at"] else prd_row["created_at"]
        )

        # If updated_at == created_at (never been updated), use generated_at for both
        if prd_row["updated_at"] == prd_row["created_at"] and generated_row:
            updated_at = generated_at

        return {
            "prd_content": prd_row["value"],
            "generated_at": generated_at,
            "updated_at": updated_at,
        }

    def delete_prd(self, project_id: int) -> bool:
        """Delete PRD content for a project.

        Removes all PRD-related entries from the memory table.

        Args:
            project_id: Project ID

        Returns:
            True if PRD existed and was deleted, False if no PRD existed
        """
        cursor = self.conn.cursor()

        # Check if PRD exists first
        cursor.execute(
            "SELECT COUNT(*) FROM memory WHERE project_id = ? AND category = 'prd'",
            (project_id,),
        )
        count = cursor.fetchone()[0]

        if count == 0:
            return False

        # Delete all PRD entries
        cursor.execute(
            "DELETE FROM memory WHERE project_id = ? AND category = 'prd'",
            (project_id,),
        )
        self.conn.commit()

        logger.info(f"Deleted PRD for project {project_id}")
        return True

    def delete_discovery_answers(self, project_id: int) -> int:
        """Delete all discovery answers for a project.

        Removes all discovery_answers entries from the memory table.

        Args:
            project_id: Project ID

        Returns:
            Number of answers deleted
        """
        cursor = self.conn.cursor()

        # Count existing answers
        cursor.execute(
            "SELECT COUNT(*) FROM memory WHERE project_id = ? AND category = 'discovery_answers'",
            (project_id,),
        )
        count = cursor.fetchone()[0]

        if count == 0:
            return 0

        # Delete all discovery answers
        cursor.execute(
            "DELETE FROM memory WHERE project_id = ? AND category = 'discovery_answers'",
            (project_id,),
        )
        self.conn.commit()

        logger.info(f"Deleted {count} discovery answers for project {project_id}")
        return count

    # Issues/Tasks methods (cf-26)
