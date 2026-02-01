"""Standardized API response models for CodeFRAME v2.

This module provides consistent response and error formats for all v2 API endpoints.

Standard Response Format:
{
    "success": true,
    "data": { ... },
    "message": "Optional human-readable message"
}

Standard Error Format:
{
    "error": "Error description",
    "detail": "Additional context",
    "code": "ERROR_CODE"
}

Usage:
    from codeframe.ui.response_models import ApiResponse, api_response, ApiError

    @router.get("/items")
    async def list_items() -> ApiResponse[list[Item]]:
        items = get_items()
        return api_response(items, message="Retrieved 5 items")

    # For errors, raise HTTPException with ApiError detail
    raise HTTPException(status_code=404, detail=ApiError(
        error="Item not found",
        detail=f"No item with id {item_id}",
        code="ITEM_NOT_FOUND"
    ).model_dump())
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ============================================================================
# Standard Response Models
# ============================================================================


class ApiResponse(BaseModel, Generic[T]):
    """Standard API response wrapper.

    All successful responses should use this format for consistency.
    """

    success: bool = Field(default=True, description="Whether the request succeeded")
    data: T = Field(..., description="Response payload")
    message: Optional[str] = Field(default=None, description="Optional human-readable message")


class ApiError(BaseModel):
    """Standard API error format.

    Use this for HTTPException details to ensure consistent error responses.
    """

    error: str = Field(..., description="Error description")
    detail: Optional[str] = Field(default=None, description="Additional context")
    code: str = Field(..., description="Machine-readable error code")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response wrapper."""

    success: bool = Field(default=True)
    data: list[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    message: Optional[str] = Field(default=None)


# ============================================================================
# Helper Functions
# ============================================================================


def api_response(
    data: Any,
    message: Optional[str] = None,
) -> dict:
    """Create a standard API response dict.

    Args:
        data: Response payload
        message: Optional human-readable message

    Returns:
        Dict in standard response format

    Example:
        return api_response({"id": 1, "name": "test"}, message="Created successfully")
    """
    response = {
        "success": True,
        "data": data,
    }
    if message:
        response["message"] = message
    return response


def api_error(
    error: str,
    code: str,
    detail: Optional[str] = None,
) -> dict:
    """Create a standard API error dict for HTTPException detail.

    Args:
        error: Error description
        code: Machine-readable error code
        detail: Additional context

    Returns:
        Dict in standard error format

    Example:
        raise HTTPException(
            status_code=404,
            detail=api_error("Not found", "ITEM_NOT_FOUND", f"No item {id}")
        )
    """
    result = {
        "error": error,
        "code": code,
    }
    if detail:
        result["detail"] = detail
    return result


# ============================================================================
# Common Error Codes
# ============================================================================


class ErrorCodes:
    """Standard error codes for consistent error handling."""

    # Resource errors (4xx)
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    INVALID_REQUEST = "INVALID_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # Authorization errors
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"

    # State errors
    INVALID_STATE = "INVALID_STATE"
    CONFLICT = "CONFLICT"

    # Execution errors
    EXECUTION_FAILED = "EXECUTION_FAILED"
    TIMEOUT = "TIMEOUT"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# ============================================================================
# Common Success Messages
# ============================================================================


def created_message(resource: str, id: Any = None) -> str:
    """Generate a standard created message."""
    if id:
        return f"{resource} created successfully (id: {id})"
    return f"{resource} created successfully"


def updated_message(resource: str, id: Any = None) -> str:
    """Generate a standard updated message."""
    if id:
        return f"{resource} updated successfully (id: {id})"
    return f"{resource} updated successfully"


def deleted_message(resource: str, id: Any = None) -> str:
    """Generate a standard deleted message."""
    if id:
        return f"{resource} deleted successfully (id: {id})"
    return f"{resource} deleted successfully"


def retrieved_message(resource: str, count: Optional[int] = None) -> str:
    """Generate a standard retrieval message."""
    if count is not None:
        return f"Retrieved {count} {resource}(s)"
    return f"{resource} retrieved successfully"
