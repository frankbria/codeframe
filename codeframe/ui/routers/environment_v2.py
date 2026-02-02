"""V2 Environment router - delegates to core/environment module.

This module provides v2-style API endpoints for environment validation
and tool management. Used to check if development tools are installed.

Routes:
    GET  /api/v2/env/check   - Quick environment validation
    GET  /api/v2/env/doctor  - Comprehensive diagnostics
    POST /api/v2/env/install - Install a missing tool
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.core.environment import EnvironmentValidator, ValidationResult, ToolInfo
from codeframe.core.installer import ToolInstaller
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/env", tags=["environment-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ToolInfoResponse(BaseModel):
    """Response for a single tool."""

    name: str
    path: Optional[str]
    version: Optional[str]
    status: str  # ToolStatus value
    is_available: bool


class ValidationResultResponse(BaseModel):
    """Response for environment validation."""

    project_type: str
    detected_tools: dict[str, ToolInfoResponse]
    missing_tools: list[str]
    optional_missing: list[str]
    health_score: float
    health_percent: int
    is_healthy: bool
    recommendations: list[str]
    warnings: list[str]
    conflicts: list[str]


class InstallToolRequest(BaseModel):
    """Request for installing a tool."""

    tool_name: str = Field(..., min_length=1, description="Tool to install")


class InstallResultResponse(BaseModel):
    """Response for tool installation."""

    success: bool
    tool_name: str
    message: str
    command_used: Optional[str]


# ============================================================================
# Helper Functions
# ============================================================================


def _tool_to_response(info: ToolInfo) -> ToolInfoResponse:
    """Convert a ToolInfo to a ToolInfoResponse."""
    return ToolInfoResponse(
        name=info.name,
        path=info.path,
        version=info.version,
        status=info.status.value,
        is_available=info.is_available,
    )


def _result_to_response(result: ValidationResult) -> ValidationResultResponse:
    """Convert a ValidationResult to a ValidationResultResponse."""
    return ValidationResultResponse(
        project_type=result.project_type,
        detected_tools={
            name: _tool_to_response(info)
            for name, info in result.detected_tools.items()
        },
        missing_tools=result.missing_tools,
        optional_missing=result.optional_missing,
        health_score=result.health_score,
        health_percent=int(result.health_score * 100),
        is_healthy=result.is_healthy,
        recommendations=result.recommendations,
        warnings=result.warnings,
        conflicts=result.conflicts,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/check", response_model=ValidationResultResponse)
async def check_environment(
    workspace: Workspace = Depends(get_v2_workspace),
) -> ValidationResultResponse:
    """Quick environment validation.

    Checks if required tools are installed and returns health score.

    Args:
        workspace: v2 Workspace

    Returns:
        Validation result with tool status and health score
    """
    try:
        validator = EnvironmentValidator()
        result = validator.validate_environment(workspace.repo_path)

        return _result_to_response(result)

    except Exception as e:
        logger.error(f"Failed to validate environment: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Validation failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/doctor", response_model=ValidationResultResponse)
async def run_doctor(
    workspace: Workspace = Depends(get_v2_workspace),
) -> ValidationResultResponse:
    """Comprehensive environment diagnostics.

    Performs deeper validation including optional tools, version compatibility,
    and provides detailed recommendations.

    Args:
        workspace: v2 Workspace

    Returns:
        Detailed validation result with recommendations
    """
    try:
        validator = EnvironmentValidator()

        # Doctor mode validates everything including optional tools
        result = validator.validate_environment(
            workspace.repo_path,
            # Include optional tools in the check
            optional_tools=["ruff", "black", "mypy", "pre-commit"],
        )

        return _result_to_response(result)

    except Exception as e:
        logger.error(f"Failed to run doctor: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Doctor failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.post("/install", response_model=InstallResultResponse)
async def install_tool(
    request: InstallToolRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> InstallResultResponse:
    """Install a missing tool.

    Attempts to install the specified tool using the appropriate
    package manager for the current environment.

    Args:
        request: Install request with tool name
        workspace: v2 Workspace

    Returns:
        Installation result

    Raises:
        HTTPException: 400 if tool unknown or installation fails
    """
    try:
        installer = ToolInstaller()

        # Check if tool is known
        if not installer.can_install(request.tool_name):
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    "Unknown tool",
                    ErrorCodes.INVALID_REQUEST,
                    f"Don't know how to install '{request.tool_name}'",
                ),
            )

        # Attempt installation (confirm=False for non-interactive server usage)
        result = installer.install_tool(request.tool_name, confirm=False)

        return InstallResultResponse(
            success=result.success,
            tool_name=result.tool_name,
            message=result.message,
            command_used=result.command_used,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install {request.tool_name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Installation failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/tools")
async def list_available_tools(
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict:
    """List tools that can be automatically installed.

    Args:
        workspace: v2 Workspace

    Returns:
        List of installable tools with their package managers
    """
    try:
        # List of tools known to be installable by ToolInstaller
        # These are aggregated from PipInstaller, NpmInstaller, CargoInstaller, SystemInstaller
        installable_tools = [
            # Python tools (pip/uv)
            {"name": "pytest", "category": "python", "description": "Python testing framework"},
            {"name": "ruff", "category": "python", "description": "Fast Python linter"},
            {"name": "mypy", "category": "python", "description": "Static type checker"},
            {"name": "black", "category": "python", "description": "Code formatter"},
            {"name": "flake8", "category": "python", "description": "Linting tool"},
            {"name": "pylint", "category": "python", "description": "Code analyzer"},
            {"name": "bandit", "category": "python", "description": "Security linter"},
            {"name": "pre-commit", "category": "python", "description": "Git hooks manager"},
            # Node.js tools (npm)
            {"name": "eslint", "category": "nodejs", "description": "JavaScript linter"},
            {"name": "prettier", "category": "nodejs", "description": "Code formatter"},
            {"name": "typescript", "category": "nodejs", "description": "TypeScript compiler"},
            # Rust tools (cargo)
            {"name": "rustfmt", "category": "rust", "description": "Rust formatter"},
            {"name": "clippy", "category": "rust", "description": "Rust linter"},
        ]

        return {
            "tools": installable_tools,
            "message": "Use POST /api/v2/env/install to install any of these tools",
        }

    except Exception as e:
        logger.error(f"Failed to list tools: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to list tools", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
