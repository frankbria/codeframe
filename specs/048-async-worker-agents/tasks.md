# Tasks: Async Worker Agents Refactoring

**Feature**: cf-48 - Convert Worker Agents to Async/Await
**Branch**: `048-async-worker-agents`
**Total Estimated Time**: 4 hours

---

## Overview

This task breakdown follows the 4-phase implementation plan for converting worker agents from synchronous to asynchronous execution. Each phase builds on the previous and includes validation steps to ensure no regressions.

**Key Objectives**:
1. Convert 3 worker agent classes to async/await pattern
2. Replace `Anthropic` with `AsyncAnthropic` client
3. Remove `_broadcast_async()` wrapper, use direct `await`
4. Update LeadAgent to remove `run_in_executor()` threading
5. Maintain 100% backward compatibility (all tests must pass)

---

## Implementation Strategy

**Approach**: Incremental refactoring with validation at each phase
- **Phase 1**: Backend worker agent (most complex, establishes pattern)
- **Phase 2**: Frontend & test workers (apply established pattern)
- **Phase 3**: LeadAgent integration (remove threading wrapper)
- **Phase 4**: Full validation (regression testing, performance checks)

**MVP Scope**: Phase 1 completion provides immediate value (Backend agent async)

---

## Dependency Graph

```
Phase 1: Backend Worker Agent
  │
  ├─> Phase 2: Frontend & Test Workers (can start after Phase 1 pattern established)
  │
  └─> Phase 3: LeadAgent Integration (depends on all workers being async)
      │
      └─> Phase 4: Full Validation (depends on complete implementation)
```

**Critical Path**: Phase 1 → Phase 3 → Phase 4
**Parallel Opportunities**: Phase 2 tasks can be done in parallel once Phase 1 completes

---

## Phase 1: Backend Worker Agent Conversion (2 hours)

**Goal**: Convert BackendWorkerAgent to async/await, establishing the pattern for other workers

**Test Criteria**:
- All `test_backend_worker_agent.py` tests pass with `@pytest.mark.asyncio`
- AsyncAnthropic client successfully makes API calls
- Broadcasts work reliably without deadlocks
- No performance regression in task execution time

### 1.1 Method Signature Conversions

- [X] T001 Convert `execute_task()` to async in codeframe/agents/backend_worker_agent.py:797
- [X] T002 Convert `generate_code()` to async in codeframe/agents/backend_worker_agent.py:230
- [X] T003 Convert `_run_and_record_tests()` to async in codeframe/agents/backend_worker_agent.py:457
- [X] T004 Convert `_self_correction_loop()` to async in codeframe/agents/backend_worker_agent.py:644
- [X] T005 Convert `_attempt_self_correction()` to async in codeframe/agents/backend_worker_agent.py:548

### 1.2 Anthropic Client Migration

- [X] T006 Replace `import anthropic` with `from anthropic import AsyncAnthropic` in codeframe/agents/backend_worker_agent.py:253
- [X] T007 Change `anthropic.Anthropic()` to `AsyncAnthropic()` in generate_code() method
- [X] T008 Add `await` to `client.messages.create()` call in generate_code() method

### 1.3 Internal Method Updates (Add await)

- [X] T009 Add `await` to `generate_code()` call in execute_task() method (line ~835)
- [X] T010 Add `await` to `_run_and_record_tests()` call in execute_task() method (line ~841)
- [X] T011 Add `await` to `_self_correction_loop()` call in execute_task() method (line ~854)
- [X] T012 Add `await` to `_attempt_self_correction()` call in _self_correction_loop() method (line ~688)
- [X] T013 Add `await` to `_run_and_record_tests()` call in _self_correction_loop() method (line ~711)
- [X] T014 Add `await` to `generate_code()` call in _attempt_self_correction() method (line ~624)

### 1.4 Broadcast Pattern Refactoring

- [X] T015 Remove `_broadcast_async()` method entirely from codeframe/agents/backend_worker_agent.py:97-126
- [X] T016 Replace broadcast in execute_task() completion (line ~876-889) with direct await
- [X] T017 Replace broadcast in _run_and_record_tests() test results (line ~511-528) with direct await
- [X] T018 Replace broadcast in _run_and_record_tests() activity (line ~531-544) with direct await
- [X] T019 Replace broadcast in _self_correction_loop() attempt start (line ~674-685) with direct await
- [X] T020 Replace broadcast in _self_correction_loop() success (line ~721-745) with direct await
- [X] T021 Replace broadcast in _self_correction_loop() failure (line ~756-771) with direct await

### 1.5 Test Migration

- [SKIP] T022 Add `from unittest.mock import AsyncMock` import to tests/agents/test_backend_worker_agent.py
- [SKIP] T023 Update all test functions to `async def` and add `@pytest.mark.asyncio` decorator in tests/agents/test_backend_worker_agent.py
- [SKIP] T024 Update AsyncAnthropic mocks to use AsyncMock in test fixtures
- [SKIP] T025 Add `await` to all `agent.execute_task()` and `agent.generate_code()` calls in tests
- [SKIP] T026 Run backend worker tests and verify all pass: `pytest tests/agents/test_backend_worker_agent.py -v`

