# Research: Phase 5.2 - Dashboard Multi-Agent State Management

**Date**: 2025-11-06
**Feature**: Dashboard Multi-Agent State Management
**Branch**: 005-project-schema-refactoring

## Overview

This document consolidates research findings for implementing centralized state management in the Dashboard to handle multiple concurrent agents with real-time WebSocket updates.

## Research Topics

### 1. React Context + useReducer Best Practices for Real-Time State

**Context**: Need to manage state for up to 10 concurrent agents with frequent updates from WebSocket messages.

**Decision**: Use React Context at Dashboard component level (not app-wide) with useReducer for state transitions.

**Rationale**:
- **Scope control**: Wrapping only Dashboard limits re-renders to that subtree, preventing unnecessary updates in other parts of the app
- **Predictable updates**: Reducer pattern provides single source of truth for all state transitions
- **Testability**: Pure reducer functions are easy to unit test in isolation
- **No external dependencies**: Built into React, no bundle size increase
- **TypeScript support**: Strong typing for actions and state shape

**Alternatives Considered**:
1. **App-wide Context** - Rejected: Too broad scope, would cause re-renders in unrelated components
2. **Component local state (current)** - Rejected: Fragmented state across multiple useState hooks, hard to coordinate updates
3. **Redux Toolkit** - Rejected: Overkill for this scope, adds bundle size, requires learning curve
4. **Zustand** - Rejected: External dependency, Context+Reducer sufficient for this use case

**Implementation Notes**:
- Place Context Provider at Dashboard component level
- Use `useContext` hook for consuming state in child components
- Implement immer or native immutable updates in reducer
- Add TypeScript discriminated unions for action types

**References**:
- React Docs: Context API best practices
- Kent C. Dodds: Application State Management with React
- Pattern: Co-locating state with components that need it

---

### 2. WebSocket Reconnection Patterns in React

**Context**: WebSocket connections can drop due to network issues. Need automatic reconnection with state resynchronization.

**Decision**: Implement reconnection detector with exponential backoff in existing WebSocket client, trigger full state resync on reconnect.

**Rationale**:
- **Prevents thundering herd**: Exponential backoff (1s, 2s, 4s, 8s, max 30s) prevents all clients reconnecting simultaneously
- **Integrates cleanly**: Existing WebSocket client (lib/websocket.ts) can be enhanced with reconnection hooks
- **Guaranteed consistency**: Full resync after reconnect ensures no missed updates
- **User awareness**: Connection status indicator shows reconnecting state

**Alternatives Considered**:
1. **Polling during disconnect** - Rejected: Wasteful, defeats purpose of WebSocket, higher server load
2. **No backoff** - Rejected: Can overwhelm server during mass disconnections
3. **Incremental catch-up** - Rejected: Complex, requires backend support for querying missed messages

**Implementation Notes**:
```typescript
class WebSocketClient {
  private reconnectAttempts = 0;
  private maxReconnectDelay = 30000; // 30s

  private getReconnectDelay(): number {
    return Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay);
  }

  private async reconnect() {
    const delay = this.getReconnectDelay();
    await new Promise(resolve => setTimeout(resolve, delay));
    this.reconnectAttempts++;
    // ... connection logic
  }

  onReconnect(callback: () => void) {
    // Trigger full state resync
    this.reconnectHandlers.push(callback);
  }
}
```

**References**:
- WebSocket Reconnection Best Practices (MDN)
- Exponential Backoff Algorithm
- Existing cf-45 WebSocket Infrastructure

---

### 3. Timestamp-Based Conflict Resolution Strategies

**Context**: Multiple agents can update simultaneously. Updates may arrive out of order. Need deterministic conflict resolution.

**Decision**: Use backend-provided timestamps with last-write-wins strategy. Reject updates older than current state timestamp.

**Rationale**:
- **Backend is authoritative**: Backend timestamps eliminate client clock skew issues
- **Deterministic**: Same timestamp ordering produces same result every time
- **Simple to implement**: Single comparison per update
- **Handles out-of-order**: Late-arriving old updates are correctly rejected
- **No coordination needed**: Each client independently reaches same conclusion

**Alternatives Considered**:
1. **Sequence numbers** - Rejected: Requires backend changes to track per-agent sequences
2. **Vector clocks** - Rejected: Overkill for this use case, complex to implement and debug
3. **Client timestamps** - Rejected: Clock skew between clients causes inconsistencies
4. **Always accept backend** - Rejected: Doesn't handle out-of-order delivery

