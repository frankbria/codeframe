# AI Agent Handoff Summary

**Feature**: Phase 5.2 - Dashboard Multi-Agent State Management
**Branch**: `005-project-schema-refactoring`
**Status**: Phases 1-5 Complete (95/150 tasks - 63.33%) ✅
**Date**: 2025-11-07
**Next Phase**: Phase 6 - Dashboard Integration

---

## 🎉 What's Complete

### ✅ Phase 1: Setup & Type Definitions (4/4 tasks - 100%)

**Files Created**:
1. `web-ui/src/types/agentState.ts` (330 lines)
   - All TypeScript types for state management
   - 12 action type interfaces
   - Utility type guards

2. `web-ui/src/lib/timestampUtils.ts` (80 lines)
   - Timestamp parsing utilities
   - Conflict resolution helpers

3. `web-ui/__tests__/fixtures/agentState.ts` (290 lines)
   - Factory functions for all entities
   - Edge case scenarios
   - Test data generators

**Beads**: All tasks tracked in tasks.md

---

### ✅ Phase 2: Foundational - Reducer Implementation (31/31 tasks - 100%)

**Files Created**:
1. `web-ui/src/reducers/agentReducer.ts` (370 lines)
   - Complete reducer with 12 action handlers
   - Timestamp conflict resolution
   - FIFO activity feed (50-item limit)
   - Development mode logging
   - Validation warnings

2. `web-ui/__tests__/reducers/agentReducer.test.ts` (930 lines)
   - 49 comprehensive test cases
   - 100% pass rate ✅
   - Tests for all action types
   - Immutability and conflict resolution tests

**Key Features**:
- ✅ Immutable state updates
- ✅ Timestamp-based conflict resolution (rejects stale updates)
- ✅ FIFO activity feed with 50-item limit
- ✅ Atomic operations (TASK_ASSIGNED, FULL_RESYNC)
- ✅ Validation warnings (10 agent limit, 50 activity limit)

**Test Results**: All 49 tests passing

**Beads**: cf-flx closed ✅

---

### ✅ Phase 3: Context & Hook Implementation (14/14 tasks - 100%)

**Files Created**:
1. `web-ui/src/contexts/AgentStateContext.ts` (45 lines)
   - React Context definition
   - Context value interface

2. `web-ui/src/components/AgentStateProvider.tsx` (170 lines)
   - Context Provider component
   - useReducer integration
   - SWR initial data fetching
   - Transforms API data with timestamps

3. `web-ui/src/hooks/useAgentState.ts` (370 lines)
   - Custom hook for consuming Context
   - 6 derived state values (useMemo):
     * activeAgents, idleAgents
     * activeTasks, blockedTasks, pendingTasks, completedTasks
   - 12 action wrapper functions (useCallback)
   - Error handling for missing Provider

4. `web-ui/__tests__/components/AgentStateProvider.test.tsx` (220 lines)
   - 9 test cases, 100% pass rate ✅

5. `web-ui/__tests__/hooks/useAgentState.test.tsx` (470 lines)
   - 23 test cases, 100% pass rate ✅

**Test Results**: All 32 tests passing (9 + 23)

**Beads**: cf-mhi closed ✅

---

### ✅ Phase 4: WebSocket Integration (28/28 tasks - 100%)

**Files Created**:
1. `web-ui/src/lib/websocketMessageMapper.ts` (230 lines)
   - Maps 13+ WebSocket message types to reducer actions
   - Timestamp parsing (string/number to Unix ms)
   - Project ID filtering
   - Unknown message type warnings

2. `web-ui/__tests__/lib/websocketMessageMapper.test.ts` (620 lines)
   - 29 comprehensive test cases, 100% pass rate ✅
   - All message types tested
   - Edge cases and error handling
   - Integration scenarios

**Key Features**:
- ✅ WebSocket message mapping for all event types
- ✅ Timestamp parsing and normalization
- ✅ Project ID filtering
- ✅ Connection status tracking
- ✅ Message subscription in AgentStateProvider

**Test Results**: All 29 tests passing

**Beads**: cf-gy6 closed ✅

---

### ✅ Phase 5: Reconnection & Resync (18/18 tasks - 100%)

**Files Created**:
1. `web-ui/src/lib/agentStateSync.ts` (160 lines)
   - fullStateResync function with parallel API fetches
   - Retry logic with exponential backoff
   - Error handling with context
   - Handles empty/null responses

