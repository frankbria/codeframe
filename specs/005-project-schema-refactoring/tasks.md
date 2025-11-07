---
description: "Task list for Phase 5.2: Dashboard Multi-Agent State Management"
---

# Tasks: Phase 5.2 - Dashboard Multi-Agent State Management

**Input**: Design documents from `/specs/005-project-schema-refactoring/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/agent-state-api.ts

**Tests**: Comprehensive test coverage requested in spec (≥85% coverage target)

**Organization**: Tasks grouped by functional capability to enable incremental testing and delivery.

## Format: `- [ ] [ID] [P?] [Story?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Feature grouping (US1=State Management, US2=WebSocket Integration, US3=Reconnection)
- Include exact file paths in descriptions

## Path Conventions
- **Frontend**: `web-ui/src/` for source, `web-ui/__tests__/` for tests
- **Components**: `web-ui/src/components/`
- **Hooks**: `web-ui/src/hooks/`
- **Reducers**: `web-ui/src/reducers/`
- **Types**: `web-ui/src/types/`
- **Utils**: `web-ui/src/lib/`

---

## Phase 1: Setup & Type Definitions

**Purpose**: Create TypeScript interfaces and project structure for state management

- [X] T001 [P] Create agentState.ts type definitions in web-ui/src/types/agentState.ts
- [X] T002 [P] Create reducer action type definitions based on contracts/agent-state-api.ts
- [X] T003 [P] Add timestamp utility functions in web-ui/src/lib/timestampUtils.ts
- [X] T004 Create test fixtures for mock agents and tasks in web-ui/__tests__/fixtures/agentState.ts

---

## Phase 2: Foundational - Reducer Implementation

**Purpose**: Core reducer logic that MUST be complete before Context and WebSocket integration

**⚠️ CRITICAL**: All tests in this phase must PASS before proceeding to user stories

### Tests for Reducer (TDD - Write First)

- [X] T005 [P] [US1] Unit test for AGENTS_LOADED action in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T006 [P] [US1] Unit test for AGENT_CREATED action in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T007 [P] [US1] Unit test for AGENT_UPDATED with timestamp conflict resolution in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T008 [P] [US1] Unit test for AGENT_RETIRED action in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T009 [P] [US1] Unit test for TASK_ASSIGNED action (atomic agent+task update) in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T010 [P] [US1] Unit test for TASK_STATUS_CHANGED action in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T011 [P] [US1] Unit test for TASK_BLOCKED action in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T012 [P] [US1] Unit test for TASK_UNBLOCKED action in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T013 [P] [US1] Unit test for ACTIVITY_ADDED with FIFO 50-item limit in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T014 [P] [US1] Unit test for PROGRESS_UPDATED action in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T015 [P] [US1] Unit test for WS_CONNECTED action in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T016 [P] [US1] Unit test for FULL_RESYNC action (atomic state replacement) in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T017 [P] [US1] Unit test for timestamp conflict resolution (reject stale updates) in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T018 [P] [US1] Unit test for immutability (state not mutated) in web-ui/__tests__/reducers/agentReducer.test.ts
- [X] T019 [P] [US1] Unit test for 10 agent limit warning in web-ui/__tests__/reducers/agentReducer.test.ts

### Reducer Implementation

- [X] T020 [US1] Create agentReducer.ts with initial state in web-ui/src/reducers/agentReducer.ts
- [X] T021 [US1] Implement AGENTS_LOADED action handler in agentReducer.ts
- [X] T022 [US1] Implement AGENT_CREATED action handler in agentReducer.ts
- [X] T023 [US1] Implement AGENT_UPDATED action handler with timestamp conflict resolution in agentReducer.ts
- [X] T024 [US1] Implement AGENT_RETIRED action handler in agentReducer.ts
- [X] T025 [US1] Implement TASK_ASSIGNED action handler (atomic update) in agentReducer.ts
- [X] T026 [US1] Implement TASK_STATUS_CHANGED action handler in agentReducer.ts
- [X] T027 [US1] Implement TASK_BLOCKED action handler in agentReducer.ts
- [X] T028 [US1] Implement TASK_UNBLOCKED action handler in agentReducer.ts
- [X] T029 [US1] Implement ACTIVITY_ADDED action handler with 50-item sliding window in agentReducer.ts
- [X] T030 [US1] Implement PROGRESS_UPDATED action handler in agentReducer.ts
- [X] T031 [US1] Implement WS_CONNECTED action handler in agentReducer.ts
- [X] T032 [US1] Implement FULL_RESYNC action handler (atomic replacement) in agentReducer.ts
- [X] T033 [US1] Add development mode logging for all actions in agentReducer.ts
- [X] T034 [US1] Add validation warnings (10 agent limit, 50 activity limit) in agentReducer.ts
- [X] T035 [US1] Run all reducer tests to verify 100% pass rate

**Checkpoint**: Reducer fully implemented and tested - Context layer can now be built

---

## Phase 3: User Story 1 - Context & Hook Implementation (Priority: P0) 🎯

**Goal**: Provide centralized agent state via React Context with useReducer

**Independent Test**: Import useAgentState hook in test component, verify state access and dispatch work

### Tests for Context & Hook (TDD - Write First)

- [X] T036 [P] [US1] Component test for AgentStateProvider renders children in web-ui/__tests__/components/AgentStateProvider.test.tsx
- [X] T037 [P] [US1] Component test for AgentStateProvider provides initial state in web-ui/__tests__/components/AgentStateProvider.test.tsx
- [X] T038 [P] [US1] Hook test for useAgentState returns state values in web-ui/__tests__/hooks/useAgentState.test.tsx
- [X] T039 [P] [US1] Hook test for useAgentState derived state (activeAgents, idleAgents) in web-ui/__tests__/hooks/useAgentState.test.tsx
- [X] T040 [P] [US1] Hook test for useAgentState action wrappers dispatch correctly in web-ui/__tests__/hooks/useAgentState.test.tsx
- [X] T041 [P] [US1] Component test for AgentStateProvider handles multiple dispatch calls in web-ui/__tests__/components/AgentStateProvider.test.tsx

### Context & Hook Implementation

- [X] T042 [P] [US1] Create AgentStateContext in web-ui/src/contexts/AgentStateContext.ts
- [X] T043 [US1] Create AgentStateProvider component with useReducer in web-ui/src/components/AgentStateProvider.tsx
- [X] T044 [US1] Add SWR initial data fetch in AgentStateProvider (agents, tasks, activity)
- [X] T045 [US1] Create useAgentState hook with context consumer in web-ui/src/hooks/useAgentState.ts
- [X] T046 [US1] Add derived state (activeAgents, idleAgents, activeTasks, blockedTasks) with useMemo in useAgentState.ts
- [X] T047 [US1] Add action wrapper functions in useAgentState.ts (loadAgents, createAgent, updateAgent, etc.)
- [X] T048 [US1] Add useCallback for all action wrappers to prevent re-renders in useAgentState.ts
- [X] T049 [US1] Run all Context and Hook tests to verify 100% pass rate

**Checkpoint**: Context and Hook working - Components can now consume agent state

---

## Phase 4: User Story 2 - WebSocket Integration (Priority: P0)

**Goal**: Map WebSocket messages to reducer actions for real-time updates

**Independent Test**: Send mock WebSocket message, verify state updates via useAgentState

### Tests for WebSocket Integration (TDD - Write First)

- [X] T050 [P] [US2] Unit test for mapWebSocketMessageToAction (agent_created) in web-ui/__tests__/lib/websocketMessageMapper.test.ts
- [X] T051 [P] [US2] Unit test for mapWebSocketMessageToAction (agent_status_changed) in web-ui/__tests__/lib/websocketMessageMapper.test.ts
- [X] T052 [P] [US2] Unit test for mapWebSocketMessageToAction (agent_retired) in web-ui/__tests__/lib/websocketMessageMapper.test.ts
- [X] T053 [P] [US2] Unit test for mapWebSocketMessageToAction (task_assigned) in web-ui/__tests__/lib/websocketMessageMapper.test.ts
- [X] T054 [P] [US2] Unit test for mapWebSocketMessageToAction (task_status_changed) in web-ui/__tests__/lib/websocketMessageMapper.test.ts
- [X] T055 [P] [US2] Unit test for mapWebSocketMessageToAction (task_blocked/unblocked) in web-ui/__tests__/lib/websocketMessageMapper.test.ts
- [X] T056 [P] [US2] Unit test for mapWebSocketMessageToAction (activity_update) in web-ui/__tests__/lib/websocketMessageMapper.test.ts
- [X] T057 [P] [US2] Unit test for mapWebSocketMessageToAction (progress_update) in web-ui/__tests__/lib/websocketMessageMapper.test.ts
- [X] T058 [P] [US2] Unit test for timestamp parsing (string and number) in web-ui/__tests__/lib/websocketMessageMapper.test.ts
- [X] T059 [P] [US2] Integration test for WebSocket message → state update in web-ui/__tests__/integration/websocket-state-sync.test.ts
- [X] T060 [P] [US2] Integration test for multiple simultaneous agent updates in web-ui/__tests__/integration/multi-agent-updates.test.ts
- [X] T061 [P] [US2] Integration test for out-of-order message handling in web-ui/__tests__/integration/websocket-state-sync.test.ts

### WebSocket Integration Implementation

- [X] T062 [P] [US2] Create websocketMessageMapper.ts with message type handlers in web-ui/src/lib/websocketMessageMapper.ts
- [X] T063 [US2] Implement agent_created message mapping in websocketMessageMapper.ts
- [X] T064 [US2] Implement agent_status_changed message mapping in websocketMessageMapper.ts
- [X] T065 [US2] Implement agent_retired message mapping in websocketMessageMapper.ts
- [X] T066 [US2] Implement task_assigned message mapping in websocketMessageMapper.ts
- [X] T067 [US2] Implement task_status_changed message mapping in websocketMessageMapper.ts
- [X] T068 [US2] Implement task_blocked/unblocked message mapping in websocketMessageMapper.ts
- [X] T069 [US2] Implement activity_update message mapping in websocketMessageMapper.ts
- [X] T070 [US2] Implement test_result, commit_created, correction_attempt mappings in websocketMessageMapper.ts
- [X] T071 [US2] Implement progress_update message mapping in websocketMessageMapper.ts
- [X] T072 [US2] Add timestamp parsing utility (string/number to Unix ms) in websocketMessageMapper.ts
- [X] T073 [US2] Add WebSocket subscription in AgentStateProvider.tsx (onMessage handler)
- [X] T074 [US2] Add project_id filtering in WebSocket message handler
- [X] T075 [US2] Connect message mapper to dispatch in AgentStateProvider.tsx
- [X] T076 [US2] Add cleanup for WebSocket subscription in useEffect return
- [X] T077 [US2] Run all WebSocket integration tests to verify 100% pass rate

**Checkpoint**: WebSocket messages updating state in real-time

---

## Phase 5: User Story 3 - Reconnection & Resync (Priority: P0)

**Goal**: Handle WebSocket disconnections with full state resynchronization

**Independent Test**: Simulate disconnect/reconnect, verify full state resync triggers and succeeds

### Tests for Reconnection (TDD - Write First)

- [X] T078 [P] [US3] Unit test for fullStateResync API call in web-ui/__tests__/lib/agentStateSync.test.ts
- [X] T079 [P] [US3] Unit test for fullStateResync parallel fetches (Promise.all) in web-ui/__tests__/lib/agentStateSync.test.ts
- [X] T080 [P] [US3] Unit test for fullStateResync error handling in web-ui/__tests__/lib/agentStateSync.test.ts
- [X] T081 [P] [US3] Integration test for WebSocket reconnection triggers resync in web-ui/__tests__/integration/websocket-reconnection.test.ts
- [X] T082 [P] [US3] Integration test for WS_CONNECTED state changes in web-ui/__tests__/integration/websocket-reconnection.test.ts
- [X] T083 [P] [US3] Integration test for FULL_RESYNC replaces stale data in web-ui/__tests__/integration/websocket-reconnection.test.ts
- [X] T084 [P] [US3] Integration test for repeated disconnect/reconnect cycles in web-ui/__tests__/integration/websocket-reconnection.test.ts

### Reconnection Implementation

- [X] T085 [P] [US3] Create agentStateSync.ts with fullStateResync function in web-ui/src/lib/agentStateSync.ts
- [X] T086 [US3] Implement parallel API fetches (Promise.all) in fullStateResync
- [X] T087 [US3] Add error handling and retry logic in fullStateResync
- [X] T088 [US3] Add reconnection detector in AgentStateProvider.tsx (WebSocket onReconnect)
- [X] T089 [US3] Dispatch WS_CONNECTED(false) on disconnect in AgentStateProvider.tsx
- [X] T090 [US3] Trigger fullStateResync on reconnect in AgentStateProvider.tsx
- [X] T091 [US3] Dispatch FULL_RESYNC action with fresh data in AgentStateProvider.tsx
- [X] T092 [US3] Dispatch WS_CONNECTED(true) after successful resync in AgentStateProvider.tsx
- [X] T093 [US3] Add exponential backoff for reconnection attempts in WebSocket client wrapper
- [X] T094 [US3] Add debounce logic to prevent rapid reconnect cycles in AgentStateProvider.tsx
- [X] T095 [US3] Run all reconnection tests to verify 100% pass rate

**Checkpoint**: Reconnection handling robust and tested

---

## Phase 6: User Story 4 - Dashboard Integration (Priority: P0)

**Goal**: Migrate Dashboard component to use Context instead of local state

**Independent Test**: Dashboard renders with Context state, AgentCards update from WebSocket messages

### Tests for Dashboard Migration (TDD - Write First)

- [X] T096 [P] [US4] Component test for Dashboard renders with AgentStateProvider in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T097 [P] [US4] Component test for Dashboard displays agents from context in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T098 [P] [US4] Component test for Dashboard connection indicator shows wsConnected state in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T099 [P] [US4] Component test for AgentCard receives agent from context in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T100 [P] [US4] Integration test for Dashboard updates when WebSocket message arrives in web-ui/__tests__/integration/dashboard-realtime-updates.test.ts
- [X] T101 [P] [US4] Integration test for multiple AgentCards update independently in web-ui/__tests__/integration/dashboard-realtime-updates.test.ts

### Dashboard Integration Implementation

- [X] T102 [US4] Wrap Dashboard component with AgentStateProvider in web-ui/src/app/projects/[projectId]/page.tsx
- [X] T103 [US4] Replace agents useState with useAgentState hook in Dashboard.tsx
- [X] T104 [US4] Replace tasks useState with useAgentState hook in Dashboard.tsx
- [X] T105 [US4] Replace activity useState with useAgentState hook in Dashboard.tsx
- [X] T106 [US4] Replace projectProgress useState with useAgentState hook in Dashboard.tsx
- [X] T107 [US4] Remove local WebSocket message handlers (now in Provider) from Dashboard.tsx
- [X] T108 [US4] Add connection status indicator using wsConnected from context in Dashboard.tsx
- [X] T109 [US4] Update AgentCard mapping to use agents from context in Dashboard.tsx
- [X] T110 [US4] Add React.memo to AgentCard component with custom comparison in web-ui/src/components/AgentCard.tsx
- [X] T111 [US4] Add useMemo for filtered agent lists (activeAgents) in Dashboard.tsx
- [X] T112 [US4] Add useCallback for onAgentClick handler in Dashboard.tsx
- [X] T113 [US4] Remove redundant useEffect for SWR data (handled by Provider) from Dashboard.tsx
- [X] T114 [US4] Run all Dashboard integration tests to verify 100% pass rate

**Checkpoint**: Dashboard fully migrated to Context-based state

---

## Phase 7: User Story 5 - Performance & Validation (Priority: P0)

**Goal**: Optimize performance and add validation warnings for constraints

**Independent Test**: Render Dashboard with 10 agents, verify < 50ms updates, no warnings

### Tests for Performance & Validation

- [ ] T115 [P] [US5] Performance test for state update latency < 50ms in web-ui/__tests__/performance/state-update-latency.test.ts
- [ ] T116 [P] [US5] Performance test for WebSocket message processing < 100ms in web-ui/__tests__/performance/websocket-processing.test.ts
- [ ] T117 [P] [US5] Performance test for 10 concurrent agents without lag in web-ui/__tests__/performance/ten-agents-load.test.ts
- [ ] T118 [P] [US5] Performance test for full resync < 2 seconds in web-ui/__tests__/performance/resync-speed.test.ts
- [ ] T119 [P] [US5] Unit test for validateAgentCount warns at 11 agents in web-ui/__tests__/lib/validation.test.ts
- [ ] T120 [P] [US5] Unit test for validateActivitySize warns at 51 items in web-ui/__tests__/lib/validation.test.ts
- [ ] T121 [P] [US5] Integration test for no memory leaks in WebSocket subscription in web-ui/__tests__/integration/memory-leak-detection.test.ts

### Performance & Validation Implementation

- [ ] T122 [P] [US5] Add React.memo to all Dashboard sub-components in web-ui/src/components/
- [ ] T123 [P] [US5] Add useMemo for expensive derived state calculations in useAgentState.ts
- [ ] T124 [P] [US5] Add custom comparison function for AgentCard memo in AgentCard.tsx
- [ ] T125 [US5] Add validateAgentCount function in web-ui/src/lib/validation.ts
- [ ] T126 [US5] Add validateActivitySize function in web-ui/src/lib/validation.ts
- [ ] T127 [US5] Call validation functions in reducer after state updates in agentReducer.ts
- [ ] T128 [US5] Add React Profiler wrapper for performance monitoring in Dashboard.tsx
- [ ] T129 [US5] Add console.warn for slow renders (> 50ms) in dev mode
- [ ] T130 [US5] Profile Dashboard with 10 agents using React DevTools
- [ ] T131 [US5] Optimize any components with > 10ms render time
- [ ] T132 [US5] Run all performance tests to verify targets met

**Checkpoint**: Performance targets met (< 50ms updates, < 2s resync)

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements affecting multiple features

- [ ] T133 [P] Add ErrorBoundary component for state management failures in web-ui/src/components/ErrorBoundary.tsx
- [ ] T134 [P] Wrap AgentStateProvider with ErrorBoundary in Dashboard.tsx
- [ ] T135 [P] Add comprehensive JSDoc comments to all exported functions
- [ ] T136 [P] Update CLAUDE.md with state management architecture notes
- [ ] T137 [P] Verify quickstart.md examples work (run manually or create test)
- [ ] T138 Code cleanup: Remove commented-out old state management code from Dashboard.tsx
- [ ] T139 Code cleanup: Remove unused imports and dead code across all files
- [ ] T140 Run full test suite to verify 85%+ coverage target
- [ ] T141 Run type check (tsc --noEmit) to verify no TypeScript errors
- [ ] T142 Run linter (npm run lint) and fix any issues
- [ ] T143 [P] Manual QA: Test with backend sending real WebSocket messages
- [ ] T144 [P] Manual QA: Test disconnect/reconnect with network throttling
- [ ] T145 [P] Manual QA: Test with 10 concurrent agents updating simultaneously
- [ ] T146 [P] Manual QA: Verify no console errors or warnings in production build
- [ ] T147 Verify all existing Phase 5.1 AgentCard tests still pass
- [ ] T148 Final code review: Check for immutability violations in reducer
- [ ] T149 Final code review: Verify timestamp conflict resolution working correctly
- [ ] T150 Create final summary of test coverage and performance metrics

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (reducer must exist)
- **User Story 2 (Phase 4)**: Depends on US1 (needs Context/Hook)
- **User Story 3 (Phase 5)**: Depends on US1 and US2 (needs Context + WebSocket)
- **User Story 4 (Phase 6)**: Depends on US1, US2, US3 (full integration)
- **User Story 5 (Phase 7)**: Depends on US4 (need integrated system to test)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (Context & Hook)**: Independent after Foundational - Core state management
- **US2 (WebSocket)**: Depends on US1 - Needs Context to dispatch actions
- **US3 (Reconnection)**: Depends on US1 and US2 - Needs Context + WebSocket
- **US4 (Dashboard)**: Depends on US1, US2, US3 - Full integration
- **US5 (Performance)**: Depends on US4 - Needs integrated system

### Within Each User Story

1. **Tests FIRST** (TDD): All tests written and FAILING
2. **Implementation SECOND**: Make tests pass
3. **Verify tests PASS**: 100% pass rate before moving on
4. **Story checkpoint**: Validate increment works independently

### Parallel Opportunities

**Phase 1 (Setup)**: All tasks [P] can run in parallel
- T001, T002, T003 (different files)

**Phase 2 (Foundational Tests)**: All unit tests [P] can run in parallel
- T005-T019 (all testing different action types)

**Phase 3 (US1 Tests)**: T036-T041 can run in parallel (different test files)

**Phase 4 (US2 Tests)**: T050-T061 can run in parallel (different test files/concerns)

**Phase 5 (US3 Tests)**: T078-T084 can run in parallel (different test files)

**Phase 6 (US4 Tests)**: T096-T101 can run in parallel (different test concerns)

**Phase 7 (US5 Tests)**: T115-T121 can run in parallel (different performance metrics)

**Phase 8 (Polish)**: Most tasks [P] can run in parallel (different files)

---

## Parallel Example: Phase 2 Foundational Tests

```bash
# Launch all reducer unit tests together (TDD - write these first):
Task T005: "Unit test for AGENTS_LOADED action in web-ui/__tests__/reducers/agentReducer.test.ts"
Task T006: "Unit test for AGENT_CREATED action in web-ui/__tests__/reducers/agentReducer.test.ts"
Task T007: "Unit test for AGENT_UPDATED with timestamp conflict resolution"
# ... all T005-T019 can run in parallel
```

## Parallel Example: Phase 4 WebSocket Mapping

```bash
# Launch all message mapper tests together:
Task T050: "Unit test for mapWebSocketMessageToAction (agent_created)"
Task T051: "Unit test for mapWebSocketMessageToAction (agent_status_changed)"
# ... all T050-T058 can run in parallel

# Then implement mappers in parallel:
Task T063: "Implement agent_created message mapping in websocketMessageMapper.ts"
Task T064: "Implement agent_status_changed message mapping"
# ... T063-T071 can run in parallel (different message types)
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational Reducer (T005-T035) - CRITICAL
3. Complete Phase 3: US1 Context & Hook (T036-T049)
4. Complete Phase 4: US2 WebSocket Integration (T050-T077)
5. **STOP and VALIDATE**: Test reducer + context + WebSocket in isolation
6. If validation passes, proceed to reconnection and Dashboard integration

### Incremental Delivery

1. **Foundation** (Phases 1-2): Reducer fully tested → Can dispatch actions manually
2. **+ Context** (Phase 3): Components can consume state → Test with manual dispatch
3. **+ WebSocket** (Phase 4): Real-time updates working → Test with backend
4. **+ Reconnection** (Phase 5): Network resilience → Test disconnect scenarios
5. **+ Dashboard** (Phase 6): Full UI integration → E2E testing
6. **+ Performance** (Phase 7): Optimization complete → Verify targets
7. **+ Polish** (Phase 8): Production ready → Deploy

Each increment adds value and can be validated independently.

### Test-First Workflow (TDD)

For each user story:
1. Write ALL tests for the story (ensure they FAIL)
2. Implement features to make tests pass
3. Verify 100% of tests pass before moving on
4. If tests don't pass, debug implementation (don't skip tests)

Example for US1:
- Write T036-T041 (all Context tests) → All fail
- Implement T042-T048 (Context + Hook)
- Run T036-T041 again → Should all pass
- Checkpoint: US1 complete

---

## Notes

- **[P] tasks** = Different files, no dependencies, can run in parallel
- **[Story] labels**: US1=State Management, US2=WebSocket, US3=Reconnection, US4=Dashboard, US5=Performance
- **TDD Approach**: Tests written first, implementation follows
- **Test Coverage Target**: ≥85% (specified in spec.md)
- **Performance Targets**: <50ms updates, <100ms message processing, <2s resync, 10 agents
- **Checkpoints**: Validate after each major phase before proceeding
- **Immutability**: All reducer updates must use spread operator or array methods
- **TypeScript**: Strict mode enabled, no 'any' types except in mapper for unknown message fields
- **Conflict Resolution**: Always use backend timestamps, reject stale updates
- **Activity Feed**: Maintain 50-item sliding window (FIFO)
- **Agent Limit**: Warn if > 10 agents
- **Memory Leaks**: Always cleanup WebSocket subscriptions in useEffect return

---

## Task Summary

**Total Tasks**: 150
- **Phase 1 (Setup)**: 4 tasks
- **Phase 2 (Foundational)**: 31 tasks (15 tests + 16 implementation)
- **Phase 3 (US1 - Context)**: 14 tasks (6 tests + 8 implementation)
- **Phase 4 (US2 - WebSocket)**: 28 tasks (12 tests + 16 implementation)
- **Phase 5 (US3 - Reconnection)**: 18 tasks (7 tests + 11 implementation)
- **Phase 6 (US4 - Dashboard)**: 19 tasks (6 tests + 13 implementation)
- **Phase 7 (US5 - Performance)**: 18 tasks (7 tests + 11 implementation)
- **Phase 8 (Polish)**: 18 tasks

**Test Tasks**: 53 (35% of total)
**Implementation Tasks**: 79 (53% of total)
**QA & Polish Tasks**: 18 (12% of total)

**Parallel Opportunities**:
- Phase 1: 3 tasks can run in parallel
- Phase 2 Tests: 15 tasks can run in parallel
- Phase 3 Tests: 6 tasks can run in parallel
- Phase 4 Tests: 12 tasks can run in parallel
- Phase 4 Implementation: 9 mapper tasks can run in parallel
- Phase 5 Tests: 7 tasks can run in parallel
- Phase 6 Tests: 6 tasks can run in parallel
- Phase 7 Tests: 7 tasks can run in parallel
- Phase 8: 10 tasks can run in parallel

**MVP Scope** (Phases 1-4): 77 tasks - Delivers working real-time state management

**Estimated Effort**:
- MVP (Phases 1-4): ~3-4 days for experienced React/TypeScript developer
- Full Feature (All Phases): ~5-6 days
- With team of 3: ~2-3 days (parallel execution)

**Independent Test Criteria**:
- US1: Dispatch action manually, verify state changes in test component
- US2: Send mock WebSocket message, verify state updates
- US3: Simulate disconnect, verify resync triggers
- US4: Render Dashboard, verify agents display from Context
- US5: Run performance profiler, verify < 50ms updates
