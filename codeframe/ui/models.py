"""Pydantic models for CodeFRAME API requests and responses.

Task: cf-11.1 - Request/Response models for project creation
Enhanced: cf-119 - OpenAPI documentation with examples
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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "my-web-app",
                "description": "A modern web application with React frontend and FastAPI backend",
                "source_type": "git_remote",
                "source_location": "https://github.com/example/my-web-app.git",
                "source_branch": "main",
                "workspace_name": "my-web-app-workspace"
            }
        }
    )

    # Required
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Project name (unique identifier, 1-100 characters)"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Project description explaining the purpose and scope (1-500 characters)"
    )

    # Optional - source configuration
    source_type: Optional[SourceType] = Field(
        default=SourceType.EMPTY,
        description="Source type for project initialization: 'git_remote' (clone from URL), "
                    "'local_path' (link existing directory), 'upload' (upload files), "
                    "'empty' (start fresh)"
    )
    source_location: Optional[str] = Field(
        default=None,
        description="Source location - Git URL for 'git_remote', filesystem path for 'local_path', "
                    "or upload filename for 'upload'. Required unless source_type is 'empty'."
    )
    source_branch: Optional[str] = Field(
        default="main",
        description="Git branch to clone (only used when source_type is 'git_remote')"
    )

    # Optional - workspace naming (auto-generated if not provided)
    workspace_name: Optional[str] = Field(
        default=None,
        description="Custom workspace directory name. If not provided, auto-generated from project name."
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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": 42,
                "project_id": 1,
                "files_modified": [
                    "src/components/Button.tsx",
                    "src/utils/validation.ts",
                    "tests/components/Button.test.tsx"
                ]
            }
        }
    )

    task_id: int = Field(..., description="Task ID associated with the code changes to review")
    project_id: int = Field(..., description="Project ID containing the task")
    files_modified: List[str] = Field(
        ...,
        description="List of file paths that were modified and should be reviewed"
    )


class QualityGatesRequest(BaseModel):
    """Request model for triggering quality gates.

    Sprint 10 - Phase 3: Quality Gates API (T065)
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "gate_types": ["tests", "linting", "type_check"]
            }
        }
    )

    gate_types: Optional[List[str]] = Field(
        default=None,
        description="Optional list of gate types to run. If not provided, all gates run. "
                    "Valid values: 'tests' (run test suite), 'type_check' (mypy/tsc), "
                    "'coverage' (code coverage), 'code_review' (AI review), 'linting' (ruff/eslint)"
    )


class ProjectResponse(BaseModel):
    """Response model for project data.

    Task: cf-11.1 - Create ProjectResponse model
    Updated cf-17.1: Added phase field for project phase tracking
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "my-web-app",
                "status": "running",
                "phase": "active",
                "created_at": "2026-02-03T10:30:00Z",
                "config": {
                    "tech_stack": "Python with FastAPI, React frontend",
                    "git_initialized": True
                }
            }
        }
    )

    id: int = Field(..., description="Unique project ID (auto-generated)")
    name: str = Field(..., description="Project name as specified during creation")
    status: str = Field(
        ...,
        description="Project execution status: 'init' (created), 'running' (agents active), "
                    "'paused' (manually paused), 'completed' (all tasks done), 'failed' (error state)"
    )
    phase: str = Field(
        default="discovery",
        description="Project lifecycle phase: 'discovery' (analyzing codebase), "
                    "'planning' (generating tasks), 'active' (development in progress), "
                    "'review' (code review), 'complete' (finished)"
    )
    created_at: str = Field(..., description="ISO 8601 timestamp of project creation (e.g., '2026-02-03T10:30:00Z')")
    config: Optional[dict] = Field(
        default=None,
        description="Optional project configuration including tech_stack, git settings, etc."
    )


class CheckpointCreateRequest(BaseModel):
    """Request model for creating a checkpoint (Sprint 10 Phase 4, T093)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "pre-refactor-auth",
                "description": "Checkpoint before refactoring authentication module",
                "trigger": "manual"
            }
        }
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Checkpoint name for identification (1-100 characters)"
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional description explaining the checkpoint purpose (max 500 characters)"
    )
    trigger: str = Field(
        default="manual",
        description="Trigger type: 'manual' (user-initiated), 'auto' (scheduled), "
                    "'phase_transition' (automatic on phase change)"
    )


