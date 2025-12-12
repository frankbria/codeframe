# FastAPI Router Refactoring - Architecture Assessment

**Analyst**: FastAPI Architecture Expert
**Date**: 2025-12-11
**File Analyzed**: `/home/frankbria/projects/codeframe/codeframe/ui/server.py` (4,161 lines)
**Total Endpoints**: 65 endpoints (63 REST + 1 WebSocket + 1 root health check)

---

## Executive Summary

The current server.py is a **monolithic FastAPI application** with 65 endpoints organized into 11 functional domains. The refactoring from monolith to APIRouter-based architecture is **highly feasible** with **moderate complexity**. The main challenges are:

1. **Shared State Dependencies** - 3 module-level singletons (`app.state.db`, `running_agents`, `manager`)
2. **WebSocket Broadcasting** - `ConnectionManager` used across multiple endpoint groups
3. **Background Task Orchestration** - `BackgroundTasks` with cross-domain side effects
4. **Import Cycles Risk** - If routers need to import from each other or shared state utilities

**Recommended Approach**: Extract routers in 3 waves (simple → medium → complex) with dependency injection for shared state.

---

## 1. Current Routing Patterns

### 1.1 Endpoint Organization

FastAPI tags already provide logical grouping (though not consistently applied):

| Tag Category | Endpoint Count | Prefix Pattern | Notes |
|-------------|----------------|----------------|-------|
| **Projects** (untagged) | 14 | `/api/projects/*` | Core CRUD + agent assignment |
| **Context** | 6 | `/api/agents/{id}/context/*` | Context management (T067) |
| **Review** | 6 | `/api/agents/{id}/review/*`, `/api/tasks/{id}/reviews` | Code review system |
| **Checkpoints** | 6 | `/api/projects/{id}/checkpoints/*` | Checkpoint/restore |
| **Lint** | 4 | `/api/lint/*` | Linting results |
| **Metrics** | 3 | `/api/projects/{id}/metrics/*`, `/api/agents/{id}/metrics` | Token usage & costs |
| **Quality Gates** | 2 | `/api/tasks/{id}/quality-gates` | Pre-completion checks |
| **Session** | 1 | `/api/projects/{id}/session` | Session state |
| **Blockers** | 4 | `/api/blockers/*`, `/api/projects/{id}/blockers/*` | Human-in-loop blockers |
| **Chat** | 2 | `/api/projects/{id}/chat/*` | Lead agent chat |
| **Discovery** | 2 | `/api/projects/{id}/discovery/*` | PRD discovery |
| **Tasks** | 1 | `/api/projects/{id}/tasks` | Task listing |
| **Activity** | 1 | `/api/projects/{id}/activity` | Activity feed |
| **Issues** | 1 | `/api/projects/{id}/issues` | Issue tracking |
| **Health** | 2 | `/`, `/health` | Health checks |
| **WebSocket** | 1 | `/ws` | Real-time updates |
| **Project Control** | 2 | `/api/projects/{id}/pause`, `/api/projects/{id}/resume` | Project lifecycle (TODO stubs) |

### 1.2 Observed Patterns

**Good Practices**:
- ✅ RESTful resource naming (`/api/projects/{id}/tasks`)
- ✅ Consistent use of HTTP status codes (201 for creation, 202 for async, 204 for deletion)
- ✅ Response models for type safety (Pydantic)
- ✅ Query parameters for filtering (`status`, `limit`, `offset`)
- ✅ Tags for OpenAPI grouping (though inconsistent)

**Anti-Patterns**:
- ⚠️ Inconsistent tagging (14 project endpoints have no tags)
- ⚠️ Mixed resource hierarchies (`/api/agents/{id}/context` vs `/api/projects/{id}/checkpoints`)
- ⚠️ Direct `app.state` access instead of dependency injection
- ⚠️ Global singletons (`running_agents`, `review_cache`, `manager`) mutated across endpoints

---

## 2. APIRouter Extraction Complexity Assessment

### 2.1 Low Risk (Wave 1) - Extract First

These routers have **minimal cross-domain dependencies** and can be safely extracted with simple dependency injection:

#### 🟢 **Health Router** (2 endpoints)
- **Endpoints**: `GET /`, `GET /health`
- **Dependencies**: `app.state.db` (read-only health check)
- **Extraction Complexity**: **Trivial**
- **Risk**: None
- **Notes**: No business logic, no shared state mutations

#### 🟢 **Lint Router** (4 endpoints)
- **Endpoints**: `GET /api/lint/results`, `GET /api/lint/trend`, `GET /api/lint/config`, `POST /api/lint/run`
- **Dependencies**: `app.state.db`
- **Extraction Complexity**: **Low**
- **Risk**: None
- **Notes**: Self-contained domain, POST endpoint uses BackgroundTasks but no cross-router side effects

#### 🟢 **Session Router** (1 endpoint)
- **Endpoint**: `GET /api/projects/{project_id}/session`
- **Dependencies**: `app.state.db`
- **Extraction Complexity**: **Trivial**
- **Risk**: None
- **Notes**: Read-only, no mutations

