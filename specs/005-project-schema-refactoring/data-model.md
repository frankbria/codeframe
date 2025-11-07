# Data Model: Phase 5.2 - Dashboard Multi-Agent State Management

**Feature**: Dashboard Multi-Agent State Management
**Date**: 2025-11-06
**Branch**: 005-project-schema-refactoring

## Overview

This document defines all data entities, their relationships, and state transitions for the centralized agent state management system.

## Core Entities

### AgentState (Root State Container)

The root state object managed by the reducer. Contains all multi-agent dashboard state.

```typescript
interface AgentState {
  agents: Agent[];               // All active agents (max 10)
  tasks: Task[];                 // Current tasks (from backend)
  activity: ActivityItem[];      // Activity feed (max 50 items, FIFO)
  projectProgress: ProjectProgress | null;  // Overall project progress
  wsConnected: boolean;          // WebSocket connection status
  lastSyncTimestamp: number;     // Unix ms of last full sync
}
```

**Invariants**:
- `agents.length <= 10` (warn if exceeded)
- `activity.length <= 50` (maintain sliding window)
- `lastSyncTimestamp` updated on FULL_RESYNC only
- `wsConnected` reflects real-time connection status

**Initial State**:
```typescript
const initialAgentState: AgentState = {
  agents: [],
  tasks: [],
  activity: [],
  projectProgress: null,
  wsConnected: false,
  lastSyncTimestamp: 0,
};
```

---

### Agent

Represents a single agent (Lead, Backend Worker, Frontend Worker, Test Worker) with current state and timestamp for conflict resolution.

```typescript
interface Agent {
  id: string;                    // Unique identifier (e.g., "backend-worker-1")
  type: AgentType;               // Agent specialization
  status: AgentStatus;           // Current activity status
  provider: string;              // LLM provider (e.g., "anthropic")
  maturity: AgentMaturity;       // Autonomy level
  current_task?: CurrentTask;    // Active task (if working)
  blocker?: string;              // Blocker description (if blocked)
  context_tokens: number;        // Current context window usage
  tasks_completed: number;       // Historical count (defer metrics - may remove)
  timestamp: number;             // Unix ms from backend (for conflict resolution)
}

type AgentType =
  | 'lead'
  | 'backend-worker'
  | 'frontend-specialist'
  | 'test-engineer';

type AgentStatus =
  | 'idle'        // Ready for work
  | 'working'     // Executing a task
  | 'blocked';    // Waiting on blocker resolution

type AgentMaturity =
  | 'directive'   // Requires detailed instructions
  | 'collaborative' // Can suggest approaches
  | 'autonomous'; // Self-directed

interface CurrentTask {
  id: number;     // Task ID
  title: string;  // Task description
}
```

**Validation Rules**:
- `id` must be unique within `agents` array
- `timestamp` must be > 0 (validate from backend)
- `status === 'working'` ⇒ `current_task` must be defined
- `status === 'blocked'` ⇒ `blocker` must be defined
- `tasks_completed >= 0` (non-negative)

**State Transitions**:
```
idle → working    (when task assigned)
working → idle    (when task completed)
working → blocked (when blocker encountered)
blocked → idle    (when blocker resolved)
```

---

### Task

Represents a work item that can be assigned to agents. Used for tracking agent assignments and dependencies.

```typescript
interface Task {
  id: number;                    // Unique task identifier
  title: string;                 // Task description
  status: TaskStatus;            // Current state
  agent_id?: string;             // Assigned agent (if any)
  blocked_by?: number[];         // Task IDs blocking this task
  progress?: number;             // Completion percentage (0-100)
  timestamp: number;             // Unix ms from backend
}

type TaskStatus =
  | 'pending'       // Not started, no blockers
  | 'in_progress'   // Agent actively working
  | 'blocked'       // Waiting on dependencies
  | 'completed';    // Finished
```

