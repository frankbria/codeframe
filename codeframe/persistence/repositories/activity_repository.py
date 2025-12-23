"""Repository for Activity Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import os
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging


from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Audit verbosity configuration
AUDIT_VERBOSITY = os.getenv("AUDIT_VERBOSITY", "low").lower()
if AUDIT_VERBOSITY not in ("low", "high"):
    logger.warning(f"Invalid AUDIT_VERBOSITY='{AUDIT_VERBOSITY}', defaulting to 'low'")
    AUDIT_VERBOSITY = "low"


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
            WHERE project_id = ? AND category = 'prd' AND key = 'prd_content'
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

        # Convert SQLite timestamps to RFC 3339 format
        def ensure_rfc3339(timestamp_str: str) -> str:
            """Ensure timestamp is in RFC 3339 format with timezone."""
            if not timestamp_str:
                return timestamp_str
            # If already has 'Z' or timezone, return as-is
            if "Z" in timestamp_str or "+" in timestamp_str:
                return timestamp_str
            # Parse and add Z suffix for UTC
            try:
                # SQLite format: "2025-10-17 22:01:56"
                dt = datetime.fromisoformat(timestamp_str)
                return dt.isoformat() + "Z"
            except ValueError:
                return timestamp_str

        # Determine generated_at
        generated_at = (
            generated_row["value"] if generated_row else ensure_rfc3339(prd_row["created_at"])
        )

        # Determine updated_at - use generated_at if updated_at is same as created_at
        updated_at = ensure_rfc3339(
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

    # Issues/Tasks methods (cf-26)