2. `web-ui/__tests__/lib/agentStateSync.test.ts` (340 lines)
   - 12 unit tests, 100% pass rate ✅
   - Tests API calls, parallel execution, error handling

**Enhanced Files**:
- `web-ui/src/lib/websocket.ts`
  - Exponential backoff (1s, 2s, 4s, 8s, 16s, 30s max)
  - Debounce logic (500ms minimum interval)
  - Max 10 reconnection attempts
  - Reset counter on successful connection

- `web-ui/src/components/AgentStateProvider.tsx`
  - Reconnection detection with onReconnect
  - Triggers fullStateResync on reconnect
  - Dispatches FULL_RESYNC action
  - Connection status management

**Key Features**:
- ✅ Full state resynchronization after reconnection
- ✅ Parallel API fetches (Promise.all)
- ✅ Exponential backoff for reconnection
- ✅ Debounce to prevent rapid cycles
- ✅ Retry logic for transient failures
- ✅ Connection status tracking

**Test Results**: All 12 tests passing

**Beads**: cf-rlq closed ✅

---

## 🎯 What's Next - Phase 6: Dashboard Integration

### Overview

**Goal**: Migrate Dashboard component to use Context instead of local state

**Tasks**: T096-T114 (19 tasks)
- 6 test tasks (T096-T101)
- 13 implementation tasks (T102-T114)

**Estimated Time**: 1-1.5 days

### Critical Path

Phase 6 integrates all previous phases into the Dashboard UI. This is the final step to make the state management system visible and functional in the UI.

### Current Dashboard State

**File**: `web-ui/src/components/Dashboard.tsx` (642 lines)

**Current Architecture** (needs migration):
- Uses local `useState` for agents, tasks, activity, projectProgress
- Has extensive WebSocket message handlers (lines 90-270)
- Manually updates state for each message type
- Uses SWR for initial data fetching
- Maps agents to AgentCard components (line 546-559)

**Problems with Current Approach**:
- Duplicates logic that's now in AgentStateProvider
- No timestamp-based conflict resolution
- No automatic reconnection handling
- Inconsistent state updates
- Hard to test and maintain

### Migration Strategy

**Step 1: Wrap with Provider (T102)**
- Import `AgentStateProvider`
- Wrap Dashboard content with `<AgentStateProvider projectId={projectId}>`
- This enables access to centralized state

**Step 2: Replace Local State (T103-T106)**
```typescript
// Before:
const [agents, setAgents] = useState<Agent[]>([]);
const [tasks, setTasks] = useState<Task[]>([]);
const [activity, setActivity] = useState<ActivityItem[]>([]);
const [projectProgress, setProjectProgress] = useState<any>(null);

// After:
const {
  agents,
  tasks,
  activity,
  projectProgress,
  wsConnected
} = useAgentState();
```

**Step 3: Remove Redundant Code (T107)**
- Delete WebSocket message handlers (lines 90-270) - now handled by Provider
- Delete useEffect hooks that initialize local state from SWR
- Provider's SWR hooks handle initial data loading

**Step 4: Add Connection Indicator (T108)**
```typescript
{wsConnected ? (
  <span className="text-green-500">● Connected</span>
) : (
  <span className="text-red-500">● Disconnected</span>
)}
```

**Step 5: Performance Optimizations (T109-T112)**

Add React.memo to AgentCard (T110):
```typescript
// In AgentCard.tsx
export const AgentCard = React.memo<AgentCardProps>(
  ({ agent, onAgentClick }) => {
    // ... component code
  },
  (prev, next) => {
    // Only re-render if agent changed
    return prev.agent.id === next.agent.id &&
           prev.agent.timestamp === next.agent.timestamp;
  }
);
```

Add useMemo for filtered lists (T111):
```typescript
const activeAgents = useMemo(
  () => agents.filter(a => a.status === 'working'),
  [agents]
);
```

Add useCallback for handlers (T112):
```typescript
const handleAgentClick = useCallback((agentId: string) => {
  console.log('Agent clicked:', agentId);
}, []);
```

### Step 6: Write Tests (T096-T101)

