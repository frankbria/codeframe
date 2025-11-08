# Implementation Guide: Phase 5.2 - Dashboard Multi-Agent State Management

**Status**: Phase 1 Complete (4/150 tasks) - Ready for Phase 2
**Branch**: `005-project-schema-refactoring`
**Last Updated**: 2025-11-06
**Next AI Agent**: Start at Phase 2

---

## Quick Start for AI Agent

### What's Been Done ✅

**Phase 1: Setup & Type Definitions (COMPLETE)**
- ✅ All TypeScript types defined in `web-ui/src/types/agentState.ts`
- ✅ Timestamp utilities in `web-ui/src/lib/timestampUtils.ts`
- ✅ Test fixtures in `web-ui/__tests__/fixtures/agentState.ts`
- ✅ Directory structure created

**Files Created** (3 files, 700+ lines):
```
web-ui/src/types/agentState.ts         (330 lines - all types)
web-ui/src/lib/timestampUtils.ts       (80 lines - utilities)
web-ui/__tests__/fixtures/agentState.ts (290 lines - test data)
```

### What's Next 🎯

**Phase 2: Foundational - Reducer Implementation (31 tasks)**

**CRITICAL**: This phase BLOCKS all other phases. Must complete before proceeding.

**Start Here**:
1. Open `specs/005-project-schema-refactoring/tasks.md`
2. Find "Phase 2: Foundational - Reducer Implementation"
3. Begin with T005 (first test task)
4. Follow TDD workflow: Tests → Implementation → Validation

**Estimated Time**: 1.5-2 days

---

## Architecture Overview

### Technology Stack

**Frontend** (All changes in `web-ui/`):
- React 18.2 with TypeScript 5.3+
- Next.js 14.1
- State: React Context + useReducer (no Redux)
- Testing: Jest 30.2 + React Testing Library 16.3
- WebSocket: Existing client in `lib/websocket.ts`

**Backend** (No changes):
- Python/FastAPI - Already provides WebSocket messages with timestamps

### State Management Pattern

```
┌─────────────────────────────────────────────┐
│           Dashboard Component                │
│  ┌───────────────────────────────────────┐  │
│  │   AgentStateProvider (Context)        │  │
│  │   ├─ useReducer(agentReducer)         │  │
│  │   ├─ WebSocket subscription           │  │
│  │   └─ Reconnection logic               │  │
│  └───────────────────────────────────────┘  │
│                    │                         │
│         ┌──────────┴──────────┐             │
│         ▼                      ▼             │
│   AgentCard(s)          ActivityFeed        │
│   (use Context)         (use Context)       │
└─────────────────────────────────────────────┘
```

**Key Principles**:
1. **Single Source of Truth**: All state in one Context
2. **Immutability**: Never mutate state, always return new objects
3. **Timestamp Conflict Resolution**: Backend timestamps, last-write-wins
4. **Network Resilience**: Full state resync on reconnect
5. **Performance**: React.memo, useMemo, useCallback

---

## Project Structure

### Directories Created ✅

```
web-ui/
├── src/
│   ├── types/
│   │   └── agentState.ts                    ✅ DONE
│   ├── lib/
│   │   ├── timestampUtils.ts                ✅ DONE
│   │   ├── websocketMessageMapper.ts        TODO (Phase 4)
│   │   └── agentStateSync.ts                TODO (Phase 5)
│   ├── reducers/
│   │   └── agentReducer.ts                  TODO (Phase 2)
│   ├── contexts/
│   │   └── AgentStateContext.ts             TODO (Phase 3)
│   ├── components/
│   │   ├── AgentStateProvider.tsx           TODO (Phase 3)
│   │   ├── AgentCard.tsx                    EXISTS (Phase 5.1)
│   │   └── Dashboard.tsx                    EXISTS (will refactor Phase 6)
│   └── hooks/
│       └── useAgentState.ts                 TODO (Phase 3)
└── __tests__/
    ├── fixtures/
    │   └── agentState.ts                    ✅ DONE
    ├── reducers/
    │   └── agentReducer.test.ts             TODO (Phase 2)
    ├── components/
    │   └── AgentStateProvider.test.tsx      TODO (Phase 3)
    ├── hooks/
    │   └── useAgentState.test.ts            TODO (Phase 3)
    └── integration/
        ├── websocket-state-sync.test.ts     TODO (Phase 4)
        └── multi-agent-updates.test.ts      TODO (Phase 4)
```

