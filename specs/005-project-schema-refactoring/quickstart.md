# Quick Start Guide: Agent State Management

**Feature**: Phase 5.2 - Dashboard Multi-Agent State Management
**Date**: 2025-11-06
**Audience**: Frontend developers working on the Dashboard

## Overview

This guide helps you understand and work with the centralized agent state management system built with React Context + useReducer.

## Architecture at a Glance

```
Dashboard Component
    └─ AgentStateProvider (Context)
        ├─ useReducer(agentReducer)
        ├─ WebSocket subscription
        └─ Children (AgentCard, ActivityFeed, etc.)
            └─ useAgentState() hook
```

**Key Concepts**:
- **Single Source of Truth**: All agent/task state in one Context
- **Predictable Updates**: All state changes via reducer actions
- **Conflict Resolution**: Timestamp-based last-write-wins
- **Network Resilience**: Full resync on WebSocket reconnection

---

## For Component Developers

### Consuming Agent State

Use the `useAgentState()` hook in any component within the Dashboard:

```typescript
import { useAgentState } from '@/hooks/useAgentState';

function MyComponent() {
  const { agents, activeAgents, wsConnected } = useAgentState();

  return (
    <div>
      <p>Connected: {wsConnected ? 'Yes' : 'No'}</p>
      <p>Active agents: {activeAgents.length}</p>
      {agents.map(agent => (
        <div key={agent.id}>{agent.id}: {agent.status}</div>
      ))}
    </div>
  );
}
```

**Available State**:
- `agents`: All agents (max 10)
- `tasks`: All tasks
- `activity`: Activity feed (max 50 items)
- `projectProgress`: Overall progress metrics
- `wsConnected`: WebSocket connection status
- `lastSyncTimestamp`: Last full resync time

**Derived State** (memoized for performance):
- `activeAgents`: Agents with status 'working' or 'blocked'
- `idleAgents`: Agents with status 'idle'
- `activeTasks`: Tasks with status 'in_progress'
- `blockedTasks`: Tasks with status 'blocked'

### Dispatching Actions

If you need to manually trigger state updates (rare - most come from WebSocket):

```typescript
const { updateAgent, addActivity } = useAgentState();

// Update an agent
updateAgent('backend-worker-1', { status: 'idle' }, Date.now());

// Add activity item
addActivity({
  timestamp: new Date().toISOString(),
  type: 'activity_update',
  agent: 'system',
  message: 'User triggered manual refresh',
});
```

**Available Actions**:
- `loadAgents(agents)` - Load initial agent list
- `createAgent(agent)` - Add new agent
- `updateAgent(id, updates, timestamp)` - Partial update
- `retireAgent(id, timestamp)` - Remove agent
- `assignTask(taskId, agentId, title, timestamp)` - Assign task
- `updateTaskStatus(taskId, status, progress, timestamp)` - Update task
- `blockTask(taskId, blockedBy, timestamp)` - Mark task blocked
- `unblockTask(taskId, timestamp)` - Unblock task
- `addActivity(item)` - Add activity feed entry
- `updateProgress(progress)` - Update project progress
- `setWSConnected(connected)` - Update connection status
- `fullResync(payload)` - Replace entire state (after reconnect)

### Performance Optimization

Wrap your component with `React.memo` if it renders frequently:

```typescript
import React from 'react';

export const MyAgentComponent = React.memo<MyAgentComponentProps>(
  ({ agent }) => {
    return <div>{agent.status}</div>;
  },
  (prevProps, nextProps) => {
    // Custom comparison: only re-render if this agent changed
    return (
      prevProps.agent.id === nextProps.agent.id &&
      prevProps.agent.status === nextProps.agent.status &&
      prevProps.agent.timestamp === nextProps.agent.timestamp
    );
  }
);
```

Use `useMemo` for expensive computations:

```typescript
const { agents } = useAgentState();

// Only recompute when agents array changes
const workingAgents = useMemo(
  () => agents.filter(a => a.status === 'working'),
  [agents]
);
```

---

## For Reducer Developers

