# Session: Fix Multi-Agent Per Project Architecture

**Date**: 2025-12-03
**Branch**: `fix/multi-agent-per-project-architecture` (feature branch)
**Base Commit**: `8894c89` - fix(e2e): Update Playwright tests to navigate to correct dashboard URL
**Goal**: Fix architectural issue - refactor from "one project per agent" to "one project with multiple agents"

## Problem Statement

Current architecture incorrectly maps one project to one agent. The correct architecture should be:
- **One project can have multiple agents** (orchestrator, backend, frontend, test, review)
- **Multiple projects can exist simultaneously**
- **Each agent has isolated context** scoped by `(project_id, agent_id)`

This requires changes across:
- Database schema and CRUD operations
- API endpoints and business logic
- Frontend state management and components
- All test suites (backend, frontend, E2E)

## Simplifications (Non-Production App)

Since this is not in production:
- ✅ No backwards compatibility needed
- ✅ No API contract versioning required
- ✅ No complex database migration (can recreate schema)
- ✅ No client-side migration concerns

## Execution Plan (8 Phases)

### Phase 1: Database Schema Investigation & Design ⏳
**Status**: In Progress
**Goal**: Analyze current schema and design proper multi-agent architecture
**Resources**: `python-expert`, `system-architect`
**Expected Outcome**:
- Document current schema flaws
- Design new schema with proper one-to-many relationship (projects → agents)
- Identify all tables needing updates (agents, context_items, tasks, etc.)

### Phase 2: Database Migration Implementation
**Status**: Pending
**Goal**: Implement schema changes and update CRUD methods
**Resources**: `python-expert`, `pytest-bdd`
**Expected Outcome**:
- Updated schema in `database.py`
- Updated Database class methods for multi-agent support
- BDD tests for data integrity

### Phase 3: API & Business Logic Updates (Parallel)
**Status**: Pending
**Goal**: Update FastAPI endpoints and agent business logic
**Resources**: `fastapi-expert`, `python-expert`, `rest-expert` (parallel)
**Expected Outcome**:
- New API routes: `GET/POST /projects/{id}/agents`
- Updated `WorkerAgent.__init__()` to require project_id
- All agent methods use `(project_id, agent_id)` scoping

### Phase 4: Backend Test Fixes (Parallel)
**Status**: Pending
**Goal**: Fix all backend tests
**Resources**: `python-expert`, `quality-engineer`, `pytest-bdd` (parallel)
**Expected Outcome**:
- All unit tests passing (database, agents, lib)
- All integration tests passing
- Updated BDD scenarios

### Phase 5: Frontend Updates
**Status**: Pending
**Goal**: Update React components for multi-agent display
**Resources**: `react-expert`, `typescript-expert`, `rest-expert`
**Expected Outcome**:
- Updated types in `web-ui/src/types/`
- Updated API clients in `web-ui/src/api/`
- New components: `AgentList`, `AgentSelector`

### Phase 6: Frontend Test Fixes
**Status**: Pending
**Goal**: Fix Jest tests and validate coverage
**Resources**: `jest-expert`, `quality-engineer`
**Expected Outcome**:
- All frontend unit tests passing
- 85%+ coverage maintained

### Phase 7: End-to-End Test Fixes
**Status**: Pending
**Goal**: Fix Playwright E2E tests
**Resources**: `playwright-expert`, `playwright-skill`
**Expected Outcome**:
- Fixed E2E tests for multi-agent workflows
- New scenarios for agent coordination

### Phase 8: Final Integration & Validation
**Status**: Pending
**Goal**: Comprehensive quality validation
**Resources**: `/fhb:code-review`, `reviewing-code`, `quality-engineer`
**Expected Outcome**:
- Code review passed
- OWASP compliance validated
- All tests passing (100% pass rate)
- Coverage ≥85%

## Estimated Metrics

- **Token Usage**: ~127k tokens total
- **Risk Level**: Low (non-production, can break things freely)
- **Expected Improvement**: Proper architectural foundation for multi-agent collaboration

## Validation Strategy

- ✅ After Phase 1: Approve schema design
- ✅ After Phase 2: Verify schema works with basic CRUD operations
- ✅ After Phase 4: All backend tests must pass before frontend work
- ✅ After Phase 7: All E2E tests must pass before final review

## Notes

- Previous session (Playwright E2E fixes) archived to: `claudedocs/2025-12-03_SESSION_playwright-e2e.md`
- Testing strategy: Test progressively (DB → API → Frontend) rather than all at end
- Parallelization: Phases 3 and 4 use parallel agents for independent work