#### 🟢 **Metrics Router** (3 endpoints)
- **Endpoints**: `GET /api/projects/{id}/metrics/tokens`, `GET /api/projects/{id}/metrics/costs`, `GET /api/agents/{id}/metrics`
- **Dependencies**: `app.state.db`, `MetricsTracker`
- **Extraction Complexity**: **Low**
- **Risk**: None
- **Notes**: Read-only analytics, `MetricsTracker` is a library utility (no state)

### 2.2 Medium Risk (Wave 2) - Extract Second

These routers have **moderate dependencies** on shared state or background tasks:

#### 🟡 **Discovery Router** (2 endpoints)
- **Endpoints**: `POST /api/projects/{id}/discovery/answer`, `GET /api/projects/{id}/discovery/progress`
- **Dependencies**: `app.state.db`, `LeadAgent` (instantiated ad-hoc)
- **Extraction Complexity**: **Medium**
- **Risk**: Instantiates `LeadAgent` directly - needs refactoring to use agent from `running_agents` or factory pattern
- **Notes**: Creates `LeadAgent` with `api_key="dummy-key-for-status"` which is a code smell

#### 🟡 **Tasks Router** (1 endpoint)
- **Endpoint**: `GET /api/projects/{id}/tasks`
- **Dependencies**: `app.state.db`
- **Extraction Complexity**: **Low**
- **Risk**: None (just a read operation)
- **Notes**: Could be merged into Projects router

#### 🟡 **Activity Router** (1 endpoint)
- **Endpoint**: `GET /api/projects/{id}/activity`
- **Dependencies**: `app.state.db`
- **Extraction Complexity**: **Low**
- **Risk**: None
- **Notes**: Could be merged into Projects router

#### 🟡 **Issues Router** (1 endpoint)
- **Endpoint**: `GET /api/projects/{id}/issues`
- **Dependencies**: `app.state.db`
- **Extraction Complexity**: **Low**
- **Risk**: None
- **Notes**: Could be merged into Projects router

#### 🟡 **Quality Gates Router** (2 endpoints)
- **Endpoints**: `GET /api/tasks/{id}/quality-gates`, `POST /api/tasks/{id}/quality-gates`
- **Dependencies**: `app.state.db`, `QualityGatesRunner`, `BackgroundTasks`, `manager.broadcast()`
- **Extraction Complexity**: **Medium**
- **Risk**: Uses WebSocket broadcasting for real-time updates - needs `ConnectionManager` dependency
- **Notes**: Background task mutates database and broadcasts events

#### 🟡 **Context Router** (6 endpoints)
- **Endpoints**: `POST /api/agents/{id}/context`, `GET /api/agents/{id}/context/{item_id}`, `GET /api/agents/{id}/context`, `DELETE /api/agents/{id}/context/{item_id}`, `POST /api/agents/{id}/context/update-scores`, `POST /api/agents/{id}/context/update-tiers`, `POST /api/agents/{id}/flash-save`, `GET /api/agents/{id}/flash-save/checkpoints`, `GET /api/agents/{id}/context/stats`, `GET /api/agents/{id}/context/items`
- **Dependencies**: `app.state.db`, `ContextManager`, `TokenCounter`, `manager.broadcast()` (for flash-save)
- **Extraction Complexity**: **Medium**
- **Risk**: Flash-save uses WebSocket broadcasting - needs `ConnectionManager` dependency
- **Notes**: 10 endpoints, mostly CRUD, one background broadcast

### 2.3 High Risk (Wave 3) - Extract Last

These routers have **complex dependencies** on shared state, background tasks, and WebSocket broadcasting:

#### 🔴 **Projects Router** (14 endpoints)
- **Endpoints**: All `/api/projects/*` endpoints (CRUD, start, status, agents, pause, resume)
- **Dependencies**: `app.state.db`, `app.state.workspace_manager`, `running_agents` dict, `manager.broadcast()`, `BackgroundTasks`, `LeadAgent`, `WorkspaceManager`
- **Extraction Complexity**: **High**
- **Risk**:
  - Mutates global `running_agents` dict (lines 171, 199, 480)
  - Uses `BackgroundTasks` to spawn `start_agent()` which broadcasts WebSocket events
  - `start_agent()` is a module-level function that needs to be refactored into a service
- **Notes**: Core domain with highest coupling to shared state

#### 🔴 **Chat Router** (2 endpoints)
- **Endpoints**: `POST /api/projects/{id}/chat`, `GET /api/projects/{id}/chat/history`
- **Dependencies**: `app.state.db`, `running_agents` dict, `manager.broadcast()`
- **Extraction Complexity**: **High**
- **Risk**: Reads from `running_agents` dict to interact with `LeadAgent` - needs agent service abstraction
- **Notes**: Chat POST broadcasts messages via WebSocket

#### 🔴 **Blockers Router** (4 endpoints)
- **Endpoints**: `GET /api/projects/{id}/blockers`, `GET /api/blockers/{id}`, `POST /api/blockers/{id}/resolve`, `GET /api/projects/{id}/blockers/metrics`
- **Dependencies**: `app.state.db`, `manager.broadcast()`
- **Extraction Complexity**: **Medium-High**
- **Risk**: Resolve endpoint broadcasts blocker resolution events
- **Notes**: Could be Wave 2 if WebSocket dependency is abstracted

