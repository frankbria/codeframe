"""Discovery workflow router.

This module handles discovery-related endpoints for projects,
allowing submission of discovery answers and retrieval of discovery progress.
"""

import os
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends

from codeframe.persistence.database import Database
from codeframe.core.models import DiscoveryAnswer, DiscoveryAnswerResponse
from codeframe.agents.lead_agent import LeadAgent
from codeframe.ui.dependencies import get_db
from codeframe.ui.shared import manager

# Module logger
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/discovery", tags=["discovery"])


@router.post("/answer")
async def submit_discovery_answer(
    project_id: int, answer_data: DiscoveryAnswer, db: Database = Depends(get_db)
) -> DiscoveryAnswerResponse:
    """Submit answer to current discovery question (Feature: 012-discovery-answer-ui, US5).

    Implementation following TDD approach (T041-T044):
    - Validates project exists and is in discovery phase
    - Processes answer through Lead Agent
    - Broadcasts WebSocket events for real-time UI updates
    - Returns updated discovery status

    Args:
        project_id: Project ID
        answer_data: Answer submission data (Pydantic model with validation)
        db: Database instance (injected)

    Returns:
        DiscoveryAnswerResponse with next question and progress

    Raises:
        HTTPException:
            - 400: Validation error or wrong phase
            - 404: Project not found
            - 500: Missing API key or processing error
    """
    from codeframe.ui.websocket_broadcasts import (
        broadcast_discovery_answer_submitted,
        broadcast_discovery_question_presented,
        broadcast_discovery_completed,
    )

    # T041: Validate project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # T041: Validate project is in discovery phase
    if project.get("phase") != "discovery":
        raise HTTPException(
            status_code=400,
            detail=f"Project is not in discovery phase. Current phase: {project.get('phase')}",
        )

    # T042: Validate ANTHROPIC_API_KEY is available
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY environment variable is not set. Cannot process discovery answers.",
        )

    # T042: Get Lead Agent and process answer
    try:
        agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)

        # CRITICAL: Validate discovery is active before processing answer
        status = agent.get_discovery_status()
        if status.get("state") != "discovering":
            raise HTTPException(
                status_code=400,
                detail=f"Discovery is not active. Current state: {status.get('state')}. "
                f"Please start discovery first by calling POST /api/projects/{project_id}/discovery/start",
            )

        # Process the answer (trimmed by Pydantic validator)
        agent.process_discovery_answer(answer_data.answer)

        # Get updated discovery status after processing
        status = agent.get_discovery_status()

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Failed to process discovery answer for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process answer: {str(e)}")

    # T043: Compute derived values from status to match LeadAgent.get_discovery_status() format
    is_complete = status.get("state") == "completed"
    total_questions = status.get("total_required", 0)
    answered_count = status.get("answered_count", 0)
    current_question_index = answered_count  # Index is based on how many answered
    current_question_id = status.get("current_question", {}).get("id", "")
    current_question_text = status.get("current_question", {}).get("text", "")
    progress_percentage = status.get("progress_percentage", 0.0)

    # T043: Broadcast WebSocket events
    try:
        # Broadcast answer submitted event
        await broadcast_discovery_answer_submitted(
            manager=manager,
            project_id=project_id,
            question_id=current_question_id,
            answer_preview=answer_data.answer[:100],  # First 100 chars
            current_index=current_question_index,
            total_questions=total_questions,
        )

        # Broadcast appropriate follow-up event
        if is_complete:
            await broadcast_discovery_completed(
                manager=manager,
                project_id=project_id,
                total_answers=answered_count,
                next_phase="prd_generation",
            )
        else:
            await broadcast_discovery_question_presented(
                manager=manager,
                project_id=project_id,
                question_id=current_question_id,
                question_text=current_question_text,
                current_index=current_question_index,
                total_questions=total_questions,
            )

    except Exception as e:
        logger.warning(f"Failed to broadcast WebSocket events for project {project_id}: {e}")
        # Non-fatal - continue with response

    # T044: Generate and return response
    return DiscoveryAnswerResponse(
        success=True,
        next_question=current_question_text if not is_complete else None,
        is_complete=is_complete,
        current_index=current_question_index,
        total_questions=total_questions,
        progress_percentage=progress_percentage,
    )


@router.get("/progress")
async def get_discovery_progress(project_id: int, db: Database = Depends(get_db)) -> Dict[str, Any]:
    """Get discovery progress for a project (cf-17.2).

    Returns discovery progress combined with project phase.

    Response format:
        {
            "project_id": int,
            "phase": str,  # Project phase (discovery, planning, development, etc.)
            "discovery": {  # null if discovery not started (idle state)
                "state": str,  # idle, discovering, completed
                "progress_percentage": float,  # 0-100
                "answered_count": int,
                "total_required": int,
                "remaining_count": int,  # Only in discovering state
                "current_question": dict,  # Only in discovering state
                "structured_data": dict  # Only in completed state
            }
        }

    Args:
        project_id: Project ID
        db: Database instance (injected)

    Returns:
        Discovery progress response

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get project phase (default to "discovery" if not set)
    project_phase = project.get("phase", "discovery")

    # Initialize LeadAgent to get discovery status
    # Use dummy API key for status retrieval (no API calls made)
    try:
        agent = LeadAgent(project_id=project_id, db=db, api_key="dummy-key-for-status")

        # Get discovery status
        status = agent.get_discovery_status()

        # If discovery is in idle state, return null for discovery field
        if status["state"] == "idle":
            discovery_data = None
        else:
            # Build discovery response, excluding sensitive fields
            discovery_data = {
                "state": status["state"],
                "progress_percentage": status["progress_percentage"],
                "answered_count": status["answered_count"],
                "total_required": status["total_required"],
            }

            # Add state-specific fields
            if status["state"] == "discovering":
                discovery_data["remaining_count"] = status["remaining_count"]
                discovery_data["current_question"] = status.get("current_question")

            if status["state"] == "completed":
                discovery_data["structured_data"] = status.get("structured_data")

            # Exclude "answers" field for security (contains raw user input)

        return {"project_id": project_id, "phase": project_phase, "discovery": discovery_data}

    except Exception as e:
        # Log error but don't expose internals
        raise HTTPException(
            status_code=500, detail=f"Error retrieving discovery progress: {str(e)}"
        )
