# Implementation Plan: Phase 5.2 - Dashboard Multi-Agent State Management

**Branch**: `005-project-schema-refactoring` | **Date**: 2025-11-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-project-schema-refactoring/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Enhance the Dashboard with centralized state management using React Context + useReducer to handle multiple concurrent agents (up to 10) with real-time WebSocket updates, full state resynchronization on reconnection, and timestamp-based conflict resolution for simultaneous updates.

**Key Technical Decisions:**
- React Context + useReducer for centralized agent state management
- Full state resync on WebSocket reconnection for guaranteed consistency
- Timestamp-based last-write-wins conflict resolution
- Support for 10 concurrent agents maximum
- Current state only (defer historical metrics to future sprint)

## Technical Context

**Language/Version**: TypeScript 5.3+ (frontend), Python 3.11+ (backend - existing)
**Primary Dependencies**:
- Frontend: React 18.2, Next.js 14.1, SWR 2.2.4, Tailwind CSS 3.4
- Testing: Jest 30.2, React Testing Library 16.3, MSW 2.11.5
- Existing: AgentCard component (Phase 5.1), WebSocket client (cf-45)

**Storage**: N/A (state management only - backend SQLite already exists)
**Testing**: Jest with React Testing Library, integration tests with MSW for WebSocket mocking
**Target Platform**: Web (Next.js React app running in browser)
**Project Type**: Web application (frontend enhancement only)

**Performance Goals**:
- State update latency < 50ms for agent status changes
- WebSocket message processing < 100ms
- Full resync after reconnect < 2 seconds
- Support 10 concurrent agents without UI lag

**Constraints**:
- Must integrate with existing AgentCard component without breaking changes
- Must use existing WebSocket client (lib/websocket.ts)
- Must maintain backward compatibility with Dashboard layout
- Must continue using SWR for initial data fetching
- Activity feed capped at 50 items (sliding window)

**Scale/Scope**:
- 10 concurrent agents maximum
- 13+ WebSocket message types to handle
- ~100 tasks per Sprint 4 spec assumption
- 50 activity items in feed

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: No project constitution found. Proceeding with standard best practices:
- ✅ Test-First Development: Unit tests for reducer, integration tests for WebSocket
- ✅ Type Safety: TypeScript strict mode enabled
- ✅ Performance: React.memo, useMemo for optimization
- ✅ Error Handling: Error boundaries for state management failures
- ✅ Observability: Console logging in dev mode for state transitions

## Project Structure

### Documentation (this feature)

```
specs/005-project-schema-refactoring/
├── spec.md              # Feature specification with clarifications
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (generated below)
├── data-model.md        # Phase 1 output (generated below)
├── quickstart.md        # Phase 1 output (generated below)
├── contracts/           # Phase 1 output (generated below)
│   └── agent-state-api.ts  # TypeScript interfaces for state management
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
web-ui/
├── src/
│   ├── components/
│   │   ├── AgentCard.tsx               # Existing (Phase 5.1)
│   │   ├── Dashboard.tsx               # Existing - will be refactored
│   │   └── AgentStateProvider.tsx      # NEW - Context provider
│   ├── hooks/
│   │   ├── useAgentState.ts            # NEW - Context consumer hook
│   │   └── useAgentStateReducer.ts     # NEW - Reducer logic
│   ├── lib/
│   │   ├── websocket.ts                # Existing (cf-45)
│   │   └── agentStateSync.ts           # NEW - Resync logic
│   ├── types/
│   │   ├── index.ts                    # Existing types
│   │   └── agentState.ts               # NEW - State management types
│   └── reducers/
│       └── agentReducer.ts             # NEW - Agent state reducer
└── tests/
    ├── components/
    │   ├── AgentCard.test.tsx          # Existing
    │   ├── Dashboard.test.tsx          # Existing - update
    │   └── AgentStateProvider.test.tsx # NEW
    ├── hooks/
    │   └── useAgentState.test.ts       # NEW
    ├── reducers/
    │   └── agentReducer.test.ts        # NEW - critical unit tests
    └── integration/
        ├── websocket-state-sync.test.ts    # NEW
        └── multi-agent-updates.test.ts     # NEW
```

**Structure Decision**: Web application structure with frontend-only changes. All new code in `web-ui/src/` directory. Backend (Python/FastAPI) unchanged - already provides WebSocket messages with timestamps. Focus on React state management layer between WebSocket client and UI components.

## Complexity Tracking

*No constitution violations - proceeding with standard React patterns.*

| Aspect | Justification |
|--------|---------------|
| Context + Reducer | Standard React pattern for complex state - simpler than Redux, more maintainable than local state |
| Timestamp conflict resolution | Required for multi-agent coordination - prevents race conditions from simultaneous updates |
| Full resync on reconnect | Simplest reliable approach - eliminates complexity of incremental catch-up |

## Phase 0: Research & Investigation

### Research Tasks

1. **React Context + useReducer Best Practices for Real-Time State**
   - Decision: Use Context at Dashboard level (not app-wide) to scope state
   - Rationale: Limits re-renders to Dashboard subtree, easier to test
   - Alternatives considered: App-wide Context (too broad), Component state (current - too fragmented)

2. **WebSocket Reconnection Patterns in React**
   - Decision: Implement reconnection detector with exponential backoff in WebSocket client
   - Rationale: Prevents thundering herd on reconnect, integrates with existing client
   - Alternatives considered: Polling during disconnect (wasteful), No backoff (can overload server)