### Adding a New Action Type

1. **Define the action interface** in `contracts/agent-state-api.ts`:

```typescript
export interface MyNewAction {
  type: 'MY_NEW_ACTION';
  payload: {
    someData: string;
    timestamp: number;
  };
}

// Add to the union type
export type AgentAction =
  | AgentsLoadedAction
  | AgentCreatedAction
  | MyNewAction  // ← Add here
  // ... other actions
```

2. **Handle the action in the reducer** (`reducers/agentReducer.ts`):

```typescript
export function agentReducer(
  state: AgentState,
  action: AgentAction
): AgentState {
  switch (action.type) {
    // ... existing cases

    case 'MY_NEW_ACTION':
      // Implement state transition
      return {
        ...state,
        // Update relevant fields
        someField: action.payload.someData,
      };

    default:
      return state;
  }
}
```

3. **Add a wrapper function in the hook** (`hooks/useAgentState.ts`):

```typescript
const myNewAction = useCallback((someData: string, timestamp: number) => {
  dispatch({
    type: 'MY_NEW_ACTION',
    payload: { someData, timestamp },
  });
}, [dispatch]);

return {
  // ... existing values
  myNewAction,
};
```

4. **Write unit tests** (`tests/reducers/agentReducer.test.ts`):

```typescript
describe('agentReducer - MY_NEW_ACTION', () => {
  it('should update someField when action dispatched', () => {
    const initialState = getInitialState();
    const action: MyNewAction = {
      type: 'MY_NEW_ACTION',
      payload: { someData: 'test', timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.someField).toBe('test');
    expect(newState).not.toBe(initialState); // Immutability check
  });
});
```

### Implementing Timestamp Conflict Resolution

For actions that update existing entities, always check timestamps:

```typescript
case 'AGENT_UPDATED': {
  const { agentId, updates, timestamp } = action.payload;
  const existingAgent = state.agents.find(a => a.id === agentId);

  // Conflict resolution: reject stale updates
  if (existingAgent && existingAgent.timestamp > timestamp) {
    console.warn(`Rejected stale update for agent ${agentId}`);
    return state; // No change
  }

  // Apply update
  return {
    ...state,
    agents: state.agents.map(a =>
      a.id === agentId
        ? { ...a, ...updates, timestamp }
        : a
    ),
  };
}
```

### Maintaining Immutability

**Always return new objects**:

```typescript
// ✅ Good - creates new array
agents: state.agents.map(a => ({ ...a, status: 'idle' }))

// ❌ Bad - mutates existing array
state.agents.forEach(a => a.status = 'idle')
return state;
```

**Use spread operator for nested updates**:

```typescript
return {
  ...state,
  projectProgress: {
    ...state.projectProgress,
    completed_tasks: state.projectProgress.completed_tasks + 1,
  },
};
```

---

## For WebSocket Integration

### Mapping WebSocket Messages to Actions

Create a mapper function to translate backend messages:

```typescript
// lib/websocketMessageMapper.ts
import { WebSocketMessage, AgentAction } from '@/types/agentState';

export function mapWebSocketMessageToAction(
  message: WebSocketMessage
): AgentAction | null {
  const timestamp = parseTimestamp(message.timestamp);

  switch (message.type) {
    case 'agent_created':
      return {
        type: 'AGENT_CREATED',
        payload: {
          id: message.agent_id,
          type: message.agent_type,
          status: 'idle',
          provider: message.provider || 'anthropic',
          maturity: 'directive',
          context_tokens: 0,
          tasks_completed: 0,
          timestamp,
        },
      };

    case 'agent_status_changed':
      return {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: message.agent_id,
          updates: {
            status: message.status,
            current_task: message.current_task,
            progress: message.progress,
          },
          timestamp,
        },
      };

    // ... other message types

    default:
      console.warn(`Unknown WebSocket message type: ${message.type}`);
      return null;
  }
}

function parseTimestamp(timestamp: string | number): number {
  if (typeof timestamp === 'number') return timestamp;
  return new Date(timestamp).getTime();
}
```