class CheckpointResponse(BaseModel):
    """Response model for a checkpoint (Sprint 10 Phase 4, T092-T094)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 5,
                "project_id": 1,
                "name": "pre-refactor-auth",
                "description": "Checkpoint before refactoring authentication module",
                "trigger": "manual",
                "git_commit": "a1b2c3d4e5f6",
                "database_backup_path": "/backups/project_1/checkpoint_5.db",
                "context_snapshot_path": "/backups/project_1/checkpoint_5_context.json",
                "metadata": {
                    "task_count": 15,
                    "completed_tasks": 8,
                    "phase": "active"
                },
                "created_at": "2026-02-03T14:30:00Z"
            }
        }
    )

    id: int = Field(..., description="Unique checkpoint ID")
    project_id: int = Field(..., description="Project this checkpoint belongs to")
    name: str = Field(..., description="Checkpoint name")
    description: Optional[str] = Field(None, description="Optional checkpoint description")
    trigger: str = Field(..., description="What triggered checkpoint creation (manual/auto/phase_transition)")
    git_commit: str = Field(..., description="Git commit hash at checkpoint time")
    database_backup_path: str = Field(..., description="Path to database backup file")
    context_snapshot_path: str = Field(..., description="Path to context snapshot file")
    metadata: dict = Field(..., description="Checkpoint metadata including task counts, phase, etc.")
    created_at: str = Field(..., description="ISO 8601 timestamp of checkpoint creation")


class RestoreCheckpointRequest(BaseModel):
    """Request model for restoring a checkpoint (Sprint 10 Phase 4, T096-T097)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "confirm_restore": True
            }
        }
    )

    confirm_restore: bool = Field(
        default=False,
        description="If False, returns diff preview only. If True, actually restores the checkpoint. "
                    "Use False first to review changes before committing to restore."
    )


class CheckpointDiffResponse(BaseModel):
    """Response model for checkpoint diff (Sprint 10 Phase 4)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "files_changed": 12,
                "insertions": 245,
                "deletions": 89,
                "diff": "diff --git a/src/auth.py b/src/auth.py\n--- a/src/auth.py\n+++ b/src/auth.py\n@@ -10,6 +10,8 @@..."
            }
        }
    )

    files_changed: int = Field(..., description="Number of files changed since checkpoint")
    insertions: int = Field(..., description="Total number of lines inserted since checkpoint")
    deletions: int = Field(..., description="Total number of lines deleted since checkpoint")
    diff: str = Field(..., description="Full git diff output showing all changes since checkpoint")


# Multi-Agent Per Project API Models (Phase 3)


class AgentAssignmentRequest(BaseModel):
    """Request model for assigning an agent to a project."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "backend-agent-001",
                "role": "primary_backend"
            }
        }
    )

    agent_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Agent ID to assign to the project (1-100 characters)"
    )
    role: str = Field(
        default="worker",
        min_length=1,
        max_length=50,
        description="Agent's role in this project. Common roles: 'lead' (orchestrator), "
                    "'primary_backend', 'frontend', 'test', 'code_reviewer', 'worker' (default)"
    )