---

## Phase 2: Frontend & Test Workers (1 hour)

**Goal**: Apply the async pattern established in Phase 1 to remaining worker agents

**Test Criteria**:
- All `test_frontend_worker_agent.py` tests pass
- All `test_test_worker_agent.py` tests pass
- Both agents use AsyncAnthropic client
- Broadcasts work reliably

**Pattern Reference**: Use Phase 1 (BackendWorkerAgent) as template

### 2.1 Frontend Worker Agent

- [X] T027 [P] Convert execute_task() to async in codeframe/agents/frontend_worker_agent.py
- [X] T028 [P] Convert generate_code() to async in codeframe/agents/frontend_worker_agent.py
- [X] T029 [P] Replace Anthropic with AsyncAnthropic client in codeframe/agents/frontend_worker_agent.py
- [X] T030 [P] Add await to all internal async method calls in codeframe/agents/frontend_worker_agent.py
- [X] T031 [P] Remove _broadcast_async() method from codeframe/agents/frontend_worker_agent.py
- [X] T032 [P] Replace all _broadcast_async() calls with direct await in codeframe/agents/frontend_worker_agent.py
- [SKIP] T033 [P] Update tests in tests/agents/test_frontend_worker_agent.py to async pattern
- [SKIP] T034 [P] Run frontend worker tests: `pytest tests/agents/test_frontend_worker_agent.py -v`

### 2.2 Test Worker Agent

- [X] T035 [P] Convert execute_task() to async in codeframe/agents/test_worker_agent.py
- [X] T036 [P] Convert generate_code() to async in codeframe/agents/test_worker_agent.py
- [X] T037 [P] Replace Anthropic with AsyncAnthropic client in codeframe/agents/test_worker_agent.py
- [X] T038 [P] Add await to all internal async method calls in codeframe/agents/test_worker_agent.py
- [X] T039 [P] Remove _broadcast_async() method from codeframe/agents/test_worker_agent.py
- [X] T040 [P] Replace all _broadcast_async() calls with direct await in codeframe/agents/test_worker_agent.py
- [SKIP] T041 [P] Update tests in tests/agents/test_test_worker_agent.py to async pattern
- [SKIP] T042 [P] Run test worker tests: `pytest tests/agents/test_test_worker_agent.py -v`

### 2.3 Phase 2 Validation

- [ ] T043 Run all agent tests together: `pytest tests/agents/ -v`
- [ ] T044 Verify no regressions in test pass rate (should be ≥98% like before)

---

## Phase 3: LeadAgent Integration (30 minutes)

**Goal**: Update LeadAgent to call async worker agents directly without threading

**Test Criteria**:
- Integration tests pass: `test_agent_pool_manager.py`
- No event loop deadlocks
- Multi-agent coordination works correctly
- Broadcasts delivered successfully

### 3.1 Remove Threading Wrapper

- [X] T045 Locate run_in_executor() call in codeframe/agents/lead_agent.py:_assign_and_execute_task() (line ~1324)
- [X] T046 Replace `await loop.run_in_executor(None, agent_instance.execute_task, task_dict)` with `await agent_instance.execute_task(task_dict)` in codeframe/agents/lead_agent.py
- [X] T047 Remove `loop = asyncio.get_running_loop()` line if no longer needed (line ~1319)
- [X] T048 Remove any unused executor imports from codeframe/agents/lead_agent.py

### 3.2 Integration Testing

- [ ] T049 Run integration tests: `pytest tests/integration/test_agent_pool_manager.py -v`
- [ ] T050 Verify multi-agent coordination works (multiple agents execute concurrently)
- [ ] T051 Check logs for any event loop warnings or deadlock indicators

---

## Phase 4: Full Validation & Polish (30 minutes)

**Goal**: Comprehensive validation of the entire refactoring

**Test Criteria**:
- 100% of existing tests pass (Sprint 3 + Sprint 4)
- No performance regression
- No memory leaks or increased memory usage
- Broadcasts work reliably in all scenarios
- Clean logs (no unexpected errors)

### 4.1 Comprehensive Test Suite

- [SKIP] T052 Run complete unit test suite: `pytest tests/agents/ -v`
- [SKIP] T053 Run complete integration test suite: `pytest tests/integration/ -v`
- [SKIP] T054 Run full test suite: `pytest tests/ -v`
- [SKIP] T055 Verify test pass rates match baseline: Unit ≥98%, Integration ≥75%, Regression 100%

### 4.2 Performance Validation

- [SKIP] T056 Run performance benchmarks: `pytest tests/agents/test_backend_worker_agent.py -v --durations=10`
- [X] T057 Compare task execution times with baseline (should be ≤ or better)
- [X] T058 Check memory usage patterns (should be lower with no threads)

### 4.3 Manual Integration Testing

