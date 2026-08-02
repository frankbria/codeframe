"""Audit logging infrastructure for CodeFRAME.

This module provides centralized audit logging for security-relevant events including:
- Authentication events (login, logout, failed attempts)
- Authorization checks (access granted/denied)
- Project lifecycle events (create, update, delete)
- User management events (user creation, role changes)

All audit logs are stored in the database with timestamps, user context, and event metadata.
"""

import logging
from datetime import datetime, UTC
from contextvars import ContextVar

from starlette.requests import Request
from typing import Optional, Dict, Any
from enum import Enum

from codeframe.platform_store.database import Database

logger = logging.getLogger(__name__)


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

    # API key lifecycle (#937). Minting and revoking a credential are the
    # security-relevant events here; a key's *use* is covered by the auth events.
    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"

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
        # Never raise: an audit write must not fail the operation being audited
        # — refusing a login because the audit table is unavailable would be a
        # self-inflicted outage. But it is logged at WARNING, not debug: a
        # silently missing audit trail is indistinguishable from "nothing
        # happened", which is exactly what an audit trail exists to rule out
        # (#937).
        try:
            self.db.create_audit_log(
                event_type=event_type.value,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                metadata=metadata,
                timestamp=datetime.now(UTC),
            )
        except Exception:  # noqa: BLE001 - see comment
            logger.warning(
                "Audit write failed for %s (user_id=%s) — the event happened but "
                "was NOT recorded. (audit_logs.user_id is a foreign key: passing "
                "an id with no users row fails the whole insert.)",
                event_type.value,
                user_id,
                exc_info=True,
            )


def audit_from_request(
    request,
    event_type: "AuditEventType",
    *,
    user_id: Optional[int] = None,
    email: Optional[str] = None,
    resource_type: str = "auth",
    resource_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Write one audit event using the Database on the app state (#937).

    A single funnel for the call sites that only have a ``Request``: it resolves
    the store, records the client IP, and is guarded end to end so no caller
    needs its own try/except. Returns quietly when there is no database (unit
    tests build routers without app state) but logs when a write is attempted
    and fails.
    """
    db = getattr(getattr(getattr(request, "app", None), "state", None), "db", None)
    if db is None:
        return

    client = getattr(request, "client", None)
    kwargs = dict(
        event_type=event_type,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=getattr(client, "host", None),
        metadata={**(metadata or {}), **({"email": email} if email else {})},
    )

    queue = _pending.get()
    if queue is not None:
        # Inside a captured route: flush after the other dependencies close, so
        # the write never contends with an open auth transaction on the same
        # SQLite file (#937).
        queue.append((db, kwargs))
        return

    AuditLogger(db)._log_event(**kwargs)


#: The in-flight Request, for audit call sites that cannot receive one.
#: ``UserManager.authenticate`` is the motivating case: fastapi-users calls it
#: with only the submitted credentials, but a failed login is precisely the
#: event worth auditing, and the row needs the client IP. Set by the
#: ``capture_audit_request`` dependency on the auth routes (#937).
_current_request: ContextVar[Optional[Any]] = ContextVar(
    "codeframe_audit_request", default=None
)

#: Events queued for after the request's other dependencies have torn down.
_pending: ContextVar[Optional[list]] = ContextVar(
    "codeframe_audit_pending", default=None
)


async def capture_audit_request(request: Request):
    """FastAPI dependency: expose this request to request-less audit call sites,
    and defer their writes until the rest of the request has torn down.

    The annotation is load-bearing: without it FastAPI reads ``request`` as a
    query parameter and every login 422s.

    Deferral matters on the auth routes (codex review on #937). fastapi-users'
    async SQLAlchemy session and ``app.state.db`` are two connections to the SAME
    SQLite file, and ``authenticate()`` can leave a write open (it rewrites a
    legacy password hash). Writing the audit row inline would then queue behind
    that transaction on ``busy_timeout = 5000`` — a 5s stall on every failed
    login, and then a lost audit row when the wait expires. Router-level
    dependencies tear down LAST, after the route's session dependency has
    closed, so flushing here writes against an uncontended file.
    """
    request_token = _current_request.set(request)
    pending_token = _pending.set([])
    try:
        yield
    finally:
        queued = _pending.get() or []
        # Reset BEFORE flushing so a failure below cannot strand the context.
        # Reset rather than clear: ContextVar state leaking between requests on a
        # reused worker task would attribute one user's IP to another's event.
        _pending.reset(pending_token)
        _current_request.reset(request_token)
        for db, kwargs in queued:
            AuditLogger(db)._log_event(**kwargs)


def current_audit_request():
    """The in-flight Request, or None outside a captured route."""
    return _current_request.get()