---

## Phase-by-Phase Implementation Guide

### Phase 2: Foundational - Reducer Implementation (NEXT)

**Goal**: Implement core reducer with 12+ action types

**Why This Phase is Critical**:
- BLOCKS all other phases
- Provides the state management engine
- Must be 100% tested before proceeding

#### Step 1: Write Tests First (TDD)

**Tasks T005-T019** (15 test tasks, can run in parallel)

Create `web-ui/__tests__/reducers/agentReducer.test.ts`:

```typescript
import { agentReducer, getInitialState } from '@/reducers/agentReducer';
import { createMockAgent, createInitialAgentState } from '@/__tests__/fixtures/agentState';
import type { AgentUpdatedAction } from '@/types/agentState';

describe('agentReducer', () => {
  describe('AGENTS_LOADED', () => {
    it('should load initial agents', () => {
      const initialState = getInitialState();
      const agents = [createMockAgent()];

      const action = {
        type: 'AGENTS_LOADED' as const,
        payload: agents,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents).toEqual(agents);
      expect(newState).not.toBe(initialState); // Immutability check
    });
  });

  describe('AGENT_UPDATED', () => {
    it('should update agent with newer timestamp', () => {
      const initialState = createInitialAgentState({
        agents: [
          createMockAgent({
            id: 'agent-1',
            status: 'idle',
            timestamp: 1000,
          }),
        ],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'agent-1',
          updates: { status: 'working' },
          timestamp: 2000, // Newer
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents[0].status).toBe('working');
      expect(newState.agents[0].timestamp).toBe(2000);
    });

    it('should reject update with older timestamp', () => {
      const initialState = createInitialAgentState({
        agents: [
          createMockAgent({
            id: 'agent-1',
            status: 'working',
            timestamp: 3000, // Current is newer
          }),
        ],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'agent-1',
          updates: { status: 'idle' },
          timestamp: 2000, // Older - should be rejected
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents[0].status).toBe('working'); // Unchanged
      expect(newState.agents[0].timestamp).toBe(3000); // Unchanged
    });
  });

  // ... Add tests for all 12 action types
  // Pattern: Test normal case, edge cases, immutability
});
```

**Test Checklist** (T005-T019):
- [ ] T005: AGENTS_LOADED - loads initial agents
- [ ] T006: AGENT_CREATED - adds new agent
- [ ] T007: AGENT_UPDATED - updates with newer timestamp, rejects older
- [ ] T008: AGENT_RETIRED - removes agent
- [ ] T009: TASK_ASSIGNED - updates both task and agent atomically
- [ ] T010: TASK_STATUS_CHANGED - updates task status
- [ ] T011: TASK_BLOCKED - adds blocked_by array
- [ ] T012: TASK_UNBLOCKED - clears blocked_by
- [ ] T013: ACTIVITY_ADDED - adds to feed, maintains 50 item limit (FIFO)
- [ ] T014: PROGRESS_UPDATED - updates project progress
- [ ] T015: WS_CONNECTED - updates connection status
- [ ] T016: FULL_RESYNC - replaces entire state atomically
- [ ] T017: Timestamp conflict resolution - comprehensive test
- [ ] T018: Immutability - ensures no mutations
- [ ] T019: Agent limit warning - console.warn at 11 agents

**Run Tests** (they should FAIL):
```bash
cd web-ui
npm test agentReducer.test.ts
# Expected: All tests fail (reducer doesn't exist yet)
```

#### Step 2: Implement Reducer (T020-T034)

Create `web-ui/src/reducers/agentReducer.ts`:

