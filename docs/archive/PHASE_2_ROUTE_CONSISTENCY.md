# Phase 2: Route Consistency Audit

**Created:** 2026-02-01
**Issue:** #322 - Server Layer Refactor
**Branch:** phase-2/server-layer

This document audits v2 API routes for consistency and tracks standardization progress.

---

## 1. Standards

### 1.1 URL Pattern

**Standard:** `/api/v2/{resource}/{id?}/{action?}`

- Resources: plural nouns (`tasks`, `checkpoints`, `templates`)
- IDs: path parameters (`/{task_id}`, `/{checkpoint_id}`)
- Actions: verbs for non-CRUD operations (`/start`, `/stop`, `/restore`)

**Examples:**
- `GET /api/v2/tasks` - list resources
- `GET /api/v2/tasks/{id}` - get single resource
- `POST /api/v2/tasks/{id}/start` - perform action on resource
- `POST /api/v2/tasks/approve` - bulk action

### 1.2 Response Format

**Success Response:**
```json
{
    "success": true,
    "data": { ... },
    "message": "Optional human-readable message"
}
```

**Note:** The `data` field contains the actual payload. This wrapper enables:
- Consistent client-side response handling
- Optional messages for UI feedback
- Clear success/failure indication

### 1.3 Error Format

**Error Response:**
```json
{
    "error": "Error description",
    "detail": "Additional context",
    "code": "ERROR_CODE"
}
```

**Standard Error Codes:**
| Code | HTTP Status | Description |
|------|-------------|-------------|
| `NOT_FOUND` | 404 | Resource not found |
| `ALREADY_EXISTS` | 409 | Resource already exists |
| `INVALID_REQUEST` | 400 | Invalid request parameters |
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `INVALID_STATE` | 409 | Invalid state transition |
| `EXECUTION_FAILED` | 500 | Operation failed |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

---

## 2. Current V2 Route Audit

### 2.1 Discovery Routes (`/api/v2/discovery`)

| Route | Method | Current Pattern | Compliance | Notes |
|-------|--------|-----------------|------------|-------|
| `/start` | POST | Action-only | ✅ Good | Starts new session |
| `/status` | GET | Action-only | ✅ Good | Get current status |
| `/{session_id}/answer` | POST | `/{id}/action` | ✅ Good | Submit answer |
| `/{session_id}/generate-prd` | POST | `/{id}/action` | ✅ Good | Generate PRD |
| `/reset` | POST | Action-only | ✅ Good | Reset session |
| `/generate-tasks` | POST | Action-only | ✅ Good | Generate tasks |

**Response Format:** ⚠️ Returns raw data, needs wrapper

### 2.2 Task Routes (`/api/v2/tasks`)

| Route | Method | Current Pattern | Compliance | Notes |
|-------|--------|-----------------|------------|-------|
| `` | GET | List | ✅ Good | List tasks |
| `/{task_id}` | GET | `/{id}` | ✅ Good | Get task |
| `/approve` | POST | Bulk action | ✅ Good | Approve tasks |
| `/assignment-status` | GET | Status query | ✅ Good | Check status |
| `/execute` | POST | Action | ✅ Good | Start execution |
| `/{task_id}/start` | POST | `/{id}/action` | ✅ Good | Start task |
| `/{task_id}/stop` | POST | `/{id}/action` | ✅ Good | Stop task |
| `/{task_id}/resume` | POST | `/{id}/action` | ✅ Good | Resume task |

**Response Format:** ⚠️ Returns raw data, needs wrapper

### 2.3 Checkpoint Routes (`/api/v2/checkpoints`)

| Route | Method | Current Pattern | Compliance | Notes |
|-------|--------|-----------------|------------|-------|
| `` | POST | Create | ✅ Good | Create checkpoint |
| `` | GET | List | ✅ Good | List checkpoints |
| `/{checkpoint_id}` | GET | `/{id}` | ✅ Good | Get checkpoint |
| `/{checkpoint_id}/restore` | POST | `/{id}/action` | ✅ Good | Restore |
| `/{checkpoint_id}` | DELETE | `/{id}` | ✅ Good | Delete |
| `/{id_a}/diff/{id_b}` | GET | Compare | ⚠️ Non-standard | Could be `/diff?a={}&b={}` |

**Response Format:** ⚠️ Returns raw data, needs wrapper

### 2.4 Schedule Routes (`/api/v2/schedule`)

| Route | Method | Current Pattern | Compliance | Notes |
|-------|--------|-----------------|------------|-------|
| `` | GET | List | ✅ Good | Get schedule |
| `/predict` | GET | Query | ✅ Good | Predict completion |
| `/bottlenecks` | GET | Query | ✅ Good | Get bottlenecks |

