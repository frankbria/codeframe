"""Metrics and cost tracking for LLM API calls (Sprint 10 Phase 5).

This module provides token usage tracking and cost estimation for LLM calls
across agents and projects. It supports:

- Recording token usage per LLM call (async and sync)
- Cost calculation for Claude models (Sonnet 4.5, Opus 4, Haiku 4)
- Cost aggregation by project, agent, model, task, and workspace
- Timeline-based token usage statistics
- Export to CSV and JSON

Example:
    >>> from codeframe.lib.metrics_tracker import MetricsTracker
    >>> from codeframe.persistence.database import Database
    >>> from codeframe.core.models import CallType
    >>>
    >>> db = Database("state.db")
    >>> db.initialize()
    >>> tracker = MetricsTracker(db=db)
    >>>
    >>> # Record token usage after LLM call (sync)
    >>> usage_id = tracker.record_token_usage_sync(
    ...     task_id=27,
    ...     agent_id="backend-001",
    ...     project_id=1,
    ...     model_name="claude-sonnet-4-5",
    ...     input_tokens=1000,
    ...     output_tokens=500,
    ...     call_type=CallType.TASK_EXECUTION
    ... )
    >>>
    >>> # Get project costs
    >>> costs = await tracker.get_project_costs(project_id=1)
    >>> print(f"Total: ${costs['total_cost_usd']:.2f}")
    Total: $0.01
"""

import csv
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union
from codeframe.core.models import CallType, TokenUsage
from codeframe.persistence.database import Database

logger = logging.getLogger(__name__)

# Model pricing as of 2025-11 (per million tokens)
# Source: Anthropic pricing page
MODEL_PRICING = {
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-haiku-4": {"input": 0.80, "output": 4.00},
}

# Regex to strip -YYYYMMDD date suffixes from Anthropic API model names
# (e.g., "claude-sonnet-4-5-20250514" → "claude-sonnet-4-5")
_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")


def normalize_model_name(raw_model: str) -> str:
    """Normalize a model name by stripping date suffixes.

    The Anthropic API returns model names like 'claude-sonnet-4-5-20250514'
    but our pricing dict uses 'claude-sonnet-4-5'. This function strips
    the date suffix and returns the canonical name.

    Args:
        raw_model: Raw model name from the API (e.g., 'claude-sonnet-4-5-20250514')

    Returns:
        Normalized model name (e.g., 'claude-sonnet-4-5')
    """
    # If it already matches a known model, return as-is
    if raw_model in MODEL_PRICING:
        return raw_model

    # Try stripping date suffix (8 digits at the end)
    stripped = _DATE_SUFFIX_RE.sub("", raw_model)
    if stripped in MODEL_PRICING:
        return stripped

    # Unknown model - return as-is
    return raw_model


