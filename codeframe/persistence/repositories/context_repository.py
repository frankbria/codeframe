"""Repository for Context Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import logging

import aiosqlite

from codeframe.core.models import (
    ProjectStatus,
    ProjectPhase,
    SourceType,
    Project,
    Task,
    TaskStatus,
    AgentMaturity,
    Issue,
    IssueWithTaskCount,
    CallType,
)
from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Audit verbosity configuration
AUDIT_VERBOSITY = os.getenv("AUDIT_VERBOSITY", "low").lower()
if AUDIT_VERBOSITY not in ("low", "high"):
    logger.warning(f"Invalid AUDIT_VERBOSITY='{AUDIT_VERBOSITY}', defaulting to 'low'")
    AUDIT_VERBOSITY = "low"


class ContextRepository(BaseRepository):
    """Repository for context repository operations."""


    def create_context_item(
        self, project_id: int, agent_id: str, item_type: str, content: str
    ) -> str:
        """Create a new context item with auto-calculated importance score.

        Auto-calculates importance score using hybrid exponential decay algorithm:
        - Type weight (40%): Based on item_type
        - Age decay (40%): Exponential decay (new items get 1.0)
        - Access boost (20%): Log-normalized frequency (new items get 0.0)

        Args:
            project_id: Project ID this context belongs to
            agent_id: Agent ID that created this context
            item_type: Type of context (TASK, CODE, ERROR, TEST_RESULT, PRD_SECTION)
            content: The actual context content

        Returns:
            Created context item ID (UUID string)
        """
        import uuid
        from datetime import datetime, UTC
        from codeframe.lib.importance_scorer import calculate_importance_score, assign_tier

        # Auto-calculate importance score for new item
        created_at = datetime.now(UTC)
        importance_score = calculate_importance_score(
            item_type=item_type,
            created_at=created_at,
            access_count=0,  # New item has no accesses yet
            last_accessed=created_at,
        )

        # Auto-assign tier based on importance score (T040)
        # Convert to lowercase for current_tier column
        tier = assign_tier(importance_score).lower()

        # Generate UUID for id (actual schema uses TEXT PRIMARY KEY)
        item_id = str(uuid.uuid4())

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO context_items (
                id, project_id, agent_id, item_type, content, importance_score,
                current_tier, created_at, last_accessed, access_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                project_id,
                agent_id,
                item_type,
                content,
                importance_score,
                tier,
                created_at.isoformat(),
                created_at.isoformat(),
                0,
            ),
        )
        self.conn.commit()
        return item_id



    def get_context_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a context item by ID.

        Args:
            item_id: Context item ID (UUID string)

        Returns:
            Context item dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM context_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        return dict(row) if row else None



    def list_context_items(
        self,
        project_id: int,
        agent_id: str,
        tier: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List context items for an agent on a project, optionally filtered by tier.

        Args:
            project_id: Project ID to filter by
            agent_id: Agent ID to filter by
            tier: Optional tier filter (HOT, WARM, COLD)
            limit: Maximum number of items to return
            offset: Number of items to skip

        Returns:
            List of context item dictionaries
        """
        cursor = self.conn.cursor()

        if tier:
            # Convert tier to lowercase for current_tier column
            tier_lower = tier.lower()
            query = """
                SELECT * FROM context_items
                WHERE project_id = ? AND agent_id = ? AND current_tier = ?
                ORDER BY importance_score DESC, last_accessed DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, (project_id, agent_id, tier_lower, limit, offset))
        else:
            query = """
                SELECT * FROM context_items
                WHERE project_id = ? AND agent_id = ?
                ORDER BY importance_score DESC, last_accessed DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, (project_id, agent_id, limit, offset))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]



    def update_context_item_tier(self, item_id: str, tier: str, importance_score: float) -> None:
        """Update a context item's tier and importance score.

        Args:
            item_id: Context item ID (UUID string)
            tier: New tier (HOT, WARM, COLD)
            importance_score: Updated importance score
        """
        # Convert tier to lowercase for current_tier column
        tier_lower = tier.lower()

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE context_items
            SET current_tier = ?, importance_score = ?
            WHERE id = ?
            """,
            (tier_lower, importance_score, item_id),
        )
        self.conn.commit()



    def delete_context_item(self, item_id: str) -> None:
        """Delete a context item.

        Args:
            item_id: Context item ID to delete (UUID string)
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM context_items WHERE id = ?", (item_id,))
        self.conn.commit()



    def update_context_item_access(self, item_id: str) -> None:
        """Update last_accessed timestamp and increment access_count.

        Args:
            item_id: Context item ID (UUID string)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE context_items
            SET last_accessed = CURRENT_TIMESTAMP,
                access_count = access_count + 1
            WHERE id = ?
            """,
            (item_id,),
        )
        self.conn.commit()



    def archive_cold_items(self, project_id: int, agent_id: str) -> int:
        """Archive (delete) all COLD tier items for an agent (T053).

        This method is called during flash save to reduce memory footprint.
        COLD tier items are fully archived in the checkpoint before deletion.

        Args:
            project_id: Project ID the agent is working on
            agent_id: Agent ID to archive COLD items for

        Returns:
            int: Number of items archived (deleted)

        Example:
            >>> db.archive_cold_items(123, "backend-worker-001")
            15  # 15 COLD items deleted
        """
        cursor = self.conn.cursor()

        # Delete all COLD tier items for this agent on this project
        cursor.execute(
            """DELETE FROM context_items
               WHERE project_id = ?
                 AND agent_id = ?
                 AND current_tier = 'cold'""",
            (project_id, agent_id),
        )

        deleted_count = cursor.rowcount
        self.conn.commit()

        return deleted_count

