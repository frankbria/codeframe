# Feature Specification: Context Panel Integration

**Feature ID**: 013
**Feature Name**: Context Panel Integration
**Sprint**: 9.5 - Critical UX Fixes
**Priority**: P0 - Provides transparency into context management
**Effort**: 3 hours

## Problem Statement

### Current Behavior

```
ContextPanel.tsx exists (170 lines) ✅
ContextTierChart.tsx exists ✅
ContextItemList.tsx exists ✅
↓
Dashboard.tsx NEVER imports them ❌
↓
Users have ZERO visibility into:
- Flash saves (happen silently)
- What's in HOT/WARM/COLD tiers
- Why context was pruned
- Token usage vs limits
↓
Complexity score: 10/10 - "Feature exists but completely hidden"
```

### Expected Behavior

```
Dashboard → Tabs: [Overview] [Agents] [Context] [Settings]
↓
User clicks "Context" tab
↓
ContextPanel shows:
- Token usage: 50K / 180K (28%)
- Tier distribution chart
- HOT: 20 items (30K tokens)
- WARM: 45 items (15K tokens)
- COLD: 10 items (5K tokens)
↓
User understands what's in memory
```

## Scope

### Frontend Changes

#### Update Dashboard Component (`web-ui/src/components/Dashboard.tsx`)

**Current Structure** (lines 109-313):
- Header with project name, status, phase
- Progress section
- Agent cards section
- Blocker panel
- Activity feed
- Chat interface

**Add Tabbed Interface**:

1. **Import Dependencies**:
```tsx
import { ContextPanel } from './context/ContextPanel';
import { Tab } from '@headlessui/react';
```

2. **Add Tab State**:
```tsx
const [selectedTab, setSelectedTab] = useState<'overview' | 'context'>('overview');
const [selectedAgentForContext, setSelectedAgentForContext] = useState<string | null>(null);
```

3. **Render Tabs**: See implementation details in sprint doc (lines 913-1046)

4. **Add Click Handler to AgentCard**:
```tsx
// In AgentCard.tsx, add onClick prop
interface AgentCardProps {
  agent: Agent;
  onClick?: () => void;
}

export function AgentCard({ agent, onClick }: AgentCardProps) {
  return (
    <div
      onClick={onClick}
      className="p-4 border rounded-lg hover:shadow-md transition-shadow cursor-pointer"
    >
      {/* ... existing content ... */}
    </div>
  );
}
```

**Alternative**: Collapsible Section (if tabs not preferred) - see lines 1068-1081 in sprint doc

## User Stories

### Story 1: View Context Tab (P1 - Critical)
**As a** technical user
**I want** to see a "Context" tab in the Dashboard
**So that** I can access context management features

**Acceptance Criteria**:
- [ ] Dashboard displays tabs: "Overview" and "Context"
- [ ] Clicking "Context" tab switches view
- [ ] Tab state persists during session
- [ ] Active tab is visually distinct

**Test Scenarios**:
```tsx
describe('Dashboard - Context Tab', () => {
  it('renders Overview tab by default');
  it('switches to Context tab on click');
  it('shows active tab with highlighted style');
  it('maintains tab state during navigation');
});
```

### Story 2: Select Agent for Context View (P1 - Critical)
**As a** technical user
**I want** to select which agent's context to view
**So that** I can inspect memory for specific agents

**Acceptance Criteria**:
- [ ] Agent selector dropdown visible in Context tab
- [ ] Dropdown lists all active agents
- [ ] Selecting agent updates ContextPanel
- [ ] Default shows "All Agents" or prompt to select

**Test Scenarios**:
```tsx
describe('Context Tab - Agent Selector', () => {
  it('displays agent selector dropdown');
  it('lists all active agents in dropdown');
  it('updates ContextPanel when agent selected');
  it('shows placeholder when no agent selected');
});
```

### Story 3: View Context Statistics (P1 - Critical)
**As a** technical user
**I want** to see token usage and tier distribution
**So that** I understand what's in agent memory

