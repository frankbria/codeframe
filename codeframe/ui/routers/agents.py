"""Agent lifecycle and management router.

This module provides API endpoints for:
- Starting/stopping/pausing/resuming agents
- Agent-project assignments (multi-agent per project)
- Agent status and information
"""

import logging
import os
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse

from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User
from codeframe.ui.shared import running_agents, start_agent, manager
from codeframe.ui.services.agent_service import AgentService
from codeframe.agents.lead_agent import LeadAgent
from codeframe.ui.models import (
    AgentAssignmentRequest,
    AgentRoleUpdateRequest,
    AgentAssignmentResponse,
    ProjectAssignmentResponse,
    AgentStartResponse,
    ErrorResponse,
)
from codeframe.lib.rate_limiter import rate_limit_standard, rate_limit_ai


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api", tags=["agents"])


@router.post(
    "/projects/{project_id}/start",
    status_code=202,
    response_model=AgentStartResponse,
    summary="Start Lead Agent for project",
    description="Starts the Lead Agent for a project, initiating the discovery phase. "
                "Returns 202 Accepted immediately while the agent starts in the background. "
                "Idempotent: if the project is already running, returns current discovery status. "
                "If discovery is 'idle', restarts discovery; if 'discovering' or 'completed', returns that status.",
    responses={
        200: {"model": AgentStartResponse, "description": "Discovery already in progress or completed"},
        202: {"model": AgentStartResponse, "description": "Agent starting in background"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        500: {"model": ErrorResponse, "description": "ANTHROPIC_API_KEY not configured"},
    },
)
@rate_limit_ai()
async def start_project_agent(
    request: Request,
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start Lead Agent for a project (cf-10.2).

    Returns 202 Accepted immediately and starts agent in background.
    Checks discovery state when project is already running - if discovery
    is "idle", starts discovery; if "discovering" or "completed", returns
    appropriate status.

    Args:
        project_id: Project ID to start agent for
        background_tasks: FastAPI background tasks
        db: Database connection
        current_user: Authenticated user

    Returns:
        202 Accepted: Starting discovery (even if project status is "running" but discovery is "idle")
        200 OK: Discovery already in progress or completed
        404 Not Found: Project doesn't exist
        403 Forbidden: User lacks project access
        500 Internal Server Error: API key not configured

    Raises:
        HTTPException: 403 if unauthorized, 404 if project not found, 500 if API key not configured
    """
    # cf-10.2: Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # cf-10.2: Handle idempotent behavior - check discovery state if already running
    if project["status"] == ProjectStatus.RUNNING.value:
        # Check discovery state before returning "already running"
        # If discovery is idle, we should still start discovery
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                # First check if agent already exists in running_agents to avoid duplicate instantiation
                existing_agent = running_agents.get(project_id)
                if existing_agent:
                    # Reuse existing agent for status check
                    discovery_status = existing_agent.get_discovery_status()
                else:
                    # Create temporary agent only for status check (will be replaced by start_agent if needed)
                    temp_agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)
                    discovery_status = temp_agent.get_discovery_status()

                discovery_state = discovery_status.get("state", "idle")

                if discovery_state == "idle":
                    # Discovery not started - proceed to start discovery
                    logger.info(f"Project {project_id} is running but discovery is idle - starting discovery")
                    # Broadcast immediate feedback before background task starts
                    await manager.broadcast(
                        {
                            "type": "discovery_starting",
                            "project_id": project_id,
                            "status": "starting",
                            "timestamp": time.time(),
                        },
                        project_id=project_id
                    )
                    background_tasks.add_task(start_agent, project_id, db, running_agents, api_key)
                    return {"message": f"Starting discovery for project {project_id}", "status": "starting"}
                elif discovery_state == "discovering":
                    # Discovery already in progress
                    return JSONResponse(
                        status_code=200,
                        content={"message": f"Project {project_id} discovery already in progress", "status": "running"},
                    )
                elif discovery_state == "completed":
                    # Discovery completed
                    return JSONResponse(
                        status_code=200,
                        content={"message": f"Project {project_id} discovery already completed", "status": "completed"},
                    )
            except Exception as e:
                logger.warning(f"Failed to check discovery status for project {project_id}: {e}")
                # Fall back to normal start flow on error - try to start discovery
                # This is safer than blocking since start_agent handles duplicates gracefully
                background_tasks.add_task(start_agent, project_id, db, running_agents, api_key)
                return {"message": f"Starting discovery for project {project_id}", "status": "starting"}
        else:
            # No API key available - can't check discovery status or start
            return JSONResponse(
                status_code=200,
                content={"message": f"Project {project_id} is already running", "status": "running"},
            )

    # cf-10.2: Get API key from environment
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    # Broadcast immediate feedback before background task starts
    await manager.broadcast(
        {
            "type": "discovery_starting",
            "project_id": project_id,
            "status": "starting",
            "timestamp": time.time(),
        },
        project_id=project_id
    )

    # cf-10.2: Start agent in background task (non-blocking)
    background_tasks.add_task(start_agent, project_id, db, running_agents, api_key)

    # cf-10.2: Return 202 Accepted immediately
    return {"message": f"Starting Lead Agent for project {project_id}", "status": "starting"}


@router.post(
    "/projects/{project_id}/pause",
    summary="Pause project execution",
    description="Pauses all agent execution for a project. Running agents will complete their current step "
                "then pause. The project status changes to 'paused'. Safe to call even if no agent is running.",
    responses={
        200: {"description": "Project paused successfully"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
@rate_limit_standard()
async def pause_project(
    request: Request,
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause project execution.

    Args:
        project_id: Project ID to pause
        db: Database connection

    Returns:
        Success message

    Raises:
        HTTPException: 404 if project not found
    """
    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Use AgentService to pause agent
    agent_service = AgentService(db=db, running_agents=running_agents)
    paused = await agent_service.pause_agent(project_id)

    if paused:
        return {"success": True, "message": "Project paused"}
    else:
        # No agent running - just update status
        db.update_project(project_id, {"status": ProjectStatus.PAUSED})
        return {"success": True, "message": "Project paused (no agent was running)"}


@router.post(
    "/projects/{project_id}/resume",
    summary="Resume project execution",
    description="Resumes a paused project, restarting agent execution. Agents will continue with their "
                "assigned tasks from where they left off. The project status changes to 'running'.",
    responses={
        200: {"description": "Project resuming"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
@rate_limit_ai()
async def resume_project(
    request: Request,
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume project execution.

    Args:
        project_id: Project ID to resume
        db: Database connection

    Returns:
        Success message

    Raises:
        HTTPException: 404 if project not found
    """
    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Use AgentService to resume agent
    agent_service = AgentService(db=db, running_agents=running_agents)
    resumed = await agent_service.resume_agent(project_id)

    if resumed:
        return {"success": True, "message": "Project resuming"}
    else:
        # No agent running - just update status
        db.update_project(project_id, {"status": ProjectStatus.RUNNING})
        return {"success": True, "message": "Project status updated to running (no agent found)"}


@router.get(
    "/projects/{project_id}/agents",
    response_model=List[AgentAssignmentResponse],
    summary="Get agents assigned to project",
    description="Returns all agents currently assigned to a project with their roles, status, and metrics. "
                "Use active_only=False to also include previously unassigned agents for historical view.",
    responses={
        200: {"description": "List of agent assignments"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        500: {"model": ErrorResponse, "description": "Database error"},
    },
)
@rate_limit_standard()
async def get_project_agents(
    request: Request,
    project_id: int,
    active_only: bool = Query(
        True,
        alias="is_active",
        description="If True (default), only returns currently assigned agents. "
                    "If False, includes historical assignments."
    ),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all agents assigned to a project.

    Multi-Agent Per Project API (Phase 3) - Updated endpoint.

    Args:
        project_id: Project ID
        active_only: If True, only return currently assigned agents (default: True)
        db: Database connection

    Returns:
        List of agents with assignment metadata

    Raises:
        HTTPException: 404 if project not found, 500 on database error
    """
    import json

    try:
        # Verify project exists
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Authorization check
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get agents for project using database method
        agents = db.get_agents_for_project(project_id, active_only=active_only)

        # Parse metrics JSON for each agent
        for agent in agents:
            metrics_json = agent.get("metrics")
            if metrics_json:
                try:
                    agent["metrics"] = (
                        json.loads(metrics_json)
                        if isinstance(metrics_json, str)
                        else metrics_json
                    )
                except (json.JSONDecodeError, TypeError):
                    agent["metrics"] = None
            else:
                agent["metrics"] = None

        return agents
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching agents for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching agents: {str(e)}")


@router.post(
    "/projects/{project_id}/agents",
    status_code=201,
    summary="Assign agent to project",
    description="Assigns an agent to a project with a specific role. Each agent can only have one active "
                "assignment per project. Use different roles like 'primary_backend', 'frontend', 'test', etc. "
                "to organize multi-agent workflows.",
    responses={
        201: {"description": "Agent assigned successfully"},
        400: {"model": ErrorResponse, "description": "Agent already assigned to this project"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Project or agent not found"},
        500: {"model": ErrorResponse, "description": "Error assigning agent"},
    },
)
@rate_limit_standard()
async def assign_agent_to_project(
    request: Request,
    project_id: int,
    body: AgentAssignmentRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign an agent to a project.

    Multi-Agent Per Project API (Phase 3) - New endpoint.

    Args:
        project_id: Project ID
        request: Agent assignment request with agent_id and role
        db: Database connection

    Returns:
        dict with assignment_id and success message

    Raises:
        HTTPException: 400 if agent already assigned, 404 if project/agent not found, 500 on error
    """
    try:
        # Verify project exists
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Authorization check
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Verify agent exists
        agent = db.get_agent(body.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {body.agent_id} not found")

        # Check if agent is already assigned (active)
        existing = db.get_agent_assignment(project_id, body.agent_id)
        if existing and existing.get("is_active"):
            raise HTTPException(
                status_code=400,
                detail=f"Agent {body.agent_id} is already assigned to project {project_id}",
            )

        # Assign agent to project
        assignment_id = db.assign_agent_to_project(
            project_id=project_id, agent_id=body.agent_id, role=body.role
        )

        logger.info(
            f"Assigned agent {body.agent_id} to project {project_id} with role {body.role}"
        )

        return {
            "assignment_id": assignment_id,
            "message": f"Agent {body.agent_id} assigned to project {project_id} with role {body.role}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning agent to project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error assigning agent: {str(e)}")


@router.delete(
    "/projects/{project_id}/agents/{agent_id}",
    status_code=204,
    summary="Remove agent from project",
    description="Removes an agent from a project (soft delete). The assignment record is preserved "
                "with an unassigned_at timestamp for audit purposes. The agent can be re-assigned later.",
    responses={
        204: {"description": "Agent removed (no content)"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "No active assignment found for this agent/project"},
        500: {"model": ErrorResponse, "description": "Error removing agent"},
    },
)
@rate_limit_standard()
async def remove_agent_from_project(
    request: Request,
    project_id: int,
    agent_id: str,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove an agent from a project (soft delete).

    Multi-Agent Per Project API (Phase 3) - New endpoint.

    Args:
        project_id: Project ID
        agent_id: Agent ID to remove
        db: Database connection

    Returns:
        No content (204) on success

    Raises:
        HTTPException: 404 if assignment not found, 500 on error
    """
    try:
        # Verify project exists
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Authorization check
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Remove agent from project
        rows_affected = db.remove_agent_from_project(project_id, agent_id)

        if rows_affected == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No active assignment found for agent {agent_id} on project {project_id}",
            )

        logger.info(f"Removed agent {agent_id} from project {project_id}")

        return None  # 204 No Content
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing agent from project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error removing agent: {str(e)}")


@router.put(
    "/projects/{project_id}/agents/{agent_id}/role",
    response_model=AgentAssignmentResponse,
    summary="Update agent role on project",
    description="Updates the role of an assigned agent on a project. Use this to reassign agents "
                "to different responsibilities without removing and re-adding them.",
    responses={
        200: {"model": AgentAssignmentResponse, "description": "Role updated, returns full assignment details"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "No active assignment found"},
        500: {"model": ErrorResponse, "description": "Error updating agent role"},
    },
)
@rate_limit_standard()
async def update_agent_role(
    request: Request,
    project_id: int,
    agent_id: str,
    body: AgentRoleUpdateRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an agent's role on a project.

    Multi-Agent Per Project API (Phase 3) - New endpoint.

    Args:
        project_id: Project ID
        agent_id: Agent ID
        request: New role for the agent
        db: Database connection

    Returns:
        AgentAssignmentResponse with updated assignment details

    Raises:
        HTTPException: 404 if assignment not found, 500 on error
    """
    try:
        # Verify project exists
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Authorization check
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Update agent role
        rows_affected = db.reassign_agent_role(
            project_id=project_id, agent_id=agent_id, new_role=body.role
        )

        if rows_affected == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No active assignment found for agent {agent_id} on project {project_id}",
            )

        logger.info(f"Updated agent {agent_id} role to {body.role} on project {project_id}")

        # Fetch assignment details (junction table fields only)
        assignment = db.get_agent_assignment(project_id, agent_id)
        if not assignment:
            raise HTTPException(
                status_code=404,
                detail=f"Failed to retrieve updated assignment for agent {agent_id}",
            )

        # Fetch full agent details (type, provider, status, etc.)
        agent = db.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Merge assignment and agent data to create full AgentAssignmentResponse
        full_assignment = {
            # From agents table
            "agent_id": agent["id"],
            "type": agent["type"],
            "provider": agent.get("provider"),
            "maturity_level": agent.get("maturity_level"),
            "status": agent.get("status"),
            "current_task_id": agent.get("current_task_id"),
            "last_heartbeat": agent.get("last_heartbeat"),
            # From project_agents table
            "assignment_id": assignment["id"],
            "role": assignment["role"],
            "assigned_at": assignment["assigned_at"],
            "unassigned_at": assignment.get("unassigned_at"),
            "is_active": assignment["is_active"],
        }

        return full_assignment
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent role: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating agent role: {str(e)}")


@router.patch(
    "/projects/{project_id}/agents/{agent_id}",
    summary="Update agent role (PATCH)",
    description="Updates the role of an assigned agent on a project. This is a PATCH variant of "
                "the PUT endpoint, returning a simple success message instead of full assignment details.",
    responses={
        200: {"description": "Role updated successfully"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "No active assignment found"},
        422: {"model": ErrorResponse, "description": "Validation error in request body"},
        500: {"model": ErrorResponse, "description": "Error updating agent role"},
    },
)
@rate_limit_standard()
async def patch_agent_role(
    request: Request,
    project_id: int,
    agent_id: str,
    body: AgentRoleUpdateRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an agent's role on a project (PATCH variant).

    Multi-Agent Per Project API (Phase 3) - PATCH endpoint for consistency with tests.

    Args:
        project_id: Project ID
        agent_id: Agent ID
        body: New role for the agent
        db: Database connection

    Returns:
        dict with success message

    Raises:
        HTTPException: 404 if assignment not found, 422 for validation errors, 500 on error
    """
    try:
        # Verify project exists
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Authorization check
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Update agent role
        rows_affected = db.reassign_agent_role(
            project_id=project_id, agent_id=agent_id, new_role=body.role
        )

        if rows_affected == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No active assignment found for agent {agent_id} on project {project_id}",
            )

        logger.info(f"Updated agent {agent_id} role to {body.role} on project {project_id}")

        return {
            "message": f"Agent {agent_id} role updated to {body.role} on project {project_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent role: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating agent role: {str(e)}")


@router.get(
    "/agents/{agent_id}/projects",
    response_model=List[ProjectAssignmentResponse],
    summary="Get projects for agent",
    description="Returns all projects an agent is assigned to, with the agent's role in each project. "
                "Results are filtered to only include projects the authenticated user has access to. "
                "Use active_only=False to include historical assignments.",
    responses={
        200: {"description": "List of project assignments"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        404: {"model": ErrorResponse, "description": "Agent not found"},
        500: {"model": ErrorResponse, "description": "Database error"},
    },
)
@rate_limit_standard()
async def get_agent_projects(
    request: Request,
    agent_id: str,
    active_only: bool = Query(
        True,
        description="If True (default), only returns active assignments. If False, includes historical."
    ),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all projects an agent is assigned to.

    Multi-Agent Per Project API (Phase 3) - New endpoint.

    Args:
        agent_id: Agent ID
        active_only: If True, only return active assignments (default: True)
        db: Database connection
        current_user: Authenticated user

    Returns:
        List of projects with assignment metadata (filtered by user access)

    Raises:
        HTTPException: 404 if agent not found, 500 on database error
    """
    try:
        # Verify agent exists
        agent = db.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Get projects for agent using database method
        projects = db.get_projects_for_agent(agent_id, active_only=active_only)

        # Security: Filter to only include projects the user has access to
        filtered_projects = [
            project for project in projects
            if db.user_has_project_access(current_user.id, project["project_id"])
        ]

        return filtered_projects
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching projects for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching projects: {str(e)}")
