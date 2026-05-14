"""Cost analytics API router for CodeFRAME v2 (issue #557).

Aggregates the workspace's `token_usage` table into a daily-bucket summary
for the /costs page in the web UI. Hosts a single endpoint:

    GET /api/v2/costs/summary?days=30

Returns an empty-state payload (all zeros, zero-filled daily series) when
no spend data exists or the table isn't present — never 404.

The handler opens the workspace SQLite database directly to avoid the
pre-existing schema conflict between `codeframe/core/workspace.py` and
`codeframe/persistence/schema_manager.py` — wiring `TokenRepository`
to a raw connection skips `Database.initialize()` entirely.
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from codeframe.core import tasks as tasks_module
from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.persistence.repositories.token_repository import TokenRepository
from codeframe.ui.dependencies import get_v2_workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/costs", tags=["metrics"])


class DailyCostPoint(BaseModel):
    """One day of aggregated spend."""

    date: str  # ISO format YYYY-MM-DD
    cost_usd: float


class CostSummaryResponse(BaseModel):
    """Aggregated spend over the requested window."""

    total_spend_usd: float
    total_tasks: int
    avg_cost_per_task: float
    daily: List[DailyCostPoint]


def _empty_summary(days: int) -> Dict:
    """Build a zero-state response with `days` daily buckets."""
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)
    daily = [
        {"date": (start_date + timedelta(days=i)).isoformat(), "cost_usd": 0.0}
        for i in range(days)
    ]
    return {
        "total_spend_usd": 0.0,
        "total_tasks": 0,
        "avg_cost_per_task": 0.0,
        "daily": daily,
    }


def _query_costs(db_path: str, days: int) -> Dict:
    """Query the workspace DB via TokenRepository on a raw connection.

    Returns an empty summary if the DB can't be opened or the table is missing,
    rather than raising — keeps the endpoint safe for fresh workspaces.

    TODO(schema-conflict): we open the connection directly rather than through
    `Database(...).initialize()` because the v2 workspace schema in
    `codeframe/core/workspace.py` and the global schema in
    `persistence/schema_manager.py` define `blockers` incompatibly, and
    `Database.initialize()` therefore crashes on existing workspace DBs.
    Remove this workaround once the two schemas converge.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        logger.warning("costs: failed to open %s: %s", db_path, e)
        return _empty_summary(days)

    try:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='token_usage'"
            )
            if cursor.fetchone() is None:
                return _empty_summary(days)

            repo = TokenRepository(sync_conn=conn)
            return repo.get_costs_summary(days)
        except sqlite3.Error as e:
            # Locked DB, corrupted schema, etc. — fall back to empty state
            # rather than 500'ing the dashboard.
            logger.warning("costs: query failed on %s: %s", db_path, e)
            return _empty_summary(days)
    finally:
        conn.close()


@router.get("/summary", response_model=CostSummaryResponse)
@rate_limit_standard()
async def get_costs_summary(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
    days: int = Query(30, ge=7, le=90, description="Window size in days (7-90)"),
):
    """Return total spend, task count, average cost, and a daily series.

    Reads from the workspace's `token_usage` table. Returns zero-filled
    daily buckets so the client can render a chart without conditionals.
    If the table doesn't exist (no agent has run in this workspace yet),
    returns an empty-state response rather than an error.
    """
    summary = _query_costs(str(workspace.db_path), days)
    return CostSummaryResponse(
        total_spend_usd=summary["total_spend_usd"],
        total_tasks=summary["total_tasks"],
        avg_cost_per_task=summary["avg_cost_per_task"],
        daily=[
            DailyCostPoint(date=d["date"], cost_usd=d["cost_usd"])
            for d in summary["daily"]
        ],
    )


# ---------------------------------------------------------------------------
# Per-task and per-agent breakdowns (Issue #558)
# ---------------------------------------------------------------------------


class TaskCostEntry(BaseModel):
    """One task's aggregated cost with the most-used agent."""

    task_id: str
    task_title: str
    agent_id: str
    input_tokens: int
    output_tokens: int
    total_cost_usd: float


class TaskCostsResponse(BaseModel):
    """Top-N tasks by cost over the requested window."""

    tasks: List[TaskCostEntry]


class AgentCostEntry(BaseModel):
    """One agent's aggregated cost over the window."""

    agent_id: str
    input_tokens: int
    output_tokens: int
    total_cost_usd: float
    call_count: int


