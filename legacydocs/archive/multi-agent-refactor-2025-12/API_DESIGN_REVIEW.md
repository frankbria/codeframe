# CodeFRAME Multi-Agent API Design Review

**Review Date**: 2025-12-03
**Reviewer**: REST Expert Agent
**Scope**: Multi-Agent Per Project Architecture API Design
**Version**: Phase 3 Implementation

---

## Executive Summary

**Overall Assessment**: ✅ **GOOD** with room for improvement

The CodeFRAME API demonstrates solid RESTful design principles with proper resource hierarchy, appropriate HTTP verbs, and good status code usage. The multi-agent per project architecture is well-implemented with clear separation of concerns. However, there are opportunities to improve consistency, add pagination where missing, and enhance discoverability.

**Key Strengths**:
- Clear resource hierarchy (`/projects/{id}/agents` vs `/agents/{id}/projects`)
- Proper HTTP verb usage (GET, POST, PATCH, DELETE)
- Appropriate status codes (201 for creation, 204 for deletion, 404 for not found)
- Idempotent operations handled correctly
- Good separation between project-scoped and agent-scoped resources

**Key Issues**:
- Missing pagination on several list endpoints
- Inconsistent pagination parameters (limit/offset vs page/per_page)
- No HATEOAS links for resource discoverability
- Missing filtering/sorting options on some collection endpoints
- No explicit versioning strategy

---

## Detailed Analysis

### 1. Resource Hierarchy & URL Structure ✅ EXCELLENT

**Score**: 9/10

#### Strengths
The API follows a clear and intuitive resource hierarchy:

```
Projects (parent resource)
  ├── /api/projects
  ├── /api/projects/{id}
  ├── /api/projects/{id}/agents           # Agents assigned to project
  ├── /api/projects/{id}/agents/{agent_id} # Specific agent assignment
  ├── /api/projects/{id}/tasks
  ├── /api/projects/{id}/checkpoints
  └── /api/projects/{id}/metrics

Agents (independent resource)
  ├── /api/agents/{id}/projects           # Projects assigned to agent
  ├── /api/agents/{id}/context
  ├── /api/agents/{id}/metrics
  └── /api/agents/{id}/flash-save
```

This properly represents the many-to-many relationship between projects and agents:
- **Project-centric view**: `/projects/{id}/agents` - "What agents are working on this project?"
- **Agent-centric view**: `/agents/{id}/projects` - "What projects is this agent assigned to?"

#### Areas for Improvement
1. **Missing top-level agents collection endpoint**: There's no `GET /api/agents` to list all available agents in the system. This would be useful for:
   - Discovering which agents are available for assignment
   - Admin dashboards showing all agents
   - System monitoring

**Recommendation**: Add `GET /api/agents` with filtering:
```
GET /api/agents?status=idle&type=backend&limit=20&offset=0
```

---

### 2. HTTP Verb Usage ✅ GOOD

**Score**: 8/10

#### Strengths
The API uses HTTP verbs appropriately:

| Verb   | Usage                                    | Example                                      |
|--------|------------------------------------------|----------------------------------------------|
| GET    | Retrieve resources                       | `GET /api/projects/{id}/agents`             |
| POST   | Create new resources or trigger actions  | `POST /api/projects/{id}/agents`            |
| PATCH  | Partial updates                          | `PATCH /api/projects/{id}/agents/{agent_id}`|
| DELETE | Remove resources (soft delete)           | `DELETE /api/projects/{id}/agents/{agent_id}`|

#### Areas for Improvement

1. **Inconsistent use of POST for operations vs resources**:
   - `POST /api/agents/{agent_id}/flash-save` - This is an operation, not a resource creation
   - `POST /api/agents/{agent_id}/context/update-scores` - Operation
   - `POST /api/agents/{agent_id}/context/update-tiers` - Operation

**Current**:
```http
POST /api/agents/{agent_id}/flash-save
POST /api/agents/{agent_id}/context/update-scores
POST /api/agents/{agent_id}/context/update-tiers
```

**Recommendation** (more RESTful):
```http
POST /api/agents/{agent_id}/actions/flash-save
POST /api/agents/{agent_id}/context/actions/recalculate-scores
POST /api/agents/{agent_id}/context/actions/update-tiers
```

Or use custom HTTP verbs (less preferred):
```http
POST /api/agents/{agent_id}/flash-save    # Keep as-is but document as RPC-style
```