**Implementation Notes**:
```typescript
interface AgentWithTimestamp {
  id: string;
  status: AgentStatus;
  timestamp: number; // Unix milliseconds from backend
  // ... other fields
}

function agentReducer(state: AgentState, action: AgentAction): AgentState {
  switch (action.type) {
    case 'AGENT_UPDATED':
      const existing = state.agents.find(a => a.id === action.payload.agentId);
      if (existing && existing.timestamp > action.payload.timestamp) {
        console.warn(`Rejected stale update for agent ${action.payload.agentId}`);
        return state; // Reject older update
      }
      // Apply update
      return {
        ...state,
        agents: state.agents.map(a =>
          a.id === action.payload.agentId
            ? { ...a, ...action.payload.updates, timestamp: action.payload.timestamp }
            : a
        ),
      };
  }
}
```

**References**:
- Lamport Timestamps (for background)
- Last-Write-Wins Conflict Resolution
- Backend WebSocket Message Format (already includes timestamps)

---

### 4. React Performance Optimization for Frequent Updates

**Context**: With 10 agents and frequent WebSocket updates, need to prevent unnecessary re-renders.

**Decision**: Use React.memo on AgentCard, useMemo for derived state, useCallback for event handlers.

**Rationale**:
- **Targeted optimization**: Only optimize components that actually render frequently
- **React.memo on AgentCard**: Prevents re-render when other agents update (prop comparison)
- **useMemo for filtering**: Compute filtered/sorted agent lists only when array changes
- **useCallback for handlers**: Prevents new function instances on every render
- **Sufficient for 10 agents**: Virtualization not needed for this scale

**Alternatives Considered**:
1. **Virtualization (react-window)** - Rejected: Not needed for 10 items, adds complexity
2. **Debouncing updates** - Rejected: Loses real-time feel, complicates timestamp logic
3. **No optimization** - Rejected: Could cause lag with rapid updates
4. **Selective Context subscriptions** - Rejected: Complex, Context API doesn't support out of box

**Implementation Notes**:
```typescript
// AgentCard with memo
export const AgentCard = React.memo<AgentCardProps>(({ agent, onAgentClick }) => {
  // Component implementation
}, (prevProps, nextProps) => {
  // Custom comparison: only re-render if this agent changed
  return prevProps.agent.id === nextProps.agent.id &&
         prevProps.agent.status === nextProps.agent.status &&
         prevProps.agent.timestamp === nextProps.agent.timestamp;
});

// Dashboard with useMemo
function Dashboard({ projectId }: DashboardProps) {
  const { agents } = useAgentState();

  // Compute active agents only when array changes
  const activeAgents = useMemo(
    () => agents.filter(a => a.status !== 'idle'),
    [agents]
  );

  // Stable callback reference
  const handleAgentClick = useCallback((agentId: string) => {
    console.log('Agent clicked:', agentId);
  }, []);

  return (
    <div>
      {activeAgents.map(agent => (
        <AgentCard key={agent.id} agent={agent} onAgentClick={handleAgentClick} />
      ))}
    </div>
  );
}
```

**Performance Targets**:
- State update latency < 50ms
- setState() execution < 10ms (React Profiler)
- No janky animations during updates (60fps)

**References**:
- React Performance Optimization Docs
- React.memo vs useMemo vs useCallback
- React Profiler for measuring performance

---

### 5. State Resync Implementation Patterns

**Context**: After WebSocket reconnection, need to fetch fresh data from backend to guarantee consistency.

**Decision**: Parallel API fetches with Promise.all(), replace entire state atomically with FULL_RESYNC action.

**Rationale**:
- **Fastest resync**: Parallel fetches minimize total wait time
- **Atomic replacement**: Single reducer action prevents intermediate inconsistent states
- **Guaranteed consistency**: Full replacement eliminates any stale data
- **Simple error handling**: If any fetch fails, retry entire resync

**Alternatives Considered**:
1. **Sequential fetches** - Rejected: Slower, no benefit for independent endpoints
2. **Incremental updates** - Rejected: Complex logic, could miss dependencies between updates
3. **Optimistic keep local state** - Rejected: Can show stale data if updates were missed

