"""Repository for Token Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import logging


from codeframe.core.models import (
    CallType,
)
from codeframe.persistence.repositories.base import BaseRepository

if TYPE_CHECKING:
    from codeframe.core.models import TokenUsage

logger = logging.getLogger(__name__)


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
        if self._sync_lock is not None:
            with self._sync_lock:
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
        else:
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



    def get_task_token_summary(self, task_id: int) -> Dict[str, Any]:
        """Get aggregated token usage summary for a single task.

        Args:
            task_id: Task ID to summarize

        Returns:
            Dictionary with aggregated token data:
            {
                "task_id": int,
                "total_input_tokens": int,
                "total_output_tokens": int,
                "total_tokens": int,
                "total_cost_usd": float,
                "call_count": int,
            }
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost_usd,
                COUNT(*) as call_count
            FROM token_usage
            WHERE task_id = ?
            """,
            (task_id,),
        )
        row = cursor.fetchone()

        return {
            "task_id": task_id,
            "total_input_tokens": row["total_input_tokens"],
            "total_output_tokens": row["total_output_tokens"],
            "total_tokens": row["total_tokens"],
            "total_cost_usd": row["total_cost_usd"],
            "call_count": row["call_count"],
        }

    def get_batch_token_usage(
        self,
        task_ids: List[int],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get token usage records filtered by a list of task IDs.

        Args:
            task_ids: List of task IDs to filter by
            start_date: Optional start of date range (inclusive)
            end_date: Optional end of date range (inclusive)

        Returns:
            List of token usage records as dictionaries
        """
        if not task_ids:
            return []

        cursor = self.conn.cursor()
        placeholders = ",".join("?" for _ in task_ids)
        query = f"SELECT * FROM token_usage WHERE task_id IN ({placeholders})"
        params: list = list(task_ids)

        if start_date is not None:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date is not None:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY timestamp DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_workspace_token_usage(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get all token usage records across the workspace.

        Args:
            start_date: Optional start of date range (inclusive)
            end_date: Optional end of date range (inclusive)

        Returns:
            List of token usage records as dictionaries
        """
        cursor = self.conn.cursor()
        query = "SELECT * FROM token_usage WHERE 1=1"
        params: list = []

        if start_date is not None:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date is not None:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY timestamp DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_costs_summary(self, days: int) -> Dict[str, Any]:
        """Aggregate token_usage costs into daily buckets for analytics.

        Args:
            days: Number of trailing days to include in the summary.

        Returns:
            Dictionary with keys:
                total_spend_usd: float — sum of estimated_cost_usd in window
                total_tasks: int — distinct task_id count (excludes NULL)
                avg_cost_per_task: float — total_spend_usd / total_tasks (0 if no tasks)
                daily: list of {"date": "YYYY-MM-DD", "cost_usd": float}
                       — one entry per day in the window, oldest first,
                         zero-filled for days with no spend.
        """
        if days <= 0:
            raise ValueError("days must be a positive integer")

        now_utc = datetime.now(timezone.utc)
        # Inclusive window starting at midnight UTC, `days` calendar days back.
        # Use a space-separated, offset-free format so lexicographic comparison
        # works against both `CURRENT_TIMESTAMP` defaults ("YYYY-MM-DD HH:MM:SS")
        # and Python `.isoformat()` outputs ("YYYY-MM-DDTHH:MM:SS+00:00").
        end_date = now_utc.date()
        start_date = end_date - timedelta(days=days - 1)
        start_iso = start_date.strftime("%Y-%m-%d %H:%M:%S")
        # Exclusive upper bound = midnight after today, so the daily chart and
        # the KPI cards always cover the same set of rows even if some records
        # are future-dated (clock skew, bad seed data).
        end_iso = (end_date + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

        cursor = self.conn.cursor()

        # Totals over the window. total_spend includes NULL-task records so it
        # matches the chart; total_tasks only counts records linked to a task.
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(estimated_cost_usd), 0.0) AS total_spend,
                COUNT(DISTINCT CASE WHEN task_id IS NOT NULL THEN task_id END) AS task_count
            FROM token_usage
            WHERE timestamp >= ? AND timestamp < ?
            """,
            (start_iso, end_iso),
        )
        totals = cursor.fetchone()
        total_spend = float(totals["total_spend"] or 0.0)
        total_tasks = int(totals["task_count"] or 0)
        avg_cost = (total_spend / total_tasks) if total_tasks > 0 else 0.0

        # Daily aggregation — group by calendar date in UTC
        cursor.execute(
            """
            SELECT
                DATE(timestamp) AS day,
                COALESCE(SUM(estimated_cost_usd), 0.0) AS cost
            FROM token_usage
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY DATE(timestamp)
            """,
            (start_iso, end_iso),
        )
        by_day: Dict[str, float] = {row["day"]: float(row["cost"] or 0.0) for row in cursor.fetchall()}

        daily: List[Dict[str, Any]] = []
        for offset in range(days):
            d = start_date + timedelta(days=offset)
            iso = d.isoformat()
            daily.append({"date": iso, "cost_usd": by_day.get(iso, 0.0)})

        return {
            "total_spend_usd": total_spend,
            "total_tasks": total_tasks,
            "avg_cost_per_task": avg_cost,
            "daily": daily,
        }

    def _window_iso_bounds(self, days: int) -> tuple[str, str]:
        """Return inclusive start / exclusive end ISO strings for a `days` window.

        Mirrors get_costs_summary's bounds so the per-task and per-agent
        aggregations cover the same rows. Space-separated, offset-free format
        works against both ``CURRENT_TIMESTAMP`` defaults and ``.isoformat()``.
        """
        if days <= 0:
            raise ValueError("days must be a positive integer")
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days - 1)
        start_iso = start_date.strftime("%Y-%m-%d %H:%M:%S")
        end_iso = (end_date + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        return start_iso, end_iso

    def get_top_tasks_by_cost(
        self,
        days: int,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Aggregate spend per task and return the top N by cost.

        Args:
            days: Trailing window in days.
            limit: Maximum number of tasks to return.

        Returns:
            List of dicts, sorted by total_cost_usd DESC:
                {
                    "task_id": <native value from token_usage.task_id>,
                    "agent_id": str,
                    "input_tokens": int,
                    "output_tokens": int,
                    "total_cost_usd": float,
                }
            Excludes rows where task_id IS NULL. The reported ``agent_id`` is
            the agent that made the most calls for that task (ties broken
            arbitrarily). ``task_id`` is returned as stored — SQLite preserves
            the inserted type, so v2 UUID strings come back as strings and v1
            integers come back as integers.
        """
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        start_iso, end_iso = self._window_iso_bounds(days)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                task_id,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(estimated_cost_usd), 0.0) AS total_cost_usd
            FROM token_usage
            WHERE task_id IS NOT NULL
              AND timestamp >= ?
              AND timestamp < ?
            GROUP BY task_id
            ORDER BY total_cost_usd DESC
            LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        rows = cursor.fetchall()

        result: List[Dict[str, Any]] = []
        for row in rows:
            task_id = row["task_id"]
            # Find the most-used agent for this task in the same window.
            cursor.execute(
                """
                SELECT agent_id, COUNT(*) AS calls
                FROM token_usage
                WHERE task_id = ?
                  AND timestamp >= ?
                  AND timestamp < ?
                GROUP BY agent_id
                ORDER BY calls DESC
                LIMIT 1
                """,
                (task_id, start_iso, end_iso),
            )
            agent_row = cursor.fetchone()
            agent_id = agent_row["agent_id"] if agent_row else ""

            result.append({
                "task_id": task_id,
                "agent_id": agent_id,
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
                "total_cost_usd": float(row["total_cost_usd"] or 0.0),
            })

        return result

    def get_costs_by_agent(self, days: int) -> Dict[str, Any]:
        """Aggregate spend per agent over a trailing `days` window.

        Args:
            days: Trailing window in days.

        Returns:
            {
                "by_agent": [
                    {
                        "agent_id": str,
                        "input_tokens": int,
                        "output_tokens": int,
                        "total_cost_usd": float,
                        "call_count": int,
                    },
                    ...
                ],
                "total_input_tokens": int,
                "total_output_tokens": int,
            }

        Includes records with NULL ``task_id`` — calls without a task still
        attribute to an agent. Sorted by total_cost_usd DESC.
        """
        start_iso, end_iso = self._window_iso_bounds(days)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                agent_id,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(estimated_cost_usd), 0.0) AS total_cost_usd,
                COUNT(*) AS call_count
            FROM token_usage
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY agent_id
            ORDER BY total_cost_usd DESC
            """,
            (start_iso, end_iso),
        )
        rows = cursor.fetchall()

        by_agent: List[Dict[str, Any]] = []
        total_input = 0
        total_output = 0
        for row in rows:
            inp = int(row["input_tokens"] or 0)
            out = int(row["output_tokens"] or 0)
            by_agent.append({
                "agent_id": row["agent_id"],
                "input_tokens": inp,
                "output_tokens": out,
                "total_cost_usd": float(row["total_cost_usd"] or 0.0),
                "call_count": int(row["call_count"] or 0),
            })
            total_input += inp
            total_output += out

        return {
            "by_agent": by_agent,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
        }

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

