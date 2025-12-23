"""Repository for Blocker Repository operations.

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


class BlockerRepository(BaseRepository):
    """Repository for blocker repository operations."""


    def create_blocker(
        self,
        agent_id: str,
        project_id: int,
        task_id: Optional[int],
        blocker_type: str,
        question: str,
    ) -> int:
        """Create a new blocker with rate limiting.

        Rate limit: 10 blockers per minute per agent (T063).

        Args:
            agent_id: ID of the agent creating the blocker
            project_id: ID of the project this blocker belongs to
            task_id: Associated task ID (nullable for agent-level blockers)
            blocker_type: Type of blocker ('SYNC' or 'ASYNC')
            question: Question for the user (max 2000 chars)

        Returns:
            Blocker ID of the created blocker

        Raises:
            ValueError: If agent exceeds rate limit (10 blockers/minute)
        """
        cursor = self.conn.cursor()

        # Check rate limit: 10 blockers per minute per agent
        cursor.execute(
            """SELECT COUNT(*) as count
               FROM blockers
               WHERE agent_id = ?
                 AND datetime(created_at) > datetime('now', '-60 seconds')""",
            (agent_id,),
        )
        row = cursor.fetchone()
        recent_blocker_count = row["count"]

        if recent_blocker_count >= 10:
            raise ValueError(
                f"Rate limit exceeded: Agent {agent_id} has created {recent_blocker_count} "
                f"blockers in the last minute (limit: 10/minute)"
            )

        # Create the blocker
        cursor.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status)
               VALUES (?, ?, ?, ?, ?, 'PENDING')""",
            (agent_id, project_id, task_id, blocker_type, question),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_blocker(self, blocker_id: int) -> Optional[Dict[str, Any]]:
        """Get blocker details by ID.

        Args:
            blocker_id: ID of the blocker

        Returns:
            Blocker dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM blockers WHERE id = ?", (blocker_id,))
        row = cursor.fetchone()
        return dict(row) if row else None



    def resolve_blocker(self, blocker_id: int, answer: str) -> bool:
        """Resolve a blocker with user's answer.

        Args:
            blocker_id: ID of the blocker to resolve
            answer: User's answer (max 5000 chars)

        Returns:
            True if blocker was resolved, False if already resolved or not found
        """
        from datetime import UTC

        cursor = self.conn.cursor()
        resolved_at = datetime.now(UTC).isoformat()
        cursor.execute(
            """UPDATE blockers
               SET answer = ?, status = 'RESOLVED', resolved_at = ?
               WHERE id = ? AND status = 'PENDING'""",
            (answer, resolved_at, blocker_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0



    def list_blockers(self, project_id: int, status: Optional[str] = None) -> Dict[str, Any]:
        """List blockers with agent/task info joined.

        Args:
            project_id: Filter by project ID
            status: Optional status filter ('PENDING', 'RESOLVED', 'EXPIRED')

        Returns:
            Dictionary with blockers list and counts:
            - blockers: List of blocker dictionaries with enriched data
            - total: Total number of blockers
            - pending_count: Number of pending blockers
            - sync_count: Number of SYNC blockers
            - async_count: Number of ASYNC blockers
        """
        cursor = self.conn.cursor()

        # Build query with optional status filter
        query = """
            SELECT
                b.*,
                a.type as agent_name,
                t.title as task_title,
                (julianday('now') - julianday(b.created_at)) * 86400000 as time_waiting_ms
            FROM blockers b
            LEFT JOIN agents a ON b.agent_id = a.id
            LEFT JOIN tasks t ON b.task_id = t.id
            WHERE b.project_id = ?
        """
        params = [project_id]

        if status:
            query += " AND b.status = ?"
            params.append(status)

        query += " ORDER BY b.created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        blockers = [dict(row) for row in rows]
        pending_count = sum(1 for b in blockers if b.get("status") == "PENDING")
        sync_count = sum(1 for b in blockers if b.get("blocker_type") == "SYNC")
        async_count = sum(1 for b in blockers if b.get("blocker_type") == "ASYNC")

        return {
            "blockers": blockers,
            "total": len(blockers),
            "pending_count": pending_count,
            "sync_count": sync_count,
            "async_count": async_count,
        }



    def get_pending_blocker(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get oldest pending blocker for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            Blocker dictionary or None if no pending blockers
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM blockers
               WHERE agent_id = ? AND status = 'PENDING'
               ORDER BY created_at ASC LIMIT 1""",
            (agent_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None



    def expire_stale_blockers(self, hours: int = 24) -> List[int]:
        """Expire blockers pending longer than specified hours.

        Args:
            hours: Number of hours before blocker is considered stale (default: 24)

        Returns:
            List of expired blocker IDs
        """
        cursor = self.conn.cursor()
        cursor.execute(
            f"""UPDATE blockers
               SET status = 'EXPIRED'
               WHERE status = 'PENDING'
                 AND datetime(created_at) < datetime('now', '-{hours} hours')
               RETURNING id"""
        )
        # Fetch results BEFORE commit (SQLite requirement for RETURNING clause)
        expired_ids = [row[0] for row in cursor.fetchall()]
        self.conn.commit()
        return expired_ids



    def get_blocker_metrics(self, project_id: int) -> Dict[str, Any]:
        """Calculate blocker metrics for a project.

        Tracks:
        - Average resolution time (seconds from created_at to resolved_at for RESOLVED blockers)
        - Expiration rate (percentage of blockers that expired vs resolved)
        - Total blocker counts by status and type

        Args:
            project_id: Project ID to calculate metrics for

        Returns:
            Dictionary with metrics:
            - avg_resolution_time_seconds: Average time to resolve (None if no resolved blockers)
            - expiration_rate_percent: Percentage of blockers that expired (0-100)
            - total_blockers: Total count of all blockers
            - resolved_count: Count of RESOLVED blockers
            - expired_count: Count of EXPIRED blockers
            - pending_count: Count of PENDING blockers
            - sync_count: Count of SYNC blockers
            - async_count: Count of ASYNC blockers
        """
        cursor = self.conn.cursor()

        # Get all blockers for tasks in this project
        cursor.execute(
            """
            SELECT
                b.status,
                b.blocker_type,
                b.created_at,
                b.resolved_at
            FROM blockers b
            INNER JOIN tasks t ON b.task_id = t.id
            WHERE t.project_id = ?
        """,
            (project_id,),
        )

        rows = cursor.fetchall()

        if not rows:
            return {
                "avg_resolution_time_seconds": None,
                "expiration_rate_percent": 0.0,
                "total_blockers": 0,
                "resolved_count": 0,
                "expired_count": 0,
                "pending_count": 0,
                "sync_count": 0,
                "async_count": 0,
            }

        # Calculate metrics
        total_blockers = len(rows)
        resolved_count = 0
        expired_count = 0
        pending_count = 0
        sync_count = 0
        async_count = 0
        resolution_times = []

        for row in rows:
            status = row["status"]
            blocker_type = row["blocker_type"]
            created_at = row["created_at"]
            resolved_at = row["resolved_at"]

            # Count by status
            if status == "RESOLVED":
                resolved_count += 1
                # Calculate resolution time
                if created_at and resolved_at:
                    from datetime import datetime, timezone

                    created = datetime.fromisoformat(created_at)
                    resolved = datetime.fromisoformat(resolved_at)

                    # Normalize both to timezone-aware (assume UTC if naive)
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if resolved.tzinfo is None:
                        resolved = resolved.replace(tzinfo=timezone.utc)

                    resolution_time_seconds = (resolved - created).total_seconds()
                    resolution_times.append(resolution_time_seconds)
            elif status == "EXPIRED":
                expired_count += 1
            elif status == "PENDING":
                pending_count += 1

            # Count by type
            if blocker_type == "SYNC":
                sync_count += 1
            elif blocker_type == "ASYNC":
                async_count += 1

        # Calculate average resolution time
        avg_resolution_time = None
        if resolution_times:
            avg_resolution_time = sum(resolution_times) / len(resolution_times)

        # Calculate expiration rate
        completed_blockers = resolved_count + expired_count
        expiration_rate = 0.0
        if completed_blockers > 0:
            expiration_rate = (expired_count / completed_blockers) * 100.0

        return {
            "avg_resolution_time_seconds": avg_resolution_time,
            "expiration_rate_percent": expiration_rate,
            "total_blockers": total_blockers,
            "resolved_count": resolved_count,
            "expired_count": expired_count,
            "pending_count": pending_count,
            "sync_count": sync_count,
            "async_count": async_count,
        }