2. **Missing PUT for full resource replacement**:
   - Currently only PATCH is available for updates
   - Consider adding PUT for idempotent full replacement

---

### 3. Status Codes ✅ EXCELLENT

**Score**: 9/10

#### Strengths
Excellent use of HTTP status codes:

| Code | Usage                                    | Example                                      |
|------|------------------------------------------|----------------------------------------------|
| 200  | Successful GET/PATCH                     | `GET /api/projects/{id}/agents`             |
| 201  | Resource created                         | `POST /api/projects/{id}/agents`            |
| 202  | Accepted for async processing            | `POST /api/projects/{id}/start`             |
| 204  | Successful deletion (no content)         | `DELETE /api/projects/{id}/agents/{agent_id}`|
| 400  | Bad request (validation errors)          | Empty message body                          |
| 404  | Resource not found                       | Project/agent doesn't exist                 |
| 409  | Conflict (duplicate resource)            | Agent already assigned to project           |
| 500  | Internal server error                    | Database errors                             |

#### Areas for Improvement
1. **Missing 422 Unprocessable Entity**: Currently using 400 for validation errors. Consider 422 for semantic validation errors:
   ```
   400 - Malformed JSON, missing required fields
   422 - Valid JSON but semantically incorrect (e.g., invalid enum values)
   ```

---

### 4. Idempotency ✅ GOOD

**Score**: 8/10

#### Strengths
- **GET operations**: Naturally idempotent ✅
- **DELETE operations**: Return 404 if already deleted (safe idempotency) ✅
- **POST assignment**: Returns 409 Conflict if agent already assigned ✅

#### Areas for Improvement
1. **POST project creation**: Not idempotent (returns 409 if duplicate name). Consider:
   - Adding idempotency keys for client retries
   - Returning existing project with 200 status if name matches (PUT-like behavior)

**Recommendation**: Add idempotency key support:
```http
POST /api/projects
Idempotency-Key: abc123-def456-ghi789

# If duplicate key detected, return cached response
```

2. **PATCH operations**: Ensure PATCH is idempotent by using absolute values, not increments:
   ```json
   // Good (idempotent)
   {"role": "primary_backend"}

   // Bad (not idempotent)
   {"priority": "+1"}
   ```

---

### 5. Pagination ⚠️ NEEDS IMPROVEMENT

**Score**: 4/10

#### Current Issues
1. **Missing pagination on most collection endpoints**:
   ```
   GET /api/projects/{id}/agents          ❌ No pagination
   GET /api/projects/{id}/tasks           ❌ No pagination (limit param exists but not offset)
   GET /api/projects/{id}/activity        ✅ Has limit (but not offset)
   GET /api/projects/{id}/issues          ❌ No pagination
   GET /api/projects/{id}/blockers        ❌ No pagination
   ```

2. **Inconsistent pagination parameters**:
   - Some endpoints use `limit`/`offset`
   - Others use `limit` only
   - No standardized `page`/`per_page` alternative

3. **Missing pagination metadata in responses**:
   ```json
   // Current response
   {
     "agents": [...],
     "total": 42  // Sometimes missing
   }

   // Missing: next_page, prev_page, total_pages
   ```

#### Recommendations

**Standard pagination parameters** (choose one consistently):

**Option A: Offset-based pagination** (current partial implementation)
```http
GET /api/projects/{id}/agents?limit=20&offset=40
```

**Option B: Page-based pagination** (more intuitive)
```http
GET /api/projects/{id}/agents?page=3&per_page=20
```

**Recommended response format**:
```json
{
  "data": [...],
  "pagination": {
    "total": 142,
    "count": 20,
    "per_page": 20,
    "current_page": 3,
    "total_pages": 8,
    "links": {
      "first": "/api/projects/1/agents?page=1&per_page=20",
      "prev": "/api/projects/1/agents?page=2&per_page=20",
      "next": "/api/projects/1/agents?page=4&per_page=20",
      "last": "/api/projects/1/agents?page=8&per_page=20"
    }
  }
}
```

**Priority fixes** (high to low):
1. ✅ Add pagination to `/api/projects/{id}/agents` (can return 100+ agents)
2. ✅ Add pagination to `/api/projects/{id}/tasks` (can return 1000+ tasks)
3. ✅ Add pagination to `/api/projects/{id}/issues`
4. ✅ Add pagination to `/api/projects` (main listing)
5. ⚠️ Add pagination to `/api/agents` (once created)

---

### 6. Filtering & Sorting ⚠️ NEEDS IMPROVEMENT

