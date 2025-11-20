# API Contracts: Context Panel Integration

**Feature**: 013-context-panel-integration
**Date**: 2025-11-19

## Overview

This feature is a **pure UI integration** with **ZERO new API endpoints**. All required APIs were implemented in **007-context-management** and are already in production.

## Existing API Endpoints (No Changes)

### 1. Get Context Statistics

**Endpoint**: `GET /api/agents/:agentId/context/stats`

**Query Parameters**:
- `project_id` (number, required): Project ID the agent is working on

**Response**:
```typescript
interface ContextStatsResponse {
  agent_id: string;
  project_id: number;
  hot_count: number;      // Number of HOT tier items
  warm_count: number;     // Number of WARM tier items
  cold_count: number;     // Number of COLD tier items
  total_tokens: number;   // Total token count across all tiers
  token_usage_percentage: number;  // Percentage of 180k limit
}
```

**Example**:
```bash
GET /api/agents/agent-001/context/stats?project_id=123

# Response:
{
  "agent_id": "agent-001",
  "project_id": 123,
  "hot_count": 20,
  "warm_count": 45,
  "cold_count": 10,
  "total_tokens": 50000,
  "token_usage_percentage": 27.8
}
```

**Consumed By**: `ContextPanel` component (via `fetchContextStats()`)

**Implementation**: Already exists in `codeframe/ui/app.py` (007-context-management)

---

### 2. Get Context Items

**Endpoint**: `GET /api/agents/:agentId/context/items`

**Query Parameters**:
- `project_id` (number, required): Project ID
- `tier` (string, optional): Filter by tier ('hot', 'warm', 'cold')
- `limit` (number, optional): Max items to return (default: 50)
- `offset` (number, optional): Pagination offset (default: 0)

**Response**:
```typescript
interface ContextItemsResponse {
  items: ContextItem[];
  total: number;
  has_more: boolean;
}

interface ContextItem {
  id: number;
  agent_id: string;
  project_id: number;
  item_type: string;  // 'task', 'code', 'error', 'prd_section', etc.
  content: string;
  importance_score: number;  // 0.0-1.0
  tier: 'hot' | 'warm' | 'cold';
  created_at: string;  // ISO 8601 timestamp
  last_accessed_at: string;  // ISO 8601 timestamp
}
```

**Example**:
```bash
GET /api/agents/agent-001/context/items?project_id=123&tier=hot&limit=20

# Response:
{
  "items": [
    {
      "id": 1,
      "agent_id": "agent-001",
      "project_id": 123,
      "item_type": "task",
      "content": "Implement JWT authentication",
      "importance_score": 0.95,
      "tier": "hot",
      "created_at": "2025-11-19T10:00:00Z",
      "last_accessed_at": "2025-11-19T14:30:00Z"
    },
    // ... more items
  ],
  "total": 20,
  "has_more": false
}
```

**Consumed By**: `ContextItemList` component

**Implementation**: Already exists in `codeframe/ui/app.py` (007-context-management)

---

## Frontend API Client (No Changes)

### Context API Module

**Location**: `web-ui/src/api/context.ts`

**Functions**:
```typescript
/**
 * Fetch context statistics for an agent (EXISTING)
 */
export async function fetchContextStats(
  agentId: string,
  projectId: number
): Promise<ContextStats> {
  const response = await fetch(
    `/api/agents/${agentId}/context/stats?project_id=${projectId}`
  );
  if (!response.ok) throw new Error('Failed to fetch context stats');
  return response.json();
}

/**
 * Fetch context items for an agent (EXISTING)
 */
export async function fetchContextItems(
  agentId: string,
  projectId: number,
  tier?: 'hot' | 'warm' | 'cold',
  limit = 50,
  offset = 0
): Promise<ContextItemsResponse> {
  const params = new URLSearchParams({
    project_id: String(projectId),
    limit: String(limit),
    offset: String(offset),
  });
  if (tier) params.set('tier', tier);

  const response = await fetch(
    `/api/agents/${agentId}/context/items?${params}`
  );
  if (!response.ok) throw new Error('Failed to fetch context items');
  return response.json();
}
```

