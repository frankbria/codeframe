"""Metrics API router for CodeFRAME.

This module provides endpoints for token usage and cost metrics,
including project-level and agent-level breakdowns.

Endpoints:
    - GET /api/projects/{project_id}/metrics/tokens - Get token usage metrics
    - GET /api/projects/{project_id}/metrics/costs - Get cost metrics
    - GET /api/agents/{agent_id}/metrics - Get agent-specific metrics
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from codeframe.lib.metrics_tracker import MetricsTracker
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User

# Module logger
logger = logging.getLogger(__name__)

# Create router for metrics endpoints
router = APIRouter(tags=["metrics"])


@router.get("/api/projects/{project_id}/metrics/tokens")
async def get_project_token_metrics(
    project_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get token usage metrics for a project (T127).

    Sprint 10 - Phase 5: Metrics & Cost Tracking

    Returns token usage records for a project, optionally filtered by date range.
    Includes timeline statistics and aggregated token counts.

    Args:
        project_id: Project ID to get token metrics for
        start_date: Optional start date (ISO 8601 format, e.g., '2025-11-01T00:00:00Z')
        end_date: Optional end date (ISO 8601 format, e.g., '2025-11-30T23:59:59Z')
        db: Database instance (injected)

    Returns:
        200 OK: Token usage records with timeline stats
        {
            "project_id": int,
            "total_tokens": int,
            "total_calls": int,
            "total_cost_usd": float,
            "date_range": {
                "start": str | null,
                "end": str | null
            },
            "usage_records": [
                {
                    "id": int,
                    "task_id": int | null,
                    "agent_id": str,
                    "model_name": str,
                    "input_tokens": int,
                    "output_tokens": int,
                    "estimated_cost_usd": float,
                    "call_type": str,
                    "timestamp": str
                },
                ...
            ]
        }
        400 Bad Request: Invalid date format
        404 Not Found: Project not found
        500 Internal Server Error: Database or processing error

    Example:
        GET /api/projects/1/metrics/tokens
        GET /api/projects/1/metrics/tokens?start_date=2025-11-01T00:00:00Z&end_date=2025-11-30T23:59:59Z
    """
    # Validate project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Parse and validate date parameters
    start_dt = None
    end_dt = None

    try:
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format. Use ISO 8601 format (e.g., '2025-11-01T00:00:00Z'): {str(e)}",
        )

    try:
        # Get token usage stats using MetricsTracker
        tracker = MetricsTracker(db=db)
        stats = await tracker.get_token_usage_stats(
            project_id=project_id, start_date=start_dt, end_date=end_dt
        )

        # Get detailed usage records
        usage_records = db.get_token_usage(
            project_id=project_id, start_date=start_dt, end_date=end_dt
        )

        # Build response
        return {
            "project_id": project_id,
            "total_tokens": stats["total_tokens"],
            "total_calls": stats["total_calls"],
            "total_cost_usd": stats["total_cost_usd"],
            "date_range": stats["date_range"],
            "usage_records": usage_records,
        }

    except Exception as e:
        logger.error(f"Failed to get token metrics for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve token metrics: {str(e)}")


