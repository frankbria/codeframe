# Phase 2: Business Logic Extraction Audit

**Created:** 2026-02-01
**Issue:** #322 - Server Layer Refactor
**Branch:** phase-2/server-layer

This document identifies routes with embedded business logic that should be
refactored to delegate to core modules.

---

## Summary

| Router Category | Status | Notes |
|-----------------|--------|-------|
| v2 Routers (10 files) | ✅ Clean | Properly delegate to core modules |
| v1 Legacy Routers (18 files) | ⚠️ Mixed | Many have embedded business logic |

---

## V2 Routers (Clean - No Refactoring Needed)

All v2 routers properly delegate to `codeframe/core/` modules:

| Router | Core Module(s) | Status |
|--------|----------------|--------|
| `discovery_v2.py` | `core.prd_discovery`, `core.prd`, `core.tasks` | ✅ Clean |
| `checkpoints_v2.py` | `core.checkpoints` | ✅ Clean |
| `schedule_v2.py` | `core.schedule` | ✅ Clean |
| `templates_v2.py` | `core.templates` | ✅ Clean |
| `projects_v2.py` | `core.project_status` | ✅ Clean |
| `git_v2.py` | `core.git` | ✅ Clean |
| `review_v2.py` | `core.review` | ✅ Clean |
| `blockers_v2.py` | `core.blockers` | ✅ Clean |
| `prd_v2.py` | `core.prd` | ✅ Clean |
| `tasks_v2.py` | `core.runtime`, `core.tasks`, `core.conductor`, `core.streaming` | ✅ Clean |

---

## V1 Routers Requiring Business Logic Extraction

### HIGH Priority (Core Workflow Impact)

#### 1. `tasks.py` (506 lines)
**Embedded Business Logic:**
- `start_development_execution()` - Background task for multi-agent execution
- Direct `LeadAgent` instantiation and lifecycle management
- `PhaseManager` orchestration for phase transitions
- WebSocket broadcasts for task status changes
- Task creation/update with database operations

**Should Extract To:**
- `core/conductor.py` - Already exists, reuse for multi-agent execution
- `core/runtime.py` - Already handles run lifecycle
- `core/events.py` - Already handles event emission

**Refactoring Effort:** Medium (v2 replacement exists)

---

#### 2. `discovery.py` (814 lines)
**Embedded Business Logic:**
- `generate_prd_background()` - PRD generation orchestration
- `run_planning_automation()` - Issue/task decomposition
- Direct `LeadAgent` usage for AI operations
- Complex state machine for discovery flow
- WebSocket broadcasts at each stage

**Should Extract To:**
- `core/prd_discovery.py` - Already exists with clean implementation
- `core/tasks.py` - Already has `generate_from_prd()`

**Refactoring Effort:** Low (v2 replacement exists and is complete)

---

#### 3. `agents.py` (588 lines)
**Embedded Business Logic:**
- `start_agent()` / `stop_agent()` - Agent lifecycle
- `running_agents` global state management
- `AgentService` dependency for agent operations
- Multi-agent assignment logic
- Role-based agent management

**Should Extract To:**
- New `core/agent_manager.py` module needed
- Could leverage `core/conductor.py` for multi-agent

**Refactoring Effort:** High (no v2 equivalent yet)

---

#### 4. `projects.py` (560 lines)
**Embedded Business Logic:**
- Project CRUD with workspace provisioning
- Session state management
- Phase/status orchestration
- Activity log tracking
- PRD and issues fetching

**Should Extract To:**
- `core/workspace.py` - Already handles workspace creation
- `core/project_status.py` - Already exists for status
- New `core/projects.py` for CRUD if needed

**Refactoring Effort:** Medium (partial v2 coverage via `projects_v2.py`)

---

### MEDIUM Priority (Feature Parity)

#### 5. `prs.py` (422 lines)
**Embedded Business Logic:**
- `GitHubIntegration` direct usage
- PR creation/merge/close logic
- GitHub API error handling
- WebSocket broadcasts for PR events

