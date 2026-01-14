# FastAPI Server Router Refactoring Plan

> **Document Created**: 2025-12-11
> **Target File**: `codeframe/ui/server.py`
> **Current Size**: 4,085 lines (~37,000 tokens)

## Executive Summary

The `server.py` file has grown to 4,085 lines containing 60+ API endpoints. This document outlines a refactoring strategy to break the monolithic file into focused FastAPI APIRouter sub-modules, reducing the main file to ~250-300 lines while maintaining all existing functionality.

---

## Current State Analysis

### Endpoint Groups Identified

| Router Name | Endpoints | Est. Lines | Description |
|------------|-----------|------------|-------------|
| `projects` | 14 | ~550 | Core project CRUD and status |
| `agents` | 8 | ~350 | Agent assignments and management |
| `chat` | 2 | ~120 | Chat with Lead Agent |
| `discovery` | 2 | ~260 | Discovery workflow |
| `blockers` | 4 | ~180 | Human-in-loop blockers |
| `lint` | 4 | ~210 | Linting endpoints |
| `session` | 1 | ~80 | Session lifecycle |
| `context` | 10 | ~450 | Context management |
| `review` | 6 | ~600 | Code review |
| `quality_gates` | 2 | ~320 | Quality gates |
| `checkpoints` | 6 | ~600 | Checkpoint/restore |
| `metrics` | 3 | ~320 | Token/cost metrics |
| `websocket` | 1 | ~50 | WebSocket handler |

### Expected Results After Refactoring

| File | Est. Lines |
|------|------------|
| `server.py` (main) | ~250-300 |
| `routers/projects.py` | ~550 |
| `routers/agents.py` | ~350 |
| `routers/chat.py` | ~120 |
| `routers/discovery.py` | ~260 |
| `routers/blockers.py` | ~180 |
| `routers/lint.py` | ~210 |
| `routers/session.py` | ~80 |
| `routers/context.py` | ~450 |
| `routers/review.py` | ~600 |
| `routers/quality_gates.py` | ~320 |
| `routers/checkpoints.py` | ~600 |
| `routers/metrics.py` | ~320 |
| `routers/websocket.py` | ~50 |

**Main server.py reduction**: From 4,085 lines to ~250-300 lines (**93% reduction**)

---

## Refactoring Benefits

1. **Reduced cognitive load**: Developers only need to understand one domain at a time
2. **Enabling parallel development**: Multiple developers can work on different routers
3. **Improved testability**: Each router can be tested in isolation
4. **Easier navigation**: Finding an endpoint is as simple as checking the appropriate router file
5. **Better code organization**: Related endpoints are grouped together
6. **Smaller PR sizes**: Future changes are scoped to specific routers

---

## AI Prompt for Execution

The following prompt can be passed to a coding agent to execute this refactoring:

```markdown
# FastAPI Router Refactoring Task

## Objective
Refactor `codeframe/ui/server.py` (4,085 lines) by extracting endpoints into
FastAPI APIRouter sub-routers, reducing the main file to ~250-300 lines while
maintaining all existing functionality and tests.

## Directory Structure to Create
```
codeframe/ui/
├── server.py                    # Main app, lifespan, middleware, router mounts
├── dependencies.py              # Shared dependencies (get_db, etc.)
├── shared.py                    # Shared state (ConnectionManager, running_agents, review_cache)
└── routers/
    ├── __init__.py
    ├── projects.py              # /api/projects/* endpoints
    ├── agents.py                # /api/agents/* and project agent assignments
    ├── chat.py                  # /api/projects/{id}/chat/* endpoints
    ├── discovery.py             # /api/projects/{id}/discovery/* endpoints
    ├── blockers.py              # /api/blockers/* and /api/projects/{id}/blockers/*
    ├── lint.py                  # /api/lint/* endpoints
    ├── session.py               # /api/projects/{id}/session endpoint
    ├── context.py               # /api/agents/{id}/context/* and flash-save endpoints
    ├── review.py                # /api/agents/{id}/review and /api/tasks/{id}/review*
    ├── quality_gates.py         # /api/tasks/{id}/quality-gates endpoints
    ├── checkpoints.py           # /api/projects/{id}/checkpoints/* endpoints
    ├── metrics.py               # /api/projects/{id}/metrics/* and agent metrics
    └── websocket.py             # /ws WebSocket handler
