"""Context management API endpoints.

This module provides API endpoints for managing agent context items,
including listing, creating, updating, deleting, and flash save operations.
"""

from typing import Optional
from datetime import datetime, UTC
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.ui.shared import manager
from codeframe.core.models import ContextItemResponse
from codeframe.lib.context_manager import ContextManager
from codeframe.lib.token_counter import TokenCounter

# Create router with prefix and tags
router = APIRouter(tags=["context"])


@router.get("/api/agents/{agent_id}/context")
async def list_context_items(
    agent_id: str,
    project_id: int,
    tier: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Database = Depends(get_db),
):
    """List context items for an agent with optional filters (T021).

    Args:
        agent_id: Agent ID to list context items for
        project_id: Project ID for the context items
        tier: Optional filter by tier (HOT, WARM, COLD)
        limit: Maximum items to return (default: 100)
        offset: Number of items to skip (default: 0)
        db: Database instance (injected)

    Returns:
        200 OK: Dictionary with:
            - items: List[ContextItemResponse]
            - total: int (total items matching filter)
            - offset: int
            - limit: int

    Raises:
        HTTPException:
            - 422: Invalid request (validation error)
    """
    # Get context items from database (returns a list, not a dict)
    items_list = db.list_context_items(
        project_id=project_id, agent_id=agent_id, tier=tier, limit=limit, offset=offset
    )

    # Convert items to ContextItemResponse models
    items = [
        ContextItemResponse(
            id=item["id"],
            agent_id=item["agent_id"],
            item_type=item["item_type"],
            content=item["content"],
            importance_score=item["importance_score"],
            tier=item["current_tier"],
            access_count=item["access_count"],
            created_at=item["created_at"],
            last_accessed=item["last_accessed"],
        )
        for item in items_list
    ]

    return {"items": items, "total": len(items), "offset": offset, "limit": limit}


@router.delete("/api/agents/{agent_id}/context/{item_id}", status_code=204)
async def delete_context_item(
    agent_id: str, item_id: str, project_id: int, db: Database = Depends(get_db)
):
    """Delete a context item (T022).

    Args:
        agent_id: Agent ID (used for ownership validation)
        item_id: Context item ID to delete (UUID string)
        project_id: Project ID (used for ownership validation)
        db: Database instance (injected)

    Returns:
        204 No Content: Successful deletion

    Raises:
        HTTPException:
            - 404: Context item not found
            - 403: Context item does not belong to specified agent/project
    """
    # Check if item exists
    item = db.get_context_item(item_id)

    if not item:
        raise HTTPException(status_code=404, detail=f"Context item {item_id} not found")

    # Validate ownership - ensure item belongs to the specified agent and project
    if item.get("agent_id") != agent_id:
        raise HTTPException(
            status_code=403,
            detail=f"Context item {item_id} does not belong to agent {agent_id}",
        )

    if item.get("project_id") != project_id:
        raise HTTPException(
            status_code=403,
            detail=f"Context item {item_id} does not belong to project {project_id}",
        )

    # Delete context item after ownership validation passes
    db.delete_context_item(item_id)

    # Return 204 No Content (no response body)
    return None


@router.post("/api/agents/{agent_id}/context/update-scores", response_model=dict)
async def update_context_scores(agent_id: str, project_id: int, db: Database = Depends(get_db)):
    """Recalculate importance scores for all context items (T033).

    Triggers batch recalculation of importance scores for all context items
    belonging to the specified agent on a project. Scores are recalculated based on:
    - Current age (time since creation)
    - Access patterns (access_count)
    - Item type weights

    Use cases:
    - Periodic batch updates (cron job)
    - Manual trigger after time passage
    - Debugging/testing score calculations

    Args:
        agent_id: Agent ID to recalculate scores for
        project_id: Project ID the agent is working on (query parameter)
        db: Database instance (injected)

    Returns:
        200 OK: {updated_count: int} - Number of items updated

    Example:
        POST /api/agents/backend-worker-001/context/update-scores?project_id=123
        Response: {"updated_count": 150}
    """
    # Create context manager
    context_mgr = ContextManager(db=db)

    # Recalculate scores for all agent context items on this project
    updated_count = context_mgr.recalculate_scores_for_agent(project_id, agent_id)

    return {"updated_count": updated_count}