**Status**: Already implemented and tested in 007-context-management

---

## WebSocket Events (No Changes)

### Agent State Events

**Event**: `agent_created`, `agent_status_changed`, `task_assigned`, etc.

**Payload**:
```typescript
interface WebSocketMessage {
  type: string;
  agent_id?: string;
  status?: string;
  // ... other fields
}
```

**Consumed By**: `useAgentState()` hook (provides agents array to Dashboard)

**Implementation**: Already exists in `AgentStateProvider` (Phase 5.2)

---

## Component Props Contracts (New)

### Dashboard Component (Modified)

```typescript
interface DashboardProps {
  projectId: number;  // EXISTING - no change
}
```

**No changes to props** - feature is internal to Dashboard component

---

### AgentCard Component (Modified)

```typescript
interface AgentCardProps {
  agent: Agent;        // EXISTING
  onClick?: () => void; // NEW - optional click handler
}
```

**Change**: Added optional `onClick` prop for navigation to context tab

**Backward Compatibility**: ✅ Optional prop, existing usages continue to work

**Usage**:
```tsx
// Overview tab - WITH onClick (navigates to context)
<AgentCard
  agent={agent}
  onClick={() => {
    setSelectedAgentId(agent.id);
    setActiveTab('context');
  }}
/>

// Other views - WITHOUT onClick (no navigation)
<AgentCard agent={agent} />
```

---

### ContextPanel Component (No Changes)

```typescript
interface ContextPanelProps {
  agentId: string;          // EXISTING
  projectId: number;        // EXISTING
  refreshInterval?: number; // EXISTING - default 5000ms
}
```

**No changes** - component used as-is

**Usage in Dashboard**:
```tsx
{selectedAgentId && (
  <ContextPanel
    agentId={selectedAgentId}
    projectId={projectId}
    refreshInterval={5000}
  />
)}
```

---

## Error Handling

All error handling is **already implemented** in existing components:

### ContextPanel Errors
- **API failure**: Shows error message in panel
- **Network timeout**: Retries with exponential backoff (SWR)
- **Invalid agent ID**: Returns 404, shows "Agent not found"

### Dashboard Errors
- **No agents available**: Shows empty state message
- **Agent disappears**: Clears selection, shows message

**No new error handling needed** - feature leverages existing patterns

---

## Testing Contracts

### Mock API Responses

```typescript
// Mock context stats
const mockContextStats: ContextStats = {
  agent_id: 'agent-001',
  project_id: 123,
  hot_count: 20,
  warm_count: 45,
  cold_count: 10,
  total_tokens: 50000,
  token_usage_percentage: 27.8,
};

// Mock context items
const mockContextItems: ContextItemsResponse = {
  items: [
    {
      id: 1,
      agent_id: 'agent-001',
      project_id: 123,
      item_type: 'task',
      content: 'Implement auth',
      importance_score: 0.95,
      tier: 'hot',
      created_at: '2025-11-19T10:00:00Z',
      last_accessed_at: '2025-11-19T14:30:00Z',
    },
  ],
  total: 1,
  has_more: false,
};
```

**Testing Strategy**: Mock API responses with MSW (already installed)

---

## Summary

**New API Endpoints**: 0
**Modified API Endpoints**: 0
**New WebSocket Events**: 0
**Modified Component Props**: 1 (AgentCard onClick - optional, backward compatible)

This feature requires **ZERO backend changes**. All APIs and data flows already exist from 007-context-management. The implementation is purely frontend integration.

**Contract Stability**: ✅ HIGH - All contracts already in production and tested
**Breaking Changes**: ✅ NONE - All changes are additive and backward compatible