#### 🔴 **Review Router** (6 endpoints)
- **Endpoints**: `POST /api/agents/{id}/review`, `GET /api/tasks/{id}/review-status`, `GET /api/projects/{id}/review-stats`, `POST /api/agents/review/analyze`, `GET /api/tasks/{id}/reviews`, `GET /api/projects/{id}/code-reviews`
- **Dependencies**: `app.state.db`, `review_cache` dict, `manager.broadcast()`, `BackgroundTasks`, `ReviewAgent`
- **Extraction Complexity**: **High**
- **Risk**:
  - Mutates global `review_cache` dict (lines 174, 2135)
  - Background task instantiates `ReviewAgent` and broadcasts events
  - Cache invalidation logic needs careful handling
- **Notes**: Analyze endpoint triggers complex async review workflow

#### 🔴 **Checkpoints Router** (6 endpoints)
- **Endpoints**: `GET /api/projects/{id}/checkpoints`, `POST /api/projects/{id}/checkpoints`, `GET /api/projects/{id}/checkpoints/{id}`, `DELETE /api/projects/{id}/checkpoints/{id}`, `POST /api/projects/{id}/checkpoints/{id}/restore`, `GET /api/projects/{id}/checkpoints/{id}/diff`
- **Dependencies**: `app.state.db`, `CheckpointManager`, SQLite direct access (line 3472)
- **Extraction Complexity**: **Medium-High**
- **Risk**: Delete endpoint uses raw SQL `cursor = app.state.db.conn.cursor()` - violates abstraction
- **Notes**: Restore endpoint could trigger complex state changes

#### 🔴 **WebSocket Router** (1 endpoint)
- **Endpoint**: `WS /ws`
- **Dependencies**: `ConnectionManager` (`manager`)
- **Extraction Complexity**: **Medium**
- **Risk**: All other routers broadcast through `manager` - needs to be injected or converted to a service
- **Notes**: Should remain in main app or be handled via dependency injection

---

## 3. Circular Import Risk Analysis

### 3.1 Current Import Structure

```
server.py (main app)
├── codeframe.core.models (Pydantic models)
├── codeframe.ui.models (Request/Response models)
├── codeframe.persistence.database (Database class)
├── codeframe.agents.lead_agent (LeadAgent)
├── codeframe.workspace (WorkspaceManager)
└── (lazy imports in functions)
    ├── codeframe.lib.context_manager (ContextManager)
    ├── codeframe.lib.checkpoint_manager (CheckpointManager)
    ├── codeframe.lib.metrics_tracker (MetricsTracker)
    ├── codeframe.lib.quality_gates (QualityGatesRunner)
    └── codeframe.lib.token_counter (TokenCounter)
```

### 3.2 Potential Circular Import Scenarios

#### ❌ **High Risk: Routers importing from each other**
**Example**: If `review_router.py` needs to trigger quality gates, it might import from `quality_gates_router.py`.

**Mitigation**: Extract business logic into service layer (`codeframe.services.review_service`, `codeframe.services.quality_gates_service`) and have routers import from services.

#### ❌ **Medium Risk: Shared state utilities importing from routers**
**Example**: If we create a `shared_state.py` module to hold `running_agents` and `review_cache`, and routers import from it, then a background task in a router tries to import another router's function.

**Mitigation**: Use dependency injection for all shared state. No global singletons.

#### ❌ **Low Risk: Dependency injection circular imports**
**Example**: If we create `dependencies.py` that imports from routers to set up dependencies.

**Mitigation**: Keep dependencies.py as a simple provider of factories, not importing any routers.

### 3.3 Recommended Import Architecture

```
# After refactoring:

codeframe/
├── ui/
│   ├── server.py                    # Main FastAPI app + lifespan
│   ├── dependencies.py              # Dependency injection providers
│   ├── websocket.py                 # ConnectionManager + WebSocket endpoint
│   ├── routers/
│   │   ├── __init__.py              # Register all routers
│   │   ├── health.py                # Health endpoints
│   │   ├── projects.py              # Project CRUD + control
│   │   ├── context.py               # Context management
│   │   ├── review.py                # Code review
│   │   ├── checkpoints.py           # Checkpoint/restore
│   │   ├── quality_gates.py         # Quality gates
│   │   ├── metrics.py               # Token usage & costs
│   │   ├── lint.py                  # Linting
│   │   ├── session.py               # Session state
│   │   ├── blockers.py              # Blockers
│   │   ├── chat.py                  # Chat with Lead Agent
│   │   └── discovery.py             # Discovery/PRD
│   ├── services/                    # Business logic layer (NEW)
│   │   ├── __init__.py
│   │   ├── agent_service.py         # Manage running_agents state
│   │   ├── review_service.py        # Review logic + cache
│   │   ├── websocket_service.py     # Broadcasting abstraction
│   │   └── project_service.py       # Project lifecycle
│   └── models.py                    # Pydantic request/response models
├── lib/                             # Library utilities (no router imports)
│   ├── context_manager.py
│   ├── checkpoint_manager.py
│   ├── metrics_tracker.py
│   ├── quality_gates.py
│   └── token_counter.py
└── ...
```

