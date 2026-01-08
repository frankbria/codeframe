"""Discovery workflow router.

This module handles discovery-related endpoints for projects,
allowing submission of discovery answers and retrieval of discovery progress.
"""

import asyncio
import os
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

from codeframe.persistence.database import Database
from codeframe.core.models import DiscoveryAnswer, DiscoveryAnswerResponse
from codeframe.agents.lead_agent import LeadAgent
from codeframe.ui.dependencies import get_db
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User
from codeframe.ui.shared import manager
from codeframe.ui.websocket_broadcasts import (
    broadcast_planning_started,
    broadcast_issues_generated,
    broadcast_tasks_decomposed,
    broadcast_tasks_ready,
    broadcast_planning_failed,
)

# Module logger
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/discovery", tags=["discovery"])


async def generate_prd_background(project_id: int, db: Database, api_key: str):
    """Background task to generate PRD after discovery completes.

    Broadcasts progress at each stage:
    1. prd_generation_started - Initial notification
    2. prd_generation_progress (gathering_data) - Collecting discovery answers
    3. prd_generation_progress (calling_llm) - Sending to Claude API
    4. prd_generation_progress (saving) - Saving PRD to database/file
    5. prd_generation_completed - Final notification
    6. Spawns planning automation as a separate async task

    Args:
        project_id: Project ID
        db: Database instance
        api_key: API key for Claude
    """
    async def broadcast_progress(stage: str, message: str, progress_pct: int = 0):
        """Helper to broadcast progress updates."""
        await manager.broadcast(
            {
                "type": "prd_generation_progress",
                "project_id": project_id,
                "stage": stage,
                "message": message,
                "progress_pct": progress_pct,
            },
            project_id=project_id,
        )

    try:
        logger.info(f"Starting PRD generation for project {project_id}")

        # Stage 1: Starting
        await manager.broadcast(
            {
                "type": "prd_generation_started",
                "project_id": project_id,
                "status": "generating",
            },
            project_id=project_id,
        )

        # Stage 2: Gathering discovery data
        await broadcast_progress(
            "gathering_data",
            "Gathering discovery answers...",
            10
        )
        agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)

        # Stage 3: Building prompt and calling LLM
        await broadcast_progress(
            "calling_llm",
            "Generating PRD with AI...",
            30
        )
        # Timeout after 120 seconds to prevent indefinite hangs
        PRD_GENERATION_TIMEOUT = 120  # seconds
        try:
            prd_content = await asyncio.wait_for(
                asyncio.to_thread(agent.generate_prd),
                timeout=PRD_GENERATION_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(f"PRD generation timed out after {PRD_GENERATION_TIMEOUT}s for project {project_id}")
            await manager.broadcast(
                {
                    "type": "prd_generation_failed",
                    "project_id": project_id,
                    "status": "failed",
                    "error": f"PRD generation timed out after {PRD_GENERATION_TIMEOUT} seconds. Please try again.",
                },
                project_id=project_id,
            )
            return  # Exit background task

        logger.info(f"PRD generated successfully for project {project_id}")

        # Stage 4: Saving PRD
        await broadcast_progress(
            "saving",
            "Saving PRD document...",
            80
        )

        # Update project phase to planning
        await asyncio.to_thread(
            db.update_project, project_id, {"phase": "planning"}
        )

        # Stage 5: Complete
        await manager.broadcast(
            {
                "type": "prd_generation_completed",
                "project_id": project_id,
                "status": "completed",
                "progress_pct": 100,
                "prd_preview": prd_content[:200] if prd_content else "",
            },
            project_id=project_id,
        )

        # Trigger planning automation as a non-blocking background task
        # This allows PRD completion to be reported immediately while planning runs
        def _handle_planning_exception(task: asyncio.Task) -> None:
            """Log any unhandled exceptions from background planning task."""
            if not task.cancelled() and task.exception():
                logger.error(
                    f"Unhandled exception in planning background task: {task.exception()}",
                    exc_info=task.exception()
                )

        planning_task = asyncio.create_task(generate_planning_background(project_id, db, api_key))
        planning_task.add_done_callback(_handle_planning_exception)

    except Exception as e:
        logger.error(f"Failed to generate PRD for project {project_id}: {e}", exc_info=True)
        # Broadcast error
        await manager.broadcast(
            {
                "type": "prd_generation_failed",
                "project_id": project_id,
                "status": "failed",
                "error": str(e),
            },
            project_id=project_id,
        )


async def generate_planning_background(project_id: int, db: Database, api_key: str):
    """Background task to generate issues and tasks after PRD completion.

    This function implements planning automation:
    1. planning_started - Notify automation begins
    2. generate_issues - Create issues from PRD
    3. issues_generated - Report issues created
    4. decompose_prd - Decompose issues into tasks
    5. tasks_decomposed - Report tasks created
    6. tasks_ready - Signal ready for user review

    Note: LeadAgent methods are synchronous and use the sync Anthropic client,
    so asyncio.to_thread() is appropriate for running them without blocking.

    Args:
        project_id: Project ID
        db: Database instance
        api_key: API key for Claude
    """
    # Configurable timeout for AI operations (default 2 minutes per operation)
    planning_timeout = float(os.environ.get("PLANNING_OPERATION_TIMEOUT", "120"))

    try:
        logger.info(f"Starting planning automation for project {project_id}")

        # Stage 1: Broadcast planning started
        await broadcast_planning_started(manager, project_id)

        # Initialize LeadAgent for issue/task generation
        agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)

        # Stage 2: Generate issues from PRD (with timeout)
        logger.info(f"Generating issues for project {project_id}")
        issues = await asyncio.wait_for(
            asyncio.to_thread(agent.generate_issues, sprint_number=1),
            timeout=planning_timeout
        )
        issue_count = len(issues) if issues else 0

        # Stage 3: Broadcast issues generated
        await broadcast_issues_generated(manager, project_id, issue_count)
        logger.info(f"Generated {issue_count} issues for project {project_id}")

        # Stage 4: Decompose PRD into tasks (with timeout)
        logger.info(f"Decomposing PRD into tasks for project {project_id}")
        decomposition_result = await asyncio.wait_for(
            asyncio.to_thread(agent.decompose_prd),
            timeout=planning_timeout
        )
        task_count = decomposition_result.get("tasks", 0) if decomposition_result else 0

        # Stage 5: Broadcast tasks decomposed
        await broadcast_tasks_decomposed(manager, project_id, task_count)
        logger.info(f"Decomposed into {task_count} tasks for project {project_id}")

        # Stage 6: Broadcast tasks ready for review
        await broadcast_tasks_ready(manager, project_id, task_count)
        logger.info(f"Planning automation completed for project {project_id}")

    except asyncio.TimeoutError:
        logger.error(
            f"Planning automation timed out for project {project_id} "
            f"(timeout={planning_timeout}s)",
            exc_info=True
        )
        await broadcast_planning_failed(manager, project_id, "Planning operation timed out")

    except Exception as e:
        logger.error(f"Planning automation failed for project {project_id}: {e}", exc_info=True)
        await broadcast_planning_failed(manager, project_id, str(e))