class AgentRoleUpdateRequest(BaseModel):
    """Request model for updating an agent's role on a project."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "code_reviewer"
            }
        }
    )

    role: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="New role for the agent. Common roles: 'lead', 'primary_backend', "
                    "'secondary_backend', 'frontend', 'test', 'code_reviewer'"
    )


class AgentMetricsResponse(BaseModel):
    """Response model for agent maturity metrics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_count": 25,
                "completed_count": 22,
                "completion_rate": 0.88,
                "avg_test_pass_rate": 0.95,
                "self_correction_rate": 0.76,
                "maturity_score": 0.85,
                "last_assessed": "2026-02-03T15:00:00Z"
            }
        }
    )

    task_count: Optional[int] = Field(None, description="Total number of tasks ever assigned to this agent")
    completed_count: Optional[int] = Field(None, description="Number of tasks successfully completed")
    completion_rate: Optional[float] = Field(
        None,
        description="Task completion rate as decimal (0.0-1.0). Calculated as completed_count/task_count."
    )
    avg_test_pass_rate: Optional[float] = Field(
        None,
        description="Average test pass rate across all completed tasks (0.0-1.0)"
    )
    self_correction_rate: Optional[float] = Field(
        None,
        description="Rate of first-attempt success without requiring fixes (0.0-1.0)"
    )
    maturity_score: Optional[float] = Field(
        None,
        description="Weighted overall maturity score combining all metrics (0.0-1.0)"
    )
    last_assessed: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp of when metrics were last calculated"
    )


class AgentAssignmentResponse(BaseModel):
    """Response model for agent assignment data."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "backend-agent-001",
                "type": "backend",
                "provider": "claude",
                "maturity_level": "senior",
                "status": "working",
                "current_task_id": 42,
                "last_heartbeat": "2026-02-03T15:30:00Z",
                "metrics": {
                    "task_count": 25,
                    "completed_count": 22,
                    "completion_rate": 0.88,
                    "maturity_score": 0.85
                },
                "assignment_id": 7,
                "role": "primary_backend",
                "assigned_at": "2026-02-01T09:00:00Z",
                "unassigned_at": None,
                "is_active": True
            }
        }
    )

    agent_id: str = Field(..., description="Unique agent identifier")
    type: str = Field(
        ...,
        description="Agent specialization type: 'lead' (orchestrator), 'backend', 'frontend', 'test', 'review'"
    )
    provider: Optional[str] = Field(
        None,
        description="LLM provider powering the agent: 'claude' (Anthropic), 'gpt4' (OpenAI)"
    )
    maturity_level: Optional[str] = Field(
        None,
        description="Agent maturity level based on performance: 'junior', 'mid', 'senior', 'expert'"
    )
    status: Optional[str] = Field(
        None,
        description="Current agent status: 'idle' (waiting for tasks), 'working' (executing task), "
                    "'blocked' (waiting for human input), 'offline' (not available)"
    )
    current_task_id: Optional[int] = Field(
        None,
        description="ID of the task currently being executed (null if idle)"
    )
    last_heartbeat: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp of last agent activity"
    )
    metrics: Optional[AgentMetricsResponse] = Field(
        None,
        description="Agent performance metrics (null if never assessed)"
    )
    assignment_id: int = Field(..., description="Unique ID for this project-agent assignment")
    role: str = Field(..., description="Agent's assigned role within this specific project")
    assigned_at: str = Field(..., description="ISO 8601 timestamp when agent was assigned to project")
    unassigned_at: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp when agent was removed from project (null if still active)"
    )
    is_active: bool = Field(..., description="True if agent is currently assigned and active on project")


class ProjectAssignmentResponse(BaseModel):
    """Response model for project assignment data (from agent perspective)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "name": "my-web-app",
                "description": "A modern web application",
                "status": "running",
                "phase": "active",
                "role": "primary_backend",
                "assigned_at": "2026-02-01T09:00:00Z",
                "unassigned_at": None,
                "is_active": True
            }
        }
    )

    project_id: int = Field(..., description="Unique project identifier")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description/purpose")
    status: str = Field(..., description="Project execution status (init/running/paused/completed/failed)")
    phase: str = Field(..., description="Project lifecycle phase (discovery/planning/active/review/complete)")
    role: str = Field(..., description="Agent's assigned role within this project")
    assigned_at: str = Field(..., description="ISO 8601 timestamp of assignment")
    unassigned_at: Optional[str] = Field(None, description="ISO 8601 timestamp of removal (null if active)")
    is_active: bool = Field(..., description="True if this assignment is currently active")


