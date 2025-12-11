# FastAPI Router Refactoring - Implementation Plan

**Goal:** Break down the monolithic 4,161-line `server.py` file into modular, maintainable router files.

**Status:** Phase 1 Complete ✓

---

## Phase Overview

### Phase 1: Analysis ✓ COMPLETE
**Deliverable:** Comprehensive analysis report
**File:** `/home/frankbria/projects/codeframe/docs/refactoring/phase1-analysis-report.md`

**Key Findings:**
- 60+ endpoints organized into 8 logical groups
- 3 shared state objects (manager, running_agents, review_cache)
- 20+ inline imports for circular dependency avoidance
- Projects router is largest (26 endpoints, ~2000 LOC)

---

### Phase 2: Extract Simple Routers (Low Risk)
**Estimated Effort:** 4-6 hours
**Files to Create:**
- `codeframe/ui/routers/__init__.py`
- `codeframe/ui/routers/root.py` (3 endpoints + WebSocket)
- `codeframe/ui/routers/blockers.py` (2 endpoints)
- `codeframe/ui/routers/lint.py` (4 endpoints)

**Steps:**
1. Create `codeframe/ui/routers/` directory
2. Extract Root router (health checks, WebSocket)
3. Extract Blockers router
4. Extract Lint router
5. Update `server.py` to include routers with `app.include_router()`
6. Run E2E tests (47 tests)

**Success Criteria:**
- All E2E tests pass
- No import errors
- WebSocket functionality intact
- Lint operations work correctly

---

### Phase 3: Shared State Refactoring & Medium Routers
**Estimated Effort:** 6-8 hours
**Files to Create:**
- `codeframe/ui/dependencies.py` (dependency injection helpers)
- `codeframe/ui/routers/tasks.py` (4 endpoints)
- `codeframe/ui/routers/agents.py` (12 endpoints)

**Files to Modify:**
- `codeframe/ui/server.py` (move shared state to `app.state`)

**Steps:**
1. **Shared State Migration:**
   - Move `manager` → `app.state.manager`
   - Move `running_agents` → `app.state.running_agents`
   - Move `review_cache` → `app.state.review_cache`

2. **Create Dependency Injection Helpers:**
   ```python
   # codeframe/ui/dependencies.py
   def get_manager(request: Request) -> ConnectionManager:
       return request.app.state.manager

   def get_running_agents(request: Request) -> Dict[int, LeadAgent]:
       return request.app.state.running_agents

   def get_review_cache(request: Request) -> Dict[int, dict]:
       return request.app.state.review_cache
   ```

3. **Extract Tasks Router:**
   - Quality gates endpoints (2)
   - Review endpoints (2)
   - Use `review_cache` via dependency injection

4. **Extract Agents Router:**
   - Context management endpoints (7)
   - Flash save endpoints (2)
   - Review endpoints (2)
   - Metrics endpoint (1)
   - Use `review_cache` via dependency injection

5. **Update All Extracted Routers:**
   - Replace direct `manager` access with dependency injection
   - Replace direct `review_cache` access with dependency injection

6. **Run E2E Tests**

**Success Criteria:**
- All E2E tests pass
- No shared state access issues
- Context management works correctly
- Review operations work correctly
- Quality gates work correctly

---

### Phase 4: Extract Complex Router & Utilities
**Estimated Effort:** 8-10 hours
**Files to Create:**
- `codeframe/ui/routers/projects.py` (26 endpoints)
- `codeframe/ui/agent_lifecycle.py` (utility functions)
- `codeframe/core/config.py` (deployment mode helpers) - if not exists

**Steps:**
1. **Extract Utility Functions:**
   - Move `start_agent()` → `codeframe/ui/agent_lifecycle.py`
   - Move `get_deployment_mode()`, `is_hosted_mode()` → `codeframe/core/config.py`

2. **Extract Projects Router:**
   - CRUD endpoints (2)
   - Agent lifecycle endpoints (3)
   - Agent assignment endpoints (5)
   - Discovery endpoints (2)
   - Chat endpoints (2)
   - Checkpoint endpoints (6)
   - Metrics endpoints (2)
   - Review endpoints (2)
   - Session endpoint (1)
   - Other project endpoints (3)

3. **Update Projects Router Dependencies:**
   - Use `get_manager()` dependency
   - Use `get_running_agents()` dependency
   - Import utility functions from `agent_lifecycle`
   - Import config helpers from `config`

4. **Simplify server.py:**
   - Remove all endpoint definitions
   - Keep only: app setup, CORS, lifespan, router includes
   - Target: 100-200 LOC

