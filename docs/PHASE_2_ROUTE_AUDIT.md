# Phase 2 Route Audit

**Objective:** Comprehensive inventory of all API routes and their current implementation patterns.

**Created:** 2026-02-01
**Issue:** #322 - Server Layer Refactor

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Total Routes | 78 |
| Already Delegating to Core | 3 |
| Needs Extraction to Core | 52 |
| No CLI Equivalent (Server-specific) | 23 |

---

## Route Classification

### Legend
- **Priority**: CRITICAL (Golden Path blocker), HIGH (CLI parity), MEDIUM (useful feature), LOW (nice to have)
- **Status**: ✓ DONE (already delegates), ⚠️ PARTIAL (some delegation), ❌ NEEDS WORK

---

## 1. Agents Router (`agents.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects/{project_id}/start` | POST | Inline + `LeadAgent` (lib) | `core.runtime` | `cf work start` | CRITICAL | ❌ |
| `/api/projects/{project_id}/pause` | POST | Inline + `AgentService` (ui) | `core.runtime` | `cf work stop` | HIGH | ❌ |
| `/api/projects/{project_id}/resume` | POST | Inline + `AgentService` (ui) | `core.runtime` | `cf work resume` | HIGH | ❌ |
| `/api/projects/{project_id}/agents` | GET | Database direct | `core.agents` | - | MEDIUM | ❌ |
| `/api/projects/{project_id}/agents` | POST | Database direct | `core.agents` | - | MEDIUM | ❌ |
| `/api/projects/{project_id}/agents/{agent_id}` | DELETE | Database direct | `core.agents` | - | MEDIUM | ❌ |
| `/api/projects/{project_id}/agents/{agent_id}/role` | PUT | Database direct | `core.agents` | - | LOW | ❌ |
| `/api/projects/{project_id}/agents/{agent_id}` | PATCH | Database direct | `core.agents` | - | LOW | ❌ |
| `/api/agents/{agent_id}/projects` | GET | Database direct | `core.agents` | - | LOW | ❌ |

**Notes:** Agent lifecycle (start/pause/resume) routes are CRITICAL - they must delegate to `core.runtime` to match CLI behavior. Multi-agent management is Phase 4 scope.

---

## 2. Blockers Router (`blockers.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects/{project_id}/blockers` | GET | Database direct | `core.blockers` | `cf blocker list` | HIGH | ❌ |
| `/api/projects/{project_id}/blockers/metrics` | GET | Database direct | `core.blockers` | - | LOW | ❌ |
| `/api/blockers/{blocker_id}` | GET | Database direct | `core.blockers` | `cf blocker show` | HIGH | ❌ |
| `/api/blockers/{blocker_id}/resolve` | POST | Database direct | `core.blockers` | `cf blocker answer` | CRITICAL | ❌ |

**Notes:** `core.blockers` module already exists with `list_blockers()`, `get_blocker()`, `resolve_blocker()`. Routes just need to call these functions instead of database directly.

---

## 3. Chat Router (`chat.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects/{project_id}/chat` | POST | Inline + `running_agents` | N/A (UI-specific) | - | LOW | UI-only |
| `/api/projects/{project_id}/chat/history` | GET | Database direct | N/A (UI-specific) | - | LOW | UI-only |

**Notes:** Chat functionality is UI-specific. No CLI equivalent needed.

---

## 4. Checkpoints Router (`checkpoints.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects/{project_id}/checkpoints` | GET | `lib/checkpoint_manager.py` | `core.checkpoints` | `cf checkpoint list` | MEDIUM | ❌ |
| `/api/projects/{project_id}/checkpoints` | POST | `lib/checkpoint_manager.py` | `core.checkpoints` | `cf checkpoint create` | MEDIUM | ❌ |
| `/api/projects/{project_id}/checkpoints/{id}` | GET | `lib/checkpoint_manager.py` | `core.checkpoints` | - | LOW | ❌ |
| `/api/projects/{project_id}/checkpoints/{id}` | DELETE | `lib/checkpoint_manager.py` | `core.checkpoints` | - | LOW | ❌ |
| `/api/projects/{project_id}/checkpoints/{id}/restore` | POST | `lib/checkpoint_manager.py` | `core.checkpoints` | `cf checkpoint restore` | MEDIUM | ❌ |
| `/api/projects/{project_id}/checkpoints/{id}/diff` | GET | `lib/checkpoint_manager.py` + git | `core.checkpoints` | - | LOW | ❌ |

**Notes:** Currently uses `lib/checkpoint_manager.py`. Should extract to `core.checkpoints` module.

---

