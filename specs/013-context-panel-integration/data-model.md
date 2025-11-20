# Data Model: Context Panel Integration

**Feature**: 013-context-panel-integration
**Date**: 2025-11-19

## Overview

This feature is a **pure UI integration** with no database changes or new API endpoints. The data model consists entirely of frontend component state and TypeScript interfaces.

## Frontend State Model

### Dashboard Component State

```typescript
/**
 * Dashboard tab selection state
 */
type DashboardTab = 'overview' | 'context';

/**
 * Dashboard local state
 */
interface DashboardState {
  /** Currently active tab */
  activeTab: DashboardTab;

  /** Selected agent ID for context view (null = no selection) */
  selectedAgentId: string | null;
}
```

**State Management**: Local component state using React useState
**Persistence**: None (ephemeral UI state, resets on page refresh)
**Validation**: TypeScript strict mode ensures type safety

### Agent Card Props (Enhanced)

```typescript
/**
 * Agent card properties (MODIFIED)
 */
interface AgentCardProps {
  /** Agent data to display */
  agent: Agent;

  /** Optional click handler for navigation to context view */
  onClick?: () => void; // NEW PROP
}
```

**Change**: Added optional `onClick` handler to enable navigation from agent card to context tab

**Backward Compatibility**: ✅ Optional prop, existing usages continue to work

## Data Flow

### 1. Tab Switching Flow

```
User clicks "Context" tab
  ↓
setActiveTab('context') called
  ↓
React re-renders Dashboard
  ↓
Conditional render shows Context panel
  ↓
Agent selector dropdown visible
```

**State Mutation**: Single setter, synchronous update
**Side Effects**: None (pure state change)

### 2. Agent Selection Flow

```
User selects agent from dropdown
  ↓
setSelectedAgentId(agentId) called
  ↓
React re-renders Context panel area
  ↓
ContextPanel receives new agentId prop
  ↓
ContextPanel fetches data via existing API
```

**State Mutation**: Single setter, synchronous update
**Side Effects**: ContextPanel triggers SWR fetch (already implemented)

### 3. Agent Card Navigation Flow

```
User clicks agent card in Overview tab
  ↓
onClick handler called
  ↓
setActiveTab('context') + setSelectedAgentId(agent.id)
  ↓
React re-renders with Context tab active
  ↓
ContextPanel shows data for clicked agent
```

**State Mutation**: Two setters, batched by React 18
**Side Effects**: Tab switch + agent pre-selection

## Existing Data Models (No Changes)

### Agent Model (from useAgentState hook)

```typescript
/**
 * Agent entity (EXISTING - no changes)
 */
interface Agent {
  id: string;
  type: string;
  status: 'idle' | 'working' | 'blocked';
  current_task?: string;
  progress?: number;
  // ... other fields
}
```

**Source**: Already provided by `useAgentState()` hook
**Usage**: Populate agent selector dropdown, render agent cards

### Context Stats (from ContextPanel)

```typescript
/**
 * Context statistics (EXISTING - no changes)
 */
interface ContextStats {
  agent_id: string;
  project_id: number;
  hot_count: number;
  warm_count: number;
  cold_count: number;
  total_tokens: number;
  token_usage_percentage: number;
}
```

**Source**: Fetched by ContextPanel via `fetchContextStats()` API
**Usage**: Displayed by ContextPanel, ContextTierChart, ContextItemList

## Validation Rules

### Tab State
- **Valid values**: 'overview' | 'context'
- **Default**: 'overview'
- **Validation**: TypeScript enum ensures type safety
- **Error handling**: N/A (controlled by type system)

### Agent Selection
- **Valid values**: string (agent ID) | null
- **Default**: null (no selection)
- **Validation**: Must match an agent ID from agents array
- **Error handling**:
  - If selected agent disappears from list → show "Agent not found" message
  - If agents array empty → disable dropdown, show "No agents available"

## State Transitions

### Tab State Machine

```
Initial State: overview

overview → context (user clicks Context tab)
context → overview (user clicks Overview tab)
```

**Invariant**: activeTab is always one of the two valid values

### Agent Selection State Machine

```
Initial State: null

null → agentId (user selects from dropdown)
agentId → null (user deselects or agent disappears)
agentId → anotherAgentId (user selects different agent)
```

**Invariant**: selectedAgentId is either null or a valid agent ID string

## Performance Considerations

### State Updates
- **Tab switching**: O(1) - single state update
- **Agent selection**: O(1) - single state update
- **Agent card click**: O(1) - two state updates, batched by React 18

### Re-renders
- **Tab switch**: Re-renders Dashboard only
- **Agent selection**: Re-renders Context panel area + ContextPanel
- **Optimization**: Use React.memo on ContextPanel to prevent re-renders when agentId unchanged

## Testing Data

### Test Fixtures

```typescript
/**
 * Mock agents for testing
 */
const mockAgents: Agent[] = [
  {
    id: 'agent-001',
    type: 'backend',
    status: 'working',
    current_task: 'Implementing auth',
    progress: 0.5,
  },
  {
    id: 'agent-002',
    type: 'frontend',
    status: 'idle',
  },
  {
    id: 'agent-003',
    type: 'test',
    status: 'blocked',
    current_task: 'Waiting for API',
  },
];

/**
 * Mock context stats for testing
 */
const mockContextStats: ContextStats = {
  agent_id: 'agent-001',
  project_id: 123,
  hot_count: 20,
  warm_count: 45,
  cold_count: 10,
  total_tokens: 50000,
  token_usage_percentage: 27.8,
};
```

## Edge Cases

### Empty States
1. **No agents available**:
   - Dropdown disabled
   - Message: "No agents available. Start a project to create agents."

2. **No agent selected**:
   - ContextPanel not rendered
   - Message: "Select an agent to view context"

3. **Selected agent disappears** (e.g., agent stopped):
   - Clear selectedAgentId → null
   - Show message: "Agent no longer available. Select another agent."

### Error States
1. **ContextPanel API error**:
   - Handled by ContextPanel component (already implemented)
   - Shows error message in panel

2. **Invalid agent ID**:
   - Dropdown validation prevents invalid selection
   - If occurs (race condition), clear selection

## No Database Changes

This feature requires **ZERO** database changes:
- ✅ No new tables
- ✅ No schema migrations
- ✅ No new columns
- ✅ No new indexes

All data comes from:
- **Frontend state**: Tab selection, agent selection (ephemeral)
- **Existing APIs**: Agent list (useAgentState), context stats (ContextPanel)

## No API Changes

This feature requires **ZERO** new API endpoints:
- ✅ Existing: `GET /api/agents/:id/context/stats?project_id=:projectId`
- ✅ Existing: `GET /api/agents/:id/context/items?project_id=:projectId`
- ✅ Existing: WebSocket events for agent state (useAgentState)

All backend functionality already implemented in **007-context-management**.

## Summary

**Data Model Complexity**: MINIMAL
- 2 local state variables (activeTab, selectedAgentId)
- 1 optional prop addition (AgentCard onClick)
- 0 database changes
- 0 API changes
- 0 new data structures

**Validation Strategy**: TypeScript strict mode + React controlled components
**Testing Strategy**: Unit tests with mock data, no API mocking needed (SWR already tested)

This is a **pure UI integration feature** with trivial data model requirements.
