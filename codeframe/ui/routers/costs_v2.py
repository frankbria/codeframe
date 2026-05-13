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

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.persistence.repositories.token_repository import TokenRepository
from codeframe.ui.dependencies import get_v2_workspace

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
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return _empty_summary(days)

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='token_usage'"
        )
        if cursor.fetchone() is None:
            return _empty_summary(days)

        repo = TokenRepository(sync_conn=conn)
        return repo.get_costs_summary(days)
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