5. **Run Full Regression Tests:**
   - E2E tests (47)
   - Backend tests (550+)
   - Manual smoke testing

**Success Criteria:**
- All tests pass (100% pass rate)
- `server.py` reduced to ~100-200 LOC
- All routers properly separated
- No circular import issues
- No shared state bugs

---

## Target File Structure

```
codeframe/ui/
├── server.py                    # App setup, CORS, lifespan (100-200 LOC) ⬅️ SIMPLIFIED
├── dependencies.py              # Dependency injection (NEW)
├── agent_lifecycle.py           # Agent utilities (NEW)
├── models.py                    # Request/response models (existing)
├── websocket_broadcasts.py      # WebSocket broadcasts (existing)
└── routers/                     # Router modules (NEW)
    ├── __init__.py
    ├── root.py                  # Health, WebSocket (50-100 LOC)
    ├── blockers.py              # Blockers (100-150 LOC)
    ├── lint.py                  # Lint operations (200-300 LOC)
    ├── tasks.py                 # Quality gates, reviews (300-400 LOC)
    ├── agents.py                # Context, flash save, metrics (400-600 LOC)
    └── projects.py              # Project lifecycle, discovery, etc. (600-800 LOC)

codeframe/core/
└── config.py                    # Deployment mode helpers (NEW or UPDATED)
```

---

## Testing Strategy

### Before Each Phase
1. Ensure all existing tests pass (baseline)
2. Document current test metrics (coverage, pass rate)

### After Each Phase
1. **Run E2E Tests:** `npx playwright test` (47 tests)
2. **Run Backend Tests:** `uv run pytest` (550+ tests)
3. **Check Coverage:** Should remain at 88%+
4. **Manual Smoke Testing:**
   - Create project
   - Start agent
   - Chat with agent
   - Discovery workflow
   - Quality gates
   - Checkpoints

### Rollback Plan
- Each phase is a separate commit
- If tests fail, revert commit and investigate
- Fix issues before proceeding to next phase

---

## Risk Mitigation

### High-Risk Areas
1. **WebSocket Integration**
   - **Risk:** manager dependency across routers
   - **Mitigation:** Move to `app.state.manager`, use dependency injection

2. **Shared State (running_agents, review_cache)**
   - **Risk:** Mutable state accessed across routers
   - **Mitigation:** Move to `app.state`, document async safety

3. **Inline Imports**
   - **Risk:** Circular dependencies
   - **Mitigation:** Preserve inline import patterns in routers

4. **Projects Router Complexity**
   - **Risk:** 26 endpoints, high coupling
   - **Mitigation:** Extract last, thorough testing

---

## Success Metrics

**Code Quality:**
- `server.py`: 4,161 LOC → 100-200 LOC (95% reduction)
- Router files: <800 LOC each (maintainable size)
- Test pass rate: 100%
- Test coverage: ≥88%

**Maintainability:**
- Clear separation of concerns
- Easy to locate endpoints (by resource type)
- Reduced cognitive load for developers
- Easier to onboard new contributors

**Performance:**
- No performance regression
- Same response times
- Same WebSocket latency

---

## Timeline Estimate

| Phase | Effort | Duration (Sequential) | Duration (Parallel) |
|-------|--------|----------------------|---------------------|
| Phase 1 (Analysis) | 4 hours | Complete | Complete |
| Phase 2 (Simple Routers) | 4-6 hours | 1 day | 1 day |
| Phase 3 (Medium Routers) | 6-8 hours | 1-2 days | 1 day |
| Phase 4 (Complex Router) | 8-10 hours | 1-2 days | 1 day |
| **Total** | **22-28 hours** | **3-5 days** | **2-3 days** |

**Note:** Parallel execution possible with multiple Claude Code sessions (worktrees)

---

## Post-Refactoring Benefits

1. **Maintainability:** Easier to locate and modify endpoints
2. **Testability:** Routers can be tested in isolation
3. **Scalability:** Can split routers into microservices later
4. **Collaboration:** Multiple developers can work on different routers
5. **Documentation:** Each router is self-contained and easier to document
6. **Code Review:** Smaller files = faster, more thorough reviews

---

## Questions & Decisions

### Q1: Should we use APIRouter tags?
**Decision:** Yes, use tags for OpenAPI grouping
```python
router = APIRouter(prefix="/api/projects", tags=["projects"])
```

### Q2: Should we keep inline imports?
**Decision:** Yes, preserve inline imports to avoid circular dependencies
- Keep imports inside endpoint functions if needed
- Document why (circular dependency avoidance)

### Q3: Should review_cache be replaced with Redis?
**Decision:** Phase 3: Move to `app.state`, Phase 5 (future): Consider Redis
- Short-term: `app.state.review_cache` (simple, works)
- Long-term: Redis or database-backed cache (multi-instance scaling)

