# Implementation Plan: Async Worker Agents

**Branch**: `048-async-worker-agents` | **Date**: 2025-11-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/048-async-worker-agents/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Refactor BackendWorkerAgent, FrontendWorkerAgent, and TestWorkerAgent from synchronous to asynchronous execution to resolve event loop deadlocks and improve architecture. This involves converting `execute_task()` methods to async/await, using AsyncAnthropic client, removing thread pool wrappers, and fixing WebSocket broadcasts.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: anthropic (AsyncAnthropic), asyncio, FastAPI, websockets
**Storage**: SQLite (existing database schema)
**Testing**: pytest with pytest-asyncio plugin
**Target Platform**: Linux server, WSL2
**Project Type**: Backend service (async worker agents)
**Performance Goals**: No degradation in task execution time, maintain current throughput
**Constraints**: Must maintain backward compatibility, all Sprint 3/4 tests must pass
**Scale/Scope**: 3 worker agent classes, ~1000 LOC modifications, 10+ test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: ✅ PASS (No constitution violations)

This refactoring:
- Does not add new libraries (uses existing anthropic SDK with async client)
- Does not require new CLI interfaces
- Follows TDD (all existing tests must pass)
- No new integration testing required (modifies existing patterns)
- Improves observability (removes problematic broadcast wrapper)
- No breaking changes (maintains existing API contracts)
- Reduces complexity (removes threading overhead)

**Note**: The constitution template appears to be a placeholder. Applying standard software engineering principles:
- Maintain backward compatibility ✅
- Comprehensive testing ✅
- Clear documentation ✅
- No unnecessary complexity ✅

## Project Structure

### Documentation (this feature)

```
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```
codeframe/
├── agents/
│   ├── backend_worker_agent.py      # MODIFY: Convert to async
│   ├── frontend_worker_agent.py     # MODIFY: Convert to async
│   ├── test_worker_agent.py         # MODIFY: Convert to async
│   └── lead_agent.py                # MODIFY: Remove run_in_executor
├── providers/
│   └── anthropic.py                 # CHECK: Verify async client usage
└── ui/
    └── websocket_broadcasts.py      # REFERENCE: Direct broadcast functions

tests/
├── agents/
│   ├── test_backend_worker_agent.py    # MODIFY: Add async tests
│   ├── test_frontend_worker_agent.py   # MODIFY: Add async tests
│   └── test_test_worker_agent.py       # MODIFY: Add async tests
└── integration/
    └── test_agent_pool_manager.py      # VERIFY: Still passes
```

**Structure Decision**: Existing codebase structure. This is a refactoring task that modifies existing files rather than creating new structure. All changes are within the `codeframe/agents/` directory and corresponding tests.

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

**Status**: N/A - No constitution violations

This refactoring actually **reduces** complexity by:
- Removing the `_broadcast_async()` wrapper (simpler direct awaits)
- Eliminating threading overhead (native async)
- Following standard Python async patterns

---

## Phase 0: Research ✅ COMPLETE

All unknowns from Technical Context have been resolved:

1. **Async/Await Patterns**: Researched Python best practices → Use `async def` for I/O-bound methods
2. **AsyncAnthropic Client**: Reviewed SDK documentation → Nearly identical API to sync client
3. **Broadcast Pattern**: Analyzed event loop issues → Direct `await` is correct approach
4. **Test Migration**: Researched pytest-asyncio → Standard decorator pattern works
5. **Performance Impact**: Analyzed async vs threading → Expect improvement due to lower overhead

**Output**: [research.md](./research.md) - Comprehensive research document with all decisions documented

---

## Phase 1: Design & Contracts ✅ COMPLETE

Generated design artifacts based on research findings:

1. **Data Model**: [data-model.md](./data-model.md)
   - Documented affected classes (BackendWorkerAgent, FrontendWorkerAgent, TestWorkerAgent, LeadAgent)
   - Defined async method signatures
   - Described state management changes
   - Specified error handling patterns

2. **API Contracts**: [contracts/worker-agent-api.md](./contracts/worker-agent-api.md)
   - Defined async API contract for all worker agent methods
   - Documented breaking changes and migration paths
   - Specified WebSocket broadcast integration
   - Provided compatibility matrix

3. **Quickstart Guide**: [quickstart.md](./quickstart.md)
   - Step-by-step implementation guide (4 phases)
   - Code examples for each conversion step
   - Testing strategy and validation steps
   - Troubleshooting guide with common issues

4. **Agent Context Updated**: CLAUDE.md updated with:
   - Python 3.11
   - anthropic (AsyncAnthropic), asyncio, FastAPI, websockets
   - SQLite database
   - Backend service project type

---

## Phase 2: Task Breakdown (Use /speckit.tasks command)

**Note**: The `/speckit.plan` command ends here. To generate `tasks.md`, run:

```bash
/speckit.tasks
```

This will create dependency-ordered, actionable tasks based on the design artifacts above.

---

## Summary of Deliverables

### Planning Artifacts ✅
- [X] spec.md - Feature specification with requirements and acceptance criteria
- [X] plan.md - This file (implementation plan)
- [X] research.md - Research findings and design decisions
- [X] data-model.md - Class structures and state management
- [X] contracts/worker-agent-api.md - API contracts and compatibility
- [X] quickstart.md - Implementation guide
- [X] CLAUDE.md - Updated agent context

### Implementation Files (Created by /speckit.tasks)
- [ ] tasks.md - Actionable task breakdown (pending /speckit.tasks command)

---

## Constitution Check Re-evaluation

**Status**: ✅ PASS (Post-Design)

After Phase 1 design, we confirm:
- No new libraries added ✅
- No new CLI interfaces required ✅
- TDD maintained (all tests must pass) ✅
- Integration testing requirements unchanged ✅
- Observability improved (broadcasts work reliably) ✅
- No breaking changes to external APIs ✅
- Complexity reduced (simpler async pattern) ✅

---

## Ready for Implementation

**Prerequisites Met**:
- ✅ All research completed
- ✅ All design decisions documented
- ✅ API contracts defined
- ✅ Implementation guide created
- ✅ Testing strategy defined
- ✅ Rollback plan documented

**Next Steps**:
1. Run `/speckit.tasks` to generate task breakdown
2. Execute tasks following quickstart.md guide
3. Commit after each phase
4. Run full test suite for validation

---

