# Quickstart: Context Panel Integration

**Feature**: 013-context-panel-integration
**Estimated Time**: 3 hours
**Difficulty**: Low (UI integration, no backend changes)

## Prerequisites

- Node.js 20+ and npm installed
- CodeFRAME project set up with agents running
- Dashboard accessible at `http://localhost:8080`

## Quick Overview

This feature adds a **Context tab** to the Dashboard that displays:
- Agent context statistics (token usage, tier distribution)
- HOT/WARM/COLD tier breakdown
- Context item details

**What's New**:
- Two-tab interface: **Overview** (existing) + **Context** (new)
- Agent selector dropdown in Context tab
- Click agent card → navigate to its context view

## 30-Second Demo

```bash
# 1. Start dashboard
codeframe serve

# 2. Open browser to http://localhost:8080

# 3. Navigate to a project with active agents

# 4. Click "Context" tab (new!)

# 5. Select an agent from dropdown

# 6. View context stats:
#    - Token usage: 50K / 180K (28%)
#    - HOT: 20 items
#    - WARM: 45 items
#    - COLD: 10 items

# 7. Click tier chart to drill down

# 8. Click agent card in Overview → jumps to Context tab
```

## Step-by-Step Implementation

### Phase 1: Add Tab UI to Dashboard (30 min)

**File**: `web-ui/src/components/Dashboard.tsx`

1. **Add state for tabs**:
```tsx
const [activeTab, setActiveTab] = useState<'overview' | 'context'>('overview');
const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
```

2. **Add tab buttons** (before existing content):
```tsx
<div className="flex border-b border-gray-200 mb-6">
  <button
    onClick={() => setActiveTab('overview')}
    className={`px-6 py-3 font-medium transition-colors ${
      activeTab === 'overview'
        ? 'text-blue-600 border-b-2 border-blue-600'
        : 'text-gray-600 hover:text-gray-900'
    }`}
    role="tab"
    aria-selected={activeTab === 'overview'}
  >
    📊 Overview
  </button>
  <button
    onClick={() => setActiveTab('context')}
    className={`px-6 py-3 font-medium transition-colors ${
      activeTab === 'context'
        ? 'text-blue-600 border-b-2 border-blue-600'
        : 'text-gray-600 hover:text-gray-900'
    }`}
    role="tab"
    aria-selected={activeTab === 'context'}
  >
    🧠 Context
  </button>
</div>
```

3. **Wrap existing content in Overview panel**:
```tsx
{activeTab === 'overview' && (
  <div role="tabpanel" aria-labelledby="overview-tab">
    {/* ALL existing Dashboard content goes here */}
  </div>
)}
```

4. **Test**: Tabs render, clicking switches active tab

---

### Phase 2: Add Agent Selector + ContextPanel (45 min)

**File**: `web-ui/src/components/Dashboard.tsx`

1. **Import ContextPanel**:
```tsx
import { ContextPanel } from './context/ContextPanel';
```

2. **Add Context tab panel**:
```tsx
{activeTab === 'context' && (
  <div role="tabpanel" aria-labelledby="context-tab">
    <div className="bg-white rounded-lg shadow p-6">
      {/* Agent Selector */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Select Agent
        </label>
        <select
          value={selectedAgentId || ''}
          onChange={(e) => setSelectedAgentId(e.target.value || null)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
        >
          <option value="">-- Select an agent --</option>
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.type} Agent ({agent.status})
            </option>
          ))}
        </select>
      </div>

      {/* ContextPanel */}
      {selectedAgentId ? (
        <ContextPanel
          agentId={selectedAgentId}
          projectId={projectId}
          refreshInterval={5000}
        />
      ) : (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">Select an agent to view context</p>
          <p className="text-sm">
            Context items show what's in agent memory (HOT/WARM/COLD tiers)
          </p>
        </div>
      )}
    </div>
  </div>
)}
```

3. **Test**:
   - Switch to Context tab
   - Dropdown shows agents
   - Select agent → ContextPanel renders
   - Stats display correctly

---

### Phase 3: Add Agent Card Navigation (30 min)

**File**: `web-ui/src/components/AgentCard.tsx`

1. **Update props interface**:
```tsx
interface AgentCardProps {
  agent: Agent;
  onClick?: () => void; // NEW
}

export default function AgentCard({ agent, onClick }: AgentCardProps) {
```

2. **Add onClick handler + styling**:
```tsx
<div
  onClick={onClick}
  className={`p-4 border rounded-lg transition-shadow ${
    onClick ? 'cursor-pointer hover:shadow-lg' : ''
  }`}
>
  {/* existing card content */}
</div>
```

**File**: `web-ui/src/components/Dashboard.tsx`

3. **Wire onClick in Overview tab**:
```tsx
{agents.map((agent) => (
  <AgentCard
    key={agent.id}
    agent={agent}
    onClick={() => {
      setSelectedAgentId(agent.id);
      setActiveTab('context');
    }}
  />
))}
```

4. **Test**:
   - Click agent card in Overview
   - Switches to Context tab
   - Agent pre-selected in dropdown
   - ContextPanel shows correct data

---

### Phase 4: Write Tests (1 hour 15 min)

**File**: `web-ui/__tests__/components/Dashboard.test.tsx`