**Import Rules**:
1. ✅ Routers can import from `services/`, `lib/`, `dependencies.py`
2. ✅ Services can import from `lib/`, NOT from routers
3. ✅ `dependencies.py` can import from services and `websocket.py`, NOT from routers
4. ✅ `server.py` imports from `routers/`, `dependencies.py`, `websocket.py`
5. ❌ No circular imports between routers
6. ❌ No global singletons (use dependency injection)

---

## 4. Recommended Extraction Order

### Wave 1: Simple Routers (1-2 days)
**Goal**: Prove the pattern works, establish dependency injection foundation

1. **Health Router** - Simplest, no dependencies
2. **Lint Router** - Simple, database-only
3. **Session Router** - Simple, database-only
4. **Metrics Router** - Simple, read-only analytics

**Success Criteria**: All 10 endpoints migrated, tests pass, no circular imports

---

### Wave 2: Medium Complexity (2-3 days)
**Goal**: Handle WebSocket broadcasting and background tasks

5. **Context Router** - Needs ConnectionManager injection for flash-save
6. **Quality Gates Router** - Background tasks + WebSocket
7. **Discovery Router** - Needs agent factory pattern
8. **Blockers Router** - WebSocket broadcasting
9. **Tasks/Activity/Issues Routers** - Merge into Projects or keep separate

**Success Criteria**: 20+ endpoints migrated, WebSocket events still work, background tasks operational

---

### Wave 3: Complex Routers (3-4 days)
**Goal**: Refactor shared state and agent lifecycle management

10. **Projects Router** - Extract `start_agent()` into service
11. **Chat Router** - Use agent service abstraction
12. **Review Router** - Extract cache into service
13. **Checkpoints Router** - Remove raw SQL, use Database methods
14. **WebSocket Router** - Move to `websocket.py` module

**Success Criteria**: All 65 endpoints migrated, no global state, 100% test coverage maintained

---

## 5. FastAPI-Specific Concerns

### 5.1 Dependency Injection Patterns

**Current Problem**: Direct `app.state` access violates separation of concerns
```python
# Anti-pattern (current)
@app.get("/api/projects")
async def list_projects():
    projects = app.state.db.list_projects()  # Tight coupling
```

**Solution**: Use FastAPI dependency injection
```python
# Better (after refactoring)
from fastapi import Depends
from codeframe.ui.dependencies import get_db, get_websocket_manager

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("/")
async def list_projects(db: Database = Depends(get_db)):
    projects = db.list_projects()
```

**Dependency Providers** (`dependencies.py`):
```python
from fastapi import Request
from codeframe.persistence.database import Database
from codeframe.ui.websocket import ConnectionManager
from codeframe.ui.services.agent_service import AgentService

def get_db(request: Request) -> Database:
    return request.app.state.db

def get_websocket_manager(request: Request) -> ConnectionManager:
    return request.app.state.websocket_manager

def get_agent_service(
    db: Database = Depends(get_db),
    ws: ConnectionManager = Depends(get_websocket_manager)
) -> AgentService:
    return AgentService(db=db, websocket_manager=ws)
```

### 5.2 Background Tasks

**Current Problem**: Background tasks instantiate agents and broadcast events inline
```python
# Anti-pattern (current)
async def start_agent(project_id, db, agents_dict, api_key):
    agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)
    agents_dict[project_id] = agent  # Global state mutation
    await manager.broadcast({...})   # Global singleton
```

**Solution**: Inject services into background tasks
```python
# Better (after refactoring)
@router.post("/{project_id}/start")
async def start_project(
    project_id: int,
    background_tasks: BackgroundTasks,
    agent_service: AgentService = Depends(get_agent_service)
):
    background_tasks.add_task(
        agent_service.start_agent,
        project_id=project_id
    )
```

**AgentService** (service layer):
```python
class AgentService:
    def __init__(self, db: Database, websocket_manager: ConnectionManager):
        self.db = db
        self.ws = websocket_manager
        self.running_agents: Dict[int, LeadAgent] = {}

    async def start_agent(self, project_id: int):
        api_key = self._get_api_key()
        agent = LeadAgent(project_id=project_id, db=self.db, api_key=api_key)
        self.running_agents[project_id] = agent
        await self.ws.broadcast({"type": "agent_started", ...})
```

### 5.3 WebSocket Handling

**Current Problem**: `ConnectionManager` is a global singleton mutated from multiple endpoints

**Solution**: Move to service layer with dependency injection
```python
# websocket.py
class ConnectionManager:
    # ... existing implementation ...

manager = ConnectionManager()  # Module-level singleton (OK for WebSocket)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle messages
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

**In routers**:
```python
from fastapi import Depends
from codeframe.ui.dependencies import get_websocket_manager