### Subscribing to WebSocket Messages

In the AgentStateProvider:

```typescript
useEffect(() => {
  const ws = getWebSocketClient();
  ws.connect();
  ws.subscribe(projectId);

  const unsubscribe = ws.onMessage((message: WebSocketMessage) => {
    // Filter by project
    if (message.project_id && message.project_id !== projectId) {
      return;
    }

    // Map to action and dispatch
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

### Handling Reconnection

Trigger full resync when WebSocket reconnects:

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
      // Show error to user
    }
  };

  ws.onReconnect(handleReconnect);

  return () => {
    ws.offReconnect(handleReconnect);
  };
}, [projectId, dispatch]);
```

---

## Testing

### Unit Testing Reducers

Test each action type in isolation:

```typescript
import { agentReducer, getInitialState } from '@/reducers/agentReducer';
import type { AgentUpdatedAction } from '@/types/agentState';

describe('agentReducer - AGENT_UPDATED', () => {
  it('should update agent status', () => {
    const initialState = {
      ...getInitialState(),
      agents: [
        {
          id: 'agent-1',
          type: 'backend-worker',
          status: 'idle',
          timestamp: 1000,
          // ... other fields
        },
      ],
    };

    const action: AgentUpdatedAction = {
      type: 'AGENT_UPDATED',
      payload: {
        agentId: 'agent-1',
        updates: { status: 'working' },
        timestamp: 2000,
      },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.agents[0].status).toBe('working');
    expect(newState.agents[0].timestamp).toBe(2000);
  });

  it('should reject stale updates (timestamp conflict)', () => {
    const initialState = {
      ...getInitialState(),
      agents: [
        {
          id: 'agent-1',
          type: 'backend-worker',
          status: 'working',
          timestamp: 3000, // Newer timestamp
          // ... other fields
        },
      ],
    };

    const action: AgentUpdatedAction = {
      type: 'AGENT_UPDATED',
      payload: {
        agentId: 'agent-1',
        updates: { status: 'idle' },
        timestamp: 2000, // Older timestamp - should be rejected
      },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.agents[0].status).toBe('working'); // Unchanged
    expect(newState.agents[0].timestamp).toBe(3000);   // Unchanged
  });
});
```

### Integration Testing with WebSocket

Use MSW (Mock Service Worker) to mock WebSocket connections:

```typescript
import { render, waitFor } from '@testing-library/react';
import { setupServer } from 'msw/node';
import { ws } from 'msw';
import { AgentStateProvider } from '@/components/AgentStateProvider';

const server = setupServer();

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test('should update agent status on WebSocket message', async () => {
  const projectId = 1;

  // Mock WebSocket message
  server.use(
    ws.link('ws://localhost:8000/ws/:projectId'),
    ws.on('connection', ({ client }) => {
      client.send(
        JSON.stringify({
          type: 'agent_status_changed',
          project_id: projectId,
          agent_id: 'agent-1',
          status: 'working',
          timestamp: Date.now(),
        })
      );
    })
  );

  const { getByText } = render(
    <AgentStateProvider projectId={projectId}>
      <TestComponent />
    </AgentStateProvider>
  );

  await waitFor(() => {
    expect(getByText('agent-1: working')).toBeInTheDocument();
  });
});
```

### Component Testing with Context

Wrap components in AgentStateProvider for testing:

```typescript
import { render } from '@testing-library/react';
import { AgentStateProvider } from '@/components/AgentStateProvider';
import { MyComponent } from '@/components/MyComponent';

test('should display agents from context', () => {
  const { getByText } = render(
    <AgentStateProvider projectId={1}>
      <MyComponent />
    </AgentStateProvider>
  );

  // Component can access agent state via useAgentState()
  expect(getByText(/agents/i)).toBeInTheDocument();
});
```

---

## Debugging

### Logging State Transitions

Enable dev mode logging in the reducer:

