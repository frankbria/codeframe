"""Standardized API *error* responses for CodeFRAME v2.

Success payloads are returned bare — each v2 router declares its own response
model and FastAPI serializes it. There is no success envelope: one was defined
here originally (``ApiResponse``/``api_response``/``PaginatedResponse``) but no
endpoint ever adopted it, so #968 deleted it rather than keep advertising a
house style the codebase does not follow.

What every router does share is the error shape:

    {"error": "Error description", "detail": "Additional context", "code": "ERROR_CODE"}

Usage:
    from codeframe.ui.response_models import api_error, ErrorCodes

    raise HTTPException(
        status_code=404,
        detail=api_error("Item not found", ErrorCodes.NOT_FOUND, f"No item {item_id}"),
    )
"""

from typing import Optional


# ============================================================================
# Helper Functions
# ============================================================================


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
    # An upstream service (e.g. GitHub) rejected OUR stored credential.
    # Distinct from UNAUTHORIZED so it is never carried on a 401 — the web UI
    # treats any 401 as CodeFRAME session expiry and logs the user out (#734).
    UPSTREAM_AUTH_FAILED = "UPSTREAM_AUTH_FAILED"
    # An upstream service throttled us (GitHub rate limit). Distinct from
    # FORBIDDEN so a transient 429 is never read as "your token lacks a
    # scope" — that sent users to regenerate a working PAT (#956).
    RATE_LIMITED = "RATE_LIMITED"
    # The principal used up the operator's daily spend limit (#1303).
    SPEND_LIMIT_EXCEEDED = "SPEND_LIMIT_EXCEEDED"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


def internal_error(exc: BaseException, *, operation: str, logger=None) -> dict:
    """Log an unexpected exception and return a client-safe error body (#934).

    ``str(exc)`` on an unexpected exception leaks host filesystem paths, SQL,
    library internals and sometimes credentials in connection strings — to any
    authenticated tenant, and inside SSE ``error`` events too. The client gets a
    generic message plus a correlation id; the id is what ties their report to
    the full traceback in the operator's logs.

    Args:
        exc: The caught exception. Never rendered into the response.
        operation: Short human description, e.g. "generate PRD".
        logger: Logger to record against; falls back to this module's.

    Returns:
        A standard error dict carrying only the correlation id as detail.
    """
    import logging as _logging
    import uuid as _uuid

    correlation_id = str(_uuid.uuid4())
    (logger or _logging.getLogger(__name__)).error(
        "[%s] Failed to %s: %s", correlation_id, operation, exc, exc_info=True
    )
    return {
        "error": f"Failed to {operation}",
        "code": ErrorCodes.EXECUTION_FAILED,
        "detail": f"An internal error occurred. Reference: {correlation_id}",
        "correlation_id": correlation_id,
    }


def _llm_error_status() -> list:
    """(error class, HTTP status, code), most specific first.

    Auth is 502, never 401: the web UI treats any 401 as CodeFRAME session
    expiry and logs the user out (#734); this is the provider rejecting OUR
    key. A 403 from the provider is also an LLMAuthError (key valid, access
    denied), and the same reasoning applies.
    """
    from codeframe.adapters.llm.base import (
        LLMAuthError,
        LLMConnectionError,
        LLMError,
        LLMModelNotFoundError,
        LLMOverloadedError,
        LLMRateLimitError,
    )

    return [
        (LLMAuthError, 502, ErrorCodes.UPSTREAM_AUTH_FAILED),
        (LLMRateLimitError, 429, ErrorCodes.RATE_LIMITED),
        (LLMOverloadedError, 503, ErrorCodes.SERVICE_UNAVAILABLE),
        (LLMModelNotFoundError, 502, ErrorCodes.EXECUTION_FAILED),
        (LLMConnectionError, 502, ErrorCodes.SERVICE_UNAVAILABLE),
        (LLMError, 502, ErrorCodes.EXECUTION_FAILED),
    ]


def llm_error_code(error_type: str) -> Optional[str]:
    """The code for an LLM error class name, or None for anything else.

    For streams, whose error events carry the exception's class name rather
    than the exception.
    """
    for cls, _status, code in _llm_error_status():
        if cls.__name__ == error_type:
            return code
    return None


def llm_error_http(exc: BaseException, *, operation: str):
    """An HTTPException for a typed provider failure (#1328).

    The message is the adapter's own (``map_provider_error``): actionable, and
    built to name where a key came from, never the key. A route used to send
    these through ``internal_error`` as an opaque 500, so a rejected key read
    as a server fault.
    """
    from fastapi import HTTPException

    for cls, status, code in _llm_error_status():
        if isinstance(exc, cls):
            return HTTPException(status_code=status, detail=api_error(f"Failed to {operation}", code, str(exc)))
    raise TypeError(f"not an LLM error: {type(exc).__name__}")