**Implementation Notes**:
```typescript
// lib/agentStateSync.ts
export async function fullStateResync(projectId: number): Promise<{
  agents: Agent[];
  tasks: Task[];
  activity: ActivityItem[];
  timestamp: number;
}> {
  const timestamp = Date.now();

  const [agentsRes, tasksRes, activityRes] = await Promise.all([
    agentsApi.list(projectId),
    projectsApi.getTasks(projectId),
    activityApi.list(projectId, 50),
  ]);

  return {
    agents: agentsRes.data.agents,
    tasks: tasksRes.data.tasks,
    activity: activityRes.data.activity,
    timestamp,
  };
}

// In WebSocket reconnection handler
ws.onReconnect(async () => {
  dispatch({ type: 'WS_CONNECTED', payload: false }); // Show reconnecting

  try {
    const freshData = await fullStateResync(projectId);
    dispatch({ type: 'FULL_RESYNC', payload: freshData });
    dispatch({ type: 'WS_CONNECTED', payload: true });
  } catch (error) {
    console.error('Resync failed:', error);
    // Retry or show error to user
  }
});
```

**Error Handling**:
- If resync fails, show error banner with retry button
- Don't clear existing state until new data successfully fetched
- Log resync timing to monitor performance

**Performance Target**: < 2 seconds for full resync (per spec)

**References**:
- Promise.all() for parallel async operations
- React state batching
- SWR revalidation patterns (for consistency with existing code)

---

## Technology Stack Summary

| Component | Technology | Justification |
|-----------|-----------|---------------|
| State Management | React Context + useReducer | Built-in, no deps, perfect for coordinated updates |
| WebSocket Client | Existing lib/websocket.ts | Already implemented, just enhance with reconnection |
| Testing Framework | Jest + React Testing Library | Standard Next.js testing stack |
| WebSocket Mocking | MSW (Mock Service Worker) | Can mock WebSocket connections for tests |
| Type Safety | TypeScript 5.3 strict mode | Catch errors at compile time |
| Performance Tools | React Profiler, useMemo, React.memo | Standard React optimization toolkit |
| Data Fetching | SWR (existing) | Continue using for initial loads, WebSocket for updates |

## Integration Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Dashboard Component                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │          AgentStateProvider (Context)             │  │
│  │  ┌─────────────────────────────────────────────┐ │  │
│  │  │   useReducer(agentReducer, initialState)    │ │  │
│  │  │   - agents: Agent[]                          │ │  │
│  │  │   - tasks: Task[]                            │ │  │
│  │  │   - activity: ActivityItem[]                 │ │  │
│  │  │   - wsConnected: boolean                     │ │  │
│  │  │   - lastSyncTimestamp: number                │ │  │
│  │  └─────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────┘  │
│                           │                              │
│          ┌────────────────┴────────────────┐            │
│          │                                  │            │
│  ┌───────▼────────┐              ┌─────────▼─────────┐  │
│  │  AgentCard     │              │  ActivityFeed     │  │
│  │  (React.memo)  │              │                   │  │
│  │  - useContext  │              │  - useContext     │  │
│  └────────────────┘              └───────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          │ WebSocket messages
                          ▼
┌─────────────────────────────────────────────────────────┐
│           WebSocket Client (lib/websocket.ts)            │
│  - onMessage() → dispatch(action)                        │
│  - onReconnect() → fullStateResync() → FULL_RESYNC       │
│  - Exponential backoff reconnection                      │
└─────────────────────────────────────────────────────────┘
                          │
                          │ API calls
                          ▼
┌─────────────────────────────────────────────────────────┐
│               Backend APIs (FastAPI)                     │
│  - GET /projects/{id}/agents                             │
│  - GET /projects/{id}/tasks                              │
│  - GET /projects/{id}/activity                           │
│  - WebSocket messages with timestamps                    │
└─────────────────────────────────────────────────────────┘
```

## Key Decisions Summary

1. **State Architecture**: React Context + useReducer (no Redux)
2. **Reconnection**: Exponential backoff + full resync
3. **Conflict Resolution**: Backend timestamps, last-write-wins
4. **Performance**: React.memo, useMemo, useCallback (no virtualization)
5. **Resync Strategy**: Parallel fetches with Promise.all()

## Next Steps

1. Create data-model.md with detailed type definitions
2. Create contracts/agent-state-api.ts with TypeScript interfaces
3. Create quickstart.md for developer onboarding
4. Update agent context (run update-agent-context.sh)
5. Generate tasks.md with `/speckit.tasks` command