@router.post("/api/agents/{agent_id}/context/update-tiers", response_model=dict)
async def update_context_tiers(agent_id: str, project_id: int, db: Database = Depends(get_db)):
    """Recalculate scores and reassign tiers for all context items (T042).

    Triggers batch recalculation of importance scores AND tier reassignment
    for all context items belonging to the specified agent on a project. This operation:
    1. Recalculates importance scores based on current age/access patterns
    2. Reassigns tiers (HOT >= 0.8, WARM 0.4-0.8, COLD < 0.4)

    Use cases:
    - Periodic tier maintenance (hourly cron job)
    - Manual trigger to move aged items to lower tiers
    - After major time passage (e.g., daily cleanup)

    Args:
        agent_id: Agent ID to update tiers for
        project_id: Project ID the agent is working on (query parameter)
        db: Database instance (injected)

    Returns:
        200 OK: {updated_count: int} - Number of items updated with new tiers

    Example:
        POST /api/agents/backend-worker-001/context/update-tiers?project_id=123
        Response: {"updated_count": 150}
    """
    # Create context manager
    context_mgr = ContextManager(db=db)

    # Recalculate scores AND reassign tiers for all agent context items on this project
    updated_count = context_mgr.update_tiers_for_agent(project_id, agent_id)

    return {"updated_count": updated_count}


@router.post("/api/agents/{agent_id}/flash-save")
async def flash_save_context(
    agent_id: str, project_id: int, force: bool = False, db: Database = Depends(get_db)
):
    """Trigger flash save for an agent's context (T054).

    Creates a checkpoint with full context state and archives COLD tier items
    to reduce memory footprint. Only triggers if context exceeds 80% of 180k token limit
    (144k tokens) unless force=True.

    Args:
        agent_id: Agent ID to flash save
        project_id: Project ID the agent is working on (query parameter)
        force: Force flash save even if below threshold (default: False)
        db: Database instance (injected)

    Returns:
        200 OK: FlashSaveResponse with checkpoint_id, tokens_before, tokens_after, reduction_percentage
        400 Bad Request: If below threshold and force=False

    Example:
        POST /api/agents/backend-worker-001/flash-save?project_id=123&force=false
        Response: {
            "checkpoint_id": 42,
            "tokens_before": 150000,
            "tokens_after": 50000,
            "reduction_percentage": 66.67,
            "items_archived": 20,
            "hot_items_retained": 10,
            "warm_items_retained": 15
        }
    """
    # Create context manager
    context_mgr = ContextManager(db=db)

    # Check if flash save should be triggered
    should_save = context_mgr.should_flash_save(project_id, agent_id, force=force)

    if not should_save:
        return JSONResponse(
            status_code=400,
            content={"error": "Context below threshold. Use force=true to override."},
        )

    # Execute flash save
    result = context_mgr.flash_save(project_id, agent_id)

    # Emit WebSocket event (T059)
    # Note: broadcast_json doesn't exist on manager, should be broadcast
    await manager.broadcast(
        {
            "type": "flash_save_completed",
            "agent_id": agent_id,
            "project_id": project_id,
            "checkpoint_id": result["checkpoint_id"],
            "reduction_percentage": result["reduction_percentage"],
        }
    )

    return result


@router.get("/api/agents/{agent_id}/flash-save/checkpoints")
async def list_flash_save_checkpoints(
    agent_id: str, limit: int = 10, db: Database = Depends(get_db)
):
    """List checkpoints for an agent (T055).

    Returns metadata about flash save checkpoints, sorted by creation time (most recent first).
    Does not include the full checkpoint_data JSON to keep response lightweight.

    Args:
        agent_id: Agent ID to list checkpoints for
        limit: Maximum number of checkpoints to return (default: 10, max: 100)
        db: Database instance (injected)

    Returns:
        200 OK: List of checkpoint metadata objects

    Example:
        GET /api/agents/backend-worker-001/flash-save/checkpoints?limit=5
        Response: [
            {
                "id": 42,
                "agent_id": "backend-worker-001",
                "items_count": 50,
                "items_archived": 20,
                "hot_items_retained": 15,
                "token_count": 150000,
                "created_at": "2025-11-14T10:30:00Z"
            },
            ...
        ]
    """
    # Clamp limit to reasonable range
    limit = min(max(limit, 1), 100)

    # Get checkpoints from database
    checkpoints = db.list_checkpoints(agent_id, limit=limit)

    # Remove checkpoint_data from response (too large)
    for checkpoint in checkpoints:
        checkpoint.pop("checkpoint_data", None)

    return checkpoints