### Q4: Should we split Projects router further?
**Decision:** Phase 4: Keep as one router, Phase 5 (future): Consider splitting
- 26 endpoints is large but manageable
- Split into `projects.py`, `discovery.py`, `checkpoints.py` if needed

---

## Appendix: Router Endpoint Summary

### Root Router (3 endpoints + WebSocket)
- `GET /` - Simple health check
- `GET /health` - Detailed health check
- `WEBSOCKET /ws` - WebSocket connection

### Blockers Router (2 endpoints)
- `GET /api/blockers/{blocker_id}` - Get blocker
- `POST /api/blockers/{blocker_id}/resolve` - Resolve blocker

### Lint Router (4 endpoints)
- `GET /api/lint/results` - Lint results
- `GET /api/lint/trend` - Lint trend
- `GET /api/lint/config` - Lint config
- `POST /api/lint/run` - Run lint

### Tasks Router (4 endpoints)
- `GET /api/tasks/{task_id}/quality-gates` - Quality gate status
- `POST /api/tasks/{task_id}/quality-gates` - Trigger quality gates
- `GET /api/tasks/{task_id}/review-status` - Review status
- `GET /api/tasks/{task_id}/reviews` - List reviews

### Agents Router (12 endpoints)
- `GET /api/agents/{agent_id}/projects` - List agent projects
- `GET /api/agents/{agent_id}/context` - List context
- `DELETE /api/agents/{agent_id}/context/{item_id}` - Delete context
- `GET /api/agents/{agent_id}/context/stats` - Context stats
- `GET /api/agents/{agent_id}/context/items` - Context items
- `POST /api/agents/{agent_id}/context/update-scores` - Update scores
- `POST /api/agents/{agent_id}/context/update-tiers` - Update tiers
- `POST /api/agents/{agent_id}/flash-save` - Flash save
- `GET /api/agents/{agent_id}/flash-save/checkpoints` - List checkpoints
- `POST /api/agents/{agent_id}/review` - Trigger review
- `POST /api/agents/review/analyze` - Analyze review
- `GET /api/agents/{agent_id}/metrics` - Agent metrics

### Projects Router (26 endpoints)
- `GET /api/projects` - List projects
- `POST /api/projects` - Create project
- `POST /api/projects/{project_id}/start` - Start agent
- `GET /api/projects/{project_id}/status` - Project status
- `POST /api/projects/{project_id}/pause` - Pause project
- `POST /api/projects/{project_id}/resume` - Resume project
- `GET /api/projects/{project_id}/tasks` - List tasks
- `GET /api/projects/{project_id}/activity` - Activity log
- `GET /api/projects/{project_id}/issues` - List issues
- `GET /api/projects/{project_id}/blockers` - List blockers
- `GET /api/projects/{project_id}/blockers/metrics` - Blocker metrics
- `GET /api/projects/{project_id}/prd` - Get PRD
- `GET /api/projects/{project_id}/session` - Session state
- `GET /api/projects/{project_id}/agents` - List agents
- `POST /api/projects/{project_id}/agents` - Assign agent
- `DELETE /api/projects/{project_id}/agents/{agent_id}` - Remove agent
- `PUT /api/projects/{project_id}/agents/{agent_id}/role` - Update role
- `PATCH /api/projects/{project_id}/agents/{agent_id}` - Update role (alt)
- `POST /api/projects/{project_id}/discovery/answer` - Submit answer
- `GET /api/projects/{project_id}/discovery/progress` - Discovery progress
- `POST /api/projects/{project_id}/chat` - Chat
- `GET /api/projects/{project_id}/chat/history` - Chat history
- `GET /api/projects/{project_id}/checkpoints` - List checkpoints
- `POST /api/projects/{project_id}/checkpoints` - Create checkpoint
- `GET /api/projects/{project_id}/checkpoints/{id}` - Get checkpoint
- `DELETE /api/projects/{project_id}/checkpoints/{id}` - Delete checkpoint
- `POST /api/projects/{project_id}/checkpoints/{id}/restore` - Restore
- `GET /api/projects/{project_id}/checkpoints/{id}/diff` - Checkpoint diff
- `GET /api/projects/{project_id}/metrics/tokens` - Token metrics
- `GET /api/projects/{project_id}/metrics/costs` - Cost metrics
- `GET /api/projects/{project_id}/code-reviews` - List reviews
- `GET /api/projects/{project_id}/review-stats` - Review stats

---

**Next Action:** Proceed to Phase 2 - Extract Simple Routers