class AgentCostsResponse(BaseModel):
    """Per-agent breakdown plus overall token totals."""

    by_agent: List[AgentCostEntry]
    total_input_tokens: int
    total_output_tokens: int


def _placeholder_task_title(task_id: str) -> str:
    """Title to display when a task referenced by token_usage no longer exists."""
    short = str(task_id)[:8] if task_id else "unknown"
    return f"Unknown task ({short})"


def _open_workspace_conn(db_path: str) -> Optional[sqlite3.Connection]:
    """Open the workspace DB or return None if it cannot be read.

    Mirrors _query_costs's tolerance for fresh/locked workspaces: callers
    fall back to an empty response rather than 500'ing the dashboard.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.warning("costs: failed to open %s: %s", db_path, e)
        return None


def _token_usage_exists(conn: sqlite3.Connection) -> bool:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='token_usage'"
    )
    return cursor.fetchone() is not None


def _query_top_tasks(
    db_path: str, workspace: Workspace, days: int, limit: int = 10,
) -> List[Dict[str, Any]]:
    """Aggregate per-task cost and join titles via workspace.tasks.

    Returns a list of dicts ready for serialization into ``TaskCostEntry``.
    """
    conn = _open_workspace_conn(db_path)
    if conn is None:
        return []

    try:
        if not _token_usage_exists(conn):
            return []
        try:
            repo = TokenRepository(sync_conn=conn)
            rows = repo.get_top_tasks_by_cost(days=days, limit=limit)
        except sqlite3.Error as e:
            logger.warning("costs/tasks: query failed on %s: %s", db_path, e)
            return []
    finally:
        conn.close()

    entries: List[Dict[str, Any]] = []
    for row in rows:
        raw_id = row["task_id"]
        task_id_str = str(raw_id) if raw_id is not None else ""
        title = _placeholder_task_title(task_id_str)
        try:
            task = tasks_module.get(workspace, task_id_str)
            if task is not None:
                title = task.title
        except Exception:
            # Lookup failures are non-fatal — keep the placeholder title.
            logger.debug("costs/tasks: task lookup failed for %s", task_id_str, exc_info=True)

        entries.append({
            "task_id": task_id_str,
            "task_title": title,
            "agent_id": row["agent_id"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "total_cost_usd": row["total_cost_usd"],
        })

    return entries


def _query_costs_by_agent(db_path: str, days: int) -> Dict[str, Any]:
    """Aggregate per-agent cost over the window."""
    empty = {"by_agent": [], "total_input_tokens": 0, "total_output_tokens": 0}

    conn = _open_workspace_conn(db_path)
    if conn is None:
        return empty

    try:
        if not _token_usage_exists(conn):
            return empty
        try:
            repo = TokenRepository(sync_conn=conn)
            return repo.get_costs_by_agent(days=days)
        except sqlite3.Error as e:
            logger.warning("costs/by-agent: query failed on %s: %s", db_path, e)
            return empty
    finally:
        conn.close()


@router.get("/tasks", response_model=TaskCostsResponse)
@rate_limit_standard()
async def get_costs_by_task(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
    days: int = Query(30, ge=1, le=365, description="Window size in days (1-365)"),
):
    """Return the top 10 tasks by total cost over the requested window.

    Token usage rows are grouped by ``task_id``; the resulting list is sorted
    by total cost (descending) and capped at 10 entries. Rows whose ``task_id``
    is NULL are excluded — only task-attributable spend counts here.

    If the workspace has no token usage data yet (or the table doesn't exist),
    returns ``{"tasks": []}`` rather than an error.
    """
    entries = _query_top_tasks(str(workspace.db_path), workspace, days, limit=10)
    return TaskCostsResponse(
        tasks=[TaskCostEntry(**e) for e in entries],
    )


@router.get("/by-agent", response_model=AgentCostsResponse)
@rate_limit_standard()
async def get_costs_by_agent_endpoint(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
    days: int = Query(30, ge=1, le=365, description="Window size in days (1-365)"),
):
    """Return per-agent cost breakdown and overall input/output token totals.

    Token usage rows are grouped by ``agent_id`` and sorted by total cost
    (descending). Rows with NULL ``task_id`` still count toward the agent's
    totals (a non-task call still represents spend).
    """
    summary = _query_costs_by_agent(str(workspace.db_path), days)
    return AgentCostsResponse(
        by_agent=[AgentCostEntry(**a) for a in summary["by_agent"]],
        total_input_tokens=summary["total_input_tokens"],
        total_output_tokens=summary["total_output_tokens"],
    )