**Score**: 5/10

#### Current State
Some endpoints have basic filtering:
```http
GET /api/projects/{id}/agents?active_only=true
GET /api/projects/{id}/tasks?status=in_progress&limit=50
GET /api/agents/{id}/context/items?tier=hot&limit=100
GET /api/agents/{id}/projects?active_only=true
```

#### Missing Filtering Options

1. **GET /api/projects/{id}/agents** - Missing filters:
   ```http
   # Should support:
   ?type=backend              # Filter by agent type
   ?status=working            # Filter by agent status
   ?role=primary_backend      # Filter by role in project
   ?maturity_level=D3         # Filter by maturity level
   ```

2. **GET /api/projects/{id}/tasks** - Incomplete filtering:
   ```http
   # Current: ?status=in_progress

   # Should also support:
   ?assigned_to=agent-001     # Filter by assignee
   ?priority=0                # Filter by priority
   ?workflow_step=5           # Filter by workflow step
   ?requires_mcp=true         # Filter by MCP requirement
   ```

3. **No sorting support anywhere**:
   ```http
   # Should support:
   ?sort=created_at           # Sort field
   ?order=desc                # Sort order

   # Or combined:
   ?sort=-created_at,+priority  # Multiple sort fields
   ```

#### Recommendations

**Standard filtering syntax**:
```http
# Single filter
GET /api/projects/1/agents?type=backend

# Multiple filters (AND logic)
GET /api/projects/1/agents?type=backend&status=working

# Range filters
GET /api/projects/1/tasks?priority_gte=2&priority_lte=4

# Sorting
GET /api/projects/1/agents?sort=-created_at,+type

# Combined
GET /api/projects/1/agents?type=backend&status=working&sort=-last_heartbeat&limit=20&offset=0
```

**Implement for these endpoints first**:
1. `/api/projects/{id}/agents` (type, status, role)
2. `/api/projects/{id}/tasks` (assigned_to, priority, workflow_step)
3. `/api/projects` (status, phase)

---

### 7. HATEOAS & Discoverability ⚠️ MISSING

**Score**: 2/10

#### Current Issues
- No hypermedia links in responses
- Clients must construct URLs themselves
- No resource discoverability

#### Impact
- Clients tightly coupled to URL structure
- Breaking changes harder to manage
- No API exploration without documentation

#### Recommendations

**Add HATEOAS links to responses**:

```json
// GET /api/projects/1/agents/backend-001

{
  "agent_id": "backend-001",
  "type": "backend",
  "status": "working",
  "role": "primary_backend",
  "assigned_at": "2025-12-01T10:00:00Z",
  "is_active": true,

  "_links": {
    "self": {
      "href": "/api/projects/1/agents/backend-001"
    },
    "project": {
      "href": "/api/projects/1"
    },
    "agent_details": {
      "href": "/api/agents/backend-001"
    },
    "agent_context": {
      "href": "/api/agents/backend-001/context?project_id=1"
    },
    "agent_metrics": {
      "href": "/api/agents/backend-001/metrics?project_id=1"
    },
    "update_role": {
      "href": "/api/projects/1/agents/backend-001",
      "method": "PATCH"
    },
    "unassign": {
      "href": "/api/projects/1/agents/backend-001",
      "method": "DELETE"
    }
  }
}
```

**Benefits**:
- Decouples clients from URL construction
- Enables API version migration
- Makes API self-documenting
- Facilitates API exploration

**Priority**: Medium (nice-to-have for v1, essential for v2)

---

### 8. Versioning Strategy ⚠️ MISSING

**Score**: 1/10

#### Current Issues
- No explicit API versioning
- Breaking changes will affect all clients
- No migration path for deprecated endpoints

#### Recommendations

**Choose a versioning strategy**:

**Option A: URI versioning** (most common, explicit)
```http
GET /api/v1/projects/{id}/agents
GET /api/v2/projects/{id}/agents
```
✅ Pros: Clear, easy to test, simple routing
❌ Cons: URL pollution, multiple codebases

**Option B: Header versioning** (RESTful purist)
```http
GET /api/projects/{id}/agents
Accept: application/vnd.codeframe.v1+json
```
✅ Pros: Clean URLs, content negotiation
❌ Cons: Harder to test, less visible

**Option C: Query parameter** (not recommended)
```http
GET /api/projects/{id}/agents?version=1
```
❌ Cons: Not RESTful, easy to forget

