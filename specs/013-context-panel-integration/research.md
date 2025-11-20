# Research: Context Panel Integration

**Feature**: 013-context-panel-integration
**Date**: 2025-11-19
**Researcher**: Implementation Planning Agent

## Research Questions

1. **Tab UI Implementation**: What's the best approach for adding tabs to the Dashboard?
2. **State Management**: How to handle tab state and agent selection?
3. **Component Integration**: How to wire ContextPanel without modifying its internals?
4. **Testing Strategy**: How to test tab switching and navigation?

## Findings

### 1. Tab UI Implementation

**Decision**: Use native HTML + Tailwind CSS (no external library)

**Rationale**:
- **@headlessui/react NOT installed** in package.json
- Adding dependency increases bundle size (~15KB)
- Native implementation is simpler for 2-tab interface
- Tailwind provides excellent styling utilities
- Keyboard accessibility achievable with native HTML

**Alternatives Considered**:
- **@headlessui/react Tab component**: Rejected - adds dependency, overkill for 2 tabs
- **Radix UI Tabs**: Rejected - another dependency, heavier than needed
- **Custom React component**: Rejected - native HTML is simpler and more maintainable

**Implementation Pattern**:
```tsx
const [activeTab, setActiveTab] = useState<'overview' | 'context'>('overview');

// Tab buttons
<div className="flex border-b border-gray-200">
  <button
    onClick={() => setActiveTab('overview')}
    className={activeTab === 'overview' ? 'border-b-2 border-blue-600' : ''}
  >
    Overview
  </button>
  <button
    onClick={() => setActiveTab('context')}
    className={activeTab === 'context' ? 'border-b-2 border-blue-600' : ''}
  >
    Context
  </button>
</div>

// Tab panels
{activeTab === 'overview' && <OverviewContent />}
{activeTab === 'context' && <ContextContent />}
```

**Accessibility**:
- Use `role="tablist"`, `role="tab"`, `role="tabpanel"` ARIA attributes
- `aria-selected` on active tab
- Keyboard navigation: Arrow keys, Tab key, Enter/Space to activate
- `aria-labelledby` to connect panel with tab

### 2. State Management

**Decision**: Local component state with useState

**Rationale**:
- Tab state is UI-only, doesn't need global context
- Agent selection is Dashboard-scoped, not app-wide
- React's useState is sufficient and performant
- No need for Redux/Zustand/Context API overhead

**State Shape**:
```tsx
interface DashboardState {
  activeTab: 'overview' | 'context';
  selectedAgentId: string | null;
}

// In Dashboard.tsx
const [activeTab, setActiveTab] = useState<'overview' | 'context'>('overview');
const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
```

**Alternatives Considered**:
- **URL-based state** (e.g., `/projects/123?tab=context`): Rejected - adds complexity, not needed for ephemeral UI state
- **React Context**: Rejected - overkill for component-scoped state
- **Session storage**: Rejected - persistence not required, adds I/O overhead

### 3. Component Integration

**Decision**: Import and render ContextPanel as-is, no modifications

**Rationale**:
- ContextPanel already accepts `agentId` and `projectId` props
- Auto-refresh via `refreshInterval` prop already implemented
- Component is self-contained with its own data fetching
- Testing already exists (6 tests passing)

**Integration Pattern**:
```tsx
import { ContextPanel } from './context/ContextPanel';

// In Context tab panel
{selectedAgentId ? (
  <ContextPanel
    agentId={selectedAgentId}
    projectId={projectId}
    refreshInterval={5000}
  />
) : (
  <div>Select an agent to view context</div>
)}
```

**Agent Selector**:
- Use native `<select>` dropdown (accessible, semantic HTML)
- Populate from existing `agents` array (already available via useAgentState hook)
- No need for custom dropdown component

**AgentCard Enhancement**:
```tsx
// Add optional onClick prop
interface AgentCardProps {
  agent: Agent;
  onClick?: () => void; // NEW
}

// Make card clickable
<div
  onClick={onClick}
  className={`... ${onClick ? 'cursor-pointer hover:shadow-lg' : ''}`}
>
```

### 4. Testing Strategy

**Decision**: Unit tests with React Testing Library, no E2E needed

**Rationale**:
- Feature is pure UI, no backend integration
- React Testing Library excels at component interaction testing
- Tab switching and navigation are testable via user events
- E2E with Playwright unnecessary for UI-only changes