@router.post("/{blocker_id}/resolve")
async def resolve_blocker(
    blocker_id: int,
    ws: ConnectionManager = Depends(get_websocket_manager)
):
    # ... resolve logic ...
    await ws.broadcast({"type": "blocker_resolved", ...})
```

### 5.4 Lifespan Context Managers

**Current Pattern**: Good, no changes needed
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db = Database(db_path)
    app.state.db.initialize()
    app.state.workspace_manager = WorkspaceManager(workspace_root)

    yield

    # Shutdown
    if hasattr(app.state, "db") and app.state.db:
        app.state.db.close()
```

**Recommendation**: Keep in `server.py`, add WebSocket manager:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db = Database(db_path)
    app.state.db.initialize()
    app.state.workspace_manager = WorkspaceManager(workspace_root)
    app.state.websocket_manager = ConnectionManager()  # Add this

    yield

    # Shutdown
    if hasattr(app.state, "db"):
        app.state.db.close()
```

### 5.5 Middleware Dependencies

**Current Pattern**: CORS middleware configured at app level - no changes needed
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Recommendation**: Keep in `server.py`, no router-level middleware needed

---

## 6. Specific Refactoring Challenges

### 6.1 Global State: `running_agents`

**Problem**: Mutable dict accessed from Projects and Chat routers

**Solution**: Create `AgentService` class
```python
# services/agent_service.py
class AgentService:
    def __init__(self, db: Database, websocket_manager: ConnectionManager):
        self.db = db
        self.ws = websocket_manager
        self._running_agents: Dict[int, LeadAgent] = {}

    async def start_agent(self, project_id: int, api_key: str):
        agent = LeadAgent(project_id=project_id, db=self.db, api_key=api_key)
        self._running_agents[project_id] = agent
        # Update DB, broadcast events

    def get_agent(self, project_id: int) -> Optional[LeadAgent]:
        return self._running_agents.get(project_id)

    async def stop_agent(self, project_id: int):
        if project_id in self._running_agents:
            # Cleanup, broadcast
            del self._running_agents[project_id]
```

**Usage**:
```python
# dependencies.py
_agent_service: Optional[AgentService] = None

def get_agent_service(request: Request) -> AgentService:
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService(
            db=request.app.state.db,
            websocket_manager=request.app.state.websocket_manager
        )
    return _agent_service
```

### 6.2 Global State: `review_cache`

**Problem**: Mutable dict accessed from Review router

**Solution**: Create `ReviewService` class
```python
# services/review_service.py
class ReviewService:
    def __init__(self, db: Database):
        self.db = db
        self._cache: Dict[int, dict] = {}

    async def trigger_review(self, task_id: int, agent_id: str):
        # Run review, update cache
        self._cache[task_id] = report

    def get_cached_review(self, task_id: int) -> Optional[dict]:
        return self._cache.get(task_id)

    def invalidate_cache(self, task_id: int):
        self._cache.pop(task_id, None)