```typescript
import type { AgentState, AgentAction } from '@/types/agentState';

/**
 * Get initial agent state
 */
export function getInitialState(): AgentState {
  return {
    agents: [],
    tasks: [],
    activity: [],
    projectProgress: null,
    wsConnected: false,
    lastSyncTimestamp: 0,
  };
}

/**
 * Agent state reducer
 *
 * Handles all state transitions with:
 * - Immutability (always return new objects)
 * - Timestamp-based conflict resolution
 * - Activity feed FIFO (50 item limit)
 * - Agent count validation (warn at 10+)
 */
export function agentReducer(
  state: AgentState,
  action: AgentAction
): AgentState {
  // Development logging
  if (process.env.NODE_ENV === 'development') {
    console.group(`Action: ${action.type}`);
    console.log('Previous State:', state);
    console.log('Action:', action);
  }

  let newState: AgentState;

  switch (action.type) {
    case 'AGENTS_LOADED':
      newState = {
        ...state,
        agents: action.payload,
      };
      break;

    case 'AGENT_CREATED':
      newState = {
        ...state,
        agents: [...state.agents, action.payload],
      };
      break;

    case 'AGENT_UPDATED': {
      const { agentId, updates, timestamp } = action.payload;
      const existingAgent = state.agents.find(a => a.id === agentId);

      // Timestamp conflict resolution: reject stale updates
      if (existingAgent && existingAgent.timestamp > timestamp) {
        if (process.env.NODE_ENV === 'development') {
          console.warn(`Rejected stale update for agent ${agentId}`);
        }
        newState = state; // No change
        break;
      }

      newState = {
        ...state,
        agents: state.agents.map(a =>
          a.id === agentId
            ? { ...a, ...updates, timestamp }
            : a
        ),
      };
      break;
    }

    case 'AGENT_RETIRED': {
      const { agentId, timestamp } = action.payload;
      newState = {
        ...state,
        agents: state.agents.filter(a => a.id !== agentId),
      };
      break;
    }

    case 'TASK_ASSIGNED': {
      const { taskId, agentId, taskTitle, timestamp } = action.payload;

      // Atomic update: both task and agent
      newState = {
        ...state,
        tasks: state.tasks.map(t =>
          t.id === taskId
            ? { ...t, status: 'in_progress' as const, agent_id: agentId, timestamp }
            : t
        ),
        agents: state.agents.map(a =>
          a.id === agentId
            ? {
                ...a,
                status: 'working' as const,
                current_task: { id: taskId, title: taskTitle || `Task #${taskId}` },
                timestamp,
              }
            : a
        ),
      };
      break;
    }

    case 'TASK_STATUS_CHANGED': {
      const { taskId, status, progress, timestamp } = action.payload;
      newState = {
        ...state,
        tasks: state.tasks.map(t =>
          t.id === taskId
            ? { ...t, status, progress, timestamp }
            : t
        ),
      };
      break;
    }

    case 'TASK_BLOCKED': {
      const { taskId, blockedBy, timestamp } = action.payload;
      newState = {
        ...state,
        tasks: state.tasks.map(t =>
          t.id === taskId
            ? { ...t, status: 'blocked' as const, blocked_by: blockedBy, timestamp }
            : t
        ),
      };
      break;
    }

    case 'TASK_UNBLOCKED': {
      const { taskId, timestamp } = action.payload;
      newState = {
        ...state,
        tasks: state.tasks.map(t =>
          t.id === taskId
            ? { ...t, status: 'pending' as const, blocked_by: undefined, timestamp }
            : t
        ),
      };
      break;
    }

    case 'ACTIVITY_ADDED': {
      // FIFO: Keep only 50 most recent items
      newState = {
        ...state,
        activity: [
          action.payload,
          ...state.activity.slice(0, 49), // Keep only 49 old items
        ],
      };
      break;
    }

    case 'PROGRESS_UPDATED':
      newState = {
        ...state,
        projectProgress: action.payload,
      };
      break;

    case 'WS_CONNECTED':
      newState = {
        ...state,
        wsConnected: action.payload,
      };
      break;

    case 'FULL_RESYNC': {
      const { agents, tasks, activity, timestamp } = action.payload;
      // Atomic replacement of entire state
      newState = {
        agents,
        tasks,
        activity,
        projectProgress: state.projectProgress, // Preserve if not in payload
        wsConnected: true, // Resync implies reconnection
        lastSyncTimestamp: timestamp,
      };
      break;
    }

    default:
      newState = state;
  }

  // Validation warnings
  if (newState.agents.length > 10) {
    console.warn(`Agent count (${newState.agents.length}) exceeds maximum of 10`);
  }

  if (newState.activity.length > 50) {
    console.error('Activity feed exceeds 50 items - should have been trimmed');
  }

  if (process.env.NODE_ENV === 'development') {
    console.log('Next State:', newState);
    console.groupEnd();
  }

  return newState;
}
```

**Implementation Checklist** (T020-T034):
- [ ] T020: Create agentReducer.ts with initial state
- [ ] T021-T032: Implement all 12 action handlers
- [ ] T033: Add development mode logging
- [ ] T034: Add validation warnings
- [ ] T035: Run tests - should all PASS

**Run Tests** (should PASS):
```bash
npm test agentReducer.test.ts
# Expected: All tests pass (100%)
```

#### Step 3: Checkpoint Validation

Before proceeding to Phase 3, verify:

✅ **All 31 Phase 2 tasks complete**
✅ **All tests passing (100%)**
✅ **No console errors**
✅ **Reducer handles all 12 action types**
✅ **Timestamp conflict resolution working**
✅ **Immutability enforced (no mutations)**
✅ **Activity feed FIFO working**
✅ **Agent limit validation working**

**Mark Phase 2 Complete in tasks.md**:
```bash
# Update T005-T035 from [ ] to [X]
```

---

### Phase 3: Context & Hook Implementation (14 tasks)

**Goal**: Provide centralized state via React Context

**Dependencies**: Phase 2 must be complete

#### Key Files to Create:

1. **AgentStateContext.ts** (T042)
```typescript
import { createContext } from 'react';
import type { AgentState, AgentAction } from '@/types/agentState';

