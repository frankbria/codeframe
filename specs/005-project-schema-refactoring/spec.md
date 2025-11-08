# Phase 5.2: Dashboard Multi-Agent State Management

## Overview

**Goal**: Enhance Dashboard with robust multi-agent state management and comprehensive WebSocket handling for all agent lifecycle events.

**User Story**: As a developer watching the Dashboard, I want to see real-time updates for multiple agents working in parallel, with consistent state even during network interruptions, so I can monitor the multi-agent coordination system reliably.

## Clarifications

### Session 2025-11-06

- Q: What state management architecture should we use for handling multiple concurrent agent updates in the Dashboard? → A: React Context + Reducer
- Q: How should the Dashboard handle WebSocket reconnection and state synchronization after network interruptions? → A: Full state resync on reconnect
- Q: What should be the maximum number of concurrent agents the Dashboard must support without performance degradation? → A: 10 agents
- Q: How should the Dashboard handle conflicting simultaneous updates (e.g., agent status changes while task assignment is in flight)? → A: Timestamp-based last-write-wins
- Q: Should the agent state include historical metrics (e.g., average task completion time, success rate) or only current state? → A: Current state only, defer metrics

## Functional Requirements

### Core Features

1. **Centralized State Management**
   - Implement React Context + useReducer pattern for agent state
   - Single source of truth for all agent data in Dashboard
   - Predictable state transitions using reducer actions
   - Support for up to 10 concurrent agents without performance degradation

2. **Multi-Agent State Coordination**
   - Track state for all agent types: Lead, Backend Worker, Frontend Worker, Test Worker
   - Handle simultaneous updates from multiple agents
   - Resolve conflicts using timestamp-based last-write-wins strategy
   - Maintain consistency across all Dashboard components

3. **WebSocket Integration Enhancement**
   - Process all agent lifecycle events: `agent_created`, `agent_retired`, `agent_status_changed`
   - Handle task assignment events: `task_assigned`, `task_blocked`, `task_unblocked`
   - Support activity updates: `activity_update`, `test_result`, `commit_created`, `correction_attempt`
   - Implement full state resync on WebSocket reconnection

4. **Network Resilience**
   - Detect WebSocket disconnections
   - Show connection status indicator to user
   - Automatically re-fetch all agent states on reconnection
   - Guarantee data consistency after network interruptions

5. **Agent State Display**
   - Current agent status (idle, busy, blocked)
   - Current task assignment (if any)
   - Blocker information (if blocked)
   - Agent type and identifier
   - **Defer historical metrics** (tasks completed, completion time, success rate) to future sprint

### State Management Architecture

**Context Structure:**
```typescript
interface AgentState {
  agents: Agent[];
  tasks: Task[];
  activity: ActivityItem[];
  projectProgress: ProjectProgress | null;
  wsConnected: boolean;
  lastSyncTimestamp: number;
}

type AgentAction =
  | { type: 'AGENTS_LOADED'; payload: Agent[] }
  | { type: 'AGENT_CREATED'; payload: Agent }
  | { type: 'AGENT_UPDATED'; payload: { agentId: string; updates: Partial<Agent>; timestamp: number } }
  | { type: 'AGENT_RETIRED'; payload: { agentId: string; timestamp: number } }
  | { type: 'TASK_ASSIGNED'; payload: { taskId: number; agentId: string; timestamp: number } }
  | { type: 'TASK_STATUS_CHANGED'; payload: { taskId: number; status: TaskStatus; timestamp: number } }
  | { type: 'ACTIVITY_ADDED'; payload: ActivityItem }
  | { type: 'WS_CONNECTED'; payload: boolean }
  | { type: 'FULL_RESYNC'; payload: { agents: Agent[]; tasks: Task[]; activity: ActivityItem[]; timestamp: number } };
```

**Reducer Logic:**
- All updates include timestamps from backend
- Compare timestamps when applying updates (last-write-wins)
- Limit activity feed to 50 most recent items
- Validate agent count ≤ 10 (warn if exceeded)

### WebSocket Message Handling

**Enhanced Message Types:**
1. `agent_created` - Add new agent to state with idle status
2. `agent_retired` - Remove agent from state, add to activity feed
3. `agent_status_changed` - Update agent status (idle/working/blocked) with timestamp check
4. `task_assigned` - Update both task and agent state atomically
5. `task_blocked` / `task_unblocked` - Update task dependencies
6. `activity_update`, `test_result`, `commit_created`, `correction_attempt` - Add to activity feed
7. `progress_update` - Update project-level progress metrics

**Reconnection Flow:**
1. Detect WebSocket disconnect (update wsConnected: false)
2. Show "Reconnecting..." indicator in UI
3. On reconnect, trigger FULL_RESYNC action
4. Fetch fresh data: `/projects/{id}/agents`, `/projects/{id}/tasks`, `/projects/{id}/activity`
5. Replace all state with fresh data (timestamp = reconnect time)
6. Update wsConnected: true, hide reconnecting indicator

## Non-Functional Requirements

### Performance Targets
- Support 10 concurrent agents without UI lag
- State update latency < 50ms for agent status changes
- WebSocket message processing < 100ms
- Full resync after reconnect < 2 seconds
- Activity feed rendering optimized (virtualization not required for 50 items)