**Validation Rules**:
- `id` must be unique
- `status === 'in_progress'` ⇒ `agent_id` must be defined
- `status === 'blocked'` ⇒ `blocked_by` must be non-empty array
- `progress` must be in range [0, 100] if defined
- `timestamp` must be > 0

**Relationships**:
- `agent_id` → `Agent.id` (foreign key, nullable)
- `blocked_by` → `Task.id[]` (self-referential, for dependency graph)

---

### ActivityItem

Represents a single entry in the activity feed showing system events, agent actions, and status changes.

```typescript
interface ActivityItem {
  timestamp: string;             // ISO 8601 timestamp from backend
  type: ActivityType;            // Event category
  agent: string;                 // Agent ID or "system"
  message: string;               // Human-readable description
}

type ActivityType =
  | 'task_assigned'
  | 'task_completed'
  | 'task_blocked'
  | 'task_unblocked'
  | 'agent_created'
  | 'agent_retired'
  | 'test_result'
  | 'commit_created'
  | 'correction_attempt'
  | 'activity_update'
  | 'blocker_created'
  | 'blocker_resolved';
```

**Validation Rules**:
- `timestamp` must be valid ISO 8601 string
- `message` must be non-empty
- Array maintains max 50 items (FIFO eviction)

**Display Order**: Most recent first (reverse chronological)

---

### ProjectProgress

High-level progress metrics for the entire project.

```typescript
interface ProjectProgress {
  completed_tasks: number;       // Number of finished tasks
  total_tasks: number;           // Total tasks in project
  percentage: number;            // completion percentage (0-100)
}
```

**Validation Rules**:
- `completed_tasks <= total_tasks`
- `percentage === (completed_tasks / total_tasks) * 100`
- All fields >= 0

---

## Reducer Actions

All state mutations happen through reducer actions. Actions are discriminated unions for type safety.

### Action Type Definitions

```typescript
type AgentAction =
  | AgentsLoadedAction
  | AgentCreatedAction
  | AgentUpdatedAction
  | AgentRetiredAction
  | TaskAssignedAction
  | TaskStatusChangedAction
  | TaskBlockedAction
  | TaskUnblockedAction
  | ActivityAddedAction
  | ProgressUpdatedAction
  | WebSocketConnectedAction
  | FullResyncAction;

// Individual action interfaces
interface AgentsLoadedAction {
  type: 'AGENTS_LOADED';
  payload: Agent[];
}

interface AgentCreatedAction {
  type: 'AGENT_CREATED';
  payload: Agent;
}

interface AgentUpdatedAction {
  type: 'AGENT_UPDATED';
  payload: {
    agentId: string;
    updates: Partial<Agent>;
    timestamp: number;
  };
}

interface AgentRetiredAction {
  type: 'AGENT_RETIRED';
  payload: {
    agentId: string;
    timestamp: number;
  };
}

interface TaskAssignedAction {
  type: 'TASK_ASSIGNED';
  payload: {
    taskId: number;
    agentId: string;
    taskTitle?: string;
    timestamp: number;
  };
}

interface TaskStatusChangedAction {
  type: 'TASK_STATUS_CHANGED';
  payload: {
    taskId: number;
    status: TaskStatus;
    progress?: number;
    timestamp: number;
  };
}

interface TaskBlockedAction {
  type: 'TASK_BLOCKED';
  payload: {
    taskId: number;
    blockedBy: number[];
    timestamp: number;
  };
}

interface TaskUnblockedAction {
  type: 'TASK_UNBLOCKED';
  payload: {
    taskId: number;
    timestamp: number;
  };
}

interface ActivityAddedAction {
  type: 'ACTIVITY_ADDED';
  payload: ActivityItem;
}

interface ProgressUpdatedAction {
  type: 'PROGRESS_UPDATED';
  payload: ProjectProgress;
}

interface WebSocketConnectedAction {
  type: 'WS_CONNECTED';
  payload: boolean;
}

interface FullResyncAction {
  type: 'FULL_RESYNC';
  payload: {
    agents: Agent[];
    tasks: Task[];
    activity: ActivityItem[];
    timestamp: number;
  };
}
```

