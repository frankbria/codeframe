"""Agent lifecycle and management router.

This module provides API endpoints for:
- Starting/stopping/pausing/resuming agents
- Agent-project assignments (multi-agent per project)
- Agent status and information
"""

import logging
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse

from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User
from codeframe.ui.shared import running_agents, start_agent
from codeframe.ui.services.agent_service import AgentService
from codeframe.ui.models import (
    AgentAssignmentRequest,
    AgentRoleUpdateRequest,
    AgentAssignmentResponse,
    ProjectAssignmentResponse,
)


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api", tags=["agents"])


@router.post("/projects/{project_id}/start", status_code=202)
async def start_project_agent(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start Lead Agent for a project (cf-10.2).

    Returns 202 Accepted immediately and starts agent in background.

    Args:
        project_id: Project ID to start agent for
        background_tasks: FastAPI background tasks
        db: Database connection
        current_user: Authenticated user

    Returns:
        202 Accepted with message
        200 OK if already running
        404 Not Found if project doesn't exist
        403 Forbidden if user lacks project access

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

    # cf-10.2: Handle idempotent behavior - already running
    if project["status"] == ProjectStatus.RUNNING.value:
        return JSONResponse(
            status_code=200,
            content={"message": f"Project {project_id} is already running", "status": "running"},
        )

    # cf-10.2: Get API key from environment
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    # cf-10.2: Start agent in background task (non-blocking)
    background_tasks.add_task(start_agent, project_id, db, running_agents, api_key)

    # cf-10.2: Return 202 Accepted immediately
    return {"message": f"Starting Lead Agent for project {project_id}", "status": "starting"}


@router.post("/projects/{project_id}/pause")
async def pause_project(project_id: int, db: Database = Depends(get_db), current_user: User = Depends(get_current_user)):
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


@router.post("/projects/{project_id}/resume")
async def resume_project(project_id: int, db: Database = Depends(get_db), current_user: User = Depends(get_current_user)):
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


@router.get("/projects/{project_id}/agents", response_model=List[AgentAssignmentResponse])
async def get_project_agents(
    project_id: int,
    active_only: bool = Query(True, alias="is_active"),
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


@router.post("/projects/{project_id}/agents", status_code=201, response_model=dict)
async def assign_agent_to_project(
    project_id: int,
    request: AgentAssignmentRequest,
    db: Database = Depends(get_db), current_user: User = Depends(get_current_user),
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
        agent = db.get_agent(request.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {request.agent_id} not found")

        # Check if agent is already assigned (active)
        existing = db.get_agent_assignment(project_id, request.agent_id)
        if existing and existing.get("is_active"):
            raise HTTPException(
                status_code=400,
                detail=f"Agent {request.agent_id} is already assigned to project {project_id}",
            )

        # Assign agent to project
        assignment_id = db.assign_agent_to_project(
            project_id=project_id, agent_id=request.agent_id, role=request.role
        )

        logger.info(
            f"Assigned agent {request.agent_id} to project {project_id} with role {request.role}"
        )

        return {
            "assignment_id": assignment_id,
            "message": f"Agent {request.agent_id} assigned to project {project_id} with role {request.role}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning agent to project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error assigning agent: {str(e)}")


@router.delete("/projects/{project_id}/agents/{agent_id}", status_code=204)
async def remove_agent_from_project(
    project_id: int,
    agent_id: str,
    db: Database = Depends(get_db), current_user: User = Depends(get_current_user),
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


@router.put("/projects/{project_id}/agents/{agent_id}/role", response_model=AgentAssignmentResponse)
async def update_agent_role(
    project_id: int,
    agent_id: str,
    request: AgentRoleUpdateRequest,
    db: Database = Depends(get_db), current_user: User = Depends(get_current_user),
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
            project_id=project_id, agent_id=agent_id, new_role=request.role
        )

        if rows_affected == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No active assignment found for agent {agent_id} on project {project_id}",
            )

        logger.info(f"Updated agent {agent_id} role to {request.role} on project {project_id}")

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


@router.patch("/projects/{project_id}/agents/{agent_id}")
async def patch_agent_role(
    project_id: int,
    agent_id: str,
    request: AgentRoleUpdateRequest,
    db: Database = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Update an agent's role on a project (PATCH variant).

    Multi-Agent Per Project API (Phase 3) - PATCH endpoint for consistency with tests.

    Args:
        project_id: Project ID
        agent_id: Agent ID
        request: New role for the agent
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
            project_id=project_id, agent_id=agent_id, new_role=request.role
        )

        if rows_affected == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No active assignment found for agent {agent_id} on project {project_id}",
            )

        logger.info(f"Updated agent {agent_id} role to {request.role} on project {project_id}")

        return {
            "message": f"Agent {agent_id} role updated to {request.role} on project {project_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent role: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating agent role: {str(e)}")


@router.get("/agents/{agent_id}/projects", response_model=List[ProjectAssignmentResponse])
async def get_agent_projects(
    agent_id: str,
    active_only: bool = Query(True),
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
