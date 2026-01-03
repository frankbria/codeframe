"""Authentication dependencies for route handlers."""

import logging
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
        from codeframe.auth.manager import SECRET, get_async_session_maker
        from sqlalchemy import select

        # Decode JWT token directly using PyJWT
        # This avoids the need for a user_manager instance
        try:
            payload = pyjwt.decode(
                credentials.credentials,
                SECRET,
                algorithms=["HS256"],
                audience=["fastapi-users:auth"],
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