**Acceptance Criteria**:
- [ ] ContextPanel displays for selected agent
- [ ] Token usage shown (e.g., "50K / 180K (28%)")
- [ ] Tier distribution chart visible
- [ ] Count of items per tier (HOT/WARM/COLD)

**Test Scenarios**:
```tsx
describe('ContextPanel Rendering', () => {
  it('displays token usage stats');
  it('shows tier distribution chart');
  it('displays item counts per tier');
  it('handles empty context gracefully');
});
```

### Story 4: Navigate to Context via Agent Card (P2 - Enhancement)
**As a** technical user
**I want** to click an agent card to view its context
**So that** I can quickly inspect agent memory

**Acceptance Criteria**:
- [ ] Agent cards are clickable
- [ ] Clicking agent card switches to Context tab
- [ ] Selected agent is pre-populated in dropdown
- [ ] Visual feedback on hover

**Test Scenarios**:
```tsx
describe('Agent Card Navigation', () => {
  it('makes agent cards clickable');
  it('switches to Context tab on click');
  it('pre-selects agent in dropdown');
  it('shows hover state on agent card');
});
```

## API Requirements

### Existing Endpoints (Verify)
- `GET /api/agents/:id/context/stats?project_id=:projectId` - Get context stats
- `GET /api/agents/:id/context/items?project_id=:projectId&tier=:tier` - Get context items

**No new endpoints required** - all backend functionality exists in 007-context-management

## Dependencies

### External
- `@headlessui/react` - For tab UI (check if installed)

### Internal
- ContextPanel component (already exists at `web-ui/src/components/context/ContextPanel.tsx`)
- ContextTierChart component (already exists)
- ContextItemList component (already exists)

## Testing Requirements

### Unit Tests (Target: ≥85% coverage)

**Dashboard Tab Tests** (`web-ui/__tests__/components/Dashboard.test.tsx`):
- Tab rendering (Overview, Context)
- Tab switching functionality
- Active tab highlighting
- Tab state persistence

**Agent Selector Tests**:
- Dropdown rendering
- Agent list population
- Selection handling
- Empty state

**ContextPanel Integration Tests**:
- Panel renders with agent data
- Updates when agent changed
- Error handling (no data, API failure)
- Loading states

### Integration Tests

**Full Workflow**:
1. Navigate to Dashboard
2. Click "Context" tab
3. Select agent from dropdown
4. Verify ContextPanel renders
5. Verify tier chart shows data
6. Verify context items list populated

**Agent Card Workflow**:
1. Click agent card in Overview tab
2. Verify navigation to Context tab
3. Verify agent pre-selected in dropdown
4. Verify ContextPanel shows correct data

## Non-Goals (Out of Scope)

- Creating new context management features (already implemented)
- Modifying ContextPanel internals
- Adding new API endpoints
- Context item editing/deletion
- Real-time WebSocket updates for context changes

## Deliverables

- [ ] Tabbed interface in Dashboard (Overview + Context)
- [ ] Import ContextPanel, ContextTierChart, ContextItemList
- [ ] Agent selector dropdown in Context tab
- [ ] Click agent card → switches to Context tab with that agent selected
- [ ] Context stats visible (token usage, tier distribution)
- [ ] Unit tests (≥85% coverage)
- [ ] Manual test: verify all context components render correctly

## Definition of Done

- [ ] All user stories tested and passing
- [ ] ≥85% test coverage on new code
- [ ] Manual testing checklist 100% complete
- [ ] No console errors or warnings
- [ ] Tabs keyboard accessible (Tab key navigation)
- [ ] No regressions in existing Dashboard functionality
- [ ] Code reviewed (self or pair)
- [ ] Documentation updated (inline comments)

## References

- [Sprint 9.5 Specification](../../sprints/sprint-09.5-critical-ux-fixes.md) - Feature 4 details (lines 840-1098)
- [007 Context Management](../007-context-management/) - Backend implementation
- [ContextPanel Source](../../web-ui/src/components/context/ContextPanel.tsx) - Existing component
- [Dashboard Source](../../web-ui/src/components/Dashboard.tsx) - Component to modify