Create `web-ui/__tests__/components/Dashboard.test.tsx`:
```typescript
import { render, screen, waitFor } from '@testing-library/react';
import { AgentStateProvider } from '@/components/AgentStateProvider';
import Dashboard from '@/components/Dashboard';

describe('Dashboard with AgentStateProvider', () => {
  it('should render with context state', () => {
    render(
      <AgentStateProvider projectId={1}>
        <Dashboard projectId={1} />
      </AgentStateProvider>
    );

    expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();
  });

  it('should display agents from context', async () => {
    // Mock API responses
    // Render Dashboard
    // Verify agents are displayed
  });

  it('should show connection indicator', async () => {
    // Test wsConnected state is displayed
  });
});
```

Create `web-ui/__tests__/integration/dashboard-realtime-updates.test.ts`:
```typescript
import { render, screen, waitFor } from '@testing-library/react';
import { AgentStateProvider } from '@/components/AgentStateProvider';
import Dashboard from '@/components/Dashboard';

describe('Dashboard Real-time Updates', () => {
  it('should update when WebSocket message arrives', async () => {
    // Mock WebSocket
    // Send agent_status_changed message
    // Verify Dashboard updates without full re-render
  });

  it('should handle multiple agent updates independently', async () => {
    // Test that updating one agent doesn't re-render all AgentCards
  });
});
```

### Expected Outcomes

After Phase 6 completion:

**Functionality**:
- ✅ Dashboard uses centralized state from Context
- ✅ Real-time updates work automatically (via Provider)
- ✅ Connection status indicator visible
- ✅ No duplicate WebSocket handlers
- ✅ Timestamp-based conflict resolution active
- ✅ Automatic reconnection handling

**Performance**:
- ✅ AgentCard memoized (no unnecessary re-renders)
- ✅ Filtered lists memoized
- ✅ Event handlers stable (useCallback)
- ✅ Only changed agents re-render

**Code Quality**:
- ✅ ~200 fewer lines in Dashboard (remove WebSocket handlers)
- ✅ Single source of truth (no local state duplication)
- ✅ Easier to test (Provider handles complexity)
- ✅ Better separation of concerns

### Testing Checklist

Before marking Phase 6 complete:
- [ ] All Dashboard tests passing
- [ ] Integration tests passing
- [ ] No console errors or warnings
- [ ] Connection indicator works
- [ ] AgentCards update on WebSocket messages
- [ ] No memory leaks
- [ ] Performance acceptable (< 50ms updates)

### Files to Modify/Create

**Modify**:
1. `web-ui/src/components/Dashboard.tsx`
   - Replace local state with useAgentState
   - Remove WebSocket handlers (~200 lines)
   - Add connection indicator
   - Add performance optimizations

2. `web-ui/src/components/AgentCard.tsx`
   - Add React.memo with custom comparison

**Create**:
1. `web-ui/__tests__/components/Dashboard.test.tsx`
   - Component tests for Dashboard with Provider

2. `web-ui/__tests__/integration/dashboard-realtime-updates.test.ts`
   - Integration tests for real-time updates
     * activity_update, progress_update
     * test_result, commit_created, correction_attempt
   - Timestamp parsing (string/number → Unix ms)

2. **`web-ui/__tests__/lib/websocketMessageMapper.test.ts`**
   - Unit tests for each message type (T050-T058)
   - Integration tests (T059-T061)

3. **Update `web-ui/src/components/AgentStateProvider.tsx`**
   - Add WebSocket subscription
   - Add message handler with project_id filtering
   - Connect mapper to dispatch
   - Add cleanup for subscription

4. **`web-ui/__tests__/integration/websocket-state-sync.test.ts`**
   - Integration test for WebSocket → state updates
   - Test out-of-order messages

5. **`web-ui/__tests__/integration/multi-agent-updates.test.ts`**
   - Test multiple simultaneous agent updates

### Implementation Guide

**Step 1: Write Tests First (TDD - T050-T061)**

Create test file with Mock Service Worker (MSW) for WebSocket mocking:

```typescript
// __tests__/lib/websocketMessageMapper.test.ts
import { mapWebSocketMessageToAction } from '@/lib/websocketMessageMapper';

describe('mapWebSocketMessageToAction', () => {
  it('should map agent_created message', () => {
    const message = {
      type: 'agent_created',
      agent_id: 'backend-worker-1',
      agent_type: 'backend-worker',
      provider: 'anthropic',
      timestamp: 1699999999000,
    };

    const action = mapWebSocketMessageToAction(message);

    expect(action).toEqual({
      type: 'AGENT_CREATED',
      payload: {
        id: 'backend-worker-1',
        type: 'backend-worker',
        status: 'idle',
        provider: 'anthropic',
        maturity: 'directive',
        context_tokens: 0,
        tasks_completed: 0,
        timestamp: 1699999999000,
      },
    });
  });

  // ... similar tests for all 13 message types
});
```

