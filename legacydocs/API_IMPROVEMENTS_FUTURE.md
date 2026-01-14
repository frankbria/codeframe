# API Improvements for Future Development

**Date Created**: 2025-12-03
**Last Updated**: 2026-01-06
**Context**: PR #37 - Multi-Agent Per Project Architecture
**Status**: Backlog - Production hardening improvements

> **Note**: MVP is complete as of Sprint 10 (2025-11-23). These improvements are now prioritized
> for production hardening rather than "post-MVP" work. Review priority based on production needs.

---

## Overview

During the code review of PR #37, several API structure improvements were identified that would enhance consistency, scalability, and developer experience. These improvements are documented here for a future development session when we focus on API maturity and production readiness.

---

## 1. API Versioning

### Current State
- All endpoints are unversioned (e.g., `/api/projects/{id}/agents`)
- Breaking changes would require careful coordination with frontend

### Proposed Improvement
Add version prefix to all API routes to enable graceful evolution:

```python
# Before
@app.get("/api/projects/{project_id}/agents")

# After
@app.get("/api/v1/projects/{project_id}/agents")
```

**Benefits**:
- Allows introducing breaking changes in v2 while maintaining v1
- Standard industry practice for production APIs
- Easier to deprecate old endpoints

**Implementation Strategy**:
1. Add version prefix to all routes (`/api/v1/...`)
2. Update frontend API client to use versioned endpoints
3. Document versioning policy in API docs
4. Consider version negotiation header: `Accept: application/vnd.codeframe.v1+json`

---

## 2. Consistent Response Envelopes

### Current State
Mixed response formats across endpoints:
- Some return bare objects: `GET /api/projects/{id}` → `{...project}`
- Some return bare arrays: `GET /api/projects/{id}/agents` → `[...agents]`
- Some return wrapped: `POST /api/projects/{id}/agents` → `{"assignment_id": 42, "message": "..."}`

### Proposed Improvement
Standardize on consistent envelope pattern for all responses:

```typescript
// Success response envelope
{
  "data": <actual_response_data>,
  "meta": {
    "timestamp": "2025-12-03T10:30:00Z",
    "request_id": "req_abc123"
  }
}

// List response envelope with pagination
{
  "data": [...items],
  "meta": {
    "timestamp": "2025-12-03T10:30:00Z",
    "request_id": "req_abc123",
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total_pages": 5,
      "total_items": 97
    }
  }
}

// Error response envelope
{
  "error": {
    "code": "AGENT_NOT_FOUND",
    "message": "Agent backend-001 not found",
    "details": {...}
  },
  "meta": {
    "timestamp": "2025-12-03T10:30:00Z",
    "request_id": "req_abc123"
  }
}
```

**Benefits**:
- Predictable response structure for all endpoints
- Room for metadata without breaking schema
- Standard error format
- Request tracing via request_id

**Implementation Strategy**:
1. Create Pydantic response envelope models
2. Update all endpoints to use envelopes
3. Update frontend API client to unwrap responses
4. Provide migration guide for any external consumers

---

## 3. Pagination Support

### Current State
List endpoints return all results:
- `GET /api/projects/{id}/agents` → Returns ALL agents
- No limit on response size
- Performance degrades with scale

### Proposed Improvement
Add pagination to all list endpoints:

```python
@app.get("/api/v1/projects/{project_id}/agents")
async def get_project_agents(
    project_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    active_only: bool = Query(True, alias="is_active"),
):
    # Calculate offset
    offset = (page - 1) * per_page

    # Get paginated results + total count
    agents, total_count = db.get_agents_for_project_paginated(
        project_id,
        limit=per_page,
        offset=offset,
        active_only=active_only
    )

    return {
        "data": agents,
        "meta": {
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_pages": math.ceil(total_count / per_page),
                "total_items": total_count
            }
        }
    }
```

**Benefits**:
- Improved performance for large datasets
- Reduced bandwidth usage
- Standard API pattern
- Frontend can implement infinite scroll or pagination UI

**Implementation Strategy**:
1. Add pagination parameters to all list endpoints
2. Update database methods to support LIMIT/OFFSET
3. Return pagination metadata in response envelopes
4. Provide default per_page values (20-50 items)
5. Add max per_page limit (100 items)

---

## 4. Filtering & Sorting

### Current State
Limited filtering capabilities:
- Only `is_active` filter on agent/project lists
- No sorting options
- No multi-field filtering

### Proposed Improvement
Add comprehensive filtering and sorting:

```python
@app.get("/api/v1/projects/{project_id}/agents")
async def get_project_agents(
    project_id: int,
    # Pagination
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    # Filtering
    is_active: bool | None = Query(None),
    role: str | None = Query(None),
    agent_type: str | None = Query(None),
    status: str | None = Query(None),
    # Sorting
    sort_by: str = Query("assigned_at", regex="^(assigned_at|agent_id|role)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
):
    filters = {
        "is_active": is_active,
        "role": role,
        "agent_type": agent_type,
        "status": status
    }
    # Remove None values
    filters = {k: v for k, v in filters.items() if v is not None}

    agents, total = db.get_agents_for_project(
        project_id,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=per_page,
        offset=(page - 1) * per_page
    )

    return {"data": agents, "meta": {...}}
```