```

## Step-by-Step Instructions

### Step 1: Create shared.py
Extract shared state that multiple routers need:
- `ConnectionManager` class and `manager` instance
- `running_agents: Dict[int, LeadAgent]`
- `review_cache: Dict[int, dict]`
- `start_agent()` async function

### Step 2: Create dependencies.py
Create FastAPI dependencies for database access:
```python
from fastapi import Request

def get_db(request: Request):
    return request.app.state.db

def get_workspace_manager(request: Request):
    return request.app.state.workspace_manager
```

### Step 3: Create routers/__init__.py
Empty file or re-exports of all routers.

### Step 4: Create each router file
For each router, follow this pattern:
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from ..dependencies import get_db
from ..shared import manager, running_agents

router = APIRouter(prefix="/api/...", tags=["tag-name"])

@router.get("/endpoint")
async def endpoint_name(db=Depends(get_db)):
    ...
```

### Step 5: Router Mappings

**routers/projects.py** - prefix="/api/projects"
- GET / -> list_projects
- POST / -> create_project
- POST /{project_id}/start -> start_project_agent
- GET /{project_id}/status -> get_project_status
- GET /{project_id}/tasks -> get_tasks
- GET /{project_id}/activity -> get_activity
- GET /{project_id}/prd -> get_project_prd
- GET /{project_id}/issues -> get_project_issues
- POST /{project_id}/pause -> pause_project
- POST /{project_id}/resume -> resume_project

**routers/agents.py** - prefix="/api"
- GET /projects/{project_id}/agents -> get_project_agents
- POST /projects/{project_id}/agents -> assign_agent_to_project
- DELETE /projects/{project_id}/agents/{agent_id} -> remove_agent_from_project
- PUT /projects/{project_id}/agents/{agent_id}/role -> update_agent_role
- PATCH /projects/{project_id}/agents/{agent_id} -> patch_agent_role
- GET /agents/{agent_id}/projects -> get_agent_projects

**routers/chat.py** - prefix="/api/projects/{project_id}/chat"
- POST / -> chat_with_lead (uses: running_agents)
- GET /history -> get_chat_history

**routers/discovery.py** - prefix="/api/projects/{project_id}/discovery"
- POST /answer -> submit_discovery_answer (uses: manager for broadcasts)
- GET /progress -> get_discovery_progress

**routers/blockers.py** - prefix="/api"
- GET /projects/{project_id}/blockers -> get_project_blockers
- GET /blockers/{blocker_id} -> get_blocker
- POST /blockers/{blocker_id}/resolve -> resolve_blocker_endpoint (uses: manager)
- GET /projects/{project_id}/blockers/metrics -> get_blocker_metrics_endpoint

**routers/lint.py** - prefix="/api/lint", tags=["lint"]
- GET /results -> get_lint_results
- GET /trend -> get_lint_trend
- GET /config -> get_lint_config
- POST /run -> run_lint_manual (uses: manager for broadcasts)

**routers/session.py** - prefix="/api/projects/{project_id}/session", tags=["session"]
- GET / -> get_session_state

**routers/context.py** - prefix="/api/agents/{agent_id}", tags=["context"]
- POST /context -> create_context_item
- GET /context/{item_id} -> get_context_item
- GET /context -> list_context_items
- DELETE /context/{item_id} -> delete_context_item
- POST /context/update-scores -> update_context_scores
- POST /context/update-tiers -> update_context_tiers
- POST /flash-save -> flash_save_context (uses: manager)
- GET /flash-save/checkpoints -> list_flash_save_checkpoints
- GET /context/stats -> get_context_stats
- GET /context/items -> get_context_items

**routers/review.py** - prefix="/api", tags=["review"]
- POST /agents/{agent_id}/review -> trigger_review (uses: manager, review_cache)
- GET /tasks/{task_id}/review-status -> get_review_status (uses: review_cache)
- GET /projects/{project_id}/review-stats -> get_review_stats (uses: review_cache)
- POST /agents/review/analyze -> analyze_code_review (uses: manager)
- GET /tasks/{task_id}/reviews -> get_task_reviews
- GET /projects/{project_id}/code-reviews -> get_project_code_reviews