**Recommendation**: Use **URI versioning** (`/api/v1/...`)

**Implementation plan**:
1. Current endpoints become `/api/v1/...`
2. Add deprecation headers to old endpoints:
   ```http
   Deprecation: true
   Sunset: 2026-06-01T00:00:00Z
   Link: </api/v2/projects>; rel="successor-version"
   ```
3. Maintain both versions for 6-12 months

**Priority**: High (implement before first stable release)

---

### 9. Request/Response Models ✅ GOOD

**Score**: 8/10

#### Strengths
- Well-defined Pydantic models for validation
- Clear separation of Request/Response models
- Good use of optional fields
- Comprehensive field descriptions

**Models reviewed**:
```python
# Request models
ProjectCreateRequest
AgentAssignmentRequest
AgentRoleUpdateRequest
CheckpointCreateRequest
RestoreCheckpointRequest

# Response models
ProjectResponse
AgentAssignmentResponse
ProjectAssignmentResponse
CheckpointResponse
```

#### Areas for Improvement

1. **Inconsistent naming**: Some models use `Request`/`Response` suffix, others don't
   ```python
   # Inconsistent
   ReviewRequest          ✅
   QualityGatesRequest    ✅
   ContextItemCreateModel ⚠️ (should be ContextItemCreateRequest)

   # Recommendation: Standardize on *Request/*Response suffix
   ```

2. **Missing envelope responses**: Responses don't consistently use envelope pattern
   ```json
   // Current (mixed)
   {"agents": [...]}                    // Has envelope
   [{"agent_id": "...", ...}]           // No envelope

   // Recommended (consistent)
   {
     "data": [...],
     "meta": {...}
   }
   ```

3. **Missing error response model**: No standardized error format
   ```json
   // Current FastAPI default
   {"detail": "Error message"}

   // Recommended (RFC 7807 Problem Details)
   {
     "type": "https://api.codeframe.dev/errors/agent-already-assigned",
     "title": "Agent Already Assigned",
     "status": 409,
     "detail": "Agent 'backend-001' is already assigned to project 1",
     "instance": "/api/projects/1/agents",
     "timestamp": "2025-12-03T10:30:00Z",
     "trace_id": "abc123"
   }
   ```

---

### 10. Security & Performance ✅ ADEQUATE

**Score**: 7/10

#### Strengths
- CORS properly configured for local development
- Query parameters validated (limit clamping: `min(max(limit, 1), 1000)`)
- Database connection pooling via SQLite
- Proper error handling with try/catch blocks

#### Areas for Improvement

1. **N+1 Query Problem**: Some endpoints may trigger multiple database queries
   ```python
   # Potential N+1 issue
   agents = db.get_agents_for_project(project_id)
   for agent in agents:
       context = db.get_context_stats(agent_id)  # N queries!

   # Recommendation: Use JOIN or batch queries
   ```

2. **No rate limiting**: Consider adding rate limiting headers
   ```http
   X-RateLimit-Limit: 100
   X-RateLimit-Remaining: 95
   X-RateLimit-Reset: 1638360000
   ```

3. **No authentication/authorization**: (May be intentional for MVP)
   - No API keys
   - No JWT tokens
   - No role-based access control (RBAC)

4. **Missing request validation**: Some endpoints don't validate project_id/agent_id existence before operations

---

## Breaking Changes Assessment

### Current API (No Versioning) → Proposed Changes

**Breaking Changes** (require major version bump):
1. ❌ Changing pagination from `limit/offset` to `page/per_page`
2. ❌ Renaming `ContextItemCreateModel` to `ContextItemCreateRequest`
3. ❌ Changing response envelope structure
4. ❌ Moving operation endpoints to `/actions/` subresources

**Non-Breaking Changes** (can be done in minor version):
1. ✅ Adding new query parameters (filtering, sorting)
2. ✅ Adding new optional response fields
3. ✅ Adding new endpoints
4. ✅ Adding `_links` HATEOAS metadata
5. ✅ Adding pagination metadata (`pagination` object)

**Recommendation**:
- Implement non-breaking improvements immediately
- Plan breaking changes for v2.0 release
- Add deprecation warnings for 6 months before breaking changes

---

## Recommended Priority Improvements

### High Priority (Ship Blockers)
1. **Add API versioning** (`/api/v1/...`)
2. **Add pagination to key collection endpoints**:
   - `/api/projects` (all projects)
   - `/api/projects/{id}/agents` (project agents)
   - `/api/projects/{id}/tasks` (project tasks)