**Query Examples**:
```
GET /api/v1/projects/1/agents?role=backend&status=working&sort_by=assigned_at&sort_order=desc
GET /api/v1/projects/1/agents?is_active=false&agent_type=frontend
```

**Benefits**:
- Powerful query capabilities for frontend
- Reduced data transfer (filter server-side)
- Standard REST query patterns

**Implementation Strategy**:
1. Add filter/sort parameters to all list endpoints
2. Update database methods to build dynamic WHERE/ORDER BY clauses
3. Validate filter field names (prevent SQL injection)
4. Document available filters in API docs

---

## 5. Rate Limiting & Throttling

### Current State
- No rate limiting
- Vulnerable to abuse/DoS
- No protection against runaway loops

### Proposed Improvement
Add rate limiting middleware:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/api/v1/projects/{project_id}/agents")
@limiter.limit("100/minute")  # 100 requests per minute per IP
async def get_project_agents(request: Request, project_id: int):
    # ...
```

**Proposed Limits**:
- Read endpoints: 100 requests/minute
- Write endpoints: 30 requests/minute
- Authentication endpoints: 5 requests/minute
- Global: 1000 requests/hour per IP

**Benefits**:
- Protection against abuse
- Improved service stability
- Fair resource allocation

---

## 6. API Documentation (OpenAPI/Swagger)

### Current State
- Minimal inline docstrings
- No interactive API documentation
- Schema definitions scattered

### Proposed Improvement
Enhance FastAPI's auto-generated OpenAPI docs:

```python
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="CodeFRAME API",
        version="1.0.0",
        description="Multi-Agent Project Management API",
        routes=app.routes,
    )

    # Add custom schema extensions
    openapi_schema["info"]["x-logo"] = {
        "url": "https://example.com/logo.png"
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

**Benefits**:
- Interactive API explorer at `/docs`
- Auto-generated client SDKs
- Up-to-date documentation
- Request/response examples

---

## 7. HATEOAS Links (Hypermedia)

### Current State
- Clients must construct URLs manually
- Hard-coded URL patterns in frontend
- Breaking URL changes require frontend updates

### Proposed Improvement
Include navigational links in responses:

```json
{
  "data": {
    "project_id": 1,
    "agent_id": "backend-001",
    "role": "primary_backend",
    "assigned_at": "2025-12-03T10:30:00Z",
    "is_active": true
  },
  "links": {
    "self": "/api/v1/projects/1/agents/backend-001",
    "project": "/api/v1/projects/1",
    "agent": "/api/v1/agents/backend-001",
    "unassign": {
      "href": "/api/v1/projects/1/agents/backend-001",
      "method": "DELETE"
    },
    "update_role": {
      "href": "/api/v1/projects/1/agents/backend-001/role",
      "method": "PUT"
    }
  },
  "meta": {...}
}
```

**Benefits**:
- Self-documenting API
- Frontend decoupled from URL structure
- Easier to refactor routes
- Discoverability of related resources

---

## 8. Health Check & Metrics Endpoints

### Current State
- No health check endpoint
- No metrics exposure
- Difficult to monitor in production

### Proposed Improvement
Add standard health/metrics endpoints:

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(UTC).isoformat()
    }

@app.get("/health/ready")
async def readiness_check():
    # Check database connection
    try:
        db.conn.execute("SELECT 1")
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"

    return {
        "status": "ready" if db_status == "healthy" else "not_ready",
        "checks": {
            "database": db_status
        }
    }

@app.get("/metrics")
async def metrics():
    return {
        "requests_total": request_counter.get(),
        "requests_active": active_requests.get(),
        "database_connections": db.pool_size(),
        "uptime_seconds": time.time() - app.state.start_time
    }
```

**Benefits**:
- Kubernetes/Docker health probes
- Monitoring/alerting integration
- Performance visibility

---

## Implementation Priority

> **Updated 2026-01-06**: MVP complete. Re-prioritized based on production needs.

### High Priority (Production Hardening)
1. **Health Checks** - Required for monitoring/ops (partially implemented via `/health`)
2. **Rate Limiting** - Security/stability critical
3. **Pagination** - Performance/scalability critical

### Medium Priority (Developer Experience)
4. **API Versioning** - Foundational for future evolution
5. **Response Envelopes** - Consistency and metadata support
6. **API Documentation** - OpenAPI/Swagger already auto-generated by FastAPI

### Low Priority (Nice to Have)
7. **Filtering/Sorting** - Can be added incrementally per endpoint
8. **HATEOAS Links** - Advanced REST feature

---

## Next Steps

1. **Review & Approve**: Discuss with team and prioritize improvements
2. **Create Issues**: Break down into implementable issues
3. **Prototype**: Build proof-of-concept for versioning + pagination
4. **Migrate Incrementally**: Roll out changes endpoint-by-endpoint
5. **Update Frontend**: Coordinate frontend updates with each change

---

## References

- [REST API Best Practices](https://github.com/microsoft/api-guidelines)
- [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [Pagination Patterns](https://www.moesif.com/blog/technical/api-design/REST-API-Design-Filtering-Sorting-and-Pagination/)
- [API Versioning](https://www.freecodecamp.org/news/how-to-version-a-rest-api/)
