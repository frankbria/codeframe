"""Authentication dependencies for route handlers.

Supports dual authentication:
- JWT Bearer tokens (existing FastAPI Users integration)
- API keys via X-API-Key header (new for programmatic access)

API keys use scope-based permissions (read, write, admin).
JWT tokens get full permissions for backward compatibility.
"""

import logging
import os
import re
from typing import Callable, Dict, Optional, Any, Tuple

from fastapi import Depends, HTTPException, Request, Security, WebSocket, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

from codeframe.auth.models import User
from codeframe.auth.api_keys import (
    extract_prefix,
    verify_api_key,
    SCOPE_READ,
    SCOPE_WRITE,
    SCOPE_ADMIN,
)
from codeframe.auth.scopes import has_scope

logger = logging.getLogger(__name__)

# Security schemes
security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Truthy/falsy values for CODEFRAME_AUTH_REQUIRED (case-insensitive).
_AUTH_FALSY = {"0", "false", "no", "off"}

# Routes allowed to authenticate via a ?token=<JWT> query parameter. Browser
# EventSource (SSE) cannot send an Authorization header, so these streaming
# routes accept the token in the URL — the same trade-off the WebSocket
# routes already make. Keep this list tight: query-string credentials can
# leak via proxy/access logs and browser history, so the fallback must NOT
# apply to the rest of the API (codex review P2, issue #336).
_QUERY_TOKEN_PATHS = (
    re.compile(r"^/api/v2/tasks/[^/]+/stream$"),  # task event stream (SSE)
    re.compile(r"^/api/v2/prd/stress-test$"),  # PRD stress-test stream (SSE)
)


def _query_token_allowed(path: str) -> bool:
    """Whether this request path may authenticate via ?token= (SSE only)."""
    return any(pattern.match(path) for pattern in _QUERY_TOKEN_PATHS)