@router.get("/api/projects/{project_id}/metrics/costs")
async def get_project_cost_metrics(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get cost breakdown for a project (T128).

    Sprint 10 - Phase 5: Metrics & Cost Tracking

    Returns total costs and breakdowns by agent and model for a project.
    Useful for understanding cost allocation and identifying high-cost operations.

    Args:
        project_id: Project ID to get cost breakdown for
        db: Database instance (injected)

    Returns:
        200 OK: Cost breakdown
        {
            "project_id": int,
            "total_cost_usd": float,
            "total_tokens": int,
            "total_calls": int,
            "by_agent": [
                {
                    "agent_id": str,
                    "cost_usd": float,
                    "tokens": int,
                    "calls": int
                },
                ...
            ],
            "by_model": [
                {
                    "model_name": str,
                    "cost_usd": float,
                    "total_tokens": int,
                    "total_calls": int
                },
                ...
            ]
        }
        404 Not Found: Project not found
        500 Internal Server Error: Database or processing error

    Example:
        GET /api/projects/1/metrics/costs
        Response: {
            "project_id": 1,
            "total_cost_usd": 0.125,
            "total_tokens": 15000,
            "total_calls": 10,
            "by_agent": [
                {"agent_id": "backend-001", "cost_usd": 0.075, "tokens": 9000, "calls": 6},
                {"agent_id": "review-001", "cost_usd": 0.05, "tokens": 6000, "calls": 4}
            ],
            "by_model": [
                {"model_name": "claude-sonnet-4-5", "cost_usd": 0.125, "total_tokens": 15000, "total_calls": 10}
            ]
        }
    """
    # Validate project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Get project costs using MetricsTracker
        tracker = MetricsTracker(db=db)
        costs = await tracker.get_project_costs(project_id=project_id)

        logger.info(
            f"Retrieved cost metrics for project {project_id}: ${costs['total_cost_usd']:.6f}"
        )

        return costs

    except Exception as e:
        logger.error(f"Failed to get cost metrics for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve cost metrics: {str(e)}")


@router.get("/api/agents/{agent_id}/metrics")
async def get_agent_metrics(
    agent_id: str,
    project_id: Optional[int] = None,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get metrics for a specific agent (T129).

    Sprint 10 - Phase 5: Metrics & Cost Tracking

    Returns cost and usage statistics for a specific agent, optionally filtered
    by project. Includes breakdowns by call type and project.

    Args:
        agent_id: Agent ID to get metrics for
        project_id: Optional project ID to filter metrics (query parameter)
        db: Database instance (injected)

    Returns:
        200 OK: Agent metrics
        {
            "agent_id": str,
            "total_cost_usd": float,
            "total_tokens": int,
            "total_calls": int,
            "by_call_type": [
                {
                    "call_type": str,
                    "cost_usd": float,
                    "calls": int
                },
                ...
            ],
            "by_project": [
                {
                    "project_id": int,
                    "cost_usd": float
                },
                ...
            ]
        }
        500 Internal Server Error: Database or processing error

    Example:
        GET /api/agents/backend-001/metrics
        GET /api/agents/backend-001/metrics?project_id=1
        Response: {
            "agent_id": "backend-001",
            "total_cost_usd": 0.085,
            "total_tokens": 12000,
            "total_calls": 8,
            "by_call_type": [
                {"call_type": "task_execution", "cost_usd": 0.06, "calls": 5},
                {"call_type": "code_review", "cost_usd": 0.025, "calls": 3}
            ],
            "by_project": [
                {"project_id": 1, "cost_usd": 0.085}
            ]
        }
    """
    # Authorization check - if project_id provided, verify access
    if project_id is not None:
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Get agent costs using MetricsTracker
        tracker = MetricsTracker(db=db)
        costs = await tracker.get_agent_costs(agent_id=agent_id)

        # Security: Filter by_project to only include projects the user has access to
        # This prevents cross-project data leakage when project_id is not specified
        if project_id is None:
            # Get user's accessible projects
            user_projects = db.get_user_projects(current_user.id)
            accessible_project_ids = {p["id"] for p in user_projects}

            # Filter by_project to only include accessible projects
            costs["by_project"] = [
                p for p in costs["by_project"]
                if p["project_id"] in accessible_project_ids
            ]

            # Recalculate totals based on filtered projects
            # Get all usage records for this agent across accessible projects only
            all_usage_records = []
            for proj_id in accessible_project_ids:
                project_records = db.get_token_usage(agent_id=agent_id, project_id=proj_id)
                all_usage_records.extend(project_records)

            # Recalculate aggregates
            total_cost = sum(r["estimated_cost_usd"] for r in all_usage_records)
            total_tokens = sum(r["input_tokens"] + r["output_tokens"] for r in all_usage_records)
            total_calls = len(all_usage_records)

            # Aggregate by call type
            call_type_stats = {}
            for record in all_usage_records:
                call_type = record["call_type"]
                if call_type not in call_type_stats:
                    call_type_stats[call_type] = {
                        "call_type": call_type,
                        "cost_usd": 0.0,
                        "calls": 0,
                    }
                call_type_stats[call_type]["cost_usd"] += record["estimated_cost_usd"]
                call_type_stats[call_type]["calls"] += 1

            # Round costs
            for stats in call_type_stats.values():
                stats["cost_usd"] = round(stats["cost_usd"], 6)

            # Update costs with filtered data
            costs["total_cost_usd"] = round(total_cost, 6)
            costs["total_tokens"] = total_tokens
            costs["total_calls"] = total_calls
            costs["by_call_type"] = list(call_type_stats.values())
            # by_project already filtered above

        # If project_id is specified, filter the results
        if project_id is not None:
            # Filter by_project to only include the specified project
            filtered_projects = [p for p in costs["by_project"] if p["project_id"] == project_id]

            if not filtered_projects:
                # No data for this agent in this project
                return {
                    "agent_id": agent_id,
                    "total_cost_usd": 0.0,
                    "total_tokens": 0,
                    "total_calls": 0,
                    "by_call_type": [],
                    "by_project": [],
                }

            # Recalculate totals based on filtered project
            # We need to get usage records for this specific project
            usage_records = db.get_token_usage(agent_id=agent_id, project_id=project_id)

            # Recalculate aggregates
            total_cost = sum(r["estimated_cost_usd"] for r in usage_records)
            total_tokens = sum(r["input_tokens"] + r["output_tokens"] for r in usage_records)
            total_calls = len(usage_records)

            # Aggregate by call type
            call_type_stats = {}
            for record in usage_records:
                call_type = record["call_type"]
                if call_type not in call_type_stats:
                    call_type_stats[call_type] = {
                        "call_type": call_type,
                        "cost_usd": 0.0,
                        "calls": 0,
                    }
                call_type_stats[call_type]["cost_usd"] += record["estimated_cost_usd"]
                call_type_stats[call_type]["calls"] += 1

            # Round costs
            for stats in call_type_stats.values():
                stats["cost_usd"] = round(stats["cost_usd"], 6)

            return {
                "agent_id": agent_id,
                "total_cost_usd": round(total_cost, 6),
                "total_tokens": total_tokens,
                "total_calls": total_calls,
                "by_call_type": list(call_type_stats.values()),
                "by_project": [{"project_id": project_id, "cost_usd": round(total_cost, 6)}],
            }

        logger.info(f"Retrieved metrics for agent {agent_id}: ${costs['total_cost_usd']:.6f}")

        return costs

    except Exception as e:
        logger.error(f"Failed to get metrics for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve agent metrics: {str(e)}")
