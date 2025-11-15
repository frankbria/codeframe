"""Pydantic models for CodeFRAME API requests and responses.

Task: cf-11.1 - Request/Response models for project creation
"""

from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional


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