export interface AgentStateContextValue {
  state: AgentState;
  dispatch: React.Dispatch<AgentAction>;
}

export const AgentStateContext = createContext<AgentStateContextValue | null>(null);
```

2. **AgentStateProvider.tsx** (T043-T044)
```typescript
import React, { useReducer, useEffect } from 'react';
import { AgentStateContext } from '@/contexts/AgentStateContext';
import { agentReducer, getInitialState } from '@/reducers/agentReducer';
import { agentsApi, projectsApi, activityApi } from '@/lib/api';
import useSWR from 'swr';

interface AgentStateProviderProps {
  projectId: number;
  children: React.ReactNode;
}

export function AgentStateProvider({ projectId, children }: AgentStateProviderProps) {
  const [state, dispatch] = useReducer(agentReducer, getInitialState());

  // Initial data fetch with SWR
  const { data: agentsData } = useSWR(
    `/projects/${projectId}/agents`,
    () => agentsApi.list(projectId).then(res => res.data.agents)
  );

  // Load initial agents
  useEffect(() => {
    if (agentsData) {
      dispatch({ type: 'AGENTS_LOADED', payload: agentsData });
    }
  }, [agentsData]);

  return (
    <AgentStateContext.Provider value={{ state, dispatch }}>
      {children}
    </AgentStateContext.Provider>
  );
}
```

3. **useAgentState.ts** (T045-T048)
```typescript
import { useContext, useMemo, useCallback } from 'react';
import { AgentStateContext } from '@/contexts/AgentStateContext';
import type { Agent, Task, ActivityItem, ProjectProgress } from '@/types/agentState';