def auth_required() -> bool:
    """Whether authentication is enforced, read from the environment.

    Controlled by ``CODEFRAME_AUTH_REQUIRED`` (default ON / secure by default).
    Read at request time so tests can monkeypatch the value per call.

    Falsy values (case-insensitive): ``0``, ``false``, ``no``, ``off``.
    Anything else (including unset) is treated as enabled.
    """
    value = os.getenv("CODEFRAME_AUTH_REQUIRED")
    if value is None:
        return True
    return value.strip().lower() not in _AUTH_FALSY


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Get currently authenticated user.

    Requires a valid JWT, supplied as an ``Authorization: Bearer`` header.
    On the allowlisted SSE routes only (``_QUERY_TOKEN_PATHS``), a
    ``?token=<JWT>`` query parameter is accepted when no header is present
    (browser EventSource cannot send headers; mirrors the WebSocket
    auth pattern).

    Args:
        request: FastAPI request object
        credentials: Bearer token from Authorization header (optional)

    Returns:
        Authenticated user

    Raises:
        HTTPException: 401 if authentication not provided or invalid
    """
    # Resolve the bearer token from the Authorization header. Only the
    # allowlisted SSE routes may fall back to a ?token= query parameter
    # (EventSource cannot send headers); everywhere else query-string
    # credentials are rejected to keep them out of logs/history.
    token: Optional[str] = None
    if credentials and getattr(credentials, "credentials", None):
        token = credentials.credentials
    elif request is not None and _query_token_allowed(request.url.path):
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate JWT token
    try:
        import jwt as pyjwt
        from codeframe.auth.manager import (
            SECRET,
            JWT_ALGORITHM,
            JWT_AUDIENCE,
            get_async_session_maker,
        )
        from sqlalchemy import select

        # Decode JWT token directly using PyJWT
        # Note: We use direct PyJWT decoding instead of JWTStrategy.read_token()
        # because read_token() requires a user_manager instance, which would
        # create a circular dependency. The JWT constants are centralized in
        # auth.manager to ensure consistency with the JWTStrategy configuration.
        try:
            payload = pyjwt.decode(
                token,
                SECRET,
                algorithms=[JWT_ALGORITHM],
                audience=JWT_AUDIENCE,
            )
            user_id_str = payload.get("sub")
            if not user_id_str:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing subject",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user_id = int(user_id_str)
        except pyjwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (pyjwt.InvalidTokenError, ValueError) as e:
            logger.debug(f"JWT decode error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user from database
        async_session_maker = get_async_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User is inactive",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return user

    except HTTPException:
        raise
    except Exception as e:
        # Log full error server-side for debugging
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        # Return generic message to client (avoid leaking implementation details)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """Get currently authenticated user, or None if not authenticated.

    Non-raising version for endpoints that optionally use authentication.
    """
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


# =============================================================================
# API Key Authentication
# =============================================================================


async def get_api_key_auth(
    api_key: Optional[str] = Security(api_key_header),
    request: Request = None,
) -> Optional[Dict[str, Any]]:
    """Extract and validate API key from X-API-Key header.

    Args:
        api_key: API key from header (auto-extracted by FastAPI Security)
        request: FastAPI request object (for accessing db via state)

    Returns:
        Auth dict if valid API key, None otherwise.
        Dict contains: type, user_id, scopes, key_id
    """
    if not api_key:
        return None

    try:
        # Get database from app state (singleton) or request state
        db = getattr(request.app.state, "db", None)
        if db is None:
            db = getattr(request.state, "db", None)
        if db is None:
            # Fallback: create database connection
            logger.warning("No db in app.state, creating fallback connection for API key auth")
            import os
            from codeframe.platform_store.database import Database

            db_path = os.getenv(
                "DATABASE_PATH",
                os.path.join(os.getcwd(), ".codeframe", "state.db")
            )
            db = Database(db_path)
            db.initialize()
            # Store on request state so it can be cleaned up by middleware
            if request is not None:
                request.state.db = db

        # Extract prefix and look up key
        try:
            prefix = extract_prefix(api_key)
        except ValueError:
            logger.warning("API key auth failed: invalid key format")
            return None

        key_record = db.api_keys.get_by_prefix(prefix)
        if key_record is None:
            logger.warning(f"API key auth failed: key not found (prefix: {prefix[:4]}...)")
            return None

        # Verify the full key against stored hash
        if not verify_api_key(api_key, key_record["key_hash"]):
            logger.warning(f"API key auth failed: verification failed (prefix: {prefix[:4]}...)")
            return None

        # Update last used timestamp (fire and forget)
        try:
            db.api_keys.update_last_used(key_record["id"])
        except Exception as e:
            logger.warning(f"Failed to update last_used_at: {e}")

        return {
            "type": "api_key",
            "user_id": key_record["user_id"],
            "scopes": key_record["scopes"],
            "key_id": key_record["id"],
        }

    except Exception as e:
        logger.debug(f"API key authentication error: {e}")
        return None


async def require_auth(
    api_key_auth: Optional[Dict[str, Any]] = Depends(get_api_key_auth),
    jwt_user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    """Require authentication via either API key or JWT token.

    API keys take precedence if both are present.

    Args:
        api_key_auth: Result from get_api_key_auth (if API key provided)
        jwt_user: Result from get_current_user_optional (if JWT provided)

    Returns:
        Auth dict with: type, user_id, scopes, and optional user/key_id

    Raises:
        HTTPException: 401 if no valid authentication provided
    """
    # Prefer API key if provided
    if api_key_auth is not None:
        return api_key_auth

    # Fall back to JWT
    if jwt_user is not None:
        return {
            "type": "jwt",
            "user_id": jwt_user.id,
            # JWT users get all scopes for backward compatibility
            "scopes": [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN],
            "user": jwt_user,
        }

    # Auth disabled (local opt-out): return a synthetic local-admin principal
    # instead of raising. Real credentials above always take precedence.
    if not auth_required():
        return {
            "type": "disabled",
            "user_id": None,
            "scopes": [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN],
        }

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer, ApiKey"},
    )


async def authenticate_websocket(
    websocket: WebSocket,
    *,
    close_code: int,
) -> Tuple[bool, Optional[int]]:
    """Authenticate a WebSocket connection, honoring the no-auth opt-out.

    This is the single source of truth for WebSocket auth so the terminal and
    session-chat sockets cannot drift from the REST behavior of ``require_auth()``:

    - When auth is disabled (``CODEFRAME_AUTH_REQUIRED`` falsy), returns
      ``(True, None)`` without requiring a token — the same synthetic local
      principal (``user_id=None``) REST admits in no-auth mode.
    - Otherwise validates the ``?token=<JWT>`` query parameter (decode → subject
      → active DB user). On success returns ``(True, user_id)``. On any failure
      the socket is closed with ``close_code`` and ``(False, None)`` is returned.

    Args:
        websocket: The incoming WebSocket connection (not yet accepted).
        close_code: Close code to use when rejecting (callers pass their existing
            code, e.g. ``4001`` for terminal, ``1008`` for session chat).

    Returns:
        ``(authenticated, user_id)``. ``user_id`` is ``None`` both in no-auth
        mode and on failure — callers gate on the boolean, not on ``user_id``.
    """
    # Single source of truth for the no-auth opt-out — shared with require_auth().
    if not auth_required():
        return True, None

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=close_code, reason="Authentication required: missing token")
        return False, None

    import jwt as pyjwt
    from sqlalchemy import select

    from codeframe.auth import manager
    from codeframe.auth.manager import (
        JWT_ALGORITHM,
        JWT_AUDIENCE,
        get_async_session_maker,
    )

    try:
        # Read manager.SECRET live: it may be refreshed from .env at server
        # startup (after import), so binding the value at import would stale it.
        payload = pyjwt.decode(
            token, manager.SECRET, algorithms=[JWT_ALGORITHM], audience=JWT_AUDIENCE
        )
        user_id_str = payload.get("sub")
        if not user_id_str:
            await websocket.close(code=close_code, reason="Invalid token: missing subject")
            return False, None
        user_id = int(user_id_str)
    except pyjwt.ExpiredSignatureError:
        await websocket.close(code=close_code, reason="Token expired")
        return False, None
    except (pyjwt.InvalidTokenError, ValueError) as exc:
        logger.debug("WebSocket JWT decode error: %s", exc)
        await websocket.close(code=close_code, reason="Invalid authentication token")
        return False, None

    try:
        async_session_maker = get_async_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                await websocket.close(code=close_code, reason="User not found")
                return False, None
            if not user.is_active:
                await websocket.close(code=close_code, reason="User is inactive")
                return False, None
    except Exception as exc:
        logger.error("WebSocket user lookup error: %s", exc)
        await websocket.close(code=close_code, reason="Authentication failed")
        return False, None

    return True, user_id


def require_scope(required_scope: str) -> Callable:
    """Create a dependency that checks for a required scope.

    Scope Hierarchy:
        - admin: grants read, write, and admin permissions
        - write: grants read and write permissions
        - read: grants read permission only

    Usage:
        @router.post("/resource")
        async def create_resource(auth: dict = Depends(require_scope("write"))):
            ...

    Args:
        required_scope: The scope required for access (read, write, or admin)

    Returns:
        Dependency function that validates scope
    """
    async def check_scope(auth: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
        """Verify principal has required scope."""
        if not has_scope(auth, required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: '{required_scope}' scope required",
            )
        return auth

    return check_scope