**Step 2: Implement Message Mapper (T062-T072)**

```typescript
// web-ui/src/lib/websocketMessageMapper.ts
import type { AgentAction } from '@/types/agentState';

export function mapWebSocketMessageToAction(
  message: any
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

    // ... handle all message types

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

**Step 3: Add WebSocket Subscription to Provider (T073-T077)**

Update `AgentStateProvider.tsx`:

```typescript
// Add to AgentStateProvider component

useEffect(() => {
  // Assuming there's a WebSocket client in lib/websocket.ts
  const ws = getWebSocketClient();

  // Subscribe to messages
  const unsubscribe = ws.onMessage((message: any) => {
    // Filter by project ID
    if (message.project_id && message.project_id !== projectId) {
      return;
    }

    // Map message to action
    const action = mapWebSocketMessageToAction(message);

    if (action) {
      dispatch(action);
    }
  });

  // Cleanup on unmount
  return () => {
    unsubscribe();
  };
}, [projectId, dispatch]);
```

**Step 4: Write Integration Tests (T059-T061)**

Use MSW to mock WebSocket:

```typescript
// __tests__/integration/websocket-state-sync.test.ts
import { renderHook, act } from '@testing-library/react';
import { setupServer } from 'msw/node';
import { ws } from 'msw';

const server = setupServer();

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test('should update agent status on WebSocket message', async () => {
  // Mock WebSocket
  server.use(
    ws.link('ws://localhost:8000/ws/:projectId'),
    ws.on('connection', ({ client }) => {
      client.send(JSON.stringify({
        type: 'agent_status_changed',
        project_id: 1,
        agent_id: 'agent-1',
        status: 'working',
        timestamp: Date.now(),
      }));
    })
  );

  // Test that state updates
  // ...
});
```

### Resources Available

**Existing WebSocket Client**:
- Location: `web-ui/src/lib/websocket.ts` (exists from cf-45)
- Already handles connections
- Just need to add message subscription hooks

**API Documentation**:
- See `specs/005-project-schema-refactoring/contracts/agent-state-api.ts`
- Message format examples in `research.md`

**Test Patterns**:
- Look at `__tests__/reducers/agentReducer.test.ts` for patterns
- Use `createMock*` fixtures from `__tests__/fixtures/agentState.ts`

### Success Criteria

**Must Complete** before moving to Phase 5:
- ✅ All 12 unit tests passing (T050-T061)
- ✅ Message mapper handles all 13+ message types
- ✅ WebSocket subscription added to Provider
- ✅ Integration tests passing
- ✅ Project ID filtering working
- ✅ Cleanup subscriptions on unmount

**Checkpoint**: "WebSocket messages updating state in real-time"

---

## 📁 Current Project Structure

```
web-ui/
├── src/
│   ├── types/agentState.ts              ✅ Phase 1
│   ├── lib/
│   │   ├── timestampUtils.ts            ✅ Phase 1
│   │   ├── api.ts                       ✅ Existing
│   │   ├── websocket.ts                 ✅ Existing (cf-45)
│   │   └── websocketMessageMapper.ts    📝 TODO Phase 4
│   ├── reducers/agentReducer.ts         ✅ Phase 2
│   ├── contexts/AgentStateContext.ts    ✅ Phase 3
│   ├── components/
│   │   ├── AgentStateProvider.tsx       ✅ Phase 3
│   │   ├── AgentCard.tsx                ✅ Existing (Phase 5.1)
│   │   └── Dashboard.tsx                ✅ Existing (refactor Phase 6)
│   └── hooks/useAgentState.ts           ✅ Phase 3
└── __tests__/
    ├── fixtures/agentState.ts           ✅ Phase 1
    ├── reducers/
    │   └── agentReducer.test.ts         ✅ Phase 2
    ├── components/
    │   └── AgentStateProvider.test.tsx  ✅ Phase 3
    ├── hooks/
    │   └── useAgentState.test.tsx       ✅ Phase 3
    ├── lib/
    │   └── websocketMessageMapper.test.ts  📝 TODO Phase 4
    └── integration/
        ├── websocket-state-sync.test.ts    📝 TODO Phase 4
        └── multi-agent-updates.test.ts     📝 TODO Phase 4