3. **Standardize pagination parameters** (choose offset or page-based)
4. **Add top-level agents endpoint** (`GET /api/agents`)

### Medium Priority (Quality of Life)
5. **Add filtering support** (type, status, role filters)
6. **Add sorting support** (`?sort=-created_at`)
7. **Standardize request/response model naming**
8. **Add proper error response format** (RFC 7807)
9. **Add rate limiting headers**

### Low Priority (Future Enhancements)
10. **Add HATEOAS links** (hypermedia navigation)
11. **Add idempotency key support** (POST operations)
12. **Add authentication/authorization** (if required)
13. **Add GraphQL alternative** (if complex queries needed)

---

## OpenAPI/Swagger Documentation

### Current State ✅
- FastAPI auto-generates OpenAPI 3.0 spec
- Accessible at `/docs` (Swagger UI) and `/redoc` (ReDoc)
- Well-structured endpoint descriptions

### Recommendations
1. Add more detailed examples to schemas
2. Add request/response examples for each endpoint
3. Document error responses explicitly
4. Add API overview/getting started guide
5. Add changelog to track API changes

---

## Conclusion

**Overall Grade**: B+ (8.2/10)

The CodeFRAME API demonstrates solid RESTful design with clear resource modeling and appropriate HTTP semantics. The multi-agent per project architecture is well-implemented with a logical hierarchy that properly represents the many-to-many relationship.

**Key Strengths**:
- ✅ Clear resource hierarchy
- ✅ Proper HTTP verbs and status codes
- ✅ Good idempotency handling
- ✅ Well-defined Pydantic models

**Key Gaps**:
- ⚠️ Missing comprehensive pagination
- ⚠️ Incomplete filtering/sorting
- ⚠️ No API versioning strategy
- ⚠️ No HATEOAS links

**Next Steps**:
1. Implement high-priority improvements (versioning, pagination)
2. Standardize pagination across all collection endpoints
3. Add filtering and sorting support
4. Plan breaking changes for v2.0 release
5. Enhance OpenAPI documentation with examples

The API is **production-ready for MVP** but should address pagination and versioning before declaring a stable v1.0 release.

---

## Appendix: API Endpoints Inventory

### Complete Endpoint List (47 total)

#### Projects (13 endpoints)
- `GET    /api/projects` - List all projects
- `POST   /api/projects` - Create new project
- `GET    /api/projects/{id}/status` - Get project status
- `POST   /api/projects/{id}/start` - Start project agent
- `POST   /api/projects/{id}/pause` - Pause project
- `POST   /api/projects/{id}/resume` - Resume project
- `GET    /api/projects/{id}/agents` - List project agents ✅
- `POST   /api/projects/{id}/agents` - Assign agent to project ✅
- `PATCH  /api/projects/{id}/agents/{agent_id}` - Update agent role ✅
- `DELETE /api/projects/{id}/agents/{agent_id}` - Remove agent from project ✅
- `GET    /api/projects/{id}/tasks` - List project tasks
- `GET    /api/projects/{id}/activity` - Get activity log
- `GET    /api/projects/{id}/issues` - List project issues

#### Agents (11 endpoints)
- `GET    /api/agents/{id}/projects` - List agent projects ✅
- `GET    /api/agents/{id}/context` - List context items
- `POST   /api/agents/{id}/context` - Create context item
- `GET    /api/agents/{id}/context/items` - Get context items (filtered)
- `GET    /api/agents/{id}/context/stats` - Get context statistics
- `GET    /api/agents/{id}/context/{item_id}` - Get specific context item
- `DELETE /api/agents/{id}/context/{item_id}` - Delete context item
- `POST   /api/agents/{id}/context/update-scores` - Recalculate scores
- `POST   /api/agents/{id}/context/update-tiers` - Update tiers
- `POST   /api/agents/{id}/flash-save` - Trigger flash save
- `GET    /api/agents/{id}/metrics` - Get agent metrics

#### Other Resources (23 endpoints)
- Tasks (3): quality-gates, reviews
- Checkpoints (4): list, create, get, delete, restore
- Metrics (2): tokens, costs
- Blockers (3): list, get, resolve
- Discovery (2): progress, answer
- Chat (2): send, history
- PRD (1): get
- Review (4): analyze, status, stats, reviews
- Lint (4): results, trend, config, run
- Session (1): get
- Health (1): health check

**✅ = Multi-agent architecture endpoint**