**Response Format:** ⚠️ Returns raw data, needs wrapper

### 2.5 Template Routes (`/api/v2/templates`)

| Route | Method | Current Pattern | Compliance | Notes |
|-------|--------|-----------------|------------|-------|
| `` | GET | List | ✅ Good | List templates |
| `/categories` | GET | Subresource | ✅ Good | List categories |
| `/{template_id}` | GET | `/{id}` | ✅ Good | Get template |
| `/apply` | POST | Action | ✅ Good | Apply template |

**Response Format:** ⚠️ Returns raw data, needs wrapper

### 2.6 Project Routes (`/api/v2/projects`)

| Route | Method | Current Pattern | Compliance | Notes |
|-------|--------|-----------------|------------|-------|
| `/status` | GET | Status query | ✅ Good | Get status |
| `/progress` | GET | Subresource | ✅ Good | Get progress |
| `/task-counts` | GET | Subresource | ✅ Good | Get counts |
| `/session` | GET | Subresource | ✅ Good | Get session |
| `/session` | DELETE | Subresource | ✅ Good | Clear session |

**Response Format:** ⚠️ Returns raw data, needs wrapper

### 2.7 Git Routes (`/api/v2/git`)

| Route | Method | Current Pattern | Compliance | Notes |
|-------|--------|-----------------|------------|-------|
| `/status` | GET | Status query | ✅ Good | Get git status |
| `/commits` | GET | List | ✅ Good | List commits |
| `/commit` | POST | Action | ✅ Good | Create commit |
| `/diff` | GET | Query | ✅ Good | Get diff |
| `/branch` | GET | Query | ✅ Good | Get branch |
| `/clean` | GET | Query | ✅ Good | Check clean |

**Response Format:** ⚠️ Returns raw data, needs wrapper

### 2.8 Review Routes (`/api/v2/review`)

| Route | Method | Current Pattern | Compliance | Notes |
|-------|--------|-----------------|------------|-------|
| `/files` | POST | Action | ✅ Good | Review files |
| `/task` | POST | Action | ✅ Good | Review task |
| `/files/summary` | POST | Action | ✅ Good | Summary only |

**Response Format:** ⚠️ Returns raw data, needs wrapper

---

## 3. Standardization Plan

### 3.1 Phase 1: Response Wrapper (Current)

1. ✅ Create `response_models.py` with standard formats
2. 🔄 Update routes to use `api_response()` wrapper
3. 🔄 Update error handling to use `api_error()` format

### 3.2 Phase 2: URL Pattern Cleanup (Future)

1. ⏳ Update checkpoint diff route to query params
2. ⏳ Review and standardize any remaining inconsistencies

### 3.3 Phase 3: Documentation (Future)

1. ⏳ Generate OpenAPI spec with consistent schemas
2. ⏳ Document all endpoints in API reference

---

## 4. Implementation Progress

### Completed

- [x] Created `response_models.py` with `ApiResponse`, `ApiError`, helpers
- [x] Defined standard error codes in `ErrorCodes` class
- [x] Updated tasks_v2.py error handling to use `api_error()` format

### In Progress

- [ ] Update checkpoints_v2.py to use standard error format
- [ ] Update remaining v2 routers error handling

### Remaining

- [ ] All v2 routers using standard error format
- [ ] Consider adding response wrapper for consistency
- [ ] Integration tests verify response format

---

## 5. Migration Guide

### Before (Raw Response)

```python
@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    task = tasks.get(workspace, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(...)
```

### After (Standard Response)

```python
from codeframe.ui.response_models import api_response, api_error, ErrorCodes

@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    task = tasks.get(workspace, task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=api_error("Task not found", ErrorCodes.NOT_FOUND, f"No task with id {task_id}")
        )
    return api_response(
        TaskResponse(...).model_dump(),
        message=f"Retrieved task {task_id}"
    )
```

---

## 6. Notes

### Backward Compatibility

The v1 routes remain unchanged for backward compatibility. Only v2 routes are
being standardized. Clients using v1 routes will continue to work.

### Optional Wrapper

The response wrapper is optional per endpoint. For simple GET endpoints that
return a single resource, the wrapper adds overhead. Consider:
- Use wrapper for actions (POST, PUT, DELETE)
- Use wrapper for list endpoints
- Optional for single-resource GET endpoints

### WebSocket Routes

WebSocket routes (`/ws/*`) are excluded from this standardization as they
use a different communication pattern.
