"""Repository for Token Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import os
from datetime import datetime
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import logging


from codeframe.core.models import (
    CallType,
)
from codeframe.persistence.repositories.base import BaseRepository

if TYPE_CHECKING:
    from codeframe.core.models import TokenUsage

logger = logging.getLogger(__name__)

# Audit verbosity configuration
AUDIT_VERBOSITY = os.getenv("AUDIT_VERBOSITY", "low").lower()
if AUDIT_VERBOSITY not in ("low", "high"):
    logger.warning(f"Invalid AUDIT_VERBOSITY='{AUDIT_VERBOSITY}', defaulting to 'low'")
    AUDIT_VERBOSITY = "low"


class TokenRepository(BaseRepository):
    """Repository for token repository operations."""


    def save_token_usage(self, token_usage: "TokenUsage") -> int:
        """Save a token usage record to the database.

        Args:
            token_usage: TokenUsage model instance

        Returns:
            Database ID of the created record

        Example:
            >>> from codeframe.core.models import TokenUsage, CallType
            >>> usage = TokenUsage(
            ...     task_id=27,
            ...     agent_id="backend-001",
            ...     project_id=1,
            ...     model_name="claude-sonnet-4-5",
            ...     input_tokens=1000,
            ...     output_tokens=500,
            ...     estimated_cost_usd=0.0105,
            ...     call_type=CallType.TASK_EXECUTION
            ... )
            >>> usage_id = db.save_token_usage(usage)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO token_usage (
                task_id, agent_id, project_id, model_name,
                input_tokens, output_tokens, estimated_cost_usd,
                actual_cost_usd, call_type, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_usage.task_id,
                token_usage.agent_id,
                token_usage.project_id,
                token_usage.model_name,
                token_usage.input_tokens,
                token_usage.output_tokens,
                token_usage.estimated_cost_usd,
                token_usage.actual_cost_usd,
                (
                    token_usage.call_type.value
                    if isinstance(token_usage.call_type, CallType)
                    else token_usage.call_type
                ),
                token_usage.timestamp.isoformat(),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_token_usage(
        self,
        project_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get token usage records with optional filtering.

        Args:
            project_id: Filter by project ID (optional)
            agent_id: Filter by agent ID (optional)
            start_date: Filter by start date (inclusive, optional)
            end_date: Filter by end date (inclusive, optional)

        Returns:
            List of token usage records as dictionaries

        Example:
            >>> # Get all usage for a project
            >>> usage = db.get_token_usage(project_id=1)
            >>>
            >>> # Get usage for an agent in a date range
            >>> from datetime import datetime, timedelta
            >>> start = datetime.now() - timedelta(days=7)
            >>> usage = db.get_token_usage(agent_id="backend-001", start_date=start)
        """
        cursor = self.conn.cursor()

        # Build query with filters
        query = "SELECT * FROM token_usage WHERE 1=1"
        params = []

        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)

        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id)

        if start_date is not None:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date is not None:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY timestamp DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]



    def get_project_costs_aggregate(self, project_id: int) -> Dict[str, Any]:
        """Get aggregated cost statistics for a project.

        This is a convenience method that aggregates costs by agent and model
        in a single database query for better performance.

        Args:
            project_id: Project ID

        Returns:
            Dictionary with aggregated costs:
            {
                "total_cost": float,
                "total_tokens": int,
                "by_agent": {...},
                "by_model": {...}
            }

        Example:
            >>> stats = db.get_project_costs_aggregate(project_id=1)
            >>> print(f"Total: ${stats['total_cost']:.2f}")
        """
        cursor = self.conn.cursor()

        # Get overall totals
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(estimated_cost_usd), 0) as total_cost,
                COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                COUNT(*) as total_calls
            FROM token_usage
            WHERE project_id = ?
            """,
            (project_id,),
        )
        totals = cursor.fetchone()

        # Get breakdown by agent
        cursor.execute(
            """
            SELECT
                agent_id,
                SUM(estimated_cost_usd) as cost,
                SUM(input_tokens + output_tokens) as tokens,
                COUNT(*) as calls
            FROM token_usage
            WHERE project_id = ?
            GROUP BY agent_id
            ORDER BY cost DESC
            """,
            (project_id,),
        )
        by_agent = [dict(row) for row in cursor.fetchall()]

        # Get breakdown by model
        cursor.execute(
            """
            SELECT
                model_name,
                SUM(estimated_cost_usd) as cost,
                SUM(input_tokens + output_tokens) as tokens,
                COUNT(*) as calls
            FROM token_usage
            WHERE project_id = ?
            GROUP BY model_name
            ORDER BY cost DESC
            """,
            (project_id,),
        )
        by_model = [dict(row) for row in cursor.fetchall()]

        return {
            "total_cost": totals["total_cost"],
            "total_tokens": totals["total_tokens"],
            "total_calls": totals["total_calls"],
            "by_agent": by_agent,
            "by_model": by_model,
        }

