"""Authentication dependencies for route handlers.

Supports dual authentication:
- JWT Bearer tokens (existing FastAPI Users integration)
- API keys via X-API-Key header (new for programmatic access)

API keys use scope-based permissions (read, write, admin).
JWT tokens get full permissions for backward compatibility.
"""

import logging
from typing import Callable, Dict, Optional, Any

from fastapi import Depends, HTTPException, Request, Security, status
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


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Get currently authenticated user.

    Authentication is always required. All requests must include a valid
    JWT Bearer token in the Authorization header.

    Args:
        request: FastAPI request object
        credentials: Bearer token from Authorization header

    Returns:
        Authenticated user

    Raises:
        HTTPException: 401 if authentication not provided or invalid
    """
    # Authentication is always required
    if not credentials or not credentials.credentials:
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
                credentials.credentials,
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
        # Get database from request state or create new instance
        db = getattr(request.state, "db", None)
        if db is None:
            # Fallback: create database connection
            import os
            from codeframe.persistence.database import Database

            db_path = os.getenv(
                "DATABASE_PATH",
                os.path.join(os.getcwd(), ".codeframe", "state.db")
            )
            db = Database(db_path)
            db.initialize()

        # Extract prefix and look up key
        try:
            prefix = extract_prefix(api_key)
        except ValueError:
            logger.debug("Invalid API key format")
            return None

        key_record = db.api_keys.get_by_prefix(prefix)
        if key_record is None:
            logger.debug(f"API key not found for prefix {prefix}")
            return None

        # Verify the full key against stored hash
        if not verify_api_key(api_key, key_record["key_hash"]):
            logger.debug(f"API key verification failed for prefix {prefix}")
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

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer, ApiKey"},
    )


def require_scope(required_scope: str) -> Callable:
    """Create a dependency that checks for a required scope.

    Usage:
        @router.post("/resource")
        async def create_resource(auth: dict = Depends(require_scope("write"))):
            ...

    Args:
        required_scope: The scope required for access

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