**routers/quality_gates.py** - prefix="/api/tasks/{task_id}/quality-gates", tags=["quality-gates"]
- GET / -> get_quality_gate_status
- POST / -> trigger_quality_gates (uses: manager)

**routers/checkpoints.py** - prefix="/api/projects/{project_id}/checkpoints", tags=["checkpoints"]
- GET / -> list_checkpoints
- POST / -> create_checkpoint
- GET /{checkpoint_id} -> get_checkpoint
- DELETE /{checkpoint_id} -> delete_checkpoint
- POST /{checkpoint_id}/restore -> restore_checkpoint
- GET /{checkpoint_id}/diff -> get_checkpoint_diff

**routers/metrics.py** - prefix="/api", tags=["metrics"]
- GET /projects/{project_id}/metrics/tokens -> get_project_token_metrics
- GET /projects/{project_id}/metrics/costs -> get_project_cost_metrics
- GET /agents/{agent_id}/metrics -> get_agent_metrics

**routers/websocket.py** - No prefix (mounted separately)
- WebSocket /ws -> websocket_endpoint (uses: manager)

### Step 6: Update server.py
After extracting all routers, the main server.py should contain only:
1. Imports
2. `DeploymentMode` enum and helper functions
3. Logger setup
4. `lifespan` async context manager
5. FastAPI app creation
6. CORS middleware
7. Health check endpoints (GET /, GET /health)
8. Router mounting:
```python
from .routers import (
    projects, agents, chat, discovery, blockers, lint,
    session, context, review, quality_gates, checkpoints,
    metrics, websocket
)

app.include_router(projects.router)
app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(discovery.router)
app.include_router(blockers.router)
app.include_router(lint.router)
app.include_router(session.router)
app.include_router(context.router)
app.include_router(review.router)
app.include_router(quality_gates.router)
app.include_router(checkpoints.router)
app.include_router(metrics.router)
app.include_router(websocket.router)
```
9. `run_server()` function
10. `__main__` block

### Step 7: Verify All Tests Pass
Run the test suite to ensure no functionality was broken:
```bash
pytest tests/ -v
```

## Important Notes

1. **Preserve all imports in each router** - Each router file should have its own
   imports for the functionality it uses.

2. **Handle circular imports** - Use `from ..shared import manager` pattern to
   avoid circular dependencies.

3. **Maintain WebSocket functionality** - The `manager` instance must be accessible
   from all routers that need to broadcast messages.

4. **Keep background task functions** - Functions like `start_agent()` and
   `run_quality_gates()` should move to `shared.py` or stay with their respective
   routers.

5. **No behavior changes** - This is a pure refactoring task. All API contracts,
   response formats, and error handling must remain identical.

6. **Preserve tags** - Maintain the existing OpenAPI tags (["lint"], ["review"], etc.)

## Success Criteria
- All 550+ existing tests pass
- Main server.py reduced to ~250-300 lines
- Each router is self-contained and focused on a single domain
- No code duplication between routers
- OpenAPI documentation (Swagger) remains functional
```

---

## Risk Mitigation

### Potential Issues

1. **Circular imports**: Solved by extracting shared state to `shared.py`
2. **WebSocket manager access**: Solved by importing from `shared.py`
3. **Database access**: Solved by FastAPI dependency injection via `dependencies.py`
4. **Test breakage**: Mitigated by running full test suite after each router extraction

### Recommended Approach

Extract routers incrementally in this order (lowest risk to highest):
1. `lint.py` - Self-contained, minimal dependencies
2. `session.py` - Single endpoint, simple
3. `metrics.py` - Read-only, minimal state
4. `blockers.py` - Few dependencies
5. `discovery.py` - Uses manager for broadcasts
6. `chat.py` - Uses running_agents
7. `context.py` - Multiple endpoints, uses manager
8. `review.py` - Complex, uses manager and review_cache
9. `quality_gates.py` - Complex background tasks
10. `checkpoints.py` - File system operations
11. `agents.py` - Cross-cutting concerns
12. `projects.py` - Core functionality, extract last
13. `websocket.py` - Extract with shared.py

Run tests after each extraction to catch issues early.