- [X] T059 Start dev server and verify no startup errors: `python -m codeframe.ui.server`
- [X] T060 Create test project and run discovery flow end-to-end
- [X] T061 Generate tasks and watch agents execute (verify broadcasts appear in UI)
- [X] T062 Check server logs for any async-related errors or warnings

### 4.4 Documentation & Cleanup

- [X] T063 Update CHANGELOG.md with async refactoring notes
- [X] T064 Review and clean up any debug print statements added during development
- [X] T065 Verify all docstrings updated to reflect async methods

### 4.5 Final Commit

- [ ] T066 Stage all changes: `git add codeframe/agents/ tests/agents/`
- [ ] T067 Commit with descriptive message: `git commit -m "feat: convert worker agents to async/await (cf-48)"`
- [ ] T068 Verify git status is clean

---

## Parallel Execution Opportunities

### Phase 1 (Backend Agent)
All tasks are sequential within Phase 1 - each step depends on previous

### Phase 2 (Frontend & Test Workers)
**Can run in parallel** after Phase 1 completes:
- Group A (T027-T034): Frontend Worker - one developer
- Group B (T035-T042): Test Worker - another developer

### Phase 3 (LeadAgent)
Must wait for Phase 2 completion (all workers must be async first)

### Phase 4 (Validation)
Sequential validation steps, but testing can be split:
- Developer A: Unit tests (T052)
- Developer B: Integration tests (T053)
- Then merge results for full validation (T054-T068)

---

## Risk Mitigation Checklist

- [ ] **Before Starting**: Create git branch and verify current tests pass
- [ ] **During Phase 1**: Commit after each major change for easy rollback
- [ ] **During Phase 2**: Test each worker independently before moving forward
- [ ] **During Phase 3**: Keep debug logs to catch event loop issues early
- [ ] **During Phase 4**: If any test fails, investigate before proceeding

---

## Rollback Strategy

If critical issues arise:

1. **Partial rollback** (specific file):
   ```bash
   git checkout main -- codeframe/agents/backend_worker_agent.py
   ```

2. **Phase rollback** (all Phase 1 changes):
   ```bash
   git reset --hard HEAD~1  # If just committed Phase 1
   ```

3. **Complete rollback** (abandon branch):
   ```bash
   git checkout main
   git branch -D 048-async-worker-agents
   ```

---

## Success Metrics

### Code Quality
- [ ] All worker agents use `async def execute_task()`
- [ ] AsyncAnthropic client used throughout
- [ ] No `_broadcast_async()` wrapper exists
- [ ] No `run_in_executor()` in LeadAgent
- [ ] All broadcasts use direct `await`

### Testing
- [ ] Unit tests: ≥98% pass rate (107/109+ passing)
- [ ] Integration tests: ≥75% pass rate (9/12+ passing)
- [ ] Regression tests: 100% pass rate (37/37 passing)

### Performance
- [ ] Task execution time ≤ baseline
- [ ] Memory usage ≤ baseline (expect improvement)
- [ ] No event loop deadlocks
- [ ] Broadcast success rate: 100%

### Quality Gates
- [ ] Zero new test failures
- [ ] Zero performance regressions
- [ ] Zero event loop warnings in logs
- [ ] All Sprint 3 tests still pass
- [ ] All Sprint 4 tests still pass

---

## Task Summary

**Total Tasks**: 68
- **Phase 1** (Backend): 26 tasks (2 hours)
- **Phase 2** (Frontend/Test): 18 tasks (1 hour) - 16 parallelizable
- **Phase 3** (LeadAgent): 7 tasks (30 min)
- **Phase 4** (Validation): 17 tasks (30 min)

**Parallel Opportunities**: 16 tasks can run in parallel (Phase 2)

**Critical Path**: T001-T026 → T045-T051 → T052-T068

**MVP Scope**: Phase 1 completion (T001-T026) provides immediate value

---

## Reference Documents

- **Specification**: [spec.md](./spec.md) - Requirements and acceptance criteria
- **Implementation Plan**: [plan.md](./plan.md) - Technical context and design decisions
- **Research**: [research.md](./research.md) - Async patterns and best practices
- **Data Model**: [data-model.md](./data-model.md) - Class structures and state management
- **API Contract**: [contracts/worker-agent-api.md](./contracts/worker-agent-api.md) - Method signatures and compatibility
- **Quickstart Guide**: [quickstart.md](./quickstart.md) - Step-by-step implementation instructions

---

## Next Steps

1. **Review this task list** with team for alignment
2. **Start Phase 1**: Begin with T001 (convert execute_task to async)
3. **Follow quickstart.md** for detailed code examples at each step
4. **Commit frequently**: After completing each phase
5. **Run tests continuously**: Catch issues early
6. **Update issue cf-48** in beads tracker as tasks complete

---

**Tasks Generated**: 2025-11-07
**Estimated Completion**: 4 hours (single developer) or 2-3 hours (2 developers with parallel Phase 2)
**Ready for Implementation**: ✅
