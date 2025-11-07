# Phase 6 Quick Start Guide

**For Next AI Agent: Start Here!**

---

## 📋 Context

You're taking over at **Phase 6 of 8** in the Dashboard Multi-Agent State Management feature.

**What's Done** (Phases 1-5):
- ✅ Complete TypeScript type system
- ✅ Battle-tested reducer with conflict resolution
- ✅ React Context + custom hooks
- ✅ WebSocket real-time updates
- ✅ Automatic reconnection with exponential backoff
- ✅ **90/90 tests passing**

**Your Mission** (Phase 6):
Migrate the existing 642-line Dashboard component to use the new state management system.

---

## 🎯 Quick Overview

**Current State**: Dashboard uses local `useState` and manual WebSocket handling

**Target State**: Dashboard uses `useAgentState` hook, Provider handles everything

**Impact**: ~200 lines removed, cleaner code, automatic real-time updates

**Estimated Time**: 1-1.5 days

---

## 🚀 Getting Started (5 Minutes)

### 1. Read the Current Dashboard

```bash
cd /home/frankbria/projects/codeframe
cat web-ui/src/components/Dashboard.tsx | less
```

**Key sections to understand**:
- Lines 66-69: Local state (`agents`, `tasks`, `activity`, `projectProgress`)
- Lines 84-270: WebSocket message handlers (TO BE REMOVED)
- Lines 544-560: AgentCard rendering (WILL BE SIMPLIFIED)

### 2. Understand What's Available

The infrastructure is ready:

```typescript
// This hook gives you everything:
import { useAgentState } from '@/hooks/useAgentState';

const {
  // State
  agents,
  tasks,
  activity,
  projectProgress,
  wsConnected,

  // Derived state (memoized)
  activeAgents,
  idleAgents,
  activeTasks,

  // Actions (if needed)
  updateAgent,
  // ... more actions
} = useAgentState();
```

The Provider handles:
- ✅ Initial data fetching (SWR)
- ✅ WebSocket connection
- ✅ Message mapping
- ✅ State updates
- ✅ Reconnection logic

### 3. Review Tasks

```bash
cat specs/005-project-schema-refactoring/tasks.md | grep -A 50 "Phase 6"
```

**19 tasks total**:
- T096-T101: Tests (6 tasks)
- T102-T114: Implementation (13 tasks)

---

## 📝 Step-by-Step Implementation

### Step 1: Update Beads (1 min)

```bash
bd update cf-791 --status in_progress
```

### Step 2: Create Test Files (15 min)

**File 1**: `web-ui/__tests__/components/Dashboard.test.tsx`

```typescript
import { render, screen } from '@testing-library/react';
import { AgentStateProvider } from '@/components/AgentStateProvider';
import Dashboard from '@/components/Dashboard';

describe('Dashboard with AgentStateProvider', () => {
  it('renders with context state', () => {
    render(
      <AgentStateProvider projectId={1}>
        <Dashboard projectId={1} />
      </AgentStateProvider>
    );

    expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();
  });

  // Add more tests (T096-T099)
});
```

**File 2**: `web-ui/__tests__/integration/dashboard-realtime-updates.test.ts`

```typescript
describe('Dashboard Real-time Updates', () => {
  it('updates when WebSocket message arrives', async () => {
    // Test real-time updates (T100-T101)
  });
});
```

### Step 3: Migrate Dashboard Component (60 min)

**A. Add the hook import**:

```typescript
// Add to imports at top of Dashboard.tsx
import { useAgentState } from '@/hooks/useAgentState';
```

**B. Replace local state** (Lines 66-69):

```typescript
// BEFORE (REMOVE):
const [agents, setAgents] = useState<Agent[]>([]);
const [tasks, setTasks] = useState<Task[]>([]);
const [activity, setActivity] = useState<ActivityItem[]>([]);
const [projectProgress, setProjectProgress] = useState<any>(null);

// AFTER (ADD):
const {
  agents,
  tasks,
  activity,
  projectProgress,
  wsConnected,
  activeAgents,
} = useAgentState();
```

**C. Remove WebSocket handlers** (Lines 84-270):

Delete the entire `useEffect(() => { const ws = getWebSocketClient(); ... }, [...])` block.

Provider already handles all WebSocket logic!

**D. Remove SWR initialization** (Lines 72-82):

Delete useEffect hooks that do:
```typescript
useEffect(() => {
  if (agentsData) {
    setAgents(agentsData);
  }
}, [agentsData]);
```

Provider's SWR handles this!

**E. Add connection indicator** (Near agents section):

