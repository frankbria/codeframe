"""Pydantic models for CodeFRAME API requests and responses.

Task: cf-11.1 - Request/Response models for project creation
"""

from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional


class ProjectType(str, Enum):
    """Supported project types."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    RUST = "rust"


class ProjectCreateRequest(BaseModel):
    """Request model for creating a new project.

    Task: cf-11.1 - Create ProjectCreateRequest Pydantic model
    """
    project_name: str = Field(..., description="Name of the project to create")
    project_type: ProjectType = Field(
        default=ProjectType.PYTHON,
        description="Type of project (python, javascript, typescript, etc.)"
    )

    @field_validator('project_name')
    @classmethod
    def validate_project_name(cls, v: str) -> str:
        """Validate project name is not empty."""
        if not v or not v.strip():
            raise ValueError("Project name cannot be empty")
        return v.strip()


class ProjectResponse(BaseModel):
    """Response model for project data.

    Task: cf-11.1 - Create ProjectResponse model
    """
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Unique project ID")
    name: str = Field(..., description="Project name")
    status: str = Field(..., description="Project status (init, planning, active, etc.)")
    created_at: str = Field(..., description="ISO timestamp of project creation")
    config: Optional[dict] = Field(default=None, description="Optional project configuration")