```

---

## 🔧 Quick Commands

```bash
# Navigate to project
cd /home/frankbria/projects/codeframe/web-ui

# Run all tests
npm test

# Run specific test file
npm test -- __tests__/lib/websocketMessageMapper.test.ts

# Run tests in watch mode
npm test -- --watch

# Type check
npm run type-check

# Lint
npm run lint

# Check beads status
bd list --label sprint-4

# Update beads issue
bd update cf-gy6 --status in_progress

# View tasks
cat ../specs/005-project-schema-refactoring/tasks.md | less

# View main issue
bd show cf-8jr
```

---

## 📊 Progress Tracking

### Tasks Completed

**Total**: 95/150 tasks (63.33%)
- ✅ Phase 1: 4/4 tasks
- ✅ Phase 2: 31/31 tasks
- ✅ Phase 3: 14/14 tasks
- ✅ Phase 4: 28/28 tasks
- ✅ Phase 5: 18/18 tasks
- ⏳ Phase 6: 0/19 tasks (NEXT)
- 🔒 Phase 7-8: Blocked

### Beads Issues

- ✅ cf-flx (Phase 2) - **CLOSED**
- ✅ cf-mhi (Phase 3) - **CLOSED**
- ✅ cf-gy6 (Phase 4) - **CLOSED**
- ✅ cf-rlq (Phase 5) - **CLOSED**
- ⏳ cf-791 (Phase 6) - **OPEN** (start here)
- 🔒 cf-5dh (Phase 7) - **OPEN** (blocked)
- 🔒 cf-4y8 (Phase 8) - **OPEN** (blocked)

### Test Results

**All Tests Passing**: 90/90 (100%)
- Phase 2 Reducer: 49 tests ✅
- Phase 3 Provider: 9 tests ✅
- Phase 3 Hook: 23 tests ✅
- Phase 4 WebSocket Mapper: 29 tests ✅
- Phase 5 State Sync: 12 tests ✅

---

## 🎓 Key Patterns & Decisions

### TDD Workflow (CRITICAL - Follow This!)

1. **Write tests FIRST** (they should FAIL)
2. **Implement code** to make tests pass
3. **Verify tests PASS** before moving on
4. **Mark task complete** in tasks.md
5. **Update beads** when phase complete

### Code Quality Standards

- ✅ TypeScript strict mode (no `any` types)
- ✅ Immutability (spread operators, no mutations)
- ✅ useMemo for derived state
- ✅ useCallback for event handlers
- ✅ 100% test coverage for new code
- ✅ JSDoc comments on all exported functions

### Performance Optimizations

- React.memo on frequently rendered components
- useMemo for expensive computations
- useCallback for stable function references
- Same reference return for no-op actions (performance)

### Timestamp Conflict Resolution

```typescript
// ALWAYS check timestamps before updates
if (existingAgent.timestamp > newTimestamp) {
  console.warn('Rejected stale update');
  return state; // Return same reference
}
```

---

## 🚨 Common Pitfalls & Solutions

### Issue: Tests fail with "Cannot find module"
**Solution**: Check import paths use `@/` alias, not relative paths

### Issue: WebSocket tests don't work
**Solution**: Use MSW (Mock Service Worker) for WebSocket mocking - already in dependencies

### Issue: State not updating in tests
**Solution**: Wrap hook/component in `AgentStateProvider` with valid `projectId`

### Issue: TypeScript errors with action types
**Solution**: Import types from `@/types/agentState`, use discriminated unions

### Issue: Tests pass but components don't update
**Solution**: Check useMemo/useCallback dependencies array - may be missing deps

---

## 📚 Essential Reading Before Starting

**Must Read** (in order):
1. `tasks.md` - Find "Phase 4" section
2. `contracts/agent-state-api.ts` - WebSocket message formats
3. `research.md` - Architectural decisions (WebSocket section)
4. This file (HANDOFF_SUMMARY.md)

**Reference During Work**:
- `quickstart.md` - Developer guide with patterns
- `data-model.md` - Entity relationships
- Existing test files for patterns

---

## 🎯 Immediate Next Steps for Phase 6

**For Next AI Agent**:

1. ✅ Read this handoff summary
2. ✅ Review Phase 6 tasks in `tasks.md` (T096-T114)
3. ✅ Update beads: `bd update cf-791 --status in_progress`
4. ✅ Study existing `Dashboard.tsx` (642 lines)
   - Understand current state management
   - Identify WebSocket handlers to remove (lines 90-270)
   - Note where agents are rendered (line 546-559)
5. ✅ **Start with tests (TDD)**:
   - Create `__tests__/components/Dashboard.test.tsx` (T096-T099)
   - Create `__tests__/integration/dashboard-realtime-updates.test.ts` (T100-T101)
   - Run tests (should FAIL)
6. ✅ **Migrate Dashboard** (T102-T109):
   - Import and use `useAgentState` hook
   - Remove local state (`useState` for agents, tasks, activity)
   - Remove WebSocket handlers (Provider handles this)
   - Remove redundant useEffect hooks
   - Add connection indicator using `wsConnected`
   - Update agent mapping to use context state
7. ✅ **Add Performance Optimizations** (T110-T112):
   - Add React.memo to AgentCard
   - Add useMemo for filtered lists
   - Add useCallback for event handlers
8. ✅ **Verify and Test** (T113-T114):
   - Run all tests (should PASS)
   - Test in browser with real WebSocket
   - Verify connection indicator works
   - Check that agents update in real-time
9. ✅ Mark T096-T114 as [X] in tasks.md
10. ✅ Update beads: `bd update cf-791 --status closed`
11. ✅ Proceed to Phase 7

---

## 💡 Tips for Success (Phase 6 Specific)

1. **Understand before modifying** - Read the entire Dashboard.tsx first
2. **Don't break existing features** - PRD, Tasks, Blockers sections should still work
3. **Test incrementally** - Test after each major change
4. **Use Provider correctly** - Wrap at the right level (probably in parent component)
5. **Preserve existing props** - Dashboard still needs `projectId` prop
6. **Check for console errors** - Should be no warnings after migration
7. **Verify WebSocket works** - Test with real backend if possible

### Common Pitfalls to Avoid

1. **Don't wrap Dashboard internally** - Wrap it in the parent component that renders it
2. **Don't mix old and new state** - Remove all local state, use only Context
3. **Don't forget cleanup** - Provider handles WebSocket cleanup, remove any manual cleanup
4. **Don't break other features** - Dashboard has PRD, Tasks, Blockers - keep them working
5. **Don't skip performance optimizations** - React.memo and useMemo are critical for 10 agents
6. **Don't forget connection indicator** - Users need to know when disconnected

### Dashboard Migration Checklist

**Before Starting**:
- [ ] Read full Dashboard.tsx to understand structure
- [ ] Identify all local state variables
- [ ] Map local state to Context equivalents
- [ ] Identify WebSocket handlers to remove

**During Migration**:
- [ ] Import useAgentState hook
- [ ] Replace `const [agents, setAgents]` with `const { agents }` from hook
- [ ] Replace `const [tasks, setTasks]` with `const { tasks }` from hook
- [ ] Replace `const [activity, setActivity]` with `const { activity }` from hook
- [ ] Replace `const [projectProgress, setProjectProgress]` with `const { projectProgress }`
- [ ] Get `wsConnected` from hook
- [ ] Remove WebSocket useEffect (lines ~84-270)
- [ ] Remove local state initialization useEffects
- [ ] Add connection indicator in UI
- [ ] Add React.memo to AgentCard
- [ ] Add useMemo for activeAgents filter
- [ ] Add useCallback for onAgentClick

**After Migration**:
- [ ] No TypeScript errors
- [ ] No console warnings
- [ ] Tests passing
- [ ] Dashboard renders correctly
- [ ] Agents display correctly
- [ ] Connection indicator works
- [ ] Real-time updates work (test with WebSocket)
- [ ] No performance issues
- [ ] Code is cleaner (~200 lines removed)

---

## 🎉 You've Got This!

**Foundation is solid**:
- ✅ Types defined
- ✅ Reducer battle-tested
- ✅ Context working perfectly
- ✅ Hook provides clean API

**Phase 4 is straightforward**:
- Map messages to actions (simple switch statement)
- Connect WebSocket to dispatch (one useEffect)
- Test with MSW (pattern well-established)

**Expected Time**: 1-1.5 days for experienced developer

**When Done**: System will have real-time updates! 🚀

---

## 📞 Questions?

- **Architecture questions**: See `research.md`
- **Type questions**: See `data-model.md` and `types/agentState.ts`
- **Pattern questions**: Look at existing test files
- **WebSocket format**: See `contracts/agent-state-api.ts`

---

**Good luck! The foundation is ready, now let's make it real-time!** 🎯