class MetricsTracker:
    """Tracks token usage and costs for LLM API calls.

    This class provides methods to record token usage, calculate costs,
    and retrieve aggregated statistics for projects and agents.

    Attributes:
        db: Database instance for persistence

    Example:
        >>> tracker = MetricsTracker(db=database)
        >>> usage_id = await tracker.record_token_usage(
        ...     task_id=1,
        ...     agent_id="backend-001",
        ...     project_id=1,
        ...     model_name="claude-sonnet-4-5",
        ...     input_tokens=1000,
        ...     output_tokens=500
        ... )
    """

    def __init__(self, db: Database):
        """Initialize MetricsTracker.

        Args:
            db: Database instance for storing token usage records
        """
        self.db = db

    @staticmethod
    def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost in USD for an LLM call.

        Uses current Anthropic pricing (as of 2025-11):
        - Claude Sonnet 4.5: $3.00 input / $15.00 output per MTok
        - Claude Opus 4: $15.00 input / $75.00 output per MTok
        - Claude Haiku 4: $0.80 input / $4.00 output per MTok

        Handles model names with date suffixes (e.g., 'claude-sonnet-4-5-20250514')
        by normalizing them first. Unknown models return $0.00 cost instead of
        raising, to avoid crashing the agent during recording.

        Args:
            model_name: Model identifier (e.g., "claude-sonnet-4-5" or "claude-sonnet-4-5-20250514")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD (rounded to 6 decimal places), or 0.0 for unknown models

        Example:
            >>> cost = MetricsTracker.calculate_cost(
            ...     "claude-sonnet-4-5", 1000, 500
            ... )
            >>> print(f"${cost:.4f}")
            $0.0105
        """
        normalized = normalize_model_name(model_name)

        if normalized not in MODEL_PRICING:
            logger.warning(
                f"Unknown model '{model_name}' (normalized: '{normalized}'). "
                f"Returning $0.00 cost. Supported: {', '.join(MODEL_PRICING.keys())}"
            )
            return 0.0

        prices = MODEL_PRICING[normalized]

        # Calculate cost: (tokens * price_per_mtok) / 1,000,000
        input_cost = (input_tokens * prices["input"]) / 1_000_000
        output_cost = (output_tokens * prices["output"]) / 1_000_000
        total_cost = input_cost + output_cost

        # Round to 6 decimal places for precision
        return round(total_cost, 6)

    async def record_token_usage(
        self,
        task_id: Optional[Union[int, str]],
        agent_id: str,
        project_id: int,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        call_type: CallType = CallType.OTHER,
        session_id: Optional[str] = None,  # NEW: SDK session tracking
    ) -> int:
        """Record token usage for an LLM call.

        This method calculates the estimated cost and saves the usage record
        to the database for later aggregation and analysis.

        Args:
            task_id: Task ID if this call is related to a task (None for non-task calls)
            agent_id: ID of the agent making the call
            project_id: Project ID
            model_name: Model identifier (e.g., "claude-sonnet-4-5")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            call_type: Type of call (TASK_EXECUTION, CODE_REVIEW, COORDINATION, OTHER)
            session_id: Optional SDK session ID for conversation tracking

        Returns:
            Database ID of the created token usage record

        Raises:
            ValueError: If model_name is unknown or token counts are negative

        Example:
            >>> usage_id = await tracker.record_token_usage(
            ...     task_id=27,
            ...     agent_id="backend-001",
            ...     project_id=1,
            ...     model_name="claude-sonnet-4-5",
            ...     input_tokens=1500,
            ...     output_tokens=800,
            ...     call_type=CallType.TASK_EXECUTION
            ... )
        """
        # Validate inputs
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts cannot be negative")

        # Calculate cost (returns 0.0 for unknown models)
        estimated_cost = self.calculate_cost(model_name, input_tokens, output_tokens)

        # Create TokenUsage model
        token_usage = TokenUsage(
            task_id=task_id,
            actual_cost_usd=None,
            agent_id=agent_id,
            project_id=project_id,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost,
            call_type=call_type,
            session_id=session_id,
            timestamp=datetime.now(timezone.utc),
        )

        # Save to database
        usage_id = self.db.save_token_usage(token_usage)

        logger.info(
            f"Recorded token usage: agent={agent_id}, model={model_name}, "
            f"tokens={input_tokens + output_tokens}, cost=${estimated_cost:.6f}"
        )

        return usage_id

    def record_token_usage_sync(
        self,
        task_id: Optional[Union[int, str]],
        agent_id: str,
        project_id: int,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        call_type: CallType = CallType.OTHER,
        session_id: Optional[str] = None,
    ) -> int:
        """Record token usage for an LLM call (synchronous version).

        Identical to record_token_usage but synchronous, for use from
        synchronous code paths like the ReactAgent.

        Args:
            task_id: Task ID if this call is related to a task (None for non-task calls)
            agent_id: ID of the agent making the call
            project_id: Project ID
            model_name: Model identifier (e.g., "claude-sonnet-4-5")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            call_type: Type of call (TASK_EXECUTION, CODE_REVIEW, COORDINATION, OTHER)
            session_id: Optional SDK session ID for conversation tracking

        Returns:
            Database ID of the created token usage record

        Raises:
            ValueError: If token counts are negative
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts cannot be negative")

        estimated_cost = self.calculate_cost(model_name, input_tokens, output_tokens)

        token_usage = TokenUsage(
            task_id=task_id,
            actual_cost_usd=None,
            agent_id=agent_id,
            project_id=project_id,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost,
            call_type=call_type,
            session_id=session_id,
            timestamp=datetime.now(timezone.utc),
        )

        usage_id = self.db.save_token_usage(token_usage)

        logger.info(
            f"Recorded token usage (sync): agent={agent_id}, model={model_name}, "
            f"tokens={input_tokens + output_tokens}, cost=${estimated_cost:.6f}"
        )

        return usage_id

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
        return self.db.get_task_token_summary(task_id)

    def get_workspace_costs(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get aggregated costs across all tasks in the workspace.

        Args:
            start_date: Optional start of date range (inclusive)
            end_date: Optional end of date range (inclusive)

        Returns:
            Dictionary with cost breakdown:
            {
                "total_cost_usd": float,
                "total_tokens": int,
                "total_calls": int,
            }
        """
        records = self.db.get_workspace_token_usage(
            start_date=start_date, end_date=end_date
        )

        result: Dict[str, Any] = {
            "total_cost_usd": 0.0,
            "total_tokens": 0,
            "total_calls": len(records),
        }

        for record in records:
            result["total_cost_usd"] += record["estimated_cost_usd"]
            result["total_tokens"] += record["input_tokens"] + record["output_tokens"]

        result["total_cost_usd"] = round(result["total_cost_usd"], 6)
        return result

    @staticmethod
    def export_to_csv(records: List[Dict[str, Any]], output_path: str) -> None:
        """Export token usage records to a CSV file.

        Args:
            records: List of token usage record dictionaries
            output_path: Path to write the CSV file
        """
        fieldnames = [
            "id", "task_id", "agent_id", "project_id", "model_name",
            "input_tokens", "output_tokens", "estimated_cost_usd",
            "actual_cost_usd", "call_type", "session_id", "timestamp",
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                writer.writerow(record)

    @staticmethod
    def export_to_json(records: List[Dict[str, Any]], output_path: str) -> None:
        """Export token usage records to a JSON file with metadata.

        Args:
            records: List of token usage record dictionaries
            output_path: Path to write the JSON file
        """
        # Convert sqlite3.Row objects to plain dicts if needed
        serializable_records = []
        for record in records:
            row = dict(record)
            # Ensure all values are JSON-serializable
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value.isoformat()
            serializable_records.append(row)

        data = {
            "metadata": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "record_count": len(serializable_records),
            },
            "records": serializable_records,
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    async def get_project_costs(
        self,
        project_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get total costs and breakdown for a project.

        Aggregates all token usage records for the project and provides
        breakdowns by agent and model. Optionally filter by date range.

        Args:
            project_id: Project ID to get costs for
            start_date: Optional start of date range (inclusive)
            end_date: Optional end of date range (inclusive)

        Returns:
            Dictionary with cost breakdown:
            {
                "project_id": int,
                "total_cost_usd": float,
                "total_tokens": int,
                "total_calls": int,
                "by_agent": [
                    {"agent_id": str, "cost_usd": float, "total_tokens": int, "call_count": int},
                    ...
                ],
                "by_model": [
                    {"model_name": str, "cost_usd": float, "total_tokens": int, "call_count": int},
                    ...
                ]
            }

        Example:
            >>> costs = await tracker.get_project_costs(project_id=1)
            >>> print(f"Total: ${costs['total_cost_usd']:.2f}")
            >>> for agent in costs['by_agent']:
            ...     print(f"  {agent['agent_id']}: ${agent['cost_usd']:.2f}")
        """
        # Get usage records for project (optionally filtered by date)
        usage_records = self.db.get_token_usage(
            project_id=project_id, start_date=start_date, end_date=end_date
        )

        # Initialize result
        result = {
            "project_id": project_id,
            "total_cost_usd": 0.0,
            "total_tokens": 0,
            "total_calls": len(usage_records),
            "by_agent": [],
            "by_model": [],
        }

        if not usage_records:
            return result

        # Aggregate by agent
        agent_stats: Dict[str, Dict[str, Any]] = {}
        model_stats: Dict[str, Dict[str, Any]] = {}

        for record in usage_records:
            cost = record["estimated_cost_usd"]
            tokens = record["input_tokens"] + record["output_tokens"]
            agent_id = record["agent_id"]
            model_name = record["model_name"]

            # Update totals
            result["total_cost_usd"] += cost
            result["total_tokens"] += tokens

            # Update agent stats
            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "agent_id": agent_id,
                    "cost_usd": 0.0,
                    "total_tokens": 0,
                    "call_count": 0,
                }
            agent_stats[agent_id]["cost_usd"] += cost
            agent_stats[agent_id]["total_tokens"] += tokens
            agent_stats[agent_id]["call_count"] += 1

            # Update model stats
            if model_name not in model_stats:
                model_stats[model_name] = {
                    "model_name": model_name,
                    "cost_usd": 0.0,
                    "total_tokens": 0,
                    "call_count": 0,
                }
            model_stats[model_name]["cost_usd"] += cost
            model_stats[model_name]["total_tokens"] += tokens
            model_stats[model_name]["call_count"] += 1

        # Convert to lists and round costs
        result["total_cost_usd"] = round(result["total_cost_usd"], 6)  # type: ignore[call-overload]
        result["by_agent"] = [
            {**stats, "cost_usd": round(stats["cost_usd"], 6)}
            for stats in agent_stats.values()
        ]
        result["by_model"] = [
            {**stats, "cost_usd": round(stats["cost_usd"], 6)}
            for stats in model_stats.values()
        ]

        return result

    async def get_agent_costs(self, agent_id: str) -> Dict[str, Any]:
        """Get costs for a specific agent across all projects.

        Args:
            agent_id: Agent ID to get costs for

        Returns:
            Dictionary with cost breakdown:
            {
                "agent_id": str,
                "total_cost_usd": float,
                "total_tokens": int,
                "total_calls": int,
                "by_call_type": [
                    {"call_type": str, "cost_usd": float, "calls": int},
                    ...
                ],
                "by_project": [
                    {"project_id": int, "cost_usd": float},
                    ...
                ]
            }

        Example:
            >>> costs = await tracker.get_agent_costs(agent_id="backend-001")
            >>> print(f"Agent total: ${costs['total_cost_usd']:.2f}")
        """
        # Get all usage records for agent
        usage_records = self.db.get_token_usage(agent_id=agent_id)

        # Initialize result
        result = {
            "agent_id": agent_id,
            "total_cost_usd": 0.0,
            "total_tokens": 0,
            "total_calls": len(usage_records),
            "by_call_type": [],
            "by_project": [],
        }

        if not usage_records:
            return result

        # Aggregate by call type and project
        call_type_stats: Dict[str, Dict[str, Any]] = {}
        project_stats: Dict[int, Dict[str, Any]] = {}

        for record in usage_records:
            cost = record["estimated_cost_usd"]
            tokens = record["input_tokens"] + record["output_tokens"]
            call_type = record["call_type"]
            project_id = record["project_id"]

            # Update totals
            result["total_cost_usd"] += cost
            result["total_tokens"] += tokens

            # Update call type stats
            if call_type not in call_type_stats:
                call_type_stats[call_type] = {
                    "call_type": call_type,
                    "cost_usd": 0.0,
                    "call_count": 0,
                }
            call_type_stats[call_type]["cost_usd"] += cost
            call_type_stats[call_type]["call_count"] += 1

            # Update project stats
            if project_id not in project_stats:
                project_stats[project_id] = {"project_id": project_id, "cost_usd": 0.0}
            project_stats[project_id]["cost_usd"] += cost

        # Convert to lists and round costs
        result["total_cost_usd"] = round(result["total_cost_usd"], 6)  # type: ignore[call-overload]
        result["by_call_type"] = [
            {**stats, "cost_usd": round(stats["cost_usd"], 6)}
            for stats in call_type_stats.values()
        ]
        result["by_project"] = [
            {**stats, "cost_usd": round(stats["cost_usd"], 6)}
            for stats in project_stats.values()
        ]

        return result

    async def get_token_usage_stats(
        self,
        project_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get token usage statistics for a date range.

        Args:
            project_id: Project ID to get stats for
            start_date: Start of date range (inclusive, optional)
            end_date: End of date range (inclusive, optional)

        Returns:
            Dictionary with usage statistics:
            {
                "project_id": int,
                "total_cost_usd": float,
                "total_tokens": int,
                "total_calls": int,
                "date_range": {
                    "start": str (ISO format),
                    "end": str (ISO format)
                },
                "by_day": [
                    {"date": str, "cost_usd": float, "tokens": int, "calls": int},
                    ...
                ]
            }

        Example:
            >>> from datetime import datetime, timedelta
            >>> start = datetime.now() - timedelta(days=7)
            >>> stats = await tracker.get_token_usage_stats(
            ...     project_id=1,
            ...     start_date=start
            ... )
            >>> print(f"Last 7 days: ${stats['total_cost_usd']:.2f}")
        """
        # Get usage records with date filtering
        usage_records = self.db.get_token_usage(
            project_id=project_id, start_date=start_date, end_date=end_date
        )

        # Initialize result
        result = {
            "project_id": project_id,
            "total_cost_usd": 0.0,
            "total_tokens": 0,
            "total_calls": len(usage_records),
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            "by_day": [],
        }

        if not usage_records:
            return result

        # Aggregate totals
        for record in usage_records:
            result["total_cost_usd"] += record["estimated_cost_usd"]
            result["total_tokens"] += record["input_tokens"] + record["output_tokens"]

        # Round cost
        result["total_cost_usd"] = round(result["total_cost_usd"], 6)  # type: ignore[call-overload]

        # TODO: Implement by_day aggregation (future enhancement)
        # This would group usage by date for timeline visualization

        return result

    async def get_token_usage_timeseries(
        self,
        project_id: int,
        start_date: datetime,
        end_date: datetime,
        interval: str = "day",
    ) -> list[dict[str, Any]]:
        """Get token usage aggregated by time intervals for charting.

        Groups token usage records into time buckets (hour, day, or week) for
        visualization in time series charts. Each bucket contains aggregated
        token counts and costs.

        Args:
            project_id: Project ID to get time series for
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            interval: Time interval for grouping ('hour', 'day', 'week')

        Returns:
            List of time series data points, each containing:
            {
                "timestamp": str (ISO 8601 format),
                "input_tokens": int,
                "output_tokens": int,
                "total_tokens": int,
                "cost_usd": float
            }

        Raises:
            ValueError: If interval is not one of 'hour', 'day', 'week'

        Example:
            >>> from datetime import datetime, timedelta
            >>> start = datetime.now() - timedelta(days=7)
            >>> end = datetime.now()
            >>> series = await tracker.get_token_usage_timeseries(
            ...     project_id=1,
            ...     start_date=start,
            ...     end_date=end,
            ...     interval='day'
            ... )
            >>> for point in series:
            ...     print(f"{point['timestamp']}: {point['total_tokens']} tokens")
        """
        valid_intervals = ("hour", "day", "week")
        if interval not in valid_intervals:
            raise ValueError(
                f"Invalid interval '{interval}'. Must be one of: {', '.join(valid_intervals)}"
            )

        # Get usage records with date filtering
        usage_records = self.db.get_token_usage(
            project_id=project_id, start_date=start_date, end_date=end_date
        )

        if not usage_records:
            return []

        # Group records by time bucket
        buckets: dict[str, dict[str, Any]] = {}

        for record in usage_records:
            # Parse timestamp - handle string, naive datetime, and aware datetime
            timestamp = record["timestamp"]
            if isinstance(timestamp, str):
                # Handle both ISO 8601 and simple date formats
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elif timestamp.tzinfo is None:
                # Assume UTC for naive datetimes from database
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            # Calculate bucket key based on interval
            bucket_key = self._get_bucket_key(timestamp, interval)

            # Initialize bucket if not exists
            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    "timestamp": bucket_key,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                }

            # Aggregate values
            buckets[bucket_key]["input_tokens"] += record["input_tokens"]
            buckets[bucket_key]["output_tokens"] += record["output_tokens"]
            buckets[bucket_key]["total_tokens"] += (
                record["input_tokens"] + record["output_tokens"]
            )
            buckets[bucket_key]["cost_usd"] += record["estimated_cost_usd"]

        # Round costs and sort by timestamp
        result = []
        for bucket in buckets.values():
            bucket["cost_usd"] = round(bucket["cost_usd"], 6)
            result.append(bucket)

        # Sort by timestamp
        result.sort(key=lambda x: x["timestamp"])

        return result

    def _get_bucket_key(self, timestamp: datetime, interval: str) -> str:
        """Get the bucket key for a timestamp based on the interval.

        Args:
            timestamp: Datetime to get bucket key for
            interval: Time interval ('hour', 'day', 'week')

        Returns:
            ISO 8601 formatted string representing the bucket start time
        """
        if interval == "hour":
            # Truncate to start of hour
            bucket_start = timestamp.replace(minute=0, second=0, microsecond=0)
        elif interval == "day":
            # Truncate to start of day
            bucket_start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        elif interval == "week":
            # Truncate to start of ISO week (Monday)
            # Get the weekday (0=Monday, 6=Sunday)
            days_since_monday = timestamp.weekday()
            bucket_start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            bucket_start = bucket_start - timedelta(days=days_since_monday)
        else:
            # This should never be reached due to validation in get_token_usage_timeseries
            raise ValueError(f"Invalid interval: {interval}")

        # Return ISO format with Z suffix for UTC
        return bucket_start.strftime("%Y-%m-%dT%H:%M:%SZ")