**Should Extract To:**
- Already uses `git.github_integration` but has orchestration logic
- Consider `core/pr.py` for PR lifecycle

**Refactoring Effort:** Medium (no v2 equivalent)

---

#### 6. `chat.py` (160 lines)
**Embedded Business Logic:**
- Direct agent communication via `running_agents`
- Conversation history management
- AI response generation

**Should Extract To:**
- New `core/chat.py` module needed
- Could integrate with `core/blockers.py` for human-in-loop

**Refactoring Effort:** Medium (no v2 equivalent)

---

#### 7. `context.py` (510 lines)
**Embedded Business Logic:**
- `ContextManager` direct usage
- `TokenCounter` for context sizing
- Context tier management (HOT/WARM/COLD)
- Flash save operations

**Should Extract To:**
- Already delegates to `lib/context_manager.py`
- Consider promoting to `core/context.py`

**Refactoring Effort:** Low-Medium

---

#### 8. `session.py` (122 lines)
**Embedded Business Logic:**
- `SessionManager` direct usage
- Phase step tracking

**Should Extract To:**
- `core/project_status.py` - Already has `get_session_state()`

**Refactoring Effort:** Low (v2 replacement via `projects_v2.py`)

---

### LOWER Priority (v1 Legacy Features)

#### 9. `checkpoints.py` (v1)
- Already has v2 equivalent
- Consider deprecation after Phase 3

#### 10. `schedule.py` (v1)
- Already has v2 equivalent
- Consider deprecation after Phase 3

#### 11. `templates.py` (v1)
- Already has v2 equivalent
- Consider deprecation after Phase 3

#### 12. `blockers.py` (v1)
- Already has v2 equivalent
- Consider deprecation after Phase 3

#### 13. `lint.py`
- Calls ruff/black directly
- Low priority, not in Golden Path

#### 14. `quality_gates.py`
- Gate execution logic
- Partially duplicates `core/gates.py`

#### 15. `review.py` (v1)
- Already has v2 equivalent
- Consider deprecation after Phase 3

#### 16. `git.py` (v1)
- Already has v2 equivalent
- Consider deprecation after Phase 3

#### 17. `metrics.py`
- Database metrics queries
- Low priority, analytics feature

#### 18. `websocket.py`
- WebSocket connection management
- Required for real-time UI
- Keep as thin adapter over events

---

## Recommended Extraction Order

### Phase 2A (Current - High Priority Gaps)
All HIGH priority v2 routes are now complete ✅

### Phase 2B (Next - Medium Priority)
1. **Workspace Router** - Extract `projects.py` project creation to `core/workspace.py`
2. **Batch Routes** - Already in `core/conductor.py`, just need routes
3. **Diagnose Route** - Already in `core/diagnostic_agent.py`, just need routes

### Phase 2C (Later - Feature Parity)
4. **PR Routes** - Create `core/pr.py` for PR lifecycle
5. **Environment Routes** - Already in `core/environment.py`, just need routes
6. **Gates Routes** - Already in `core/gates.py`, just need routes

### Phase 3 (Web UI Rebuild)
- Agent management (`agents.py` → new `core/agent_manager.py`)
- Chat functionality (`chat.py` → new `core/chat.py`)
- Context management (`context.py` → promote to core)
- Deprecate all v1 routers with v2 equivalents

---

## Core Modules Status