```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import Dashboard from '@/components/Dashboard';

describe('Dashboard Tabs', () => {
  it('renders Overview tab by default', () => {
    render(<Dashboard projectId={123} />);
    expect(screen.getByRole('tab', { name: /overview/i, selected: true })).toBeInTheDocument();
  });

  it('switches to Context tab when clicked', () => {
    render(<Dashboard projectId={123} />);
    const contextTab = screen.getByRole('tab', { name: /context/i });
    fireEvent.click(contextTab);
    expect(contextTab).toHaveAttribute('aria-selected', 'true');
  });

  it('displays ContextPanel when agent selected', () => {
    render(<Dashboard projectId={123} />);
    fireEvent.click(screen.getByRole('tab', { name: /context/i }));

    const dropdown = screen.getByLabelText(/select agent/i);
    fireEvent.change(dropdown, { target: { value: 'agent-001' } });

    expect(screen.getByText(/token usage/i)).toBeInTheDocument();
  });
});

describe('Agent Card Navigation', () => {
  it('switches to Context tab when agent card clicked', () => {
    render(<Dashboard projectId={123} />);
    const agentCard = screen.getByText(/backend agent/i).closest('div');
    fireEvent.click(agentCard);

    const contextTab = screen.getByRole('tab', { name: /context/i });
    expect(contextTab).toHaveAttribute('aria-selected', 'true');
  });
});
```

**Run tests**:
```bash
cd web-ui
npm test -- Dashboard.test.tsx
```

**Expected**: 20+ tests passing

---

## Manual Testing Checklist

### Tab Functionality
- [ ] Dashboard loads with Overview tab active
- [ ] Click Context tab → switches to Context view
- [ ] Click Overview tab → switches back
- [ ] Active tab has blue border + text
- [ ] Tab switching is smooth (<100ms)

### Agent Selector
- [ ] Dropdown shows all active agents
- [ ] "Select an agent" placeholder shown initially
- [ ] Selecting agent loads ContextPanel
- [ ] Changing agent updates ContextPanel
- [ ] Empty state shown when no agent selected

### Context Display
- [ ] Token usage displayed (e.g., "50K / 180K (28%)")
- [ ] Tier counts shown (HOT/WARM/COLD)
- [ ] Tier chart renders correctly
- [ ] Context items list populated
- [ ] Auto-refresh works (5 second interval)

### Agent Card Navigation
- [ ] Agent cards in Overview tab are clickable
- [ ] Hover shows shadow effect
- [ ] Click agent → switches to Context tab
- [ ] Clicked agent pre-selected in dropdown
- [ ] ContextPanel shows correct agent data

### Edge Cases
- [ ] No agents → dropdown disabled, message shown
- [ ] Selected agent disappears → selection cleared
- [ ] API error → error message in ContextPanel
- [ ] Keyboard navigation works (Tab, Arrow keys)
- [ ] Screen reader announces tab changes

---

## Troubleshooting

### Tab buttons not rendering
**Cause**: State initialization issue
**Fix**: Check `useState` is called at top level of component

### ContextPanel shows "undefined"
**Cause**: `selectedAgentId` is empty string instead of null
**Fix**: Use `e.target.value || null` in onChange handler

### Agent selector empty
**Cause**: `agents` array not populated
**Fix**: Verify `useAgentState()` hook is working, check WebSocket connection

### Clicking agent card doesn't navigate
**Cause**: `onClick` prop not passed
**Fix**: Ensure AgentCard receives `onClick={() => {...}}` in Overview tab

### Tests failing: "Cannot find ContextPanel"
**Cause**: Import path incorrect
**Fix**: Use `@/components/context/ContextPanel` with Next.js path alias

---

## Performance Tips

1. **Lazy render**: Don't render hidden tab panel
   ```tsx
   {activeTab === 'context' && <ContextPanel ... />}
   // NOT: <div style={{display: activeTab === 'context' ? 'block' : 'none'}}>
   ```

2. **Memoize ContextPanel**: Prevent re-renders when agentId unchanged
   ```tsx
   const MemoizedContextPanel = React.memo(ContextPanel);
   ```

3. **Debounce dropdown**: If needed (probably not for 10 agents)
   ```tsx
   const debouncedSelection = useDebounce(selectedAgentId, 300);
   ```

---

## Next Steps

After implementation:

1. **Run full test suite**:
   ```bash
   cd web-ui
   npm test
   npm run type-check
   npm run lint
   ```

2. **Manual testing**: Go through checklist above

3. **Create PR**: Reference spec.md and sprint doc

4. **Update CLAUDE.md**: Add Context tab to UI navigation section

---

## Quick Reference

### Files Modified
- `web-ui/src/components/Dashboard.tsx` (~80 lines added)
- `web-ui/src/components/AgentCard.tsx` (~5 lines modified)
- `web-ui/__tests__/components/Dashboard.test.tsx` (~40 lines added)
- `web-ui/__tests__/components/AgentCard.test.tsx` (~20 lines added)

### Files Imported (No Changes)
- `web-ui/src/components/context/ContextPanel.tsx`
- `web-ui/src/components/context/ContextTierChart.tsx`
- `web-ui/src/components/context/ContextItemList.tsx`

### Estimated Lines of Code
- **New code**: ~200 lines
- **Tests**: ~60 lines
- **Total**: ~260 lines

### Time Breakdown
- Phase 1 (Tabs): 30 min
- Phase 2 (Context Panel): 45 min
- Phase 3 (Navigation): 30 min
- Phase 4 (Tests): 1h 15min
- **Total**: 3 hours

---

**Happy Coding!** 🚀

For questions or issues, refer to:
- [Feature Spec](./spec.md)
- [Implementation Plan](./plan.md)
- [Sprint 9.5 Doc](../../sprints/sprint-09.5-critical-ux-fixes.md)
- [007 Context Management](../007-context-management/)