**Test Coverage**:
```tsx
// Dashboard.test.tsx
describe('Dashboard Tabs', () => {
  it('renders Overview tab by default');
  it('switches to Context tab when clicked');
  it('shows active tab styling');
  it('preserves tab state during re-renders');
  it('displays ContextPanel in Context tab');
  it('shows agent selector in Context tab');
});

describe('Agent Selection', () => {
  it('populates dropdown with active agents');
  it('updates ContextPanel when agent selected');
  it('shows placeholder when no agent selected');
  it('handles empty agent list gracefully');
});

describe('Agent Card Navigation', () => {
  it('adds onClick handler when provided');
  it('switches to Context tab on click');
  it('pre-selects clicked agent in dropdown');
  it('shows hover state when clickable');
});
```

**Testing Tools**:
- **@testing-library/react**: Already installed (16.3.0)
- **@testing-library/user-event**: Already installed (14.6.1)
- **jest**: Already installed (30.2.0)
- **msw**: Already installed (2.11.5) for API mocking if needed

## Best Practices

### 1. Tab Implementation
- Use semantic HTML (`<button>`, `<div role="tabpanel">`)
- ARIA attributes for accessibility
- Keyboard navigation (Tab, Arrow keys, Enter/Space)
- Focus management (focus tab on activation)

### 2. Performance
- Lazy render tab panels (don't render hidden tabs)
- Use React.memo on ContextPanel to prevent unnecessary re-renders
- Debounce agent selector changes if needed

### 3. User Experience
- Active tab clearly indicated (color, underline, bold)
- Smooth transitions (Tailwind transition utilities)
- Loading states for ContextPanel data fetch
- Empty states (no agents, no context data)

### 4. Testing
- Test user interactions (click, keyboard)
- Test state transitions (tab switches, agent selection)
- Test accessibility (ARIA attributes, focus management)
- Test edge cases (empty lists, API errors)

## Implementation Order

1. **Phase 1A**: Add tab UI to Dashboard (Overview + Context tabs)
   - Local state for activeTab
   - Tab button rendering with Tailwind
   - Conditional panel rendering
   - ARIA attributes for accessibility

2. **Phase 1B**: Add agent selector dropdown in Context tab
   - Local state for selectedAgentId
   - Populate from agents array (useAgentState)
   - Native `<select>` with Tailwind styling

3. **Phase 1C**: Import and wire ContextPanel
   - Import ContextPanel, ContextTierChart, ContextItemList
   - Render ContextPanel in Context tab when agent selected
   - Pass projectId and selectedAgentId as props

4. **Phase 1D**: Enhance AgentCard with onClick
   - Add optional onClick prop to AgentCardProps
   - Add cursor and hover styles conditionally
   - Wire onClick in Dashboard to switch tabs + select agent

5. **Phase 2**: Write tests
   - Dashboard tab switching tests
   - Agent selector tests
   - ContextPanel integration tests
   - AgentCard onClick tests

## Risk Mitigation

### Low Risk
- Tab UI is simple (2 tabs, basic state)
- ContextPanel already tested and working
- No backend changes required

### Medium Risk
- **Accessibility**: Ensure full keyboard navigation and ARIA compliance
  - **Mitigation**: Use ARIA attributes, test with keyboard only
  - **Validation**: axe-core accessibility testing plugin

- **State synchronization**: Agent card click → tab switch → agent selection
  - **Mitigation**: Single useState setter, immediate state updates
  - **Validation**: Test full navigation flow

### High Risk
- None identified - feature is purely additive UI integration

## References

- [WAI-ARIA Tabs Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/)
- [React Testing Library Best Practices](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)
- [Tailwind CSS Tabs Example](https://tailwindui.com/components/application-ui/navigation/tabs)
- [Feature 2 (Project Creation Flow)](../011-project-creation-flow/) - Similar form + navigation pattern
- [007 Context Management](../007-context-management/) - ContextPanel source code and API
- [Dashboard Source](../../web-ui/src/components/Dashboard.tsx) - Current implementation

## Conclusion

This feature is a **straightforward UI integration** with low complexity:
- No external dependencies needed (native HTML + Tailwind)
- No backend changes (all APIs exist)
- No ContextPanel modifications (import as-is)
- Standard React patterns (useState, conditional rendering)
- Well-defined test strategy (React Testing Library)

**Estimated Effort**: 3 hours (as per sprint spec)
- 1 hour: Tab UI + agent selector
- 1 hour: ContextPanel integration + AgentCard enhancement
- 1 hour: Testing (20+ tests)

**Confidence Level**: HIGH - All dependencies exist, no unknowns, clear implementation path.