---

## State Transition Rules

### Agent Updates (Timestamp Conflict Resolution)

```typescript
// Pseudo-code for AGENT_UPDATED handling
function handleAgentUpdated(
  state: AgentState,
  agentId: string,
  updates: Partial<Agent>,
  timestamp: number
): AgentState {
  const existing = state.agents.find(a => a.id === agentId);

  // Conflict resolution: reject stale updates
  if (existing && existing.timestamp > timestamp) {
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

### Activity Feed (FIFO Sliding Window)

```typescript
// Maintain max 50 items
function addActivity(state: AgentState, item: ActivityItem): AgentState {
  return {
    ...state,
    activity: [
      item,
      ...state.activity.slice(0, 49), // Keep only 49 old items
    ],
  };
}
```

### Task Assignment (Atomic Agent + Task Update)

```typescript
function handleTaskAssigned(
  state: AgentState,
  taskId: number,
  agentId: string,
  taskTitle: string | undefined,
  timestamp: number
): AgentState {
  return {
    ...state,
    // Update task status
    tasks: state.tasks.map(t =>
      t.id === taskId
        ? { ...t, status: 'in_progress', agent_id: agentId, timestamp }
        : t
    ),
    // Update agent status
    agents: state.agents.map(a =>
      a.id === agentId
        ? {
            ...a,
            status: 'working',
            current_task: { id: taskId, title: taskTitle || `Task #${taskId}` },
            timestamp,
          }
        : a
    ),
  };
}
```

### Full Resync (Atomic State Replacement)

```typescript
function handleFullResync(
  state: AgentState,
  payload: FullResyncAction['payload']
): AgentState {
  // Replace entire state atomically
  return {
    agents: payload.agents,
    tasks: payload.tasks,
    activity: payload.activity,
    projectProgress: state.projectProgress, // Preserve if not in payload
    wsConnected: true, // Resync implies connection restored
    lastSyncTimestamp: payload.timestamp,
  };
}
```

---

## Relationships & Dependencies

### Entity Relationship Diagram

```
┌─────────────────┐
│   AgentState    │ (Root)
│  (Context)      │
└─────────────────┘
        │
        ├─── agents: Agent[]
        │           │
        │           ├─ id (PK)
        │           ├─ current_task → Task.id (FK, nullable)
        │           └─ timestamp (for conflict resolution)
        │
        ├─── tasks: Task[]
        │           │
        │           ├─ id (PK)
        │           ├─ agent_id → Agent.id (FK, nullable)
        │           ├─ blocked_by → Task.id[] (FK, self-ref)
        │           └─ timestamp
        │
        ├─── activity: ActivityItem[]
        │           │
        │           ├─ agent → Agent.id | "system"
        │           └─ timestamp (ISO string)
        │
        ├─── projectProgress: ProjectProgress
        │
        ├─── wsConnected: boolean
        │
        └─── lastSyncTimestamp: number
