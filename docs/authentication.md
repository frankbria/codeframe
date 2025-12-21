# Authentication & Authorization Guide

This document provides comprehensive guidance on CodeFRAME's authentication and authorization system, implemented to address OWASP A01 - Broken Access Control vulnerability.

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Authorization](#authorization)
- [Audit Logging](#audit-logging)
- [Security Considerations](#security-considerations)
- [Migration Guide](#migration-guide)
- [API Reference](#api-reference)

---

## Overview

CodeFRAME implements a layered security architecture:

1. **Authentication Layer**: Better Auth v1.4.7 (frontend) + FastAPI dependencies (backend)
2. **Authorization Layer**: Project ownership model with role-based access control
3. **Audit Layer**: Comprehensive logging of security-relevant events

### Key Features

- ✅ **Email/Password Authentication**: Secure user registration and login
- ✅ **Session Management**: 7-day sessions with automatic expiry and cleanup
- ✅ **Project Ownership**: Automatic owner assignment on project creation
- ✅ **Role-Based Access**: Owner, collaborator, and viewer roles
- ✅ **Audit Logging**: Comprehensive logging of auth/authz events
- ✅ **Backward Compatibility**: Optional authentication during migration period

---

## Authentication

### Frontend (Better Auth v1.4.7)

Better Auth provides the frontend authentication UI and session management.

#### Installation

```bash
cd web-ui
npm install better-auth@1.4.7
```

#### Configuration

Better Auth is configured to use the SQLite database with the following tables:
- `users` - User accounts (email, password, name)
- `sessions` - Active sessions with 7-day expiry
- `verification_tokens` - Email verification tokens
- `accounts` - OAuth provider accounts (future)

#### Session Management

- **Session Duration**: 7 days from login
- **Session Storage**: SQLite database (sessions table)
- **Session Cleanup**: Automatic cleanup on expiry check
- **Session Token**: Stored in HTTP-only cookie

### Backend (FastAPI Dependencies)

The backend uses FastAPI dependency injection for authentication.

#### get_current_user Dependency

```python
from codeframe.ui.dependencies import get_current_user, User

@router.get("/api/protected")
async def protected_endpoint(current_user: User = Depends(get_current_user)):
    """Protected endpoint requiring authentication."""
    return {"user_id": current_user.id, "email": current_user.email}
```

**How it works**:
1. Extracts Bearer token from Authorization header
2. Validates token against sessions table
3. Checks session expiry
4. Returns User model with user information
5. Raises 401 Unauthorized if invalid/expired

#### User Model

```python
from pydantic import BaseModel

class User(BaseModel):
    id: int              # User's database ID
    email: str           # User's email address
    name: Optional[str]  # User's display name
```

#### Optional Authentication

During the migration period, authentication can be optional:

```python
from codeframe.ui.dependencies import get_current_user_optional

@router.get("/api/optional-auth")
async def endpoint(user: Optional[User] = Depends(get_current_user_optional)):
    """Endpoint with optional authentication."""
    if user:
        return {"message": f"Hello, {user.email}"}
    else:
        return {"message": "Hello, guest"}
```

---

## Authorization

### Project Ownership Model

CodeFRAME uses a flexible ownership model with three roles:

- **Owner**: Full control over project (create, update, delete, manage access)
- **Collaborator**: Can view and modify project resources
- **Viewer**: Read-only access to project resources

### Database Schema

```sql
-- Users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    name TEXT,
    email_verified INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Projects table (user_id is owner)
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    -- ... other fields
);

-- Project access table (for collaborators/viewers)
CREATE TABLE project_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('owner', 'collaborator', 'viewer')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, user_id)
);
```

### Authorization Checks

All API endpoints that access project resources must check authorization:

```python
from fastapi import HTTPException, Depends
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db, get_current_user, User

@router.get("/api/projects/{project_id}/resource")
async def get_resource(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Protected endpoint with authorization check."""

    # 1. Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # 3. Proceed with operation
    return {"resource": "data"}
```

**Key Points**:
- Always check project existence first (prevents information leakage)
- Return 403 Forbidden (not 404) for unauthorized access
- Use `user_has_project_access()` for consistent authorization logic

### Task-Scoped Endpoints

For endpoints that operate on tasks (not projects), extract the project_id from the task:

```python
@router.get("/api/tasks/{task_id}")
async def get_task(
    task_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get task details (task-scoped endpoint)."""

    # 1. Get task (implicitly checks task exists)
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 2. Extract project_id from task
    project_id = task.get("project_id")
    if not project_id:
        raise HTTPException(status_code=500, detail="Task missing project_id")

    # 3. Authorization check on project
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # 4. Return task
    return task
```

### user_has_project_access Method

The core authorization method checks both ownership and collaborator access:

```python
def user_has_project_access(self, user_id: int, project_id: int) -> bool:
    """Check if a user has access to a project.

    Args:
        user_id: User ID to check
        project_id: Project ID to check

    Returns:
        True if user is owner or has collaborator/viewer access
    """
    # Check if user is the project owner
    cursor.execute(
        "SELECT 1 FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    )
    if cursor.fetchone():
        return True  # User is owner

    # Check if user has collaborator/viewer access
    cursor.execute(
        "SELECT 1 FROM project_users WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    )
    return cursor.fetchone() is not None
```

---

## Audit Logging

CodeFRAME logs all security-relevant events to the `audit_logs` table for compliance, security monitoring, and incident investigation.

### AuditEventType Enum

```python
from codeframe.lib.audit_logger import AuditEventType

# Authentication events
AuditEventType.AUTH_LOGIN_SUCCESS
AuditEventType.AUTH_LOGIN_FAILED
AuditEventType.AUTH_LOGOUT
AuditEventType.AUTH_SESSION_CREATED
AuditEventType.AUTH_SESSION_EXPIRED

# Authorization events
AuditEventType.AUTHZ_ACCESS_GRANTED
AuditEventType.AUTHZ_ACCESS_DENIED
AuditEventType.AUTHZ_PERMISSION_CHECK

# Project lifecycle events
AuditEventType.PROJECT_CREATED
AuditEventType.PROJECT_UPDATED
AuditEventType.PROJECT_DELETED
AuditEventType.PROJECT_ACCESS_GRANTED
AuditEventType.PROJECT_ACCESS_REVOKED

# User management events
AuditEventType.USER_CREATED
AuditEventType.USER_UPDATED
AuditEventType.USER_DELETED
AuditEventType.USER_ROLE_CHANGED
```

### Using AuditLogger

```python
from codeframe.lib.audit_logger import AuditLogger, AuditEventType

# Initialize logger
audit = AuditLogger(db)

# Log authentication event
audit.log_auth_event(
    event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
    user_id=user_id,
    email=email,
    ip_address="192.168.1.1",
    metadata={"session_id": token}
)

# Log authorization event
audit.log_authz_event(
    event_type=AuditEventType.AUTHZ_ACCESS_GRANTED,
    user_id=user_id,
    resource_type="project",
    resource_id=project_id,
    granted=True,
    metadata={"access_type": "owner"}
)

# Log project lifecycle event
audit.log_project_event(
    event_type=AuditEventType.PROJECT_CREATED,
    user_id=user_id,
    project_id=project_id,
    metadata={"name": "My Project", "source_type": "api"}
)
```

### Audit Logs Database Schema

```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resource_type TEXT NOT NULL,
    resource_id INTEGER,
    ip_address TEXT,
    metadata TEXT,  -- JSON metadata
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance indexes
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id, timestamp DESC);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type, timestamp DESC);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id, timestamp DESC);
```

### Querying Audit Logs

```python
# Get all login attempts for a user
cursor.execute(
    """
    SELECT * FROM audit_logs
    WHERE user_id = ? AND event_type LIKE 'auth.login%'
    ORDER BY timestamp DESC
    LIMIT 100
    """,
    (user_id,)
)

# Get all access attempts for a project
cursor.execute(
    """
    SELECT * FROM audit_logs
    WHERE resource_type = 'project' AND resource_id = ?
    ORDER BY timestamp DESC
    """,
    (project_id,)
)
```

---

## Security Considerations

### Session Security

- **HTTP-Only Cookies**: Session tokens stored in HTTP-only cookies (prevents XSS)
- **Secure Flag**: Cookies marked as Secure in production (HTTPS only)
- **SameSite Policy**: Cookies use SameSite=Lax to prevent CSRF
- **Session Expiry**: 7-day expiry with automatic cleanup
- **Token Validation**: All tokens validated on every request

### Password Security

- **Hashing**: bcrypt with salt rounds=12 (via Better Auth)
- **No Plaintext Storage**: Passwords never stored in plaintext
- **Password Requirements**: Minimum 8 characters (configurable)

### API Security

- **Bearer Token Authentication**: All API requests require `Authorization: Bearer <token>`
- **403 vs 404 Responses**: Return 403 (not 404) to prevent information leakage
- **Rate Limiting**: Consider adding rate limiting in production
- **CORS**: Configure CORS for production deployments

### WebSocket Security

**Current Status**: WebSocket connections do not yet have authentication (Issue #132).

**Planned Implementation**:
1. Accept auth token as query parameter: `ws://host/ws?token=...`
2. Validate token and extract user_id on connection
3. Store user_id with WebSocket connection in manager
4. Check `db.user_has_project_access()` on subscribe/unsubscribe messages
5. Return authorization error if user lacks project access

**Workaround**: Deploy WebSocket endpoint behind authentication proxy or firewall until implemented.

### Database Security

- **Parameterized Queries**: All queries use parameterized statements (prevents SQL injection)
- **Cascade Deletes**: Foreign keys configured with ON DELETE CASCADE for data integrity
- **Indexes**: Performance indexes on frequently queried columns
- **Backups**: Regular database backups recommended for production

---

## Migration Guide

### Enabling Authentication

Authentication is controlled by the `AUTH_REQUIRED` environment variable:

```bash
# Development (authentication optional, default admin user)
export AUTH_REQUIRED=false

# Production (authentication required)
export AUTH_REQUIRED=true
```

### Migration Steps

1. **Deploy Backend with AUTH_REQUIRED=false**:
   ```bash
   export AUTH_REQUIRED=false
   uv run uvicorn codeframe.ui.server:app --reload
   ```

2. **Deploy Frontend with Better Auth**:
   ```bash
   cd web-ui
   npm install better-auth@1.4.7
   npm run dev
   ```

3. **Create Admin Account**:
   - Navigate to `/signup` in browser
   - Create admin account with email/password
   - Verify email (if email verification enabled)

4. **Migrate Existing Projects**:
   ```sql
   -- Assign all existing projects to admin user
   UPDATE projects SET user_id = 1 WHERE user_id IS NULL;
   ```

5. **Enable Authentication**:
   ```bash
   export AUTH_REQUIRED=true
   # Restart backend
   ```

6. **Test Authentication**:
   - Log in at `/login`
   - Verify you can access your projects
   - Verify unauthorized users get 403 errors

### Backward Compatibility

During the migration period (`AUTH_REQUIRED=false`):
- Requests without tokens receive a default admin user (id=1, email=admin@localhost)
- Requests with tokens are validated normally
- This allows gradual migration without breaking existing workflows

---

## API Reference

### Authentication Endpoints

**Login** (handled by Better Auth):
```
POST /api/auth/login
{
  "email": "user@example.com",
  "password": "password123"
}

Response:
{
  "token": "session-token-here",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "User Name"
  }
}
```

**Logout** (handled by Better Auth):
```
POST /api/auth/logout
Authorization: Bearer <token>

Response:
{
  "message": "Logged out successfully"
}
```

**Session Check**:
```
GET /api/auth/session
Authorization: Bearer <token>

Response:
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "User Name"
  }
}
```

### Authorization Endpoints

All project-scoped endpoints require authentication and authorization:

```
# Project endpoints
GET    /api/projects                           # List user's projects
POST   /api/projects                           # Create project (auto-assigns owner)
GET    /api/projects/{id}                      # Get project details
PUT    /api/projects/{id}                      # Update project
DELETE /api/projects/{id}                      # Delete project

# Agent endpoints
GET    /api/projects/{id}/agents               # List project agents
POST   /api/projects/{id}/agents               # Create agent

# Task endpoints
GET    /api/projects/{id}/tasks                # List project tasks
GET    /api/tasks/{id}                         # Get task details

# Blocker endpoints
GET    /api/projects/{id}/blockers             # List project blockers
POST   /api/blockers/{id}/answer               # Answer blocker

# Review endpoints
POST   /api/agents/{agent_id}/review           # Trigger code review
GET    /api/agents/{agent_id}/review/latest    # Get latest review

# Context endpoints
GET    /api/agents/{agent_id}/context          # List context items
POST   /api/agents/{agent_id}/flash-save       # Trigger flash save

# Session endpoints
GET    /api/projects/{id}/session              # Get session state
```

### Error Responses

**401 Unauthorized** - Missing or invalid authentication token:
```json
{
  "detail": "Missing authentication token"
}
```

**403 Forbidden** - User lacks permission to access resource:
```json
{
  "detail": "Access denied"
}
```

**404 Not Found** - Resource does not exist:
```json
{
  "detail": "Project not found"
}
```

---

## Testing

### Unit Tests

Test authentication and authorization logic:

```python
def test_get_current_user_valid_token(db, test_user):
    """Test authentication with valid token."""
    # Create session
    token = create_session(test_user.id)

    # Authenticate
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = await get_current_user(credentials, db)

    assert user.id == test_user.id
    assert user.email == test_user.email

def test_user_has_project_access_owner(db, test_user, test_project):
    """Test authorization for project owner."""
    assert db.user_has_project_access(test_user.id, test_project.id) is True

def test_user_has_project_access_denied(db, test_user, other_project):
    """Test authorization denied for non-owner."""
    assert db.user_has_project_access(test_user.id, other_project.id) is False
```

### Integration Tests

Test full authentication flow:

```python
async def test_protected_endpoint_with_auth(client, db, test_user):
    """Test protected endpoint with authentication."""
    # Login
    response = await client.post("/api/auth/login", json={
        "email": test_user.email,
        "password": "password123"
    })
    token = response.json()["token"]

    # Access protected endpoint
    response = await client.get(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

async def test_protected_endpoint_without_auth(client):
    """Test protected endpoint without authentication."""
    response = await client.get("/api/projects")
    assert response.status_code == 401
```

---

## Troubleshooting

### Common Issues

**"Missing authentication token" error**:
- Ensure `Authorization: Bearer <token>` header is included
- Check that token is valid and not expired
- Verify AUTH_REQUIRED environment variable is set correctly

**"Access denied" error (403)**:
- Verify user has access to the project
- Check `project_users` table for collaborator/viewer access
- Ensure project.user_id matches authenticated user (for owner)

**Session expired error**:
- Sessions expire after 7 days
- Re-authenticate to obtain new session token
- Check `sessions` table for session expiry timestamp

**Audit logs not appearing**:
- Verify AuditLogger is initialized with database instance
- Check that audit_logs table exists
- Verify database connection is committed after log writes

---

## Future Enhancements

- **OAuth 2.0 Providers**: Google, GitHub, Microsoft SSO
- **Two-Factor Authentication**: TOTP, SMS, or email verification
- **API Keys**: Long-lived tokens for CI/CD and automation
- **Role-Based Permissions**: Fine-grained permissions beyond owner/collaborator/viewer
- **IP Allowlisting**: Restrict access to specific IP ranges
- **WebSocket Authentication**: Token-based auth for WebSocket connections
- **Audit Log API**: Query and export audit logs via API

---

## Related Documentation

- [SECURITY.md](../SECURITY.md) - Security policy and best practices
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Development setup with authentication
- [API Documentation](../docs/api/) - Complete API reference
- [Database Schema](../CLAUDE.md) - Database schema documentation

---

**For questions or security reports, contact the project maintainers.**
