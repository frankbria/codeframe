"""Audit logging infrastructure for CodeFRAME.

This module provides centralized audit logging for security-relevant events including:
- Authentication events (login, logout, failed attempts)
- Authorization checks (access granted/denied)
- Project lifecycle events (create, update, delete)
- User management events (user creation, role changes)

All audit logs are stored in the database with timestamps, user context, and event metadata.
"""

from datetime import datetime, UTC
from typing import Optional, Dict, Any
from enum import Enum

from codeframe.persistence.database import Database


class AuditEventType(Enum):
    """Types of audit events to log."""

    # Authentication events
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILED = "auth.login.failed"
    AUTH_LOGOUT = "auth.logout"
    AUTH_SESSION_CREATED = "auth.session.created"
    AUTH_SESSION_EXPIRED = "auth.session.expired"

    # Authorization events
    AUTHZ_ACCESS_GRANTED = "authz.access.granted"
    AUTHZ_ACCESS_DENIED = "authz.access.denied"
    AUTHZ_PERMISSION_CHECK = "authz.permission.check"

    # Project lifecycle events
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_DELETED = "project.deleted"
    PROJECT_ACCESS_GRANTED = "project.access.granted"
    PROJECT_ACCESS_REVOKED = "project.access.revoked"

    # User management events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_ROLE_CHANGED = "user.role.changed"

    # Rate limiting events
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"
    RATE_LIMIT_WARNING = "rate_limit.warning"


class AuditLogger:
    """Centralized audit logger for security events.

    Logs all security-relevant events to the database for compliance,
    security monitoring, and incident investigation.

    Example:
        audit = AuditLogger(db)
        audit.log_auth_event(
            user_id=123,
            event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
            metadata={"ip_address": "192.168.1.1"}
        )
    """

    def __init__(self, db: Database):
        """Initialize audit logger.

        Args:
            db: Database instance for persisting audit logs
        """
        self.db = db

    def log_auth_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[int] = None,
        email: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log authentication-related event.

        Args:
            event_type: Type of authentication event
            user_id: User ID (if authenticated)
            email: User email (for login attempts)
            ip_address: Client IP address
            metadata: Additional event metadata
        """
        self._log_event(
            event_type=event_type,
            user_id=user_id,
            resource_type="auth",
            resource_id=None,
            ip_address=ip_address,
            metadata={
                **(metadata or {}),
                "email": email,
            },
        )

    def log_authz_event(
        self,
        event_type: AuditEventType,
        user_id: int,
        resource_type: str,
        resource_id: int,
        granted: bool,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log authorization-related event.

        Args:
            event_type: Type of authorization event
            user_id: User ID performing the action
            resource_type: Type of resource (e.g., "project", "task")
            resource_id: ID of the resource
            granted: Whether access was granted or denied
            ip_address: Client IP address
            metadata: Additional event metadata
        """
        self._log_event(
            event_type=event_type,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            metadata={
                **(metadata or {}),
                "granted": granted,
            },
        )

    def log_project_event(
        self,
        event_type: AuditEventType,
        user_id: int,
        project_id: int,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log project lifecycle event.

        Args:
            event_type: Type of project event
            user_id: User ID performing the action
            project_id: Project ID
            ip_address: Client IP address
            metadata: Additional event metadata
        """
        self._log_event(
            event_type=event_type,
            user_id=user_id,
            resource_type="project",
            resource_id=project_id,
            ip_address=ip_address,
            metadata=metadata,
        )

    def log_user_event(
        self,
        event_type: AuditEventType,
        user_id: int,
        target_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log user management event.

        Args:
            event_type: Type of user event
            user_id: User ID performing the action
            target_user_id: User ID being affected (if different from user_id)
            ip_address: Client IP address
            metadata: Additional event metadata
        """
        self._log_event(
            event_type=event_type,
            user_id=user_id,
            resource_type="user",
            resource_id=target_user_id,
            ip_address=ip_address,
            metadata=metadata,
        )

    def log_rate_limit_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        limit_category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log rate limiting event.

        Args:
            event_type: Type of rate limit event (exceeded or warning)
            user_id: User ID (if authenticated)
            ip_address: Client IP address
            endpoint: API endpoint path
            limit_category: Rate limit category (auth, standard, ai, websocket)
            metadata: Additional event metadata
        """
        self._log_event(
            event_type=event_type,
            user_id=user_id,
            resource_type="rate_limit",
            resource_id=None,
            ip_address=ip_address,
            metadata={
                **(metadata or {}),
                "endpoint": endpoint,
                "limit_category": limit_category,
            },
        )

    def _log_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[int],
        resource_type: str,
        resource_id: Optional[int],
        ip_address: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        """Internal method to log audit event to database.

        Args:
            event_type: Type of audit event
            user_id: User ID (if authenticated)
            resource_type: Type of resource being accessed
            resource_id: ID of the resource
            ip_address: Client IP address
            metadata: Additional event metadata
        """
        self.db.create_audit_log(
            event_type=event_type.value,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            metadata=metadata,
            timestamp=datetime.now(UTC),
        )