@router.get("/api/agents/{agent_id}/context/stats")
async def get_context_stats(agent_id: str, project_id: int, db: Database = Depends(get_db)):
    """Get context statistics for an agent (T067).

    Returns tier counts and token usage breakdown for an agent's context.

    Args:
        agent_id: Agent ID to get stats for
        project_id: Project ID the agent is working on
        db: Database instance (injected)

    Returns:
        200 OK: ContextStats object with tier counts and token usage

    Example:
        GET /api/agents/backend-worker-001/context/stats?project_id=123
        Response: {
            "agent_id": "backend-worker-001",
            "project_id": 123,
            "hot_count": 20,
            "warm_count": 50,
            "cold_count": 30,
            "total_count": 100,
            "hot_tokens": 15000,
            "warm_tokens": 25000,
            "cold_tokens": 10000,
            "total_tokens": 50000,
            "token_usage_percentage": 27.8,
            "calculated_at": "2025-11-14T10:30:00Z"
        }
    """
    # Get all context items for this agent
    hot_items = db.list_context_items(
        project_id=project_id, agent_id=agent_id, tier="hot", limit=10000
    )

    warm_items = db.list_context_items(
        project_id=project_id, agent_id=agent_id, tier="warm", limit=10000
    )

    cold_items = db.list_context_items(
        project_id=project_id, agent_id=agent_id, tier="cold", limit=10000
    )

    # Calculate token counts per tier
    token_counter = TokenCounter(cache_enabled=True)

    hot_tokens = token_counter.count_context_tokens(hot_items)
    warm_tokens = token_counter.count_context_tokens(warm_items)
    cold_tokens = token_counter.count_context_tokens(cold_items)

    total_tokens = hot_tokens + warm_tokens + cold_tokens

    # Calculate token usage percentage (out of 180k limit)
    TOKEN_LIMIT = 180000
    token_usage_percentage = (total_tokens / TOKEN_LIMIT) * 100 if TOKEN_LIMIT > 0 else 0.0

    return {
        "agent_id": agent_id,
        "project_id": project_id,
        "hot_count": len(hot_items),
        "warm_count": len(warm_items),
        "cold_count": len(cold_items),
        "total_count": len(hot_items) + len(warm_items) + len(cold_items),
        "hot_tokens": hot_tokens,
        "warm_tokens": warm_tokens,
        "cold_tokens": cold_tokens,
        "total_tokens": total_tokens,
        "token_usage_percentage": round(token_usage_percentage, 2),
        "calculated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/api/agents/{agent_id}/context/items")
async def get_context_items(
    agent_id: str,
    project_id: int,
    tier: Optional[str] = None,
    limit: int = 100,
    db: Database = Depends(get_db),
):
    """Get context items for an agent, optionally filtered by tier.

    Returns a list of context items with their content and metadata.

    Args:
        agent_id: Agent ID to get items for
        project_id: Project ID the agent is working on
        tier: Optional tier filter ('hot', 'warm', 'cold')
        limit: Maximum number of items to return (default: 100, max: 1000)
        db: Database instance (injected)

    Returns:
        200 OK: List of ContextItem objects

    Example:
        GET /api/agents/backend-worker-001/context/items?project_id=123&tier=hot&limit=20
    """
    # Clamp limit to reasonable range
    limit = min(max(limit, 1), 1000)

    # Validate tier if provided
    if tier and tier not in ["hot", "warm", "cold"]:
        raise HTTPException(
            status_code=400, detail="Invalid tier. Must be 'hot', 'warm', or 'cold'"
        )

    # Get items from database
    items = db.list_context_items(project_id=project_id, agent_id=agent_id, tier=tier, limit=limit)

    return items