| Core Module | v2 Router | v1 Router Dependency |
|-------------|-----------|---------------------|
| `core/prd_discovery.py` | `discovery_v2.py` ✅ | `discovery.py` |
| `core/prd.py` | `prd_v2.py` ✅ | `discovery.py` |
| `core/tasks.py` | `tasks_v2.py` ✅ | `tasks.py` |
| `core/runtime.py` | `tasks_v2.py` ✅ | `tasks.py` |
| `core/conductor.py` | `tasks_v2.py` ✅ | `tasks.py` |
| `core/blockers.py` | `blockers_v2.py` ✅ | `blockers.py` |
| `core/checkpoints.py` | `checkpoints_v2.py` ✅ | `checkpoints.py` |
| `core/schedule.py` | `schedule_v2.py` ✅ | `schedule.py` |
| `core/templates.py` | `templates_v2.py` ✅ | `templates.py` |
| `core/project_status.py` | `projects_v2.py` ✅ | `projects.py`, `session.py` |
| `core/git.py` | `git_v2.py` ✅ | `git.py` |
| `core/review.py` | `review_v2.py` ✅ | `review.py` |
| `core/streaming.py` | `tasks_v2.py` ✅ | N/A (new) |
| `core/environment.py` | `environment_v2.py` ✅ | N/A |
| `core/diagnostic_agent.py` | `diagnose_v2.py` ✅ | N/A |
| `core/workspace.py` | `workspace_v2.py` ✅ | `projects.py` |
| `core/gates.py` | `gates_v2.py` ✅ | `quality_gates.py` |
| `core/conductor.py` | `batches_v2.py` ✅ | N/A |
| `git/github_integration.py` | `pr_v2.py` ✅ | `prs.py` |
| `core/agent_manager.py` | ⚠️ Phase 3 | `agents.py` |
| `core/chat.py` | ⚠️ Phase 3 | `chat.py` |

---

## Notes

### Design Principle
The v2 architecture follows a strict separation:
- **Core modules** (`codeframe/core/`): Headless business logic, no HTTP dependencies
- **Routers** (`codeframe/ui/routers/`): Thin HTTP adapters that delegate to core
- **Adapters** (`codeframe/adapters/`): External service integrations (LLM, etc.)

### Migration Strategy
1. v1 routers remain for backwards compatibility with existing UI
2. v2 routers provide CLI-equivalent API endpoints
3. Phase 3 (Web UI Rebuild) will deprecate v1 routers
4. Business logic extraction happens incrementally as v2 routes are added

---

## Phase 2 Remaining Work

### V2 Routers Status: ✅ ALL COMPLETE

| Router | Core Module | CLI Command(s) | Status |
|--------|-------------|----------------|--------|
| `workspace_v2.py` | `core.workspace` | `cf init` | ✅ Complete |
| `batches_v2.py` | `core.conductor` | `cf work batch status/stop/resume` | ✅ Complete |
| `diagnose_v2.py` | `core.diagnostic_agent` | `cf work diagnose` | ✅ Complete |
| `pr_v2.py` | `git.github_integration` | `cf pr create/list/status/merge/close` | ✅ Complete |
| `environment_v2.py` | `core.environment` | `cf env check/doctor/install` | ✅ Complete |
| `gates_v2.py` | `core.gates` | `cf gates run` | ✅ Complete |

**Total v2 routes: 80** (across 16 routers)

### Implementation Guide

See `docs/PHASE_2_DEVELOPER_GUIDE.md` for the thin adapter pattern and implementation template.

### Test Coverage

All v2 routers have integration tests in `tests/ui/test_v2_routers_integration.py` (50 tests).
CLI integration tests remain in `tests/cli/test_v2_cli_integration.py` (76 tests).

---

## Acceptance Criteria Verification

**Verified on: 2026-02-01**

| Criterion | Status | Evidence |
|-----------|--------|----------|
| All routes delegate to `core.*` modules | ✅ Pass | All 16 v2 routers verified via code analysis |
| No business logic in route handlers | ✅ Pass | Only request parsing, response formatting, error handling |
| Route audit document created and complete | ✅ Pass | This document |
| Integration tests pass with refactored routes | ✅ Pass | 50 router tests + 76 CLI tests passing |
| 1:1 mapping between CLI commands and server routes | ✅ Pass | All CLI commands have equivalent v2 endpoints |
| Consistent URL patterns across all routes | ✅ Pass | RESTful patterns verified (collection/resource/action) |
| Consistent response formats across all routes | ✅ Pass | 64 endpoints use Pydantic response_model |
| Server remains optional (CLI works independently) | ✅ Pass | `cf --help` works without server |
