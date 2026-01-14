# Authentication & Authorization Guide

This document provides comprehensive guidance on CodeFRAME's authentication and authorization system.

**Last Updated**: 2026-01-06
**Status**: Production Ready (FastAPI Users with JWT)

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Authorization](#authorization)
- [Audit Logging](#audit-logging)
- [Security Considerations](#security-considerations)
- [API Reference](#api-reference)

---

## Overview

CodeFRAME implements a layered security architecture using **FastAPI Users** with JWT tokens:

1. **Authentication Layer**: FastAPI Users with JWT Bearer tokens
2. **Authorization Layer**: Project ownership model with role-based access control
3. **Audit Layer**: Comprehensive logging of security-relevant events

### Key Features

- **Email/Password Authentication**: Secure user registration and login
- **JWT Tokens**: Stateless authentication with configurable lifetime
- **Project Ownership**: Automatic owner assignment on project creation
- **Role-Based Access**: Owner, collaborator, and viewer roles
- **WebSocket Authentication**: Token-based auth via query parameter
- **Audit Logging**: Comprehensive logging of auth/authz events

---

## Authentication

### Architecture

CodeFRAME uses **FastAPI Users** for authentication, a production-ready authentication library that provides:

- JWT token generation and validation
- User registration and management
- Password hashing (bcrypt)
- SQLAlchemy integration

### Backend Auth Module

```
codeframe/auth/
├── __init__.py          # Module exports
├── dependencies.py      # FastAPI dependencies (get_current_user, etc.)
├── manager.py           # UserManager, JWT configuration
├── models.py            # SQLAlchemy User model
├── router.py            # Auth routes (/auth/jwt/login, /auth/register)
└── schemas.py           # Pydantic schemas (UserCreate, UserRead, UserUpdate)
```

### JWT Configuration

Tokens are configured in `codeframe/auth/manager.py`:

- **Algorithm**: HS256
- **Lifetime**: 1 hour (configurable)
- **Audience**: `fastapi-users:auth`

### get_current_user Dependency

```python
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User

@router.get("/api/protected")
async def protected_endpoint(current_user: User = Depends(get_current_user)):
    """Protected endpoint requiring authentication."""
    return {"user_id": current_user.id, "email": current_user.email}
```

**How it works**:
1. Extracts Bearer token from Authorization header
2. Decodes and validates JWT using PyJWT
3. Checks token expiry
4. Fetches user from database
5. Returns User model with user information
6. Raises 401 Unauthorized if invalid/expired

### User Model

```python
from sqlalchemy.orm import DeclarativeBase
from fastapi_users.db import SQLAlchemyBaseUserTable

class User(SQLAlchemyBaseUserTable[int], Base):
    """User model with FastAPI Users integration."""
    pass
```

FastAPI Users automatically provides fields:
- `id`: Integer primary key
- `email`: Unique email address
- `hashed_password`: bcrypt password hash
- `is_active`: Account active status
- `is_superuser`: Admin privileges
- `is_verified`: Email verification status

### Frontend Authentication

The frontend stores JWT tokens in localStorage:

```typescript
// Login stores token
const response = await authFetch('/auth/jwt/login', {
  method: 'POST',
  body: JSON.stringify({ username: email, password }),
});
localStorage.setItem('auth_token', response.access_token);

// API calls include token via interceptor (lib/api.ts)
config.headers.Authorization = `Bearer ${token}`;
```

### WebSocket Authentication

WebSocket connections require the token as a query parameter:

```typescript
// Frontend WebSocket connection
const token = localStorage.getItem('auth_token');
new WebSocket(`${WS_URL}?token=${token}`);
```

The backend validates the token on connection:

```python
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        return
    # Validate token and get user...
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
-- Users table (managed by FastAPI Users)
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    is_superuser INTEGER DEFAULT 0,
    is_verified INTEGER DEFAULT 0
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
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User

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

### user_has_project_access Method

The core authorization method checks both ownership and collaborator access:

```python
def user_has_project_access(self, user_id: int, project_id: int) -> bool:
    """Check if a user has access to a project.

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
```

---

## Security Considerations

### JWT Security

- **HS256 Algorithm**: Symmetric signing with secret key
- **Short Lifetime**: 1-hour expiry (configurable)
- **Audience Claim**: Validates `aud` claim to prevent token reuse
- **Token Validation**: Every request validates signature and expiry

### Password Security

- **Hashing**: bcrypt with automatic salt rounds (passlib[bcrypt])
- **No Plaintext Storage**: Passwords never stored in plaintext
- **Password Requirements**: Minimum length enforced by frontend

### API Security

- **Bearer Token Authentication**: All API requests require `Authorization: Bearer <token>`
- **403 vs 404 Responses**: Return 403 (not 404) to prevent information leakage
- **Rate Limiting**: Consider adding rate limiting in production
- **CORS**: Configure CORS for production deployments

### WebSocket Security

- **Token Authentication**: Required via query parameter: `ws://host/ws?token=...`
- **Connection Validation**: Token validated on connection establishment
- **Project Scoping**: WebSocket subscriptions check project access

### Database Security

- **Parameterized Queries**: All queries use parameterized statements (prevents SQL injection)
- **Cascade Deletes**: Foreign keys configured with ON DELETE CASCADE for data integrity
- **Indexes**: Performance indexes on frequently queried columns
- **Backups**: Regular database backups recommended for production

---

## API Reference

### Authentication Endpoints

**Register** (`POST /auth/register`):
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}

Response:
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_superuser": false,
  "is_verified": false
}
```

**Login** (`POST /auth/jwt/login`):
```
Content-Type: application/x-www-form-urlencoded

username=user@example.com&password=securepassword123

Response:
{
  "access_token": "eyJ0eXAi...",
  "token_type": "bearer"
}
```

**Get Current User** (`GET /users/me`):
```
Authorization: Bearer <token>

Response:
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_superuser": false,
  "is_verified": false
}
```

**Logout** (`POST /auth/jwt/logout`):
```
Authorization: Bearer <token>

Response:
null
```

### Protected Endpoints

All project-scoped endpoints require authentication:

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
```

### Error Responses

**401 Unauthorized** - Missing or invalid authentication token:
```json
{
  "detail": "Not authenticated"
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
def test_get_current_user_valid_token(test_user):
    """Test authentication with valid token."""
    token = create_jwt_token(test_user)
    user = await get_current_user(create_request(token))
    assert user.id == test_user.id

def test_user_has_project_access_owner(db, test_user, test_project):
    """Test authorization for project owner."""
    assert db.user_has_project_access(test_user.id, test_project.id) is True
```

### E2E Tests

Test full authentication flow using Playwright:

```typescript
import { loginUser } from './test-utils';

test('authenticated user can access dashboard', async ({ page }) => {
  await loginUser(page);
  await page.goto('/dashboard');
  await expect(page.locator('h1')).toContainText('Projects');
});
```

The `loginUser()` helper handles registration/login and token storage.

---

## Troubleshooting

### Common Issues

**"Not authenticated" error**:
- Ensure `Authorization: Bearer <token>` header is included
- Check that token is not expired (1 hour lifetime)
- Verify token was obtained from `/auth/jwt/login`

**"Access denied" error (403)**:
- Verify user has access to the project
- Check `project_users` table for collaborator/viewer access
- Ensure project.user_id matches authenticated user (for owner)

**Token expired**:
- Tokens expire after 1 hour
- Re-authenticate to obtain new token
- Consider implementing refresh token flow for longer sessions

**WebSocket connection rejected (code 1008)**:
- Ensure token is passed as query parameter: `?token=...`
- Verify token is valid and not expired
- Check browser console for connection errors

---

## Future Enhancements

- **OAuth 2.0 Providers**: Google, GitHub, Microsoft SSO
- **Two-Factor Authentication**: TOTP or email verification
- **API Keys**: Long-lived tokens for CI/CD and automation
- **Refresh Tokens**: Longer sessions without re-authentication
- **IP Allowlisting**: Restrict access to specific IP ranges
- **Audit Log API**: Query and export audit logs via API

---

## Related Documentation

- [Database Repository Pattern](./architecture/database-repository-pattern.md)
- [E2E Testing Guide](./e2e-testing.md)
- [Session Lifecycle](./session-lifecycle.md)
- [CLAUDE.md](../CLAUDE.md) - Authentication Architecture section

---

**For questions or security reports, contact the project maintainers.**