export function useAgentState() {
  const context = useContext(AgentStateContext);

  if (!context) {
    throw new Error('useAgentState must be used within AgentStateProvider');
  }

  const { state, dispatch } = context;

  // Derived state (memoized)
  const activeAgents = useMemo(
    () => state.agents.filter(a => a.status === 'working' || a.status === 'blocked'),
    [state.agents]
  );

  const idleAgents = useMemo(
    () => state.agents.filter(a => a.status === 'idle'),
    [state.agents]
  );

  // Action wrappers
  const updateAgent = useCallback((agentId: string, updates: Partial<Agent>, timestamp: number) => {
    dispatch({ type: 'AGENT_UPDATED', payload: { agentId, updates, timestamp } });
  }, [dispatch]);

  // ... more action wrappers

  return {
    // State
    agents: state.agents,
    tasks: state.tasks,
    activity: state.activity,
    projectProgress: state.projectProgress,
    wsConnected: state.wsConnected,

    // Derived
    activeAgents,
    idleAgents,

    // Actions
    updateAgent,
    // ... more actions
  };
}
```

**Tests**: T036-T041 (write first, then implement)

---

### Phase 4: WebSocket Integration (28 tasks)

**Goal**: Map WebSocket messages to reducer actions

**Key File**: `lib/websocketMessageMapper.ts`

**Pattern**:
```typescript
export function mapWebSocketMessageToAction(message: WebSocketMessage): AgentAction | null {
  const timestamp = parseTimestamp(message.timestamp);

  switch (message.type) {
    case 'agent_created':
      return {
        type: 'AGENT_CREATED',
        payload: {
          id: message.agent_id,
          type: message.agent_type,
          status: 'idle',
          // ... other fields
          timestamp,
        },
      };

    case 'agent_status_changed':
      return {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: message.agent_id,
          updates: { status: message.status },
          timestamp,
        },
      };

    // ... 13+ message types
  }
}
```

**Integration in AgentStateProvider**:
```typescript
useEffect(() => {
  const ws = getWebSocketClient();
  ws.connect();
  ws.subscribe(projectId);

  const unsubscribe = ws.onMessage((message) => {
    if (message.project_id !== projectId) return;

    const action = mapWebSocketMessageToAction(message);
    if (action) {
      dispatch(action);
    }
  });

  return () => {
    unsubscribe();
    ws.disconnect();
  };
}, [projectId, dispatch]);
```

---

### Phase 5: Reconnection & Resync (18 tasks)

**Goal**: Handle WebSocket disconnections with full state resync

**Key File**: `lib/agentStateSync.ts`

```typescript
export async function fullStateResync(projectId: number) {
  const timestamp = Date.now();

  // Parallel fetches
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
```

**Integration**:
```typescript
useEffect(() => {
  const ws = getWebSocketClient();

  const handleReconnect = async () => {
    dispatch({ type: 'WS_CONNECTED', payload: false });

    try {
      const freshData = await fullStateResync(projectId);
      dispatch({ type: 'FULL_RESYNC', payload: freshData });
      dispatch({ type: 'WS_CONNECTED', payload: true });
    } catch (error) {
      console.error('Resync failed:', error);
    }
  };

  ws.onReconnect(handleReconnect);

  return () => ws.offReconnect(handleReconnect);
}, [projectId, dispatch]);
```

---

### Phase 6: Dashboard Integration (19 tasks)

**Goal**: Migrate Dashboard from local state to Context

**Changes to Dashboard.tsx**:
```typescript
// Before: Local state
const [agents, setAgents] = useState<Agent[]>([]);

// After: Context
const { agents, wsConnected } = useAgentState();

// Wrap Dashboard with Provider in parent
<AgentStateProvider projectId={projectId}>
  <Dashboard projectId={projectId} />
</AgentStateProvider>
```

**Performance Optimizations**:
```typescript
// Memo AgentCard
export const AgentCard = React.memo<AgentCardProps>(
  ({ agent }) => { /* ... */ },
  (prev, next) => prev.agent.timestamp === next.agent.timestamp
);

// Memoized filters
const activeAgents = useMemo(
  () => agents.filter(a => a.status === 'working'),
  [agents]
);
```

---

### Phase 7: Performance & Validation (18 tasks)

**Goal**: Meet performance targets and add validation

**Performance Targets**:
- State update latency: < 50ms
- WebSocket message processing: < 100ms
- Full resync: < 2 seconds
- Support 10 concurrent agents

**Tools**:
```typescript
// React Profiler
<Profiler id="Dashboard" onRender={(id, phase, actualDuration) => {
  if (actualDuration > 50) {
    console.warn(`Slow render: ${id} took ${actualDuration}ms`);
  }
}}>
  <Dashboard />
</Profiler>
```

**Validation Functions**:
```typescript
// lib/validation.ts
export function validateAgentCount(agents: Agent[]): void {
  if (agents.length > 10) {
    console.warn(`Agent count exceeds 10: ${agents.length}`);
  }
}
```

---

### Phase 8: Polish & QA (18 tasks)

**Goal**: Production readiness

**Tasks**:
- ErrorBoundary for state failures
- JSDoc comments
- Code cleanup
- Full test suite (85%+ coverage)
- Manual QA with real backend
- Type checking
- Linting
- Performance metrics documentation

---

## Testing Strategy

### Test Coverage Target: ≥85%

**Test Organization**:
```
__tests__/
├── unit/
│   ├── reducers/           # Pure function tests
│   ├── lib/                # Utility function tests
│   └── hooks/              # Custom hook tests
├── integration/
│   ├── websocket-*.test.ts # WebSocket flow tests
│   └── state-sync.test.ts  # Resync tests
└── performance/
    ├── state-update-*.test.ts
    └── ten-agents-load.test.ts
```

### TDD Workflow

**For Every Feature**:
1. ✍️ Write test (should FAIL)
2. 💻 Implement feature
3. ✅ Run test (should PASS)
4. ♻️ Refactor if needed
5. 📝 Mark task complete

### Running Tests

```bash
# All tests
npm test

# Specific file
npm test agentReducer.test.ts

# Watch mode
npm test -- --watch

# Coverage
npm test -- --coverage
```

---

## Common Patterns

### Pattern 1: Immutable State Updates

```typescript
// ✅ Good - creates new array
agents: state.agents.map(a => a.id === id ? { ...a, status: 'idle' } : a)

// ❌ Bad - mutates existing
state.agents.forEach(a => a.status = 'idle')
```

### Pattern 2: Timestamp Conflict Resolution

```typescript
// Always check timestamp before applying update
if (existingAgent && existingAgent.timestamp > timestamp) {
  console.warn('Rejected stale update');
  return state; // No change
}
```

### Pattern 3: Activity Feed FIFO

```typescript
// Keep only 50 most recent
activity: [newItem, ...state.activity.slice(0, 49)]
```

### Pattern 4: Atomic Multi-Entity Updates

```typescript
// Update both task and agent in single action
case 'TASK_ASSIGNED':
  return {
    ...state,
    tasks: updateTask(),    // Update 1
    agents: updateAgent(),  // Update 2
  };
```

---

## Debugging Tips

### Enable Development Logging

Reducer automatically logs all actions in dev mode:
```
Action: AGENT_UPDATED
Previous State: { agents: [...], ... }
Action: { type: 'AGENT_UPDATED', payload: {...} }
Next State: { agents: [...], ... }
```

### React DevTools

1. Install React DevTools extension
2. Inspect AgentStateProvider component
3. View state and hooks in real-time
4. Use Profiler to measure renders

### Common Issues

**Issue**: State not updating
- ✅ Check: Component wrapped in AgentStateProvider?
- ✅ Check: Using useAgentState() hook?
- ✅ Check: Dispatch being called?

**Issue**: Stale updates applied
- ✅ Check: Timestamps compared correctly?
- ✅ Check: Backend sending timestamps?

**Issue**: Performance lag
- ✅ Check: React.memo on components?
- ✅ Check: useMemo for derived state?
- ✅ Check: useCallback for handlers?

---

## File Locations Reference

### Source Files
```
web-ui/src/
├── types/agentState.ts                    ✅ DONE
├── lib/
│   ├── timestampUtils.ts                  ✅ DONE
│   ├── websocketMessageMapper.ts          TODO Phase 4
│   ├── agentStateSync.ts                  TODO Phase 5
│   └── validation.ts                      TODO Phase 7
├── reducers/agentReducer.ts               TODO Phase 2
├── contexts/AgentStateContext.ts          TODO Phase 3
├── components/
│   └── AgentStateProvider.tsx             TODO Phase 3
└── hooks/useAgentState.ts                 TODO Phase 3
```

### Test Files
```
web-ui/__tests__/
├── fixtures/agentState.ts                 ✅ DONE
├── reducers/agentReducer.test.ts          TODO Phase 2
├── components/AgentStateProvider.test.tsx TODO Phase 3
├── hooks/useAgentState.test.ts            TODO Phase 3
└── integration/
    ├── websocket-state-sync.test.ts       TODO Phase 4
    └── multi-agent-updates.test.ts        TODO Phase 4
```

---

## Handoff Checklist for Next AI Agent

### Before Starting Phase 2

✅ **Review Completed Work**:
- [ ] Read this guide completely
- [ ] Review `web-ui/src/types/agentState.ts`
- [ ] Review `web-ui/src/lib/timestampUtils.ts`
- [ ] Review `web-ui/__tests__/fixtures/agentState.ts`
- [ ] Understand TDD workflow

✅ **Verify Environment**:
- [ ] Branch: `005-project-schema-refactoring`
- [ ] Node.js and npm installed
- [ ] Can run `npm test` successfully
- [ ] TypeScript compiles without errors

✅ **Load Context**:
- [ ] Read `specs/005-project-schema-refactoring/spec.md`
- [ ] Read `specs/005-project-schema-refactoring/plan.md`
- [ ] Read `specs/005-project-schema-refactoring/tasks.md`
- [ ] Understand Phase 2 requirements (T005-T035)

### Starting Phase 2

**Step 1**: Open `specs/005-project-schema-refactoring/tasks.md`

**Step 2**: Find "Phase 2: Foundational - Reducer Implementation"

**Step 3**: Start with T005 (first test)

**Step 4**: Follow TDD workflow:
1. Write test (T005-T019 - all tests)
2. Run tests (should FAIL)
3. Implement reducer (T020-T034)
4. Run tests (should PASS)
5. Mark tasks complete in tasks.md

**Step 5**: Move to Phase 3

---

## Success Criteria

### Phase 2 Complete When:
✅ All 31 tasks marked [X] in tasks.md
✅ All tests passing (100%)
✅ No TypeScript errors
✅ No console errors
✅ Reducer handles all 12 action types correctly
✅ Timestamp conflict resolution working
✅ Immutability enforced
✅ Activity feed FIFO (50 items) working
✅ Agent count validation working

### Overall Feature Complete When:
✅ All 150 tasks marked [X] in tasks.md
✅ Test coverage ≥ 85%
✅ All performance targets met
✅ Zero regressions in Phase 5.1 tests
✅ Manual QA passed with real backend
✅ Dashboard using Context-based state
✅ WebSocket real-time updates working
✅ Reconnection with full resync working

---

## Resources

### Design Documents (All in `specs/005-project-schema-refactoring/`)
- `spec.md` - Feature specification with clarifications
- `plan.md` - Implementation plan with architecture
- `research.md` - Technical decisions and rationale
- `data-model.md` - Entity definitions and relationships
- `contracts/agent-state-api.ts` - TypeScript contracts
- `quickstart.md` - Developer quick start guide
- `tasks.md` - 150 tasks with dependencies

### Key Decisions
- State management: React Context + useReducer
- Conflict resolution: Timestamp-based last-write-wins
- Reconnection: Full state resync
- Max agents: 10 (warn if exceeded)
- Max activity: 50 items (FIFO)
- Test coverage: ≥85%

### Performance Targets
- State updates: < 50ms
- Message processing: < 100ms
- Full resync: < 2 seconds
- Support: 10 concurrent agents

---

## Questions? Issues?

### If Tests Are Failing
1. Check test output for specific error
2. Verify reducer implementation matches test expectations
3. Check immutability (use spread operators)
4. Verify timestamps being compared correctly

### If Performance Is Slow
1. Profile with React DevTools
2. Add React.memo to components
3. Add useMemo for derived state
4. Check for unnecessary re-renders

### If TypeScript Errors
1. Check all imports from `@/types/agentState`
2. Verify action payloads match type definitions
3. Run `npm run type-check`

### Need Help?
- Review quickstart.md in specs directory
- Check data-model.md for entity relationships
- Review plan.md for architecture decisions
- Refer to this guide's pattern examples

---

## Final Notes

**Current Status**: Phase 1 complete, Phase 2 ready to start

**Next Agent Should**: Begin Phase 2 with test writing (TDD approach)

**Estimated Time to Complete**: 5-6 days for full feature (all 150 tasks)

**Critical Success Factor**: Follow TDD workflow - tests first, then implementation

Good luck! The foundation is solid and ready for the next phase! 🚀
