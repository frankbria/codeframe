"""Authentication dependencies for route handlers."""
import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from codeframe.auth.models import User

logger = logging.getLogger(__name__)

# Security scheme for extracting Bearer tokens
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Get currently authenticated user.

    Supports AUTH_REQUIRED=false for development/migration mode.
    In development mode, returns a default admin user if no token provided.

    Args:
        request: FastAPI request object
        credentials: Bearer token from Authorization header

    Returns:
        Authenticated user

    Raises:
        HTTPException: 401 if authentication required but not provided/valid
    """
    # Check if authentication is required
    auth_required = os.getenv("AUTH_REQUIRED", "false").lower() == "true"

    # If no credentials and auth not required, return default admin
    if not credentials or not credentials.credentials:
        if not auth_required:
            return await _get_default_admin_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Try to validate JWT token
    try:
        from codeframe.auth.manager import get_jwt_strategy, get_async_session_maker
        from sqlalchemy import select

        jwt_strategy = get_jwt_strategy()
        token_data = await jwt_strategy.read_token(credentials.credentials, None)

        if token_data is None:
            if not auth_required:
                return await _get_default_admin_user()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user from database
        user_id = int(token_data)
        async_session_maker = get_async_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()

            if user is None:
                if not auth_required:
                    return await _get_default_admin_user()
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
        if not auth_required:
            return await _get_default_admin_user()
        # Return generic message to client (avoid leaking implementation details)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _get_default_admin_user() -> User:
    """Get or create a default admin user for development mode.

    Note: This creates a mock user object that may not exist in the database.
    This is only safe when AUTH_REQUIRED=false (development mode) and should
    not be used for write operations that require foreign key constraints.

    WARNING: If the admin user (id=1) is not found in the database, a mock
    User object is returned. This mock user will cause foreign key violations
    if used for write operations (creating projects, tasks, etc.).
    """
    from codeframe.auth.manager import get_async_session_maker
    from sqlalchemy import select

    try:
        async_session_maker = get_async_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.id == 1)
            )
            admin_user = result.scalar_one_or_none()
            if admin_user:
                return admin_user
            else:
                # Admin user not found - this is a configuration issue
                logger.warning(
                    "Default admin user (id=1) not found in database. "
                    "Write operations may fail with FK violations. "
                    "Run database initialization or set AUTH_REQUIRED=true."
                )
    except Exception as e:
        # Log database errors for debugging (don't silently swallow)
        logger.warning(f"Could not fetch admin user from DB: {e}")

    # Fallback: create a minimal User object for development mode
    # WARNING: This user may not exist in DB - use only for read operations
    logger.warning(
        "Using fallback mock admin user (not in database). "
        "Write operations requiring user_id foreign key will fail."
    )
    mock_user = User()
    mock_user.id = 1
    mock_user.email = "admin@localhost"
    mock_user.name = "Admin User"
    mock_user.hashed_password = "!DISABLED!"
    mock_user.is_active = True
    mock_user.is_superuser = True
    mock_user.is_verified = True
    return mock_user


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