# ============================================================================
# Core Endpoint Response Models (Phase 2 OpenAPI Documentation)
# ============================================================================


class TaskResponse(BaseModel):
    """Response model for task data."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 42,
                "project_id": 1,
                "title": "Implement user authentication endpoint",
                "description": "Create POST /api/auth/login endpoint with JWT token generation",
                "status": "in_progress",
                "priority": 2,
                "workflow_step": 3,
                "assigned_to": "backend-agent-001",
                "depends_on": "41",
                "requires_mcp": False,
                "created_at": "2026-02-03T10:00:00Z",
                "updated_at": "2026-02-03T14:30:00Z"
            }
        }
    )

    id: int = Field(..., description="Unique task ID")
    project_id: int = Field(..., description="Project this task belongs to")
    title: str = Field(..., description="Task title/summary")
    description: str = Field(default="", description="Detailed task description")
    status: str = Field(
        ...,
        description="Task status: 'pending' (awaiting assignment), 'assigned' (agent assigned), "
                    "'in_progress' (being worked on), 'blocked' (waiting for human), "
                    "'completed' (done), 'failed' (error)"
    )
    priority: int = Field(
        ...,
        description="Task priority (0=critical, 1=high, 2=medium, 3=low, 4=backlog)"
    )
    workflow_step: int = Field(default=1, description="Workflow step number for ordering")
    assigned_to: Optional[str] = Field(None, description="Agent ID currently assigned to task")
    depends_on: Optional[str] = Field(None, description="Comma-separated list of task IDs this depends on")
    requires_mcp: bool = Field(default=False, description="Whether task requires MCP server access")
    created_at: str = Field(..., description="ISO 8601 timestamp of task creation")
    updated_at: Optional[str] = Field(None, description="ISO 8601 timestamp of last update")


class TaskListResponse(BaseModel):
    """Response model for paginated task list."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tasks": [
                    {
                        "id": 42,
                        "project_id": 1,
                        "title": "Implement user authentication",
                        "status": "in_progress",
                        "priority": 2
                    }
                ],
                "total": 25
            }
        }
    )

    tasks: List[dict] = Field(..., description="List of task objects")
    total: int = Field(..., description="Total number of tasks matching filter (before pagination)")


class ProjectListResponse(BaseModel):
    """Response model for project list."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "projects": [
                    {
                        "id": 1,
                        "name": "my-web-app",
                        "status": "running",
                        "phase": "active",
                        "created_at": "2026-02-01T09:00:00Z"
                    }
                ]
            }
        }
    )

    projects: List[dict] = Field(..., description="List of project objects accessible to the user")


class ProjectStatusResponse(BaseModel):
    """Response model for project status endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "name": "my-web-app",
                "status": "running",
                "phase": "active",
                "workflow_step": 3,
                "progress": {
                    "total_tasks": 25,
                    "completed_tasks": 15,
                    "in_progress_tasks": 3,
                    "blocked_tasks": 1,
                    "completion_percentage": 60.0
                }
            }
        }
    )

    project_id: int = Field(..., description="Project ID")
    name: str = Field(..., description="Project name")
    status: str = Field(..., description="Project execution status")
    phase: str = Field(..., description="Project lifecycle phase")
    workflow_step: int = Field(default=1, description="Current workflow step")
    progress: dict = Field(..., description="Progress metrics including task counts and completion percentage")


