"""Pydantic models for CodeFRAME API requests and responses.

Task: cf-11.1 - Request/Response models for project creation
"""

from enum import Enum
from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Optional, List


class SourceType(str, Enum):
    """Supported project source types."""

    GIT_REMOTE = "git_remote"
    LOCAL_PATH = "local_path"
    UPLOAD = "upload"
    EMPTY = "empty"


class ProjectCreateRequest(BaseModel):
    """Request model for creating a new project."""

    # Required
    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    description: str = Field(
        ..., min_length=1, max_length=500, description="Project description/purpose"
    )

    # Optional - source configuration
    source_type: Optional[SourceType] = Field(
        default=SourceType.EMPTY, description="Source type for project initialization"
    )
    source_location: Optional[str] = Field(
        default=None, description="Git URL, local path, or upload filename"
    )
    source_branch: Optional[str] = Field(
        default="main", description="Git branch to clone (for git_remote)"
    )

    # Optional - workspace naming (auto-generated if not provided)
    workspace_name: Optional[str] = Field(
        default=None, description="Custom workspace directory name"
    )

    @model_validator(mode="after")
    def validate_source(self):
        """Validate source_location is provided when source_type requires it."""
        if self.source_type != SourceType.EMPTY and not self.source_location:
            raise ValueError(f"source_location required when source_type={self.source_type}")
        return self


class ReviewRequest(BaseModel):
    """Request model for triggering code review.

    Sprint 9 - User Story 1: Review Agent API (T056)
    """

    task_id: int = Field(..., description="Task ID to review")
    project_id: int = Field(..., description="Project ID")
    files_modified: List[str] = Field(..., description="List of file paths to review")


class QualityGatesRequest(BaseModel):
    """Request model for triggering quality gates.

    Sprint 10 - Phase 3: Quality Gates API (T065)
    """

    gate_types: Optional[List[str]] = Field(
        default=None,
        description="Optional list of gate types to run (default: all gates). "
        "Valid values: 'tests', 'type_check', 'coverage', 'code_review', 'linting'",
    )


class ProjectResponse(BaseModel):
    """Response model for project data.

    Task: cf-11.1 - Create ProjectResponse model
    Updated cf-17.1: Added phase field for project phase tracking
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Unique project ID")
    name: str = Field(..., description="Project name")
    status: str = Field(..., description="Project status (init, planning, active, etc.)")
    phase: str = Field(
        default="discovery",
        description="Project phase (discovery, planning, active, review, complete)",
    )
    created_at: str = Field(..., description="ISO timestamp of project creation")
    config: Optional[dict] = Field(default=None, description="Optional project configuration")


class CheckpointCreateRequest(BaseModel):
    """Request model for creating a checkpoint (Sprint 10 Phase 4, T093)."""

    name: str = Field(..., min_length=1, max_length=100, description="Checkpoint name")
    description: Optional[str] = Field(None, max_length=500, description="Optional description")
    trigger: str = Field(
        default="manual", description="Trigger type (manual, auto, phase_transition)"
    )


class CheckpointResponse(BaseModel):
    """Response model for a checkpoint (Sprint 10 Phase 4, T092-T094)."""

    id: int
    project_id: int
    name: str
    description: Optional[str]
    trigger: str
    git_commit: str
    database_backup_path: str
    context_snapshot_path: str
    metadata: dict  # CheckpointMetadata as dict
    created_at: str  # ISO 8601 timestamp


class RestoreCheckpointRequest(BaseModel):
    """Request model for restoring a checkpoint (Sprint 10 Phase 4, T096-T097)."""

    confirm_restore: bool = Field(
        default=False, description="If False, show diff only. If True, restore checkpoint."
    )


class CheckpointDiffResponse(BaseModel):
    """Response model for checkpoint diff (Sprint 10 Phase 4)."""

    files_changed: int = Field(description="Number of files changed")
    insertions: int = Field(description="Number of lines inserted")
    deletions: int = Field(description="Number of lines deleted")
    diff: str = Field(description="Git diff output")


# Multi-Agent Per Project API Models (Phase 3)


class AgentAssignmentRequest(BaseModel):
    """Request model for assigning an agent to a project."""

    agent_id: str = Field(..., min_length=1, max_length=100, description="Agent ID to assign")
    role: str = Field(
        default="worker",
        min_length=1,
        max_length=50,
        description="Agent's role in this project (e.g., 'primary_backend', 'code_reviewer')",
    )


class AgentRoleUpdateRequest(BaseModel):
    """Request model for updating an agent's role on a project."""

    role: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="New role for the agent (e.g., 'primary_backend', 'secondary_backend')",
    )


class AgentMetricsResponse(BaseModel):
    """Response model for agent maturity metrics."""

    task_count: Optional[int] = Field(None, description="Total tasks assigned to agent")
    completed_count: Optional[int] = Field(None, description="Number of completed tasks")
    completion_rate: Optional[float] = Field(None, description="Task completion rate (0.0-1.0)")
    avg_test_pass_rate: Optional[float] = Field(None, description="Average test pass rate (0.0-1.0)")
    self_correction_rate: Optional[float] = Field(
        None, description="Rate of first-attempt success (0.0-1.0)"
    )
    maturity_score: Optional[float] = Field(None, description="Weighted maturity score (0.0-1.0)")
    last_assessed: Optional[str] = Field(None, description="ISO timestamp of last assessment")


class AgentAssignmentResponse(BaseModel):
    """Response model for agent assignment data."""

    agent_id: str = Field(..., description="Agent ID")
    type: str = Field(..., description="Agent type (lead, backend, frontend, test, review)")
    provider: Optional[str] = Field(None, description="LLM provider (claude, gpt4)")
    maturity_level: Optional[str] = Field(None, description="Agent maturity level")
    status: Optional[str] = Field(
        None, description="Agent status (idle, working, blocked, offline)"
    )
    current_task_id: Optional[int] = Field(None, description="Current task ID if agent is working")
    last_heartbeat: Optional[str] = Field(None, description="Last activity timestamp")
    metrics: Optional[AgentMetricsResponse] = Field(
        None, description="Agent maturity metrics (if assessed)"
    )
    assignment_id: int = Field(..., description="Assignment ID from project_agents junction table")
    role: str = Field(..., description="Role in this project")
    assigned_at: str = Field(..., description="Assignment timestamp")
    unassigned_at: Optional[str] = Field(
        None, description="Unassignment timestamp (NULL if still assigned)"
    )
    is_active: bool = Field(..., description="Whether agent is currently assigned to project")


class ProjectAssignmentResponse(BaseModel):
    """Response model for project assignment data (from agent perspective)."""

    project_id: int = Field(..., description="Project ID")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    status: str = Field(..., description="Project status")
    phase: str = Field(..., description="Project phase")
    role: str = Field(..., description="Agent's role in this project")
    assigned_at: str = Field(..., description="Assignment timestamp")
    unassigned_at: Optional[str] = Field(None, description="Unassignment timestamp")
    is_active: bool = Field(..., description="Whether assignment is active")
