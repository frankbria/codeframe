# Phase 2: Developer Guide - V2 Router Implementation

**Created:** 2026-02-02
**Issue:** #322 - Server Layer Refactor

This guide documents the thin adapter pattern for implementing v2 API routes.

---

## Core Principle: Thin Adapters

V2 routers are **thin HTTP adapters** that delegate all business logic to core modules.

```
┌─────────────────────────────────────────────────────────────────┐
│                           HTTP Layer                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ Parse Input │ -> │ Call Core   │ -> │ Transform Response  │  │
│  │ (Pydantic)  │    │ (workspace) │    │ (HTTP status, JSON) │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Core Layer                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ core.blockers, core.prd, core.tasks, core.runtime, ...  │    │
│  │ (Headless - No FastAPI imports - Works with CLI too)    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Template

### 1. File Structure

Create router at `codeframe/ui/routers/{resource}_v2.py`:

```python
"""V2 {Resource} router - delegates to core/{resource} module.

Routes:
    GET  /api/v2/{resource}             - List resources
    GET  /api/v2/{resource}/{id}        - Get specific resource
    POST /api/v2/{resource}             - Create resource
    PATCH /api/v2/{resource}/{id}       - Update resource
    DELETE /api/v2/{resource}/{id}      - Delete resource
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.core import {resource}  # Core module
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/{resource}", tags=["{resource}-v2"])
```

### 2. Request/Response Models

Use Pydantic models for type safety and validation:

```python
# Response model - what the API returns
class ResourceResponse(BaseModel):
    """Response for a single resource."""
    id: str
    workspace_id: str
    # ... other fields
    created_at: str

# List response - includes metadata
class ResourceListResponse(BaseModel):
    """Response for resource list."""
    resources: list[ResourceResponse]
    total: int
    by_status: dict[str, int] = {}  # Optional status counts

# Request model - what the API accepts
class CreateResourceRequest(BaseModel):
    """Request for creating a resource."""
    name: str = Field(..., min_length=1, description="Resource name")
    # ... other fields with validation
```

### 3. Workspace Dependency

All v2 routes use workspace-based routing:

```python
@router.get("", response_model=ResourceListResponse)
async def list_resources(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    workspace: Workspace = Depends(get_v2_workspace),  # <-- Key dependency
) -> ResourceListResponse:
```

The `get_v2_workspace()` dependency resolves workspace from:
1. `workspace_path` query parameter (explicit)
2. Server's `default_workspace_path` state (configured)
3. Current working directory (fallback)

### 4. Core Module Delegation

Route handlers should be thin - just delegation:

```python
@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ResourceResponse:
    """Get a specific resource by ID."""

    # 1. Call core module
    result = core_module.get(workspace, resource_id)

    # 2. Handle not found
    if not result:
        raise HTTPException(
            status_code=404,
            detail=api_error("Resource not found", ErrorCodes.NOT_FOUND, f"No resource with id {resource_id}"),
        )

    # 3. Transform to response
    return ResourceResponse(
        id=result.id,
        workspace_id=result.workspace_id,
        # ... map fields
        created_at=result.created_at.isoformat(),
    )
```

### 5. Error Handling

Use standard error format from `response_models.py`:

```python
from codeframe.ui.response_models import api_error, ErrorCodes

# For validation errors (400)
raise HTTPException(
    status_code=400,
    detail=api_error("Invalid status", ErrorCodes.VALIDATION_ERROR, "Details here"),
)

# For not found (404)
raise HTTPException(
    status_code=404,
    detail=api_error("Resource not found", ErrorCodes.NOT_FOUND, "Resource {id} not found"),
)

# For state errors (400)
raise HTTPException(
    status_code=400,
    detail=api_error("Invalid state", ErrorCodes.INVALID_STATE, "Resource must be X before Y"),
)

# For conflicts (409)
raise HTTPException(
    status_code=409,
    detail=api_error("Conflict", ErrorCodes.CONFLICT, "Resource has dependencies"),
)

# For server errors (500)
raise HTTPException(
    status_code=500,
    detail=api_error("Operation failed", ErrorCodes.EXECUTION_FAILED, str(e)),
)
```

### 6. Register Router

Add to `codeframe/ui/server.py`:

```python
from codeframe.ui.routers import {resource}_v2

# In router mounting section:
app.include_router({resource}_v2.router)  # v2 endpoints at /api/v2/{resource}
```

---

## URL Patterns

Follow RESTful conventions:

| Operation | URL Pattern | HTTP Method |
|-----------|-------------|-------------|
| List | `/api/v2/{resource}` | GET |
| Create | `/api/v2/{resource}` | POST |
| Get | `/api/v2/{resource}/{id}` | GET |
| Update | `/api/v2/{resource}/{id}` | PATCH |
| Delete | `/api/v2/{resource}/{id}` | DELETE |
| Action | `/api/v2/{resource}/{id}/{action}` | POST |

---

## Response Format Standards

### Success Response

```json
{
  "id": "abc123",
  "workspace_id": "def456",
  "field": "value",
  "created_at": "2026-02-02T12:00:00+00:00"
}
```

### List Response

```json
{
  "resources": [...],
  "total": 42,
  "by_status": {"OPEN": 5, "RESOLVED": 37}
}
```

### Error Response

```json
{
  "detail": {
    "error": "Resource not found",
    "code": "NOT_FOUND",
    "detail": "No blocker with id abc123"
  }
}
```

### Action Confirmation

```json
{
  "success": true,
  "message": "Resource abc123 deleted successfully"
}
```

---

## Testing

Create tests in `tests/ui/test_{resource}_v2_integration.py`:

```python
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def test_client(test_workspace):
    """Create test client with workspace dependency override."""
    from fastapi import FastAPI
    from codeframe.ui.routers import {resource}_v2
    from codeframe.ui.dependencies import get_v2_workspace

    app = FastAPI()
    app.include_router({resource}_v2.router)

    def get_test_workspace():
        return test_workspace

    app.dependency_overrides[get_v2_workspace] = get_test_workspace

    return TestClient(app)


class TestResourceV2:
    def test_list_empty(self, test_client):
        response = test_client.get("/api/v2/{resource}")
        assert response.status_code == 200
        assert response.json()["resources"] == []

    def test_create(self, test_client):
        response = test_client.post(
            "/api/v2/{resource}",
            json={"name": "Test Resource"}
        )
        assert response.status_code == 201
        assert "id" in response.json()

    def test_get_not_found(self, test_client):
        response = test_client.get("/api/v2/{resource}/nonexistent")
        assert response.status_code == 404
```

---

## Checklist for New V2 Router

- [ ] Create `codeframe/ui/routers/{resource}_v2.py`
- [ ] Define Pydantic request/response models
- [ ] Implement CRUD endpoints delegating to core module
- [ ] Use `get_v2_workspace` dependency
- [ ] Use standard error format from `response_models.py`
- [ ] Register router in `server.py`
- [ ] Add tests in `tests/ui/test_{resource}_v2_integration.py`
- [ ] Update `docs/PHASE_2_CLI_API_MAPPING.md` with new routes
- [ ] Verify core module has required functions

---

## Existing V2 Routers (Reference)

Study these for patterns:

| Router | Core Module | Key Patterns |
|--------|-------------|--------------|
| `blockers_v2.py` | `core.blockers` | Full CRUD, status filtering, action endpoints |
| `prd_v2.py` | `core.prd` | CRUD, versioning, diff endpoint |
| `tasks_v2.py` | `core.tasks`, `core.runtime` | CRUD, execution, streaming (SSE) |
| `discovery_v2.py` | `core.prd_discovery` | Multi-step workflow, session-based |
| `checkpoints_v2.py` | `core.checkpoints` | CRUD, restore action, diff |

---

## Anti-Patterns to Avoid

### ❌ Business Logic in Router

```python
# BAD - Logic belongs in core module
@router.post("/{id}/process")
async def process(id: str, workspace: Workspace = Depends(get_v2_workspace)):
    resource = core.get(workspace, id)
    if resource.status == "PENDING":
        resource.status = "PROCESSING"
        # ... lots of logic
        core.update(workspace, id, resource)
```

### ✅ Thin Delegation

```python
# GOOD - Delegate to core
@router.post("/{id}/process")
async def process(id: str, workspace: Workspace = Depends(get_v2_workspace)):
    result = core.process(workspace, id)  # All logic in core
    return ProcessResponse(...)
```

### ❌ HTTP-Specific Logic in Core

Core modules must not import FastAPI or return HTTP responses.

### ❌ Direct Database Access in Router

Routers should not use `sqlite3` or database connections directly.
Always go through core modules which handle persistence.