class ActivityItemResponse(BaseModel):
    """Response model for a single activity log item."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 100,
                "action": "task_completed",
                "timestamp": "2026-02-03T14:30:00Z",
                "details": {
                    "task_id": 42,
                    "task_title": "Implement authentication",
                    "agent_id": "backend-agent-001"
                }
            }
        }
    )

    id: int = Field(..., description="Activity log entry ID")
    action: str = Field(..., description="Action type (task_created, task_completed, blocker_created, etc.)")
    timestamp: str = Field(..., description="ISO 8601 timestamp of when action occurred")
    details: Optional[dict] = Field(None, description="Additional action-specific details")


class ActivityListResponse(BaseModel):
    """Response model for activity log list."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "activity": [
                    {
                        "id": 100,
                        "action": "task_completed",
                        "timestamp": "2026-02-03T14:30:00Z",
                        "details": {"task_id": 42}
                    }
                ]
            }
        }
    )

    activity: List[dict] = Field(..., description="List of activity log items, most recent first")


class PRDResponse(BaseModel):
    """Response model for PRD (Product Requirements Document) endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "1",
                "prd_content": "# My Web App PRD\n\n## Overview\nA modern web application...",
                "generated_at": "2026-02-01T10:00:00Z",
                "updated_at": "2026-02-03T14:00:00Z",
                "status": "available"
            }
        }
    )

    project_id: str = Field(..., description="Project ID (as string for API consistency)")
    prd_content: str = Field(..., description="PRD content in Markdown format")
    generated_at: str = Field(..., description="ISO 8601 timestamp of initial PRD generation")
    updated_at: str = Field(..., description="ISO 8601 timestamp of last PRD update")
    status: str = Field(
        ...,
        description="PRD status: 'available' (ready to use), 'generating' (being created), "
                    "'not_found' (no PRD exists)"
    )


class IssueResponse(BaseModel):
    """Response model for a single issue."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "issue-1",
                "issue_number": "1",
                "title": "User authentication not working",
                "description": "Login endpoint returns 500 error",
                "status": "open",
                "priority": 1,
                "depends_on": [],
                "proposed_by": "human",
                "created_at": "2026-02-03T09:00:00Z",
                "updated_at": "2026-02-03T14:00:00Z",
                "completed_at": None
            }
        }
    )

    id: str = Field(..., description="Issue ID")
    issue_number: str = Field(..., description="Human-readable issue number")
    title: str = Field(..., description="Issue title")
    description: str = Field(..., description="Detailed issue description")
    status: str = Field(..., description="Issue status (open, in_progress, resolved, closed)")
    priority: int = Field(..., description="Issue priority (0=critical to 4=backlog)")
    depends_on: List[str] = Field(default_factory=list, description="List of issue IDs this depends on")
    proposed_by: str = Field(..., description="Who created the issue: 'agent' or 'human'")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")
    completed_at: Optional[str] = Field(None, description="ISO 8601 completion timestamp (null if open)")


class IssuesListResponse(BaseModel):
    """Response model for issues list endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "issues": [
                    {
                        "id": "issue-1",
                        "issue_number": "1",
                        "title": "User authentication not working",
                        "status": "open"
                    }
                ],
                "total_issues": 5,
                "total_tasks": 25
            }
        }
    )

    issues: List[dict] = Field(..., description="List of issue objects")
    total_issues: int = Field(..., description="Total number of issues")
    total_tasks: int = Field(..., description="Total number of tasks across all issues")


class SessionStateResponse(BaseModel):
    """Response model for session state endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "last_session": {
                    "summary": "Completed authentication module, started on API endpoints",
                    "timestamp": "2026-02-02T18:00:00Z"
                },
                "next_actions": [
                    "Complete /api/users endpoint",
                    "Add input validation",
                    "Write unit tests"
                ],
                "progress_pct": 45.5,
                "active_blockers": [
                    {"id": 3, "title": "Need database credentials"}
                ]
            }
        }
    )

    last_session: dict = Field(
        ...,
        description="Summary of the last session including timestamp and what was accomplished"
    )
    next_actions: List[str] = Field(
        default_factory=list,
        description="List of recommended next actions for the current session"
    )
    progress_pct: float = Field(
        default=0.0,
        description="Overall project progress as percentage (0.0-100.0)"
    )
    active_blockers: List[dict] = Field(
        default_factory=list,
        description="List of active blockers requiring human attention"
    )