```typescript
<div className="flex items-center gap-2 mb-4">
  <h2 className="text-xl font-bold">Active Agents</h2>
  {wsConnected ? (
    <span className="text-green-500 text-sm">● Connected</span>
  ) : (
    <span className="text-red-500 text-sm">● Disconnected</span>
  )}
</div>
```

**F. Simplify agent rendering** (Line 546):

```typescript
// BEFORE:
{(agents.length > 0 ? agents : agentsData || []).map((agent) => (

// AFTER (much simpler):
{agents.map((agent) => (
```

### Step 4: Performance Optimizations (20 min)

**A. Memoize AgentCard** (`web-ui/src/components/AgentCard.tsx`):

```typescript
import { memo } from 'react';

// At the bottom of AgentCard.tsx:
export default memo(AgentCard, (prev, next) => {
  return prev.agent.id === next.agent.id &&
         prev.agent.timestamp === next.agent.timestamp;
});
```

**B. Add useMemo for filters** (In Dashboard.tsx):

```typescript
import { useMemo, useCallback } from 'react';

// Use activeAgents from hook (already memoized!)
// or create custom filters:
const workingAgents = useMemo(
  () => agents.filter(a => a.status === 'working'),
  [agents]
);
```

**C. Add useCallback for handlers**:

```typescript
const handleAgentClick = useCallback((agentId: string) => {
  console.log('Agent clicked:', agentId);
}, []);
```

### Step 5: Wrap with Provider (5 min)

**Find where Dashboard is rendered** (probably in `pages/` or parent component):

```typescript
// BEFORE:
<Dashboard projectId={projectId} />

// AFTER:
<AgentStateProvider projectId={projectId}>
  <Dashboard projectId={projectId} />
</AgentStateProvider>
```

### Step 6: Test Everything (15 min)

```bash
# Run tests
cd web-ui
npm test Dashboard.test.tsx
npm test dashboard-realtime-updates.test.ts

# Type check
npm run type-check

# Test in browser (if backend available)
npm run dev
# Open http://localhost:3000
# Check: agents display, connection indicator works, real-time updates work
```

---

## ✅ Success Criteria

Before marking complete:

**Functionality**:
- [ ] Dashboard renders without errors
- [ ] Agents display correctly
- [ ] Connection indicator shows correct status
- [ ] Real-time updates work (agents update when WebSocket messages arrive)
- [ ] No duplicate state or logic

**Code Quality**:
- [ ] ~200 lines removed (WebSocket handlers)
- [ ] No TypeScript errors
- [ ] No console warnings
- [ ] All tests passing

**Performance**:
- [ ] AgentCard is memoized
- [ ] No unnecessary re-renders
- [ ] Updates feel instant (< 50ms)

---

## 🚨 Common Issues & Solutions

### Issue: "useAgentState must be used within AgentStateProvider"

**Solution**: Wrap Dashboard with `<AgentStateProvider>` in parent component

### Issue: Agents not displaying

**Solution**: Check that Provider's SWR is fetching data. Look for API errors in console.

### Issue: WebSocket not connecting

**Solution**: Check `NEXT_PUBLIC_WS_URL` environment variable. Provider handles connection automatically.

### Issue: Dashboard has type errors after migration

**Solution**: Make sure you're using types from `@/types/agentState`, not the old `@/types`

### Issue: Too many re-renders

**Solution**: Did you add React.memo to AgentCard? Did you use useCallback for handlers?

---

## 📚 Reference Files

**Read These**:
- `HANDOFF_SUMMARY.md` - Complete context
- `tasks.md` - Task details (T096-T114)
- `web-ui/src/hooks/useAgentState.ts` - Hook API reference
- `web-ui/src/components/AgentStateProvider.tsx` - How Provider works

**For Patterns**:
- `web-ui/__tests__/hooks/useAgentState.test.tsx` - Hook testing patterns
- `web-ui/__tests__/components/AgentStateProvider.test.tsx` - Provider testing patterns

---

## 🎯 Mark Complete

When done:

```bash
# Update tasks.md (mark T096-T114 as [X])
cd /home/frankbria/projects/codeframe

# Update beads
bd update cf-791 --status closed

# Commit
git add .
git commit -m "feat(dashboard): migrate to AgentStateProvider

- Replace local state with useAgentState hook
- Remove redundant WebSocket handlers (~200 lines)
- Add connection status indicator
- Add performance optimizations (React.memo, useMemo)
- All tests passing

Tasks: T096-T114
Phase: 6/8 complete"
```

---

## 🎉 You've Got This!

The hard work is done (Phases 1-5). You're just connecting the dots!

**Remember**:
- Provider handles all complexity
- You're simplifying Dashboard, not adding features
- Tests will guide you
- ~200 lines will be removed (that's good!)

Good luck! 🚀
