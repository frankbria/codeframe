"""Authentication dependencies for route handlers."""
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from codeframe.auth.models import User

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
        if not auth_required:
            return await _get_default_admin_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _get_default_admin_user() -> User:
    """Get or create a default admin user for development mode."""
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
    except Exception:
        pass

    # Fallback: create a minimal User object
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