```

### 6.3 Raw SQL Access

**Problem**: Line 3472 uses `app.state.db.conn.cursor()` for checkpoint deletion

**Solution**: Add proper method to `Database` class
```python
# persistence/database.py
class Database:
    def delete_checkpoint_cascade(self, checkpoint_id: int):
        """Delete checkpoint and all related data."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,))
        self.conn.commit()
```

### 6.4 Ad-hoc Agent Instantiation

**Problem**: Lines 988, 1162, 2109 create `LeadAgent` with dummy API keys

**Example**:
```python
# Anti-pattern
agent = LeadAgent(project_id=project_id, db=app.state.db, api_key="dummy-key-for-status")
```

**Solution**: Use agent service or factory pattern
```python
# Better
agent = agent_service.get_or_create_agent(project_id)
```

---

## 7. Testing Impact

### 7.1 Test File Organization

**Current Tests** (assumption based on codebase structure):
```
tests/
├── test_server.py              # Monolithic tests (4161 lines mirrored?)
└── ...
```

**After Refactoring**:
```
tests/
├── routers/
│   ├── test_health_router.py
│   ├── test_projects_router.py
│   ├── test_context_router.py
│   ├── test_review_router.py
│   ├── ...
├── services/
│   ├── test_agent_service.py
│   ├── test_review_service.py
│   └── test_websocket_service.py
├── integration/
│   ├── test_full_workflow.py    # E2E tests
│   └── test_websocket_events.py
└── conftest.py                  # Shared fixtures
```

### 7.2 Test Fixtures Needed

```python
# conftest.py
import pytest
from fastapi.testclient import TestClient
from codeframe.ui.server import app
from codeframe.persistence.database import Database

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    db.initialize()
    yield db
    db.close()

@pytest.fixture
def client(db):
    app.state.db = db
    return TestClient(app)

@pytest.fixture
def agent_service(db):
    from codeframe.ui.services.agent_service import AgentService
    from codeframe.ui.websocket import ConnectionManager
    return AgentService(db=db, websocket_manager=ConnectionManager())
```

### 7.3 Coverage Maintenance

**Requirement**: Maintain 88%+ coverage during refactoring

**Strategy**:
1. Run coverage before each wave: `uv run pytest --cov=codeframe.ui --cov-report=html`
2. Ensure each new router file has >85% coverage
3. Write integration tests for complex background tasks
4. Test WebSocket broadcasting with `WebSocketTestSession` from Starlette

---

## 8. Performance Considerations

### 8.1 Dependency Injection Overhead

**Concern**: FastAPI's dependency injection system uses async context managers and function calls

**Impact**: Negligible (<1ms per request) - FastAPI's DI is highly optimized

**Recommendation**: Use caching for expensive dependencies (already done with `_agent_service` singleton pattern)

### 8.2 Router Registration Order

**Current**: 65 endpoints registered in a single file (linear scan)

**After**: 13 routers with ~5 endpoints each

**Impact**: None - FastAPI pre-compiles routes at startup

### 8.3 OpenAPI Schema Generation

**Current**: Single large OpenAPI spec

**After**: Same spec, but with cleaner tag organization

**Impact**: None - schema size unchanged

---

## 9. Migration Risks & Mitigations

### Risk 1: Breaking WebSocket Broadcasting

**Probability**: Medium
**Impact**: High (real-time updates stop working)

**Mitigation**:
- Create comprehensive WebSocket integration tests before refactoring
- Use dependency injection for `ConnectionManager` from day 1
- Test each router's broadcast events after extraction

### Risk 2: Background Task Failures

**Probability**: Medium
**Impact**: High (agent startup, quality gates, reviews fail silently)

**Mitigation**:
- Add structured logging to all background tasks
- Write integration tests that verify background task completion
- Use `pytest-asyncio` to test async background tasks

### Risk 3: State Inconsistency (running_agents, review_cache)

**Probability**: Low (if using service pattern)
**Impact**: Critical (agents lose state mid-execution)

**Mitigation**:
- Extract all global state to services in Wave 1
- Use thread-safe data structures (though Python's GIL helps here)
- Add state validation tests

### Risk 4: Import Cycle Hell

**Probability**: Medium (if not careful)
**Impact**: High (project unbuildable)

**Mitigation**:
- Follow strict import rules (services → lib, routers → services)
- Use lazy imports in functions if needed
- Run `import-linter` to detect cycles

### Risk 5: Test Coverage Regression

**Probability**: Medium
**Impact**: Medium (hidden bugs in production)

**Mitigation**:
- Run coverage after each wave
- Block PR merge if coverage drops below 85%
- Write integration tests for complex flows

---

## 10. Recommended File Structure (Post-Refactoring)

```
codeframe/ui/
├── __init__.py
├── server.py                    # Main FastAPI app (100 lines)
│   ├── lifespan manager
│   ├── CORS middleware
│   ├── router registration
│   └── run_server() entrypoint
│
├── dependencies.py              # DI providers (50 lines)
│   ├── get_db()
│   ├── get_websocket_manager()
│   ├── get_agent_service()
│   ├── get_review_service()
│   └── get_workspace_manager()
│
├── websocket.py                 # WebSocket + ConnectionManager (100 lines)
│   ├── ConnectionManager class
│   └── websocket_endpoint()
│
├── models.py                    # Pydantic models (keep as is)
│
├── routers/
│   ├── __init__.py              # Export all routers
│   ├── health.py                # 2 endpoints (~50 lines)
│   ├── projects.py              # 14 endpoints (~600 lines)
│   ├── context.py               # 10 endpoints (~400 lines)
│   ├── review.py                # 6 endpoints (~400 lines)
│   ├── checkpoints.py           # 6 endpoints (~400 lines)
│   ├── quality_gates.py         # 2 endpoints (~200 lines)
│   ├── metrics.py               # 3 endpoints (~200 lines)
│   ├── lint.py                  # 4 endpoints (~150 lines)
│   ├── session.py               # 1 endpoint (~50 lines)
│   ├── blockers.py              # 4 endpoints (~200 lines)
│   ├── chat.py                  # 2 endpoints (~150 lines)
│   └── discovery.py             # 2 endpoints (~150 lines)
│
└── services/
    ├── __init__.py
    ├── agent_service.py         # Manage running_agents (~200 lines)
    ├── review_service.py        # Manage review_cache (~150 lines)
    └── websocket_service.py     # Broadcasting abstraction (~100 lines)
```

**Line Count Reduction**:
- Before: 4,161 lines in 1 file
- After: ~3,500 lines across 22 files (15% reduction from removing duplication)

---

## 11. Success Criteria

### Phase 1 Complete (Wave 1)
- ✅ 10 simple endpoints migrated to 4 routers
- ✅ Dependency injection foundation established
- ✅ All tests passing (100% pass rate)
- ✅ Coverage ≥ 88%
- ✅ No circular imports

### Phase 2 Complete (Wave 2)
- ✅ 25+ endpoints migrated to 9 routers
- ✅ WebSocket broadcasting working via dependency injection
- ✅ Background tasks operational
- ✅ Service layer established

### Phase 3 Complete (Wave 3)
- ✅ All 65 endpoints migrated to 13 routers
- ✅ Zero global state (no module-level singletons)
- ✅ Raw SQL eliminated from routers
- ✅ E2E tests passing
- ✅ OpenAPI docs cleaner with proper tags

### Production Ready
- ✅ Documentation updated (API guides, architecture diagrams)
- ✅ Performance benchmarks unchanged (±5%)
- ✅ No breaking changes to API contracts
- ✅ Deployment tested in staging environment

---

## 12. Next Steps

### Immediate (Before Starting Refactoring)
1. ✅ **Establish baseline metrics**:
   - Run test suite: `uv run pytest tests/`
   - Measure coverage: `pytest --cov=codeframe.ui --cov-report=html`
   - Run linters: `ruff check codeframe/ui/server.py`
   - Measure startup time: `time python -c "from codeframe.ui.server import app"`

2. ✅ **Create comprehensive integration tests**:
   - WebSocket event broadcasting (all event types)
   - Background task completion (start_agent, quality_gates, review)
   - Agent lifecycle (start → run → stop)
   - Full workflow (create project → discovery → tasks → completion)

3. ✅ **Set up import linting**:
   ```bash
   pip install import-linter
   # Create .import-linter.toml with no-circular-imports rules
   ```

### Wave 1 (Low Risk Routers)
4. Create `dependencies.py` with `get_db()` provider
5. Create `routers/` directory and `__init__.py`
6. Extract Health router (2 endpoints)
7. Run tests, verify coverage ≥ 88%
8. Extract Lint router (4 endpoints)
9. Extract Session router (1 endpoint)
10. Extract Metrics router (3 endpoints)
11. Update `server.py` to register routers
12. **Wave 1 Checkpoint**: All tests pass, coverage maintained

### Wave 2 (Medium Complexity)
13. Create `services/websocket_service.py` for broadcasting abstraction
14. Create `websocket.py` and move ConnectionManager
15. Extract Context router (10 endpoints)
16. Extract Quality Gates router (2 endpoints)
17. Extract Discovery router (2 endpoints)
18. Extract Blockers router (4 endpoints)
19. **Wave 2 Checkpoint**: WebSocket events working, background tasks operational

### Wave 3 (High Complexity)
20. Create `services/agent_service.py` to manage running_agents
21. Create `services/review_service.py` to manage review_cache
22. Extract Projects router (14 endpoints)
23. Extract Chat router (2 endpoints)
24. Extract Review router (6 endpoints)
25. Extract Checkpoints router (6 endpoints)
26. Remove all global state from `server.py`
27. **Wave 3 Checkpoint**: Zero global state, all tests pass

### Final Polish
28. Update OpenAPI tags for all endpoints
29. Generate new API documentation
30. Performance benchmarking (compare to baseline)
31. Code review with team
32. Merge to main branch

---

## 13. Appendix: Code Examples

### Example 1: Health Router (Simple)

**File**: `codeframe/ui/routers/health.py`

```python
from fastapi import APIRouter, Depends
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from pathlib import Path
from datetime import datetime, UTC
import subprocess

router = APIRouter(tags=["health"])

@router.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "online", "service": "CodeFRAME Status Server"}

@router.get("/health")
async def health_check(db: Database = Depends(get_db)):
    """Detailed health check with deployment info."""
    # Get git commit hash
    try:
        git_commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).parent.parent.parent.parent,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        git_commit = "unknown"

    # Check database connection
    db_status = "connected" if db else "disconnected"

    return {
        "status": "healthy",
        "service": "CodeFRAME Status Server",
        "version": "0.1.0",
        "commit": git_commit,
        "deployed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "database": db_status,
    }
```

### Example 2: Dependencies File

**File**: `codeframe/ui/dependencies.py`

```python
from fastapi import Request
from codeframe.persistence.database import Database
from codeframe.ui.websocket import ConnectionManager
from codeframe.ui.services.agent_service import AgentService
from codeframe.ui.services.review_service import ReviewService
from codeframe.workspace import WorkspaceManager
from typing import Optional

# Singleton instances (initialized once)
_agent_service: Optional[AgentService] = None
_review_service: Optional[ReviewService] = None

def get_db(request: Request) -> Database:
    """Get database connection from app state."""
    return request.app.state.db

def get_websocket_manager(request: Request) -> ConnectionManager:
    """Get WebSocket manager from app state."""
    return request.app.state.websocket_manager

def get_workspace_manager(request: Request) -> WorkspaceManager:
    """Get workspace manager from app state."""
    return request.app.state.workspace_manager

def get_agent_service(request: Request) -> AgentService:
    """Get agent service singleton."""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService(
            db=get_db(request),
            websocket_manager=get_websocket_manager(request)
        )
    return _agent_service

def get_review_service(request: Request) -> ReviewService:
    """Get review service singleton."""
    global _review_service
    if _review_service is None:
        _review_service = ReviewService(db=get_db(request))
    return _review_service
```

### Example 3: Agent Service (Extracted from global state)

**File**: `codeframe/ui/services/agent_service.py`

```python
from typing import Dict, Optional
from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database
from codeframe.ui.websocket import ConnectionManager
from codeframe.core.models import ProjectStatus
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

class AgentService:
    """Service for managing running agents."""

    def __init__(self, db: Database, websocket_manager: ConnectionManager):
        self.db = db
        self.ws = websocket_manager
        self._running_agents: Dict[int, LeadAgent] = {}

    async def start_agent(self, project_id: int) -> None:
        """Start Lead Agent for a project."""
        try:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")

            # Create Lead Agent instance
            agent = LeadAgent(project_id=project_id, db=self.db, api_key=api_key)

            # Store agent reference
            self._running_agents[project_id] = agent

            # Update project status
            self.db.update_project(project_id, {"status": ProjectStatus.RUNNING})

            # Broadcast agent started event
            await self.ws.broadcast({
                "type": "agent_started",
                "project_id": project_id,
                "agent_type": "lead",
                "timestamp": asyncio.get_event_loop().time(),
            })

            # Send greeting message
            greeting = "Hi! I'm your Lead Agent. I'm here to help build your project."
            self.db.create_memory(
                project_id=project_id,
                category="conversation",
                key="assistant",
                value=greeting
            )

            await self.ws.broadcast({
                "type": "chat_message",
                "project_id": project_id,
                "role": "assistant",
                "content": greeting,
            })

            logger.info(f"Started Lead Agent for project {project_id}")

        except Exception as e:
            logger.error(f"Failed to start agent for project {project_id}: {e}", exc_info=True)
            raise

    def get_agent(self, project_id: int) -> Optional[LeadAgent]:
        """Get running agent for a project."""
        return self._running_agents.get(project_id)

    async def stop_agent(self, project_id: int) -> None:
        """Stop agent for a project."""
        if project_id in self._running_agents:
            del self._running_agents[project_id]
            self.db.update_project(project_id, {"status": ProjectStatus.PAUSED})

            await self.ws.broadcast({
                "type": "agent_stopped",
                "project_id": project_id,
                "timestamp": asyncio.get_event_loop().time(),
            })

            logger.info(f"Stopped Lead Agent for project {project_id}")
```

### Example 4: Updated server.py (Post-Refactoring)

**File**: `codeframe/ui/server.py`

```python
"""FastAPI Status Server for CodeFRAME."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os