## 5. Context Router (`context.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/agents/{agent_id}/context` | GET | `lib/context_manager.py` | Phase 4 | - | LOW | ❌ |
| `/api/agents/{agent_id}/context/{item_id}` | DELETE | `lib/context_manager.py` | Phase 4 | - | LOW | ❌ |
| `/api/agents/{agent_id}/context/update-scores` | POST | `lib/context_manager.py` | Phase 4 | - | LOW | ❌ |
| `/api/agents/{agent_id}/context/update-tiers` | POST | `lib/context_manager.py` | Phase 4 | - | LOW | ❌ |
| `/api/agents/{agent_id}/flash-save` | POST | `lib/context_manager.py` | Phase 4 | - | LOW | ❌ |
| `/api/agents/{agent_id}/flash-save/checkpoints` | GET | Database direct | Phase 4 | - | LOW | ❌ |
| `/api/agents/{agent_id}/context/stats` | GET | `lib/context_manager.py` | Phase 4 | - | LOW | ❌ |
| `/api/agents/{agent_id}/context/items` | GET | Database direct | Phase 4 | - | LOW | ❌ |

**Notes:** Context tiering is a Phase 4 (Multi-Agent Coordination) feature. Defer extraction.

---

## 6. Discovery Router (`discovery.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects/{project_id}/discovery/answer` | POST | Inline + `LeadAgent` (lib) | `core.prd_discovery` | `cf prd generate` | CRITICAL | ❌ |
| `/api/projects/{project_id}/discovery/progress` | GET | Inline + `LeadAgent` (lib) | `core.prd_discovery` | `cf prd show` | HIGH | ❌ |
| `/api/projects/{project_id}/discovery/restart` | POST | Inline + `LeadAgent` (lib) | `core.prd_discovery` | - | MEDIUM | ❌ |
| `/api/projects/{project_id}/discovery/generate-prd` | POST | Inline + `LeadAgent` (lib) | `core.prd` | `cf prd generate` | CRITICAL | ❌ |
| `/api/projects/{project_id}/discovery/generate-tasks` | POST | Inline + `LeadAgent` (lib) | `core.tasks` | `cf tasks generate` | HIGH | ❌ |

