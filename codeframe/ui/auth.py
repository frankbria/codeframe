"""Authentication and authorization for FastAPI endpoints.

This module provides authentication dependency functions for verifying
user sessions and extracting user information from Better Auth tokens.

All authentication is handled through Better Auth, with sessions stored
in the SQLite database (users, sessions tables).
"""

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.lib.audit_logger import AuditLogger, AuditEventType


class User(BaseModel):
    """Authenticated user model.

    Attributes:
        id: User's database ID
        email: User's email address
        name: User's display name (optional)
    """

    id: int
    email: str
    name: Optional[str] = None


# Security scheme for extracting Bearer tokens from Authorization header
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Database = Depends(get_db),
) -> User:
    """Get currently authenticated user from session token.

    Validates the Bearer token against the sessions table and returns
    the authenticated user. Raises 401 Unauthorized if token is missing,
    invalid, or expired.

    Args:
        credentials: Bearer token from Authorization header
        db: Database instance

    Returns:
        User model with user information

    Raises:
        HTTPException: 401 if not authenticated or token invalid/expired

    Usage:
        @router.get("/protected")
        async def protected_endpoint(user: User = Depends(get_current_user)):
            return {"message": f"Hello, {user.email}"}
    """
    # Check if authentication is required (for migration period)
    auth_required = os.getenv("AUTH_REQUIRED", "false").lower() == "true"

    if not auth_required:
        # During migration period, create a default admin user if no token provided
        if not credentials or not credentials.credentials:
            # Return a default admin user for backward compatibility
            return User(id=1, email="admin@localhost", name="Admin User")

    # Authentication is required or token is provided
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Query sessions table to verify token
    cursor = db.conn.execute(
        """
        SELECT s.user_id, s.expires_at, u.email, u.name
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
        """,
        (token,),
    )
    row = cursor.fetchone()

    if not row:
        # Log failed authentication attempt
        audit = AuditLogger(db)
        audit.log_auth_event(
            event_type=AuditEventType.AUTH_LOGIN_FAILED,
            user_id=None,
            email=None,
            ip_address=None,  # TODO: Extract from request
            metadata={"reason": "Invalid token"},
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id, expires_at_str, email, name = row

    # Check if session has expired
    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    if expires_at < datetime.now(timezone.utc):
        # Log session expiry
        audit = AuditLogger(db)
        audit.log_auth_event(
            event_type=AuditEventType.AUTH_SESSION_EXPIRED,
            user_id=user_id,
            email=email,
            ip_address=None,  # TODO: Extract from request
            metadata={"expires_at": expires_at_str},
        )

        # Delete expired session
        db.conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.conn.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Log successful authentication
    audit = AuditLogger(db)
    audit.log_auth_event(
        event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
        user_id=user_id,
        email=email,
        ip_address=None,  # TODO: Extract from request
        metadata={"session_id": token},
    )

    return User(id=user_id, email=email, name=name)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Database = Depends(get_db),
) -> Optional[User]:
    """Get currently authenticated user, or None if not authenticated.

    This is a non-raising version of get_current_user() for endpoints
    that optionally use authentication (e.g., during migration period).

    Args:
        credentials: Bearer token from Authorization header
        db: Database instance

    Returns:
        User model if authenticated, None otherwise

    Usage:
        @router.get("/optional-auth")
        async def endpoint(user: Optional[User] = Depends(get_current_user_optional)):
            if user:
                return {"message": f"Hello, {user.email}"}
            else:
                return {"message": "Hello, guest"}
    """
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