@router.post("/answer")
async def submit_discovery_answer(
    project_id: int,
    answer_data: DiscoveryAnswer,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
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

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

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
            # Trigger PRD generation in background
            background_tasks.add_task(
                generate_prd_background, project_id, db, api_key
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
async def get_discovery_progress(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
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

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

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
            # Use .get() with defaults to handle edge cases where keys may not exist
            discovery_data = {
                "state": status["state"],
                "progress_percentage": status.get("progress_percentage", 0.0),
                "answered_count": status.get("answered_count", 0),
                "total_required": status.get("total_required", 0),
            }

            # Add state-specific fields
            if status["state"] == "discovering":
                discovery_data["remaining_count"] = status.get("remaining_count", 0)
                # Map backend "text" field to frontend "question" field
                raw_question = status.get("current_question")
                if raw_question:
                    discovery_data["current_question"] = {
                        "id": raw_question.get("id", ""),
                        "question": raw_question.get("text", ""),  # Map text -> question
                        "category": raw_question.get("category", ""),
                    }
                else:
                    discovery_data["current_question"] = None

            if status["state"] == "completed":
                discovery_data["structured_data"] = status.get("structured_data")

            # Exclude "answers" field for security (contains raw user input)

        return {"project_id": project_id, "phase": project_phase, "discovery": discovery_data}

    except Exception as e:
        # Log error but don't expose internals
        raise HTTPException(
            status_code=500, detail=f"Error retrieving discovery progress: {str(e)}"
        )


@router.post("/restart")
async def restart_discovery(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Restart discovery when stuck in an invalid state.

    This endpoint resets discovery state to 'idle', allowing the user to
    start discovery fresh. Use this when discovery is stuck (e.g., state is
    'discovering' but no question is available).

    Args:
        project_id: Project ID
        db: Database instance (injected)
        current_user: Authenticated user (injected)

    Returns:
        Success message with new state

    Raises:
        HTTPException:
            - 400: Discovery cannot be restarted (e.g., already completed)
            - 403: User lacks project access
            - 404: Project not found
    """
    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check project phase - only allow restart during discovery phase
    if project.get("phase") not in ("discovery", None):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot restart discovery in {project.get('phase')} phase. "
            "Discovery can only be restarted during the discovery phase.",
        )

    # Initialize LeadAgent to get current state and reset
    try:
        agent = LeadAgent(project_id=project_id, db=db, api_key="dummy-key-for-reset")
        status = agent.get_discovery_status()

        # Don't allow restart if discovery is completed
        if status["state"] == "completed":
            raise HTTPException(
                status_code=400,
                detail="Discovery is already completed. Cannot restart completed discovery.",
            )

        # Reset discovery state
        agent.reset_discovery()

        # Broadcast discovery reset event
        await manager.broadcast(
            {
                "type": "discovery_reset",
                "project_id": project_id,
                "message": "Discovery has been reset. Click 'Start Discovery' to begin again.",
            },
            project_id=project_id,
        )

        logger.info(f"Discovery reset for project {project_id} by user {current_user.id}")

        return {
            "success": True,
            "message": "Discovery has been reset. You can now start discovery again.",
            "state": "idle",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restart discovery for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to restart discovery: {str(e)}"
        )


@router.post("/generate-prd")
async def retry_prd_generation(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retry PRD generation for a project with completed discovery.

    This endpoint allows retrying PRD generation if it previously failed,
    or manually triggering it if it wasn't started automatically.

    Args:
        project_id: Project ID
        background_tasks: FastAPI background tasks
        db: Database instance (injected)
        current_user: Authenticated user (injected)

    Returns:
        Success message indicating PRD generation has started

    Raises:
        HTTPException:
            - 400: Discovery not completed, or PRD already exists
            - 403: User lacks project access
            - 404: Project not found
            - 500: API key not configured
    """
    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify API key is available
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY environment variable is not set.",
        )

    # Check discovery state - must be completed
    try:
        agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)
        status = agent.get_discovery_status()

        if status["state"] != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Discovery must be completed before generating PRD. "
                f"Current state: {status['state']}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check discovery status for project {project_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to check discovery status: {str(e)}"
        )

    # Start PRD generation in background
    background_tasks.add_task(generate_prd_background, project_id, db, api_key)

    logger.info(f"PRD generation started for project {project_id} by user {current_user.id}")

    return {
        "success": True,
        "message": "PRD generation has been started. Watch for WebSocket updates.",
    }


@router.post("/generate-tasks")
async def generate_tasks(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Manually trigger task generation from PRD.

    This endpoint allows users to manually start task generation when the
    project is in the planning phase with a completed PRD. It reuses the
    existing generate_planning_background() function that handles issue
    creation and task decomposition.

    Args:
        project_id: Project ID
        background_tasks: FastAPI background tasks
        db: Database instance (injected)
        current_user: Authenticated user (injected)

    Returns:
        Success message indicating task generation has started

    Raises:
        HTTPException:
            - 400: Not in planning phase, PRD missing, or tasks already exist
            - 403: User lacks project access
            - 404: Project not found
            - 500: API key not configured
    """
    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify project is in planning phase
    current_phase = project.get("phase", "discovery")
    if current_phase != "planning":
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in planning phase to generate tasks. "
            f"Current phase: {current_phase}",
        )

    # Verify PRD exists
    prd = db.get_prd(project_id)
    if not prd:
        raise HTTPException(
            status_code=400,
            detail="PRD must be generated before task generation. "
            "Please complete PRD generation first.",
        )

    # Check if tasks already exist - return idempotent success instead of error
    # This improves UX for users who join late and miss WebSocket events
    existing_tasks = db.get_project_tasks(project_id)
    if existing_tasks:
        logger.info(
            f"Tasks already exist for project {project_id} "
            f"(count: {len(existing_tasks)}). Returning idempotent success."
        )
        return {
            "success": True,
            "message": "Tasks have already been generated for this project.",
            "tasks_already_exist": True,
        }

    # Verify API key is available
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY environment variable is not set.",
        )

    # Start task generation in background
    background_tasks.add_task(generate_planning_background, project_id, db, api_key)

    logger.info(f"Task generation started for project {project_id} by user {current_user.id}")

    return {
        "success": True,
        "message": "Task generation has been started. Watch for WebSocket updates.",
    }