from codeframe.persistence.database import Database
from codeframe.workspace import WorkspaceManager
from codeframe.ui.websocket import ConnectionManager, websocket_router
from codeframe.ui.routers import (
    health,
    projects,
    context,
    review,
    checkpoints,
    quality_gates,
    metrics,
    lint,
    session,
    blockers,
    chat,
    discovery,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    db_path_str = os.environ.get("DATABASE_PATH")
    if db_path_str:
        db_path = Path(db_path_str)
    else:
        workspace_root = Path(os.environ.get("WORKSPACE_ROOT", "."))
        db_path = workspace_root / ".codeframe" / "state.db"

    app.state.db = Database(db_path)
    app.state.db.initialize()

    workspace_root_str = os.environ.get(
        "WORKSPACE_ROOT", str(Path.cwd() / ".codeframe" / "workspaces")
    )
    app.state.workspace_manager = WorkspaceManager(Path(workspace_root_str))
    app.state.websocket_manager = ConnectionManager()

    yield

    # Shutdown
    if hasattr(app.state, "db") and app.state.db:
        app.state.db.close()

app = FastAPI(
    title="CodeFRAME Status Server",
    description="Real-time monitoring and control for CodeFRAME projects",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
cors_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
allowed_origins = (
    [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
    if cors_origins_env
    else ["http://localhost:3000", "http://localhost:5173"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(projects.router)
app.include_router(context.router)
app.include_router(review.router)
app.include_router(checkpoints.router)
app.include_router(quality_gates.router)
app.include_router(metrics.router)
app.include_router(lint.router)
app.include_router(session.router)
app.include_router(blockers.router)
app.include_router(chat.router)
app.include_router(discovery.router)
app.include_router(websocket_router)

def run_server(host: str = "0.0.0.0", port: int = 8080):
    """Run the Status Server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CodeFRAME Status Server")
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host to bind to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8080"))),
        help="Port to bind to",
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
```

---

## Conclusion

The FastAPI router refactoring is **feasible and recommended** with the following approach:

1. **Extract in 3 waves** (simple → medium → complex) to minimize risk
2. **Use dependency injection** for all shared state (Database, ConnectionManager, AgentService)
3. **Create service layer** to eliminate global singletons (`running_agents`, `review_cache`)
4. **Follow strict import rules** to prevent circular imports
5. **Maintain test coverage ≥ 88%** throughout refactoring
6. **Comprehensive integration tests** before starting to catch regressions

**Estimated Effort**: 7-9 days for full refactoring (1 engineer)

**Primary Benefits**:
- ✅ Better code organization (65 endpoints → 13 routers)
- ✅ Improved testability (isolated router tests)
- ✅ Easier onboarding (clear separation of concerns)
- ✅ Reduced coupling (dependency injection vs global state)
- ✅ Scalability (can parallelize development across routers)

**Risk Level**: Medium (manageable with proper planning and testing)

---

**Author**: FastAPI Architecture Expert
**Contact**: Via GitHub issue or PR comments
**Last Updated**: 2025-12-11