```

### Cascade Effects

**When Agent Retired**:
1. Remove from `agents` array
2. If agent had `current_task`, update that task to `status: 'pending'`
3. Add activity item with type `'agent_retired'`

**When Task Completed**:
1. Update task `status: 'completed'`
2. Update assigned agent `status: 'idle'`, clear `current_task`
3. Check if any tasks have this in their `blocked_by` array → trigger `TASK_UNBLOCKED`
4. Add activity item with type `'task_completed'`
5. Potentially trigger `PROGRESS_UPDATED`

---

## Validation & Invariants

### Runtime Checks

```typescript
function validateAgentState(state: AgentState): void {
  // Max agents check
  if (state.agents.length > 10) {
    console.warn(`Agent count (${state.agents.length}) exceeds maximum of 10`);
  }

  // Activity feed size check
  if (state.activity.length > 50) {
    console.error('Activity feed exceeds 50 items - should have been trimmed');
  }

  // Referential integrity checks (dev mode only)
  if (process.env.NODE_ENV === 'development') {
    state.agents.forEach(agent => {
      if (agent.status === 'working' && !agent.current_task) {
        console.error(`Agent ${agent.id} is working but has no current_task`);
      }
      if (agent.current_task) {
        const task = state.tasks.find(t => t.id === agent.current_task!.id);
        if (!task) {
          console.warn(`Agent ${agent.id} references non-existent task ${agent.current_task.id}`);
        }
      }
    });

    state.tasks.forEach(task => {
      if (task.agent_id) {
        const agent = state.agents.find(a => a.id === task.agent_id);
        if (!agent) {
          console.warn(`Task ${task.id} references non-existent agent ${task.agent_id}`);
        }
      }
    });
  }
}
```

### Immutability Enforcement

All state updates must return new objects (no mutations). Use:
- Spread operator: `{ ...state, agents: [...state.agents] }`
- Array methods: `.map()`, `.filter()`, `.slice()`
- Optional: Immer library for complex nested updates

---

## WebSocket Message to Action Mapping

### Message → Action Translation

```typescript
// lib/websocketMessageMapper.ts
export function mapWebSocketMessageToAction(
  message: WebSocketMessage
): AgentAction | null {
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
          timestamp: parseTimestamp(message.timestamp),
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
          timestamp: parseTimestamp(message.timestamp),
        },
      };

    case 'task_assigned':
      return {
        type: 'TASK_ASSIGNED',
        payload: {
          taskId: message.task_id,
          agentId: message.agent_id,
          taskTitle: message.task_title,
          timestamp: parseTimestamp(message.timestamp),
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

---

## Testing Scenarios

### Test Data Fixtures

```typescript
// tests/fixtures/agentState.ts
export const mockAgent: Agent = {
  id: 'backend-worker-1',
  type: 'backend-worker',
  status: 'idle',
  provider: 'anthropic',
  maturity: 'directive',
  context_tokens: 0,
  tasks_completed: 0,
  timestamp: Date.now(),
};

export const mockTask: Task = {
  id: 1,
  title: 'Implement authentication',
  status: 'pending',
  timestamp: Date.now(),
};

export const mockActivityItem: ActivityItem = {
  timestamp: new Date().toISOString(),
  type: 'task_assigned',
  agent: 'backend-worker-1',
  message: 'Assigned task #1 to backend-worker-1',
};
```

### Conflict Resolution Test Cases

1. **Same agent, newer update arrives first, older arrives second** → Reject older
2. **Same agent, older update arrives first, newer arrives second** → Accept newer
3. **Different agents updating simultaneously** → Both applied independently
4. **Full resync replaces all with fresh data** → All timestamps from resync

---

## Migration Notes

### Backward Compatibility

- Existing `Agent` type from Phase 5.1 is compatible (add `timestamp` field)
- AgentCard component receives same props (no breaking changes)
- Dashboard continues using SWR for initial load (Context for real-time updates)

### Data Transformation

```typescript
// Transform SWR response to Context state
function transformAPIResponse(apiAgents: APIAgent[]): Agent[] {
  return apiAgents.map(a => ({
    ...a,
    timestamp: Date.now(), // Add timestamp on initial load
  }));
}
```

---

## Performance Considerations

### Memory Bounds

- Max 10 agents × ~200 bytes = 2KB
- Max 50 activity items × ~150 bytes = 7.5KB
- ~100 tasks × ~150 bytes = 15KB
- **Total state size: ~25KB** (negligible)

### Update Frequency

- Assume worst case: 10 agents updating every second = 10 updates/sec
- Each update triggers reducer + re-render
- With React.memo on AgentCard, only changed cards re-render
- **Target: < 50ms per state update**

---

## Next Steps

1. Implement TypeScript interfaces in `web-ui/src/types/agentState.ts`
2. Implement reducer in `web-ui/src/reducers/agentReducer.ts`
3. Create Context provider in `web-ui/src/components/AgentStateProvider.tsx`
4. Write unit tests for reducer logic (all action types)
5. Write integration tests for WebSocket message handling