class AgentStartResponse(BaseModel):
    """Response model for agent start/pause/resume operations."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Starting Lead Agent for project 1",
                "status": "starting"
            }
        }
    )

    message: str = Field(..., description="Human-readable status message")
    status: str = Field(
        ...,
        description="Operation status: 'starting' (agent launching), 'running' (already active), "
                    "'completed' (discovery finished), 'paused', 'resumed'"
    )


class BlockerResponse(BaseModel):
    """Response model for blocker data."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 5,
                "project_id": 1,
                "task_id": 42,
                "blocker_type": "SYNC",
                "title": "Database credentials needed",
                "description": "Cannot connect to production database without credentials",
                "status": "PENDING",
                "priority": "high",
                "created_at": "2026-02-03T10:00:00Z",
                "expires_at": "2026-02-03T16:00:00Z",
                "resolved_at": None,
                "answer": None
            }
        }
    )

    id: int = Field(..., description="Unique blocker ID")
    project_id: int = Field(..., description="Project this blocker belongs to")
    task_id: Optional[int] = Field(None, description="Task that created the blocker (if any)")
    blocker_type: str = Field(
        ...,
        description="Blocker type: 'SYNC' (blocks task execution), 'ASYNC' (can continue with workaround)"
    )
    title: str = Field(..., description="Brief blocker title")
    description: str = Field(..., description="Detailed description of what's blocking progress")
    status: str = Field(
        ...,
        description="Blocker status: 'PENDING' (awaiting resolution), 'RESOLVED' (answered), "
                    "'EXPIRED' (timed out)"
    )
    priority: str = Field(..., description="Blocker priority: 'critical', 'high', 'medium', 'low'")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    expires_at: Optional[str] = Field(None, description="ISO 8601 expiration timestamp (for timed blockers)")
    resolved_at: Optional[str] = Field(None, description="ISO 8601 resolution timestamp")
    answer: Optional[str] = Field(None, description="Human-provided answer/resolution")


class BlockerListResponse(BaseModel):
    """Response model for blocker list endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "blockers": [
                    {
                        "id": 5,
                        "title": "Database credentials needed",
                        "status": "PENDING",
                        "blocker_type": "SYNC"
                    }
                ],
                "total": 3,
                "pending_count": 2,
                "sync_count": 1,
                "async_count": 2
            }
        }
    )

    blockers: List[dict] = Field(..., description="List of blocker objects")
    total: int = Field(..., description="Total number of blockers")
    pending_count: int = Field(..., description="Number of blockers in PENDING status")
    sync_count: int = Field(..., description="Number of SYNC (blocking) blockers")
    async_count: int = Field(..., description="Number of ASYNC (non-blocking) blockers")


class BlockerMetricsResponse(BaseModel):
    """Response model for blocker metrics endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "avg_resolution_time_seconds": 3600.5,
                "expiration_rate_percent": 15.0,
                "total_blockers": 20,
                "resolved_count": 15,
                "expired_count": 3,
                "pending_count": 2,
                "sync_count": 8,
                "async_count": 12
            }
        }
    )

    avg_resolution_time_seconds: Optional[float] = Field(
        None,
        description="Average time to resolve blockers in seconds (null if no resolved blockers)"
    )
    expiration_rate_percent: float = Field(
        ...,
        description="Percentage of blockers that expired without resolution"
    )
    total_blockers: int = Field(..., description="Total number of blockers ever created")
    resolved_count: int = Field(..., description="Number of blockers successfully resolved")
    expired_count: int = Field(..., description="Number of blockers that expired")
    pending_count: int = Field(..., description="Number of blockers currently pending")
    sync_count: int = Field(..., description="Total SYNC blockers")
    async_count: int = Field(..., description="Total ASYNC blockers")


class ErrorResponse(BaseModel):
    """Generic error response model for API errors."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Project 99 not found"
            }
        }
    )

    detail: str = Field(..., description="Error message describing what went wrong")