3. **Timestamp-Based Conflict Resolution Strategies**
   - Decision: Compare backend-provided timestamps, reject updates older than current state
   - Rationale: Backend timestamps are authoritative, no clock skew issues
   - Alternatives considered: Sequence numbers (requires backend change), Vector clocks (overkill)

4. **React Performance Optimization for Frequent Updates**
   - Decision: Use React.memo on AgentCard, useMemo for derived state, useCallback for handlers
   - Rationale: Prevents unnecessary re-renders when non-related agents update
   - Alternatives considered: Virtualization (not needed for 10 items), Debouncing (loses real-time feel)

5. **State Resync Implementation Patterns**
   - Decision: Parallel API fetches with Promise.all(), replace entire state atomically
   - Rationale: Fastest resync, guarantees consistency
   - Alternatives considered: Sequential fetches (slower), Incremental updates (complex)

### Technology Stack Decisions

| Technology | Decision | Rationale |
|------------|----------|-----------|
| State Management | React Context + useReducer | No external deps, perfect for coordinated updates, testable |
| WebSocket Library | Existing client (lib/websocket.ts) | Already implemented, just add reconnection hooks |
| Testing | Jest + RTL + MSW | Standard Next.js testing stack, MSW for WebSocket mocking |
| Type Safety | TypeScript strict mode | Catch state shape errors at compile time |
| Performance | React.memo + useMemo | Standard React optimization, sufficient for 10 agents |

### Integration Points

1. **Existing AgentCard Component**
   - No changes to component interface
   - Pass agent data from Context instead of props
   - Maintains backward compatibility

2. **Existing WebSocket Client**
   - Add reconnection event handlers
   - Keep existing message subscription API
   - Add timestamp extraction utilities

3. **Existing Dashboard Layout**
   - Wrap with AgentStateProvider
   - Replace useState hooks with useAgentState hook
   - Keep all UI structure unchanged

## Phase 1: Design & Contracts

### Data Model

See [data-model.md](./data-model.md) for complete entity definitions.

**Key Entities:**
- `AgentState` - Root state container
- `Agent` - Individual agent data with timestamp
- `Task` - Task data with assignment info
- `ActivityItem` - Activity feed entries
- `AgentAction` - Discriminated union of all reducer actions

### API Contracts

See [contracts/agent-state-api.ts](./contracts/agent-state-api.ts) for TypeScript interfaces.

**Key Contracts:**
- AgentStateContext interface
- AgentAction types (9+ action types)
- WebSocket message to action mappers
- Resync API endpoints

### Quick Start Guide

See [quickstart.md](./quickstart.md) for developer onboarding.

**Key Topics:**
- How to consume agent state in components
- How to add new WebSocket message handlers
- How to test reducer logic
- How to debug state transitions

## Implementation Phases

### Phase 0: Foundation ✅
- Research completed above
- Decisions documented
- Integration points identified

### Phase 1: Design ✅
- Data model defined (data-model.md)
- Contracts specified (contracts/)
- Quick start guide created (quickstart.md)

### Phase 2: Task Breakdown
- Execute via `/speckit.tasks` command
- Generate dependency-ordered tasks
- Includes test-first approach for each component

## Risk Mitigation

### Technical Risks

1. **Complex Reducer Logic (Medium)**
   - Risk: 9+ action types could have bugs in state transitions
   - Mitigation: Comprehensive unit tests (85%+ coverage), immutability enforcement, TypeScript
   - Contingency: Simplify to fewer action types if bugs persist

2. **WebSocket Reconnection Race Conditions (Medium)**
   - Risk: Multiple rapid disconnects/reconnects could cause state corruption
   - Mitigation: Debounce reconnection logic, cancel in-flight resyncs
   - Contingency: Add sequence IDs to resync requests

3. **Performance with 10 Agents (Low)**
   - Risk: Frequent re-renders could cause UI lag
   - Mitigation: React.memo, useMemo, profiling before release
   - Contingency: Implement virtualization or throttle updates if needed

### Integration Risks

1. **Breaking AgentCard Component (Low)**
   - Risk: Changes to Agent interface could break existing component
   - Mitigation: Maintain exact interface, add new fields as optional
   - Contingency: Version AgentCard if breaking changes unavoidable

2. **WebSocket Client Changes (Low)**
   - Risk: Existing message handlers could conflict with new Context approach
   - Mitigation: Incremental migration, run old and new side-by-side during transition
   - Contingency: Feature flag to disable Context-based state if issues arise

## Success Criteria

### Must Have (P0)
- ✅ React Context + Reducer implemented and tested
- ✅ All 13+ WebSocket message types handled
- ✅ Full state resync on reconnection working
- ✅ Timestamp conflict resolution preventing race conditions
- ✅ Support for 10 concurrent agents verified
- ✅ Test coverage ≥ 85% for new code
- ✅ Zero regressions in existing Dashboard tests

### Should Have (P1)
- Performance metrics logged in dev mode
- Error boundaries catching state failures
- Detailed state transition logging
- Developer documentation in quickstart.md

### Nice to Have (P2)
- Redux DevTools integration for time-travel debugging
- State persistence in sessionStorage
- Automated performance benchmarks

## Next Steps

1. Review this plan with team
2. Execute `/speckit.tasks` to generate task breakdown
3. Begin implementation following test-first approach
4. Monitor performance with React Profiler during development