### Reliability
- Zero data loss during normal operations
- Guaranteed consistency after reconnection
- Graceful handling of out-of-order messages via timestamps
- No memory leaks from WebSocket subscriptions

### Scalability Constraints
- Maximum 10 agents (warn if backend exceeds)
- Activity feed capped at 50 items (sliding window)
- Task list size: no hard limit (assume < 100 tasks per Sprint 4 spec)

### Observability
- Log all state transitions in development mode
- Track WebSocket reconnection events
- Console warnings for conflicts resolved via timestamp
- Error boundary for state management failures

## Edge Cases & Failure Handling

### Conflict Resolution
- **Simultaneous agent updates**: Use timestamp from backend, apply most recent
- **Out-of-order messages**: Reject updates older than current state timestamp
- **Missing agent on update**: Log warning, skip update (agent may have been retired)

### Network Failures
- **Brief disconnect (< 5s)**: Show reconnecting indicator, auto-resync on reconnect
- **Long disconnect (> 5s)**: Show warning, full resync on reconnect
- **Repeated disconnects**: Continue retrying, maintain local state for display

### Backend Inconsistencies
- **Agent count > 10**: Display all agents but log warning
- **Invalid agent status**: Fallback to 'idle', log error
- **Missing required fields**: Use sensible defaults, log validation error

### UI Edge Cases
- **No agents yet**: Show empty state with explanation
- **All agents idle**: Show "Ready for work" state
- **All agents blocked**: Highlight as potential deadlock, suggest checking dependencies

## Technical Constraints

### Existing System Integration
- Must integrate with existing AgentCard component (Phase 5.1)
- Must use existing WebSocket client (`lib/websocket.ts`)
- Must maintain backward compatibility with existing Dashboard layout
- Must continue using SWR for initial data fetching

### Technology Stack
- React 18+ with Context API
- TypeScript for type safety
- SWR for initial data fetching
- WebSocket for real-time updates
- Tailwind CSS for styling (no changes to AgentCard styles)

### Data Model
- Reuse existing Agent type from Phase 5.1
- Extend with timestamp fields for conflict resolution
- No database schema changes required (backend already sends timestamps)

## Success Metrics

### Definition of Done
- ✅ React Context + Reducer implemented for agent state
- ✅ All 13+ WebSocket message types handled correctly
- ✅ Full state resync on reconnection working
- ✅ Timestamp-based conflict resolution implemented
- ✅ Support for 10 concurrent agents verified
- ✅ Connection status indicator visible
- ✅ AgentCard components receive state from Context
- ✅ No console errors during normal operation
- ✅ No memory leaks from WebSocket subscriptions

### Test Coverage
- Unit tests for reducer logic (all action types)
- Unit tests for timestamp conflict resolution
- Integration tests for WebSocket message handling
- Integration tests for reconnection flow
- Component tests for Context provider
- E2E test for multi-agent scenario (3+ agents updating simultaneously)

### Quality Targets
- Test coverage ≥ 85% for new state management code
- Zero regressions in existing Dashboard functionality
- All existing Phase 5.1 tests continue passing
- Performance: setState calls < 10ms (React profiler)

## Out of Scope

- Historical metrics (tasks completed, avg completion time, success rate) - deferred to future sprint
- Agent detail modal/expanded view - deferred
- Custom state persistence (localStorage) - not required
- Optimistic UI updates before backend confirmation - not required (rely on WebSocket)
- WebSocket message compression or batching - backend responsibility
- Advanced visualization (charts, graphs) - deferred

## Implementation Notes

### Migration Strategy
1. Create Context and Reducer (no UI changes yet)
2. Wrap Dashboard with Context Provider
3. Migrate useState hooks to useContext one at a time
4. Refactor WebSocket handlers to dispatch reducer actions
5. Add reconnection logic with full resync
6. Add timestamp checks for conflict resolution
7. Test with multiple concurrent agent updates

### Testing Strategy
- Mock WebSocket client for unit tests
- Use React Testing Library for component tests
- Simulate network disconnections in integration tests
- Test with 10 agents to verify performance target
- Verify timestamp conflict resolution with synthetic out-of-order messages

## References

- Phase 5.1: Agent Status UI Component (cf-8ip) - AgentCard component
- Sprint 4 Spec: Multi-Agent Coordination (004-multi-agent-coordination/spec.md)
- WebSocket Infrastructure (cf-45) - Real-time Dashboard Updates
- Existing Dashboard.tsx (lines 66-399) - Current WebSocket message handling

## Risks

### Medium Risk
- **Complex state transitions**: Reducer logic with 9+ action types could have bugs
  - Mitigation: Comprehensive unit tests, immutability enforcement, TypeScript strict mode

- **WebSocket reconnection race conditions**: Multiple rapid disconnects/reconnects
  - Mitigation: Debounce reconnection logic, cancel in-flight resyncs

### Low Risk
- **Performance with 10 agents**: Frequent re-renders could cause lag
  - Mitigation: React.memo on AgentCard, useMemo for derived state, profiling

- **Timestamp clock skew**: Backend and client clocks differ
  - Mitigation: Use backend-provided timestamps only, never client Date.now()