```typescript
export function agentReducer(
  state: AgentState,
  action: AgentAction
): AgentState {
  if (process.env.NODE_ENV === 'development') {
    console.group(`Action: ${action.type}`);
    console.log('Previous State:', state);
    console.log('Action:', action);
  }

  let newState: AgentState;

  switch (action.type) {
    // ... handle actions
  }

  if (process.env.NODE_ENV === 'development') {
    console.log('Next State:', newState);
    console.groupEnd();
  }

  return newState;
}
```

### React DevTools

1. Install React DevTools browser extension
2. Open Components tab
3. Find AgentStateProvider
4. Inspect state and hooks in real-time
5. Use Time Travel debugging (if Redux DevTools integration added)

### Performance Profiling

Use React Profiler to measure render performance:

```typescript
import { Profiler } from 'react';

function onRenderCallback(
  id: string,
  phase: 'mount' | 'update',
  actualDuration: number,
  baseDuration: number,
  startTime: number,
  commitTime: number
) {
  if (actualDuration > 50) {
    console.warn(`Slow render detected in ${id}: ${actualDuration}ms`);
  }
}

<Profiler id="AgentCard" onRender={onRenderCallback}>
  <AgentCard agent={agent} />
</Profiler>
```

---

## Common Patterns

### Filtering Agents by Type

```typescript
const { agents } = useAgentState();

const backendAgents = useMemo(
  () => agents.filter(a => a.type === 'backend-worker'),
  [agents]
);
```

### Finding Agent by ID

```typescript
const { agents } = useAgentState();

const agent = useMemo(
  () => agents.find(a => a.id === agentId),
  [agents, agentId]
);
```

### Counting Active Agents

```typescript
const { agents } = useAgentState();

const activeCount = useMemo(
  () => agents.filter(a => a.status === 'working').length,
  [agents]
);
```

### Checking Connection Status

```typescript
const { wsConnected } = useAgentState();

if (!wsConnected) {
  return <div>Reconnecting...</div>;
}
```

---

## Troubleshooting

### State Not Updating

**Problem**: Component not re-rendering when state changes

**Solution**: Make sure component is wrapped in AgentStateProvider:

```typescript
// App.tsx or Dashboard.tsx
<AgentStateProvider projectId={projectId}>
  <MyComponent /> {/* Now has access to context */}
</AgentStateProvider>
```

### Stale Data After Reconnect

**Problem**: Old data still showing after WebSocket reconnects

**Solution**: Check that FULL_RESYNC action is dispatched on reconnect:

```typescript
// Should see in console:
// Action: WS_CONNECTED (false)
// Action: FULL_RESYNC
// Action: WS_CONNECTED (true)
```

### Performance Issues

**Problem**: UI lagging with frequent updates

**Solutions**:
1. Wrap expensive components with `React.memo`
2. Use `useMemo` for derived state
3. Use `useCallback` for event handlers
4. Check React Profiler for slow renders

### Timestamp Conflicts

**Problem**: Updates not applying, console shows "Rejected stale update"

**Solution**: This is expected! Old updates are correctly rejected. If this happens frequently, check:
1. Backend is sending timestamps correctly
2. Network latency isn't too high
3. Messages aren't being replayed from cache

---

## Best Practices

1. **Always use useAgentState() hook** - Don't access Context directly
2. **Never mutate state** - Always return new objects from reducer
3. **Use TypeScript** - Catch type errors at compile time
4. **Test reducers thoroughly** - Pure functions are easy to test
5. **Log actions in development** - Helps debug state transitions
6. **Profile performance** - Use React Profiler to find slow renders
7. **Keep actions focused** - One action = one state transition
8. **Validate timestamps** - Always check for stale updates

---

## Next Steps

1. Review the [data-model.md](./data-model.md) for detailed entity definitions
2. Check [contracts/agent-state-api.ts](./contracts/agent-state-api.ts) for TypeScript interfaces
3. Read [plan.md](./plan.md) for implementation strategy
4. Run `/speckit.tasks` to generate detailed task breakdown

## Questions?

- Check existing Dashboard.tsx for WebSocket message handling examples
- Review AgentCard.tsx (Phase 5.1) for component patterns
- Refer to research.md for architectural decisions and rationale