**Notes:** Discovery/PRD workflows are CRITICAL. The `core.prd_discovery` module exists (from Phase 1 #317). Routes need to delegate.

---

## 7. Git Router (`git.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects/{project_id}/git/branches` | POST | `git/workflow_manager.py` | `core.git` | - | MEDIUM | ❌ |
| `/api/projects/{project_id}/git/branches` | GET | Database + git | `core.git` | - | LOW | ❌ |
| `/api/projects/{project_id}/git/branches/{name}` | GET | Database + git | `core.git` | - | LOW | ❌ |
| `/api/projects/{project_id}/git/commit` | POST | `git/workflow_manager.py` | `core.git` | `cf commit` | HIGH | ❌ |
| `/api/projects/{project_id}/git/commits` | GET | `git/workflow_manager.py` | `core.git` | - | LOW | ❌ |
| `/api/projects/{project_id}/git/status` | GET | `git/workflow_manager.py` | `core.git` | `cf status` | MEDIUM | ❌ |

**Notes:** Git operations currently use `git/workflow_manager.py`. Could keep as adapter or extract git subset to core.

---

## 8. Lint Router (`lint.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/lint/results` | GET | Database direct | `core.gates` | `cf review` | MEDIUM | ❌ |
| `/api/lint/trend` | GET | Database direct | `core.gates` | - | LOW | ❌ |
| `/api/lint/config` | GET | `testing/lint_runner.py` | `core.gates` | - | LOW | ❌ |
| `/api/lint/run` | POST | `testing/lint_runner.py` | `core.gates` | `cf review` | MEDIUM | ❌ |

**Notes:** `core.gates` already exists. Lint router should delegate to it.

---

## 9. Metrics Router (`metrics.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects/{project_id}/metrics/tokens` | GET | `lib/metrics_tracker.py` | Phase 4 | - | LOW | ❌ |
| `/api/projects/{project_id}/metrics/tokens/timeseries` | GET | `lib/metrics_tracker.py` | Phase 4 | - | LOW | ❌ |
| `/api/projects/{project_id}/metrics/costs` | GET | `lib/metrics_tracker.py` | Phase 4 | - | LOW | ❌ |
| `/api/agents/{agent_id}/metrics` | GET | `lib/metrics_tracker.py` | Phase 4 | - | LOW | ❌ |

**Notes:** Metrics/cost tracking is Phase 4 (Advanced Features) scope. Defer extraction.

---

## 10. Projects Router (`projects.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects` | GET | Database direct | `core.workspace` | `cf status` | HIGH | ❌ |
| `/api/projects` | POST | Inline + `WorkspaceManager` | `core.workspace` | `cf init` | CRITICAL | ❌ |
| `/api/projects/{project_id}` | GET | Database direct | `core.workspace` | `cf status` | HIGH | ❌ |
| `/api/projects/{project_id}/status` | GET | Database direct | `core.workspace` | `cf status` | HIGH | ❌ |
| `/api/projects/{project_id}/tasks` | GET | Database direct | `core.tasks` | `cf tasks list` | HIGH | ❌ |
| `/api/projects/{project_id}/activity` | GET | Database direct | N/A (UI-specific) | - | LOW | UI-only |
| `/api/projects/{project_id}/prd` | GET | Database direct | `core.prd` | `cf prd show` | HIGH | ❌ |
| `/api/projects/{project_id}/issues` | GET | Database direct | `core.tasks` | - | MEDIUM | ❌ |
| `/api/projects/{project_id}/session` | GET | `core/session_manager.py` | ✓ Already correct | - | - | ✓ DONE |

**Notes:** Most project routes need delegation to `core.workspace`, `core.prd`, `core.tasks`. Session endpoint already uses core!

---

## 11. PRs Router (`prs.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects/{project_id}/prs` | POST | `git/github_integration.py` | `core.pr` | `cf pr create` | HIGH | ❌ |
| `/api/projects/{project_id}/prs` | GET | Database direct | `core.pr` | `cf pr status` | MEDIUM | ❌ |
| `/api/projects/{project_id}/prs/{pr_number}` | GET | Database direct | `core.pr` | `cf pr status` | MEDIUM | ❌ |
| `/api/projects/{project_id}/prs/{pr_number}/merge` | POST | `git/github_integration.py` | `core.pr` | `cf pr merge` | HIGH | ❌ |
| `/api/projects/{project_id}/prs/{pr_number}/close` | POST | `git/github_integration.py` | `core.pr` | - | MEDIUM | ❌ |

**Notes:** PR operations use `git/github_integration.py`. Should create `core.pr` module to match CLI.

---

## 12. Quality Gates Router (`quality_gates.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/tasks/{task_id}/quality-gates` | GET | Database direct | `core.gates` | - | MEDIUM | ❌ |
| `/api/tasks/{task_id}/quality-gates` | POST | `lib/quality_gates.py` | `core.gates` | `cf review` | MEDIUM | ❌ |

**Notes:** Quality gates should delegate to `core.gates` which already exists.

---

## 13. Review Router (`review.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/agents/{agent_id}/review` | POST | `agents/review_worker_agent.py` | `core.review` | `cf review` | MEDIUM | ❌ |
| `/api/tasks/{task_id}/review-status` | GET | In-memory cache | `core.review` | - | LOW | ❌ |
| `/api/projects/{project_id}/review-stats` | GET | In-memory cache | `core.review` | - | LOW | ❌ |
| `/api/agents/review/analyze` | POST | `agents/review_agent.py` | `core.review` | `cf review` | MEDIUM | ❌ |
| `/api/tasks/{task_id}/reviews` | GET | Database direct | `core.review` | - | MEDIUM | ❌ |
| `/api/projects/{project_id}/code-reviews` | GET | Database direct | `core.review` | - | LOW | ❌ |

**Notes:** Review endpoints use v1 agent classes. Should create `core.review` to wrap gate execution.

---

## 14. Schedule Router (`schedule.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/schedule/{project_id}` | GET | `planning/task_scheduler.py` | `core.scheduler` | `cf schedule show` | MEDIUM | ❌ |
| `/api/schedule/{project_id}/predict` | GET | `planning/task_scheduler.py` | `core.scheduler` | `cf schedule predict` | MEDIUM | ❌ |
| `/api/schedule/{project_id}/bottlenecks` | GET | `planning/task_scheduler.py` | `core.scheduler` | `cf schedule bottlenecks` | MEDIUM | ❌ |

**Notes:** Schedule endpoints already have CLI equivalents. Need `core.scheduler` to unify.

---

## 15. Session Router (`session.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/projects/{project_id}/session` | GET | `core/session_manager.py` | ✓ Already correct | - | - | ✓ DONE |

**Notes:** Session endpoint already delegates to `core.session_manager`. This is the pattern to follow!

---

## 16. Tasks Router (`tasks.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/tasks` | POST | Inline + Database | `core.tasks` | `cf tasks generate` | HIGH | ❌ |
| `/api/projects/{project_id}/tasks/approve` | POST | Inline + `PhaseManager` (core) | `core.workflow` | - | MEDIUM | ⚠️ PARTIAL |
| `/api/projects/{project_id}/tasks/assign` | POST | Inline + `LeadAgent` (lib) | `core.runtime` | `cf work batch run` | HIGH | ❌ |

**Notes:** Task approval partially uses `core.phase_manager`. Task assignment should delegate to `core.runtime` or `core.conductor`.

---

## 17. Templates Router (`templates.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/api/templates/` | GET | `planning/task_templates.py` | `core.templates` | `cf templates list` | MEDIUM | ❌ |
| `/api/templates/categories` | GET | `planning/task_templates.py` | `core.templates` | - | LOW | ❌ |
| `/api/templates/{template_id}` | GET | `planning/task_templates.py` | `core.templates` | `cf templates show` | MEDIUM | ❌ |
| `/api/templates/{project_id}/apply` | POST | `planning/task_templates.py` | `core.templates` | `cf templates apply` | MEDIUM | ❌ |

**Notes:** Template endpoints have CLI equivalents. Need to create `core.templates` or move existing `planning/task_templates.py` to core.

---

## 18. WebSocket Router (`websocket.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/ws/health` | GET | Inline | N/A (Server-specific) | - | - | Server-only |
| `/ws` | WS | Inline + `manager` | N/A (Server-specific) | - | - | Server-only |

**Notes:** WebSocket is server/UI-specific. No CLI equivalent needed.

---

## 19. Auth Router (`auth/router.py`)

| Route | Method | Current Logic Location | Target Core Module | CLI Equivalent | Priority | Status |
|-------|--------|------------------------|-------------------|----------------|----------|--------|
| `/auth/jwt/login` | POST | FastAPI Users | N/A (Server-specific) | - | - | Server-only |
| `/auth/jwt/logout` | POST | FastAPI Users | N/A (Server-specific) | - | - | Server-only |
| `/auth/register` | POST | FastAPI Users | N/A (Server-specific) | - | - | Server-only |
| `/users/me` | GET | FastAPI Users | N/A (Server-specific) | - | - | Server-only |
| `/users/me` | PATCH | FastAPI Users | N/A (Server-specific) | - | - | Server-only |

**Notes:** Auth is server-specific. CLI uses environment variables for authentication.

---

## Priority Matrix

### CRITICAL (Golden Path Blockers) - 5 routes
1. `/api/projects` POST → `core.workspace` (cf init)
2. `/api/projects/{project_id}/discovery/answer` POST → `core.prd_discovery` (cf prd generate)
3. `/api/projects/{project_id}/discovery/generate-prd` POST → `core.prd` (cf prd generate)
4. `/api/projects/{project_id}/start` POST → `core.runtime` (cf work start)
5. `/api/blockers/{blocker_id}/resolve` POST → `core.blockers` (cf blocker answer)

### HIGH (CLI Parity) - 18 routes
- Project CRUD and status
- Task listing and creation
- PRD operations
- Blocker operations
- PR operations
- Agent lifecycle (pause/resume)

### MEDIUM (Useful Features) - 22 routes
- Checkpoint operations
- Schedule operations
- Template operations
- Quality gates
- Review operations
- Git operations

### LOW (Nice to Have) - 10 routes
- Metrics/cost tracking (Phase 4)
- Context tiering (Phase 4)
- Agent management
- Chat history

### Server-Only (No Extraction Needed) - 23 routes
- WebSocket endpoints
- Auth endpoints
- Chat endpoints
- Activity endpoints

---

## Recommended Extraction Order

### Phase 2.1 - Critical Path
1. `core.workspace` - Project creation/init
2. `core.prd` + `core.prd_discovery` - PRD operations
3. `core.runtime` integration - Agent lifecycle
4. `core.blockers` integration - Already exists, just wire up routes

### Phase 2.2 - CLI Parity
1. `core.tasks` - Task CRUD
2. `core.pr` - GitHub PR operations
3. `core.git` - Git status/commit

### Phase 2.3 - Features
1. `core.checkpoints` - From lib/checkpoint_manager
2. `core.templates` - From planning/task_templates
3. `core.scheduler` - From planning/task_scheduler
4. `core.review` - Code review operations

### Deferred to Phase 4
- Context management endpoints
- Metrics/cost tracking endpoints
- Multi-agent coordination endpoints

---

## Already Correct (Pattern to Follow)

These routes already delegate to core modules:
1. `GET /api/projects/{project_id}/session` → `core/session_manager.py`
2. `POST /api/projects/{project_id}/tasks/approve` → `core/phase_manager.py` (partial)

**Pattern:**
```python
# Current (inline logic)
@router.get("/api/projects/{project_id}/prd")
async def get_prd(project_id: int, db: Database = Depends(get_db)):
    prd = db.get_prd(project_id)  # Direct DB call
    return prd

# Target (delegate to core)
from codeframe.core.prd import get_prd as core_get_prd

@router.get("/api/projects/{project_id}/prd")
async def get_prd(project_id: int, db: Database = Depends(get_db)):
    return core_get_prd(project_id, db)  # Delegate to core
```
